"""Exercise installer recovery with fake system commands, without modifying the host."""

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
STEPS = ["base-tools", "storage-check", "gpu-driver", "developer-tools",
         "training-environment", "ollama-model", "huggingface-model", "reference-documents"]
FAKE_COMMAND = r'''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
with open(os.environ['AGENTSQL_TEST_LOG'],'a') as log:
    log.write(json.dumps([name,*sys.argv[1:]])+'\n')
if name=='python' and 'training_pipeline.bootstrap' in sys.argv:
    sys.exit(int(os.environ.get('AGENTSQL_TEST_BOOTSTRAP_CODE','0')))
if name=='nvidia-smi':
    sys.exit(int(os.environ.get('AGENTSQL_TEST_GPU_CODE','0')))
if name=='lspci': print('00:01.0 NVIDIA Corporation GPU')
if name=='df': print('Filesystem 1024-blocks Used Available Capacity Mounted on\nfixture 100 99 1 99% /')
if name=='sudo' and 'tee' in sys.argv:
    Path(os.environ['AGENTSQL_TEST_LOG']+'.unit').write_text(sys.stdin.read())
if name=='git':
    args=sys.argv[1:]
    if args[:1]==['-C']: args=args[2:]
    if args==['remote','get-url','origin']: print('https://github.com/Dexmond-Technologies/agent-sql-alpha.git')
    if args==['branch','--show-current']: print('main')
if name=='tmux' and 'has-session' in sys.argv: sys.exit(1)
'''


@unittest.skipIf(os.geteuid() == 0, "The installer intentionally rejects root sessions")
class InstallerRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="agentsql-installer-test-")
        self.root = Path(self.temporary.name)
        (self.root / "scripts/aws").mkdir(parents=True)
        for name in ["install.sh", "setup-training-host.sh"]:
            shutil.copy2(ROOT / "scripts/aws" / name, self.root / "scripts/aws" / name)
        state = self.root / ".aws-setup"
        state.mkdir()
        for name in STEPS:
            (state / f"{name}.done").touch()
        commands = self.root / "fake-bin"
        commands.mkdir()
        for name in ["sudo", "nvidia-smi", "lspci", "df", "git", "tmux"]:
            path = commands / name
            path.write_text(FAKE_COMMAND)
            path.chmod(0o755)
        for directory in [".venv-tools/bin", ".venv-training/bin"]:
            path = self.root / directory / "python"
            path.parent.mkdir(parents=True)
            path.write_text(FAKE_COMMAND)
            path.chmod(0o755)
        # Ensure versions are reported by fake commands ahead of the user's executables.
        for name in ["codex", "ollama"]:
            path = state / "node/bin" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(FAKE_COMMAND)
            path.chmod(0o755)
        self.env = dict(os.environ, PATH=str(commands) + ":" + os.environ["PATH"],
                        AGENTSQL_TEST_LOG=str(self.root / "commands.jsonl"),
                        AGENTSQL_INSTALL_DIR=str(self.root))

    def tearDown(self):
        self.temporary.cleanup()

    def run_worker(self, **environment):
        return subprocess.run(["bash", "scripts/aws/setup-training-host.sh", "--worker"],
                              cwd=self.root, env={**self.env, **environment},
                              capture_output=True, text=True, timeout=15)

    def test_complete_rerun_skips_installs(self):
        result = self.run_worker()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".aws-setup/status").read_text().strip(), "complete")
        calls = (self.root / "commands.jsonl").read_text()
        self.assertNotIn('"install"', calls)
        self.assertNotIn('"pull"', calls)

    def test_download_gaps_do_not_abort_other_installs(self):
        (self.root / ".aws-setup/reference-documents.done").unlink()
        result = self.run_worker(AGENTSQL_TEST_BOOTSTRAP_CODE="3")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".aws-setup/status").read_text().strip(), "complete-with-reference-gaps")
        self.assertTrue((self.root / ".aws-setup/reference-gaps").exists())

    def test_failed_download_stage_is_retried(self):
        marker = self.root / ".aws-setup/reference-documents.done"
        marker.unlink()
        result = self.run_worker(AGENTSQL_TEST_BOOTSTRAP_CODE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(marker.exists())
        self.assertEqual((self.root / ".aws-setup/status").read_text().strip(), "failed")
        self.assertEqual(self.run_worker().returncode, 0)
        self.assertTrue(marker.exists())

    def test_driver_reboot_registers_resume_and_completes_after_restart(self):
        (self.root / ".aws-setup/gpu-driver.done").unlink()
        result = self.run_worker(AGENTSQL_TEST_GPU_CODE="1")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".aws-setup/status").read_text().strip(), "rebooting")
        unit = (self.root / "commands.jsonl.unit").read_text()
        self.assertIn("--worker", unit)
        self.assertIn("network-online.target", unit)
        self.assertIn('"shutdown", "-r", "+1"', (self.root / "commands.jsonl").read_text())
        result = self.run_worker(AGENTSQL_TEST_GPU_CODE="0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / ".aws-setup/status").read_text().strip(), "complete")

    def test_driver_failure_after_reboot_does_not_loop(self):
        (self.root / ".aws-setup/gpu-driver.done").unlink()
        (self.root / ".aws-setup/driver-reboot-requested").touch()
        result = self.run_worker(AGENTSQL_TEST_GPU_CODE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual((self.root / ".aws-setup/status").read_text().strip(), "failed")
        self.assertNotIn('"shutdown"', (self.root / "commands.jsonl").read_text())

    def test_insufficient_storage_fails_before_model_download(self):
        (self.root / ".aws-setup/storage-check.done").unlink()
        result = self.run_worker()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("140 GiB", result.stdout)
        self.assertEqual((self.root / ".aws-setup/status").read_text().strip(), "failed")

    def test_standalone_launcher_starts_background_worker(self):
        (self.root / ".git").mkdir()
        result = subprocess.run(["bash", "scripts/aws/install.sh", "--non-interactive"],
                                cwd=self.root, env=self.env, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = (self.root / "commands.jsonl").read_text()
        self.assertIn('"new-session"', calls)
        self.assertIn("--worker", calls)


class ModelRevisionTests(unittest.TestCase):
    def test_interrupted_download_reuses_the_recorded_revision(self):
        spec = importlib.util.spec_from_file_location("aws_runtime", ROOT / "scripts/aws/prepare-runtime.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        api = Mock()
        api.model_info.return_value.sha = "a" * 40
        fetch = Mock(side_effect=[RuntimeError("Interrupted transfer"), None])
        hub = types.SimpleNamespace(HfApi=Mock(return_value=api), snapshot_download=fetch)
        with tempfile.TemporaryDirectory() as temporary, patch.dict(sys.modules, huggingface_hub=hub):
            root = Path(temporary)
            with self.assertRaisesRegex(RuntimeError, "Interrupted"):
                module.download(root)
            api.model_info.return_value.sha = "b" * 40
            module.download(root)
            self.assertEqual(api.model_info.call_count, 1)
            self.assertEqual(fetch.call_args.kwargs["revision"], "a" * 40)


if __name__ == "__main__":
    unittest.main()
