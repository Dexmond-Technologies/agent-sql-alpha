"""Real gateway failure checks and pure value transformations. No mock model/ODBC replies."""
import contextlib
import decimal
import importlib.util
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def module(name, path):
    specification = importlib.util.spec_from_file_location(name, ROOT / path)
    loaded = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(loaded)
    return loaded


gateway_module = module("qwen_gateway", "deployment/qwen/gateway.py")
connector = module("ibmi_connector", "tools/ibmi/connector.py")


@contextlib.contextmanager
def environment(values):
    original = {key: os.environ.get(key) for key in values}
    try:
        os.environ.update(values)
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class GatewayFailureChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.token = secrets.token_hex(32)
        # Reserve an actual unavailable backend port. No fake server or successful reply exists.
        cls.unavailable = socket.socket()
        cls.unavailable.bind(("127.0.0.1", 0))
        with environment({"QWEN_SERVER_API_KEY": cls.token, "QWEN_BACKEND_URL": f"http://127.0.0.1:{cls.unavailable.getsockname()[1]}"}):
            cls.gateway = gateway_module.Gateway()
        cls.server = gateway_module.Server(("127.0.0.1", 0), cls.gateway, None)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.unavailable.close()

    def request(self, path, body=None, authenticated=True):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            with error:
                return error.code, json.load(error)

    def test_authentication_is_required(self):
        status, value = self.request("/v1/models", authenticated=False)
        self.assertEqual(status, 401)
        self.assertNotIn(self.token, json.dumps(value))

    def test_liveness_does_not_claim_model_readiness(self):
        status, value = self.request("/healthz", authenticated=False)
        self.assertEqual(status, 200)
        self.assertEqual(value["modelReadiness"], "not-checked")

    def test_unavailable_backend_fails_without_model_substitution(self):
        status, value = self.request("/readyz")
        self.assertEqual(status, 502)
        self.assertIn("No fallback", value["error"])
        self.assertNotIn(self.token, json.dumps(value))

    def test_invalid_roles_and_model_ids_fail_before_generation(self):
        for body in [
            {"model": "unavailable-model", "messages": [{"role": "user", "content": "connectivity check"}]},
            {"model": self.gateway.model, "messages": [{"role": "tool", "content": "not authorized"}]},
        ]:
            status, _ = self.request("/v1/chat/completions", body)
            self.assertEqual(status, 400)

    def test_verification_report_records_a_real_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "failure.json"
            result = subprocess.run([sys.executable, str(ROOT / "tools/qwen/verify_endpoint.py"),
                "--base-url", self.base + "/v1", "--runs", "1", "--report", str(report)],
                env=dict(os.environ, QWEN_API_KEY=self.token), capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 1)
            recorded = json.loads(report.read_text())
            self.assertEqual(recorded["status"], "failed")
            self.assertNotIn("observations", recorded)
            self.assertNotIn(self.token, report.read_text())


class ExactValueChecks(unittest.TestCase):
    def test_decimal_and_large_integer_precision(self):
        # Pure serialization inputs, not alleged IBM i result values.
        self.assertEqual(connector.exact_json(decimal.Decimal("12345678901234567890.123456")), "12345678901234567890.123456")
        self.assertEqual(connector.exact_json(9007199254740992), "9007199254740992")
        with self.assertRaises(ValueError):
            connector.exact_json(float("nan"))

    def test_odbc_and_identifier_escaping(self):
        self.assertEqual(connector.odbc_value("name};SSL=0"), "{name}};SSL=0}")
        self.assertEqual(connector.quote_identifier('name";CALL'), '"name"";CALL"')
        with self.assertRaises(ValueError):
            connector.odbc_value("name\nvalue")

    def test_existing_exports_are_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "serialization.json"
            connector.atomic_json(output, {"check": "serialization"})
            original = output.read_bytes()
            with self.assertRaises(ValueError):
                connector.atomic_json(output, {"check": "overwrite"})
            self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
