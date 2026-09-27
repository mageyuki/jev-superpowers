#!/usr/bin/env python3
"""POSIX offline boundary tests; all credentials here are synthetic.

Also exercises install.ps1 when PowerShell is available on this host.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
CLIENT = ROOT / "scripts/jev-systemone.py"
TOKEN = "synthetic-console-key-not-a-secret"


class IsolatedCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix=".jev-test-", dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.bin = self.home / "bin"
        self.bin.mkdir()
        self.env = {
            "HOME": str(self.home), "USERPROFILE": str(self.home),
            "XDG_DATA_HOME": str(self.home / "data"),
            "JEV_OPENCODE_DB": str(self.home / "absent.db"),
            "PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", ""),
        }
        # Keep Python usable when the real PATH starts with a HOME-sensitive shim.
        for name in ("python", "python3"):
            (self.bin / name).symlink_to(sys.executable)
        # Path discovery must never reach the real OpenCode during offline tests.
        self.tool("opencode", "exit 1")

    def tool(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def store(self, key=TOKEN, integration="opencode", value=None, path=None):
        path = path or Path(self.env["JEV_OPENCODE_DB"])
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute("CREATE TABLE credential (integration_id TEXT, value TEXT)")
            db.execute("INSERT INTO credential VALUES (?, ?)", (
                integration, value if value is not None else json.dumps({"type": "api", "key": key}),
            ))
        return path

    def run_client(self, *args):
        self.assertTrue(CLIENT.is_file(), "System One client has not been implemented")
        return subprocess.run([sys.executable, str(CLIENT), *args], env=self.env,
                              text=True, capture_output=True, timeout=15)

    def assert_no_key(self, stdout, stderr):
        self.assertNotIn(TOKEN, stdout + stderr)


class TransportTests(IsolatedCase):
    def setUp(self):
        super().setUp()
        self.assertTrue(CLIENT.is_file(), "System One client has not been implemented")
        spec = importlib.util.spec_from_file_location("jev_systemone", CLIENT)
        self.client = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.client)
        self.env["OPENCODE_API_KEY"] = TOKEN
        self.answer = {"type": "noul", "noul": 0.72}
        self.status = 200
        self.missing = False
        self.received = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.received.append((self.path, dict(self.headers), payload))
                question_id = next(iter(payload["questions"]))
                body = {"model": payload["model"], "answers": {} if owner.missing else {
                    question_id: owner.answer,
                }, "usage": {"prompt_tokens": 12, "output_tokens": 0}}
                self.send_response(owner.status)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(body).encode())

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def invoke(self, *args):
        original_open = urllib.request.OpenerDirector.open
        self.urls = []

        def loopback(opener, request, *pos, **kwargs):
            self.urls.append(request.full_url)
            request.full_url = f"http://127.0.0.1:{self.server.server_port}/zen/v1/systemone"
            return original_open(opener, request, *pos, **kwargs)

        out, err = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), \
                patch.object(sys, "argv", [str(CLIENT), *args]), \
                patch.object(urllib.request.OpenerDirector, "open", loopback), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = self.client.main()
            except SystemExit as exc:
                code = exc.code
        self.assert_no_key(out.getvalue(), err.getvalue())
        return code, out.getvalue(), err.getvalue()

    def test_zen_wire_contract_and_raw_noul(self):
        code, out, err = self.invoke("noul", "--question", "Is this clear?", "--state", "Synthetic input")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"type": "noul", "noul": 0.72})
        self.assertEqual(self.urls, ["https://opencode.ai/zen/v1/systemone"])
        _, headers, body = self.received[0]
        self.assertEqual(headers["Authorization"], "Bearer " + TOKEN)
        self.assertTrue(headers.get("User-Agent", "").strip())
        self.assertEqual(headers["Content-Type"], "application/json")
        self.assertEqual(body["model"], "jev-1.13-free")
        self.assertEqual(body["state"], "Synthetic input")
        question = next(iter(body["questions"].values()))
        self.assertEqual(question["type"], "noul")
        self.assertEqual(question["instructions"], "Is this clear?")

    def test_pick_ids_model_override_and_raw_choice(self):
        self.env["JEV_MODEL"] = "jev-1.13"
        self.answer = {"type": "choice", "choice": "opencode-zen", "confidence": 0.98,
                       "probabilities": {"opencode-zen": 0.98, "typesafe": 0.02}}
        code, out, err = self.invoke("pick", "--question", "Choose", "--options", "opencode-zen,typesafe", "--state", "Synthetic")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"type": "choice", "choice": "opencode-zen", "confidence": 0.98,
                                        "probabilities": {"opencode-zen": 0.98, "typesafe": 0.02}})
        body = self.received[0][2]
        self.assertEqual(body["model"], "jev-1.13")
        question = next(iter(body["questions"].values()))
        self.assertEqual(question["type"], "choice")
        self.assertEqual(question["criteria"], {"opencode-zen": "opencode-zen", "typesafe": "typesafe"})

    def test_score_keeps_score_confidence_legend_and_probabilities(self):
        self.answer = {"type": "score", "score": 0.89, "confidence": 0.09,
                       "legend": {"0": "Unclear", "1": "Reasonable", "2": "Clear"},
                       "probabilities": {"0": 0.31, "1": 0.49, "2": 0.20}}
        code, out, err = self.invoke("score", "--question", "Clarity", "--criteria", "Unclear,Reasonable,Clear", "--state", "Synthetic")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"type": "score", "score": 0.89, "confidence": 0.09,
                                         "legend": {"0": "Unclear", "1": "Reasonable", "2": "Clear"},
                                         "probabilities": {"0": 0.31, "1": 0.49, "2": 0.20}})
        question = next(iter(self.received[0][2]["questions"].values()))
        self.assertEqual(question["type"], "score")
        self.assertEqual(question["criteria"], {"0": "Unclear", "1": "Reasonable", "2": "Clear"})

    def test_http_error_does_not_echo_secret_response(self):
        self.status = 401
        self.answer = {"error": TOKEN}
        code, out, err = self.invoke("noul", "--question", "Q", "--state", "S")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("HTTP", err)

    def test_missing_answer_fails(self):
        self.missing = True
        code, out, err = self.invoke("noul", "--question", "Q", "--state", "S")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("answer", err.lower())

    def test_success_response_cannot_echo_credential(self):
        self.answer["detail"] = TOKEN
        code, out, err = self.invoke("noul", "--question", "Q", "--state", "S")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")

    def test_env_key_precedes_store(self):
        self.store(key="other-synthetic-key")
        code, _, err = self.invoke("noul", "--question", "Q", "--state", "S")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.received[0][1]["Authorization"], "Bearer " + TOKEN)

    def test_stored_key_is_used_read_only(self):
        del self.env["OPENCODE_API_KEY"]
        path = self.store()
        before = path.read_bytes()
        code, _, err = self.invoke("noul", "--question", "Q", "--state", "S")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.received[0][1]["Authorization"], "Bearer " + TOKEN)
        self.assertEqual(path.read_bytes(), before)


class SelectionTests(IsolatedCase):
    def test_no_key_fails_and_does_not_create_database(self):
        result = self.run_client("noul", "--question", "Q", "--state", "S")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr.lower())
        self.assertEqual(result.stdout, "")
        self.assertFalse(Path(self.env["JEV_OPENCODE_DB"]).exists())

    def test_explicit_backend_wins_and_legacy_defaults_remain(self):
        cases = [
            ({"OPENCODE_API_KEY": TOKEN}, "opencode-zen"),
            ({"OPENCODE_API_KEY": TOKEN, "TYPESAFE_API_KEY": "synthetic"}, "opencode-zen"),
            ({"OPENCODE_API_KEY": TOKEN, "TYPESAFE_API_KEY": "synthetic", "JEV_BACKEND": "typesafe"}, "typesafe"),
            ({"OPENCODE_API_KEY": TOKEN, "JEV_BACKEND": "laya"}, "laya"),
            ({"TYPESAFE_API_KEY": "synthetic"}, "typesafe"),
            ({"TYPESAFE_BASE_URL": "http://127.0.0.1:8000"}, "laya"),
            ({"TYPESAFE_BACKEND": "laya"}, "laya"),
        ]
        for changes, expected in cases:
            with self.subTest(expected=expected, keys=list(changes)):
                with patch.dict(self.env, changes):
                    result = self.run_client("--check-backend")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)
                self.assert_no_key(result.stdout, result.stderr)

    def test_explicit_zen_never_falls_back_to_typesafe(self):
        self.env.update(JEV_BACKEND="opencode-zen", TYPESAFE_API_KEY="synthetic")
        result = self.run_client("--check-backend")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("credential", result.stderr.lower())

    def test_invalid_store_is_not_a_credential(self):
        for value in ("bad-json", '{"type":"api","key":""}', '{"type":"oauth"}'):
            with self.subTest(value=value):
                path = self.store(value=value)
                try:
                    result = self.run_client("--check-backend")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("credential", result.stderr.lower())
                finally:
                    path.unlink()

    def test_other_integration_is_not_used(self):
        self.store(integration="unrelated")
        self.assertNotEqual(self.run_client("--check-backend").returncode, 0)

    def test_cli_path_then_xdg_then_home_fallback(self):
        del self.env["JEV_OPENCODE_DB"]
        discovered = self.store(path=self.home / "discovered db.sqlite")
        self.tool("opencode", f'printf "%s\\n" "{discovered}"')
        self.assertEqual(self.run_client("--check-backend").stdout.strip(), "opencode-zen")
        self.tool("opencode", "echo 'usage: not a path'; exit 0")
        self.store(path=self.home / "data/opencode/opencode.db")
        self.assertEqual(self.run_client("--check-backend").stdout.strip(), "opencode-zen")
        del self.env["XDG_DATA_HOME"]
        self.store(path=self.home / ".local/share/opencode/opencode.db")
        self.assertEqual(self.run_client("--check-backend").stdout.strip(), "opencode-zen")


class InstallerTests(IsolatedCase):
    def installer(self, filename):
        # No real tooling or plugin discovery, and no network during installation.
        for tool in ("jev-scout", "jev-axi", "git", "jev-guard", "supercov", "limpet", "jev-seo"):
            self.tool(tool, "exit 0")
        if filename.endswith(".ps1"):
            command = ["pwsh", "-NoProfile", "-File", str(ROOT / filename)]
        else:
            command = ["bash", str(ROOT / filename)]
        return subprocess.run(command, env=self.env, capture_output=True, text=True, timeout=20)

    def check_no_key(self, filename):
        result = self.installer(filename)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / ".agents/skills").exists(), "Credential check must precede copying skills")

    def check_zen(self, filename):
        self.env["OPENCODE_API_KEY"] = TOKEN
        result = self.installer(filename)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("opencode-zen", result.stdout.lower())
        self.assertTrue((self.home / ".agents/skills/jev-using-superpowers/SKILL.md").is_file())
        self.assert_no_key(result.stdout, result.stderr)

    def test_bash_no_key_has_no_install_side_effect(self):
        self.check_no_key("install.sh")

    def test_bash_zen_configures_without_second_key(self):
        self.check_zen("install.sh")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell runtime unavailable")
    def test_powershell_no_key_has_no_install_side_effect(self):
        self.check_no_key("install.ps1")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell runtime unavailable")
    def test_powershell_zen_configures_without_second_key(self):
        self.check_zen("install.ps1")


if __name__ == "__main__":
    unittest.main()
