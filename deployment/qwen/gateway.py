#!/usr/bin/env python3
"""Bounded TLS/bearer gateway for real vLLM responses; optional Ollama wire compatibility."""
import hmac
import ipaddress
import json
import logging
import math
import os
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BYTES = 2 * 1024 * 1024
INPUT_BYTES = 256 * 1024


class UpstreamFailure(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def integer(name, default, low, high):
    try:
        result = int(os.environ.get(name, default))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if not low <= result <= high:
        raise ValueError(f"{name} must be between {low} and {high}.")
    return result


class Gateway:
    def __init__(self):
        self.model = os.environ.get("QWEN_SERVED_MODEL", "qwen3-coder-30b-a3b")
        self.token = os.environ.get("QWEN_SERVER_API_KEY", "")
        if len(self.token) < 32 or not self.token.isascii() or any(c.isspace() for c in self.token):
            raise ValueError("Supply QWEN_SERVER_API_KEY with at least 32 ASCII characters and no whitespace.")
        self.backend = os.environ.get("QWEN_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
        parsed = urllib.parse.urlsplit(self.backend)
        if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise ValueError("QWEN_BACKEND_URL must be a fixed HTTP(S) origin without credentials, path, query or fragment.")
        try:
            local = parsed.hostname in ("localhost", "model") or ipaddress.ip_address(parsed.hostname).is_loopback
        except ValueError:
            local = False
        if parsed.scheme == "http" and not local:
            raise ValueError("Plaintext upstream access is restricted to loopback or the internal Compose model service. Remote upstreams require HTTPS.")
        self.context = integer("QWEN_CONTEXT_TOKENS", 32768, 4096, 262144)
        self.output = integer("QWEN_MAX_OUTPUT_TOKENS", 2048, 64, 65536)
        if self.output + 1024 >= self.context:
            raise ValueError("Output reservation is too large for the context window.")
        self.timeout = integer("QWEN_TIMEOUT_SECONDS", 120, 10, 600)
        self.jobs = threading.BoundedSemaphore(integer("QWEN_MAX_CONCURRENT", 2, 1, 32))
        # No environment proxy and no redirects: request contents stay on the configured origin.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        self.metrics_lock = threading.Lock()
        self.total = 0
        self.failed = 0
        self.seconds = 0.0

    def upstream(self, path, body=None):
        request = urllib.request.Request(self.backend + path,
            data=None if body is None else json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        try:
            with self.opener.open(request, timeout=self.timeout) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise UpstreamFailure("The model response exceeded the byte limit.")
                return json.loads(raw)
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, UnicodeError) as error:
            # Never return/log upstream error bodies, which may contain prompts or secrets.
            raise UpstreamFailure("The configured model endpoint failed. No alternative model or provider was contacted.") from error

    def models(self):
        value = self.upstream("/v1/models")
        if not isinstance(value, dict) or not isinstance(value.get("data"), list):
            raise UpstreamFailure("The model endpoint returned an invalid model list.")
        selected = [entry for entry in value["data"] if isinstance(entry, dict) and entry.get("id") == self.model]
        if len(selected) != 1:
            raise UpstreamFailure("The exact configured model is unavailable; no substitute was selected.")
        return {**value, "data": selected}

    def messages(self, body):
        if not isinstance(body, dict) or body.get("model") != self.model:
            raise ValueError("Use the exact configured served model ID.")
        messages = body.get("messages")
        if not isinstance(messages, list) or not 1 <= len(messages) <= 64:
            raise ValueError("Supply 1–64 text messages.")
        for entry in messages:
            if not isinstance(entry, dict) or set(entry) != {"role", "content"} or entry["role"] not in ("system", "user", "assistant") or not isinstance(entry["content"], str):
                raise ValueError("Only system, user and assistant text messages are accepted; tools and multimodal input are disabled.")
        if len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > INPUT_BYTES:
            raise ValueError("Messages exceed 256 KiB; narrow the schema or request.")
        return messages

    def tokenize(self, messages):
        value = self.upstream("/tokenize", {"model": self.model, "messages": messages,
                              "add_generation_prompt": True, "add_special_tokens": False})
        if not isinstance(value, dict) or type(value.get("count")) is not int or type(value.get("max_model_len")) is not int or value["count"] < 0 or value["max_model_len"] < 1:
            raise UpstreamFailure("The model tokenizer did not report valid token count and context limit.")
        return value

    def chat(self, body):
        messages = self.messages(body)
        if body.get("stream", False) is not False:
            raise ValueError("This gateway supports complete responses only; stream must be false.")
        if body.get("tools") or body.get("tool_choice") or body.get("functions"):
            raise ValueError("Model execution tools are disabled.")
        self.models()
        count = self.tokenize(messages)
        output = body.get("max_tokens", self.output)
        if type(output) is not int or not 1 <= output <= self.output:
            raise ValueError("Requested output exceeds the configured gateway output limit.")
        if count["count"] + output + 256 > min(self.context, count["max_model_len"]):
            raise ValueError("Input and reserved output exceed the actual context budget. Nothing was silently discarded.")
        payload = {"model": self.model, "messages": messages, "stream": False, "max_tokens": output}
        for name, default, low, high in [("temperature", 0.7, 0, 2), ("top_p", 0.8, 0.01, 1), ("top_k", 20, 1, 1000), ("repetition_penalty", 1.05, 1, 2)]:
            value = body.get(name, default)
            if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high or (name == "top_k" and type(value) is not int):
                raise ValueError("Invalid generation parameter.")
            payload[name] = value
        result = self.upstream("/v1/chat/completions", payload)
        if not isinstance(result, dict) or result.get("model") != self.model:
            raise UpstreamFailure("The completion model identity does not match the configured model.")
        try:
            choice = result["choices"][0]
            if choice["finish_reason"] != "stop" or choice["message"].get("tool_calls") or not isinstance(choice["message"].get("content"), str) or not choice["message"]["content"].strip():
                raise UpstreamFailure("The model returned an incomplete answer or a tool call; the response was rejected.")
        except (KeyError, IndexError, TypeError, AttributeError) as error:
            raise UpstreamFailure("The model returned an invalid completion.") from error
        return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "agentSQL-Qwen"
    sys_version = ""

    def log_message(self, *args):
        pass  # HTTP request lines can contain sensitive paths; structured metrics only.

    def reply(self, status, value, request_id):
        body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-ID", request_id)
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def handle_api(self, method):
        request_id, started, status = str(uuid.uuid4()), time.monotonic(), 500
        gateway = self.server.gateway
        acquired = False
        try:
            if method == "GET" and self.path == "/healthz":
                status = 200
                return self.reply(status, {"status": "alive", "modelReadiness": "not-checked"}, request_id)
            expected = ("Bearer " + gateway.token).encode("ascii")
            supplied = self.headers.get("Authorization", "").encode("utf-8")
            if not hmac.compare_digest(expected, supplied):
                status = 401
                return self.reply(status, {"error": "Authentication required."}, request_id)
            if self.headers.get("Transfer-Encoding") is not None:
                raise ValueError("Transfer encoding is unsupported; supply Content-Length.")
            acquired = gateway.jobs.acquire(blocking=False)
            if not acquired:
                status = 429
                return self.reply(status, {"error": "The gateway is at its concurrency limit. Retry later."}, request_id)
            if method == "GET":
                if self.path in ("/v1/models", "/api/tags", "/readyz"):
                    value = gateway.models()
                    if self.path == "/api/tags":
                        value = {"models": [{"name": entry["id"], "model": entry["id"]} for entry in value["data"]]}
                    elif self.path == "/readyz":
                        value = {"status": "model-listed", "model": gateway.model, "generation": "not-checked"}
                elif self.path == "/metrics":
                    with gateway.metrics_lock:
                        value = {"requests": gateway.total, "failed": gateway.failed, "elapsedSeconds": gateway.seconds}
                else:
                    status = 404
                    return self.reply(status, {"error": "Endpoint unavailable."}, request_id)
            else:
                length = self.headers.get("Content-Length")
                if length is None or not length.isdecimal() or not 0 < int(length) <= INPUT_BYTES:
                    raise ValueError("Supply a Content-Length between 1 and 262144 bytes.")
                raw = self.rfile.read(int(length))
                if len(raw) != int(length):
                    raise ValueError("Incomplete request body.")
                value = json.loads(raw)
                if self.path == "/tokenize":
                    value = gateway.tokenize(gateway.messages(value))
                elif self.path in ("/v1/chat/completions", "/api/chat"):
                    value = gateway.chat(value)
                    if self.path == "/api/chat":
                        value = {"model": gateway.model, "message": value["choices"][0]["message"], "done": True,
                                 "done_reason": value["choices"][0]["finish_reason"], "usage": value.get("usage")}
                else:
                    status = 404
                    return self.reply(status, {"error": "Endpoint unavailable."}, request_id)
            status = 200
            self.reply(status, value, request_id)
        except (ValueError, UnicodeError):
            status = 400
            self.reply(status, {"error": "Invalid or oversized request; check model ID, message format, generation limits and context budget."}, request_id)
        except UpstreamFailure:
            status = 502
            self.reply(status, {"error": "The configured model endpoint failed or returned an incomplete response. No fallback was attempted."}, request_id)
        except (TimeoutError, OSError):
            status = 504
            self.close_connection = True
        finally:
            if acquired:
                gateway.jobs.release()
            elapsed = time.monotonic() - started
            with gateway.metrics_lock:
                gateway.total += 1
                gateway.failed += int(status >= 400)
                gateway.seconds += elapsed
            logging.info(json.dumps({"requestId": request_id, "status": status, "elapsedMs": round(elapsed * 1000)}))

    def do_GET(self):
        self.handle_api("GET")

    def do_POST(self):
        self.handle_api("POST")


class Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, gateway, tls):
        self.gateway, self.tls = gateway, tls
        self.connections = threading.BoundedSemaphore(32)
        super().__init__(address, Handler)

    def process_request(self, request, client_address):
        if not self.connections.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            request.settimeout(15)
            if self.tls is not None:
                request = self.tls.wrap_socket(request, server_side=True)
            super().process_request_thread(request, client_address)
        except (OSError, ssl.SSLError):
            request.close()
        finally:
            self.connections.release()

    def handle_error(self, request, client_address):
        logging.error("Gateway handler failed; request contents suppressed.")


def main():
    gateway = Gateway()
    bind = os.environ.get("QWEN_GATEWAY_BIND", "127.0.0.1")
    port = integer("QWEN_GATEWAY_PORT", 8443, 1, 65535)
    certificate, key = os.environ.get("QWEN_TLS_CERT_FILE"), os.environ.get("QWEN_TLS_KEY_FILE")
    tls = None
    if bool(certificate) != bool(key):
        raise ValueError("Configure both the TLS certificate and key; partial TLS configuration is rejected.")
    if certificate and key:
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.minimum_version = ssl.TLSVersion.TLSv1_2
        tls.load_cert_chain(certificate, key)
    elif bind != "localhost" and not ipaddress.ip_address(bind).is_loopback:
        raise ValueError("Non-loopback gateway listeners require a TLS certificate and key.")
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with Server((bind, port), gateway, tls) as server:
        server.serve_forever()


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, ssl.SSLError):
        raise SystemExit("Qwen gateway startup failed. Check API token, limits, bind address and certificate/key access; secrets are not printed.")
