#!/usr/bin/env python3
"""Measure a real Qwen endpoint. Never substitutes an answer or invents performance data."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import ssl
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def validate_url(value):
    url = urllib.parse.urlsplit(value)
    try:
        local = url.hostname == "localhost" or ipaddress.ip_address(url.hostname or "").is_loopback
    except ValueError:
        local = False
    if not url.hostname or url.username or url.password or url.query or url.fragment or url.path.rstrip("/") != "/v1":
        raise ValueError("Use a base URL ending in /v1 without embedded credentials, query or fragment.")
    if url.scheme != "https" and not (url.scheme == "http" and local):
        raise ValueError("Remote endpoints require HTTPS with certificate verification.")
    return value.rstrip("/"), urllib.parse.urlunsplit((url.scheme, url.netloc, "", "", ""))


def run(args):
    base, origin = validate_url(args.base_url)
    token = os.environ.get("QWEN_API_KEY", "")
    if not token and not base.startswith(("http://127.", "http://localhost:", "http://[::1]:")):
        raise ValueError("Set QWEN_API_KEY for the real endpoint.")
    if not 1 <= args.runs <= 100 or not 1 <= args.concurrency <= 8:
        raise ValueError("Runs must be 1–100 and concurrency 1–8.")
    if not 64 <= args.max_output_tokens <= 65536:
        raise ValueError("Output limit must be 64–65536 tokens.")
    prompt = args.prompt_file.read_text(encoding="utf-8") if args.prompt_file else "Reply with the single word READY. This checks connectivity, not SQL accuracy."
    if len(prompt.encode("utf-8")) > 200 * 1024:
        raise ValueError("Prompt exceeds 200 KiB.")
    context = ssl.create_default_context(cafile=str(args.ca_certificate) if args.ca_certificate else None)
    def request(url, body=None):
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=context))
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        req = urllib.request.Request(url, data=None if body is None else json.dumps(body, allow_nan=False).encode(), headers=headers)
        with opener.open(req, timeout=args.timeout_seconds) as response:
            data = response.read(2 * 1024 * 1024 + 1)
            if len(data) > 2 * 1024 * 1024:
                raise ValueError("Endpoint response exceeds 2 MiB.")
            return json.loads(data)
    models = request(base + "/models")
    if not any(isinstance(entry, dict) and entry.get("id") == args.model for entry in models.get("data", [])):
        raise ValueError("The exact selected model was not reported. No alternative was selected.")
    messages = [{"role": "user", "content": prompt}]
    tokenized = request(origin + "/tokenize", {"model": args.model, "messages": messages, "add_generation_prompt": True, "add_special_tokens": False})
    count, capacity = tokenized.get("count"), tokenized.get("max_model_len")
    if type(count) is not int or type(capacity) is not int or count < 0 or count + args.max_output_tokens + 256 > capacity:
        raise ValueError("Real tokenization failed or the request exceeds the server context capacity.")
    payload = {"model": args.model, "messages": messages, "stream": False, "max_tokens": args.max_output_tokens,
               "temperature": 0.7, "top_p": 0.8, "top_k": 20, "repetition_penalty": 1.05}
    def measure(index):
        started = time.monotonic()
        value = request(base + "/chat/completions", payload)
        elapsed = time.monotonic() - started
        if value.get("model") != args.model:
            raise ValueError("Completion model identity mismatch.")
        choice = value["choices"][0]
        text = choice["message"].get("content")
        if choice.get("finish_reason") != "stop" or choice["message"].get("tool_calls") or not isinstance(text, str) or not text.strip():
            raise ValueError("Incomplete completion, missing text or unexpected tool call.")
        usage = value.get("usage")
        if not isinstance(usage, dict) or any(type(usage.get(key)) is not int or usage[key] < 0 for key in ("prompt_tokens", "completion_tokens", "total_tokens")):
            raise ValueError("The server did not return valid measured token usage.")
        return {"run": index + 1, "elapsedSeconds": elapsed, "reportedUsage": usage,
                "responseSha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "responseCharacters": len(text)}
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        observations = list(executor.map(measure, range(args.runs)))
    elapsed = time.monotonic() - started
    durations = sorted(result["elapsedSeconds"] for result in observations)
    return {"status": "real-endpoint-checks-passed", "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
            "model": args.model, "promptSha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
            "tokenizerPromptTokens": count, "serverContextTokens": capacity, "concurrency": args.concurrency,
            "observations": observations, "wallSeconds": elapsed, "meanResponseSeconds": statistics.mean(durations),
            "p95ResponseSeconds": durations[max(0, math.ceil(0.95 * len(durations)) - 1)],
            "aggregateCompletionTokensPerWallSecond": sum(r["reportedUsage"]["completion_tokens"] for r in observations) / elapsed,
            "limitations": ["Response timing includes prompt processing, generation and network time; it is not time to first token or decode-only throughput.",
                            "SQL semantic correctness, IBM i compatibility, GPU utilization and production acceptance were not established by this check."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", default="qwen3-coder-30b-a3b")
    parser.add_argument("--ca-certificate", type=Path)
    parser.add_argument("--prompt-file", type=Path, help="An actual reviewed question; its text is omitted from the report")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-output-tokens", type=int, default=2048)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():
        parser.error("Report already exists; choose a new path.")
    if not 10 <= args.timeout_seconds <= 600:
        parser.error("Timeout must be between 10 and 600 seconds.")
    try:
        report = run(args)
        code = 0
    except Exception as error:
        report = {"status": "failed", "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
                  "reason": str(error) if isinstance(error, ValueError) else "Real endpoint verification failed; diagnostic body suppressed to protect credentials and prompt contents.",
                  "sqlAccuracy": "not-established", "productionAcceptance": "not-established"}
        code = 1
    args.report.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(args.report, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(report, file, ensure_ascii=False, allow_nan=False, indent=2)
    print(json.dumps({"status": report["status"], "report": str(args.report)}))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
