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
        with contextlib.closing(sqlite3.connect(path)) as db:
            with db:
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
        self.redirect_to = None
        self.received = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                owner.received.append((self.path, dict(self.headers), payload))
                if owner.redirect_to:
                    self.send_response(302)
                    self.send_header("Location", owner.redirect_to)
                    self.end_headers()
                    return
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
            if request.full_url == "https://opencode.ai/zen/v1/systemone":
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
        self.assertEqual(headers["User-Agent"], "opencode/jev-superpowers")
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

    def test_pick_rejects_choice_outside_requested_options(self):
        self.answer = {"type": "choice", "choice": "unrequested", "confidence": 0.98}
        code, out, err = self.invoke("pick", "--question", "Choose", "--options", "a,b", "--state", "Synthetic")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertTrue(err.endswith("Invalid answer\n"), err)

    def test_answer_type_must_match_command(self):
        cases = (
            ({"type": "score", "choice": "a", "confidence": 0.9}, ("pick", "--options", "a,b")),
            ({"type": "score", "noul": 0.9}, ("noul",)),
            ({"type": "noul", "score": 0.9}, ("score", "--criteria", "a,b")),
            ({"noul": 0.9}, ("noul",)),
        )
        for answer, command in cases:
            with self.subTest(answer=answer, command=command):
                self.answer = answer
                code, out, err = self.invoke(*command, "--question", "Q", "--state", "Synthetic")
                self.assertEqual(code, 1)
                self.assertEqual(out, "")
                self.assertEqual(err, "Invalid answer\n")

    def test_legacy_laya_answer_without_type_still_validates_value(self):
        self.env.pop("OPENCODE_API_KEY")
        self.env["JEV_BACKEND"] = "laya"
        self.env["TYPESAFE_BASE_URL"] = f"http://127.0.0.1:{self.server.server_port}"
        self.answer = {"noul": 0.72}
        code, out, err = self.invoke("noul", "--question", "Q", "--state", "Synthetic")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), {"noul": 0.72})
        self.answer = {"noul": 1.5}
        code, out, err = self.invoke("noul", "--question", "Q", "--state", "Synthetic")
        self.assertEqual((code, out, err), (1, "", "Invalid answer\n"))
        self.answer = {"type": "score", "noul": 0.72}
        code, out, err = self.invoke("noul", "--question", "Q", "--state", "Synthetic")
        self.assertEqual((code, out, err), (1, "", "Invalid answer\n"))

    def test_laya_local_choice_is_not_mistaken_for_credential_echo(self):
        self.env.pop("OPENCODE_API_KEY")
        self.env["JEV_BACKEND"] = "laya"
        self.env["TYPESAFE_BASE_URL"] = f"http://127.0.0.1:{self.server.server_port}"
        self.answer = {"type": "choice", "choice": "local", "confidence": 0.9}
        code, out, err = self.invoke("pick", "--question", "Q", "--options", "local,remote", "--state", "Synthetic")
        self.assertEqual(code, 0, err)
        self.assertEqual(json.loads(out), self.answer)

    def test_pick_rejects_invalid_present_confidence(self):
        for confidence in ("high", -0.1, 1.1, float("nan"), float("inf"), True):
            with self.subTest(confidence=confidence):
                self.answer = {"type": "choice", "choice": "a", "confidence": confidence}
                code, out, err = self.invoke("pick", "--question", "Choose", "--options", "a,b", "--state", "Synthetic")
                self.assertNotEqual(code, 0)
                self.assertEqual(out, "")
                self.assertTrue(err.endswith("Invalid answer\n"), err)

    def test_pick_rejects_nonfinite_probabilities_without_output(self):
        for probability in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(probability=probability):
                self.answer = {"type": "choice", "choice": "a", "confidence": 0.9,
                               "probabilities": {"a": probability}}
                code, out, err = self.invoke("pick", "--question", "Choose", "--options", "a,b", "--state", "Synthetic")
                self.assertEqual((code, out, err), (1, "", "Invalid answer\n"))

    def test_pick_rejects_missing_confidence(self):
        self.answer = {"type": "choice", "choice": "a"}
        code, out, err = self.invoke("pick", "--question", "Choose", "--options", "a,b", "--state", "Synthetic")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "Invalid answer\n")

    def test_noul_rejects_invalid_values(self):
        for value in (-0.1, 1.1, "high", float("nan"), float("inf"), True):
            with self.subTest(value=value):
                self.answer = {"type": "noul", "noul": value}
                code, out, err = self.invoke("noul", "--question", "Q", "--state", "Synthetic")
                self.assertNotEqual(code, 0)
                self.assertEqual(out, "")
                self.assertTrue(err.endswith("Invalid answer\n"), err)

    def test_score_rejects_nonfinite_value(self):
        self.answer = {"type": "score", "score": float("inf"), "confidence": 0.09}
        code, out, err = self.invoke("score", "--question", "Q", "--criteria", "a,b", "--state", "Synthetic")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertTrue(err.endswith("Invalid answer\n"), err)

    def test_score_rejects_integer_too_large_for_float(self):
        self.answer = {"type": "score", "score": 10 ** 400}
        code, out, err = self.invoke("score", "--question", "Q", "--criteria", "a,b", "--state", "Synthetic")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "Invalid answer\n")

    def test_http_error_does_not_echo_secret_response(self):
        self.status = 401
        self.answer = {"error": TOKEN}
        code, out, err = self.invoke("noul", "--question", "Q", "--state", "S")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("HTTP", err)

    def test_redirect_refusal_raises_and_never_contacts_destination(self):
        received_at_destination = []

        class Destination(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                received_at_destination.append(dict(self.headers))
                self.send_response(200)
                self.end_headers()

            do_POST = do_GET

        destination = HTTPServer(("127.0.0.1", 0), Destination)
        thread = threading.Thread(target=destination.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(destination.server_close)
        self.addCleanup(destination.shutdown)
        self.redirect_to = f"http://127.0.0.1:{destination.server_port}/destination"

        code, out, err = self.invoke("noul", "--question", "Q", "--state", "Synthetic")
        self.assertNotEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("HTTP", err)
        self.assertEqual(len(self.received), 1)
        self.assertEqual(received_at_destination, [])
        with self.assertRaises(urllib.error.HTTPError) as raised:
            self.client.NoRedirect().redirect_request(
                urllib.request.Request("https://opencode.ai/zen/v1/systemone"),
                None, 302, "Found", {"Location": self.redirect_to}, self.redirect_to,
            )
        self.assertEqual(raised.exception.code, 302)

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
            ({"OPENCODE_API_KEY": TOKEN, "TYPESAFE_BASE_URL": "http://127.0.0.1:8000"}, "laya"),
            ({"OPENCODE_API_KEY": TOKEN, "TYPESAFE_BACKEND": "laya"}, "laya"),
            ({"OPENCODE_API_KEY": TOKEN, "TYPESAFE_BASE_URL": "http://127.0.0.1:8000", "JEV_BACKEND": "opencode-zen"}, "opencode-zen"),
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
            command = [shutil.which("pwsh"), "-NoProfile", "-File", str(ROOT / filename)]
        else:
            command = [shutil.which("bash"), str(ROOT / filename)]
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

    def check_typesafe_without_python(self, filename, explicit=True):
        self.env["TYPESAFE_API_KEY"] = TOKEN
        if explicit:
            self.env["JEV_BACKEND"] = "typesafe"
        for name in ("python", "python3"):
            (self.bin / name).unlink()
        for name in ("cp", "ls", "mkdir", "dirname"):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env["PATH"] = str(self.bin)
        result = self.installer(filename)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("typesafe", result.stdout.lower())
        self.assertTrue((self.home / ".agents/skills/jev-using-superpowers/SKILL.md").is_file())
        self.assert_no_key(result.stdout, result.stderr)

    def check_python_preflight_precedes_implicit_typesafe(self, filename):
        self.env.update(OPENCODE_API_KEY=TOKEN, TYPESAFE_API_KEY="synthetic-typesafe-key")
        result = self.installer(filename)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("System One backend configured: opencode-zen", result.stdout)
        self.assertTrue((self.home / ".agents/skills/jev-using-superpowers/SKILL.md").is_file())
        self.assert_no_key(result.stdout, result.stderr)

    def test_bash_no_key_has_no_install_side_effect(self):
        self.check_no_key("install.sh")

    def test_bash_zen_configures_without_second_key(self):
        self.check_zen("install.sh")

    def test_bash_typesafe_installs_without_python(self):
        self.check_typesafe_without_python("install.sh")

    def test_bash_implicit_typesafe_installs_without_python(self):
        self.check_typesafe_without_python("install.sh", explicit=False)

    def test_bash_implicit_backend_uses_python_preflight(self):
        self.check_python_preflight_precedes_implicit_typesafe("install.sh")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell runtime unavailable")
    def test_powershell_no_key_has_no_install_side_effect(self):
        self.check_no_key("install.ps1")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell runtime unavailable")
    def test_powershell_zen_configures_without_second_key(self):
        self.check_zen("install.ps1")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell runtime unavailable")
    def test_powershell_typesafe_installs_without_python(self):
        self.check_typesafe_without_python("install.ps1")

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell runtime unavailable")
    def test_powershell_implicit_typesafe_installs_without_python(self):
        self.check_typesafe_without_python("install.ps1", explicit=False)

    @unittest.skipUnless(shutil.which("pwsh"), "PowerShell runtime unavailable")
    def test_powershell_implicit_backend_uses_python_preflight(self):
        self.check_python_preflight_precedes_implicit_typesafe("install.ps1")

    def test_powershell_implicit_preflight_falls_back_to_python(self):
        source = (ROOT / "install.ps1").read_text()
        implicit_branch = source.split("} elseif (!$backend) {", 1)[1].split("\n}", 1)[0]
        self.assertRegex(
            implicit_branch,
            r"\$python = Get-Command python3 -ErrorAction SilentlyContinue\s+"
            r"if \(!\$python\) \{ \$python = Get-Command python -ErrorAction SilentlyContinue \}",
        )

    def test_powershell_suite_runs_systemone_contracts_when_python_exists(self):
        source = (ROOT / "scripts/test.ps1").read_text()
        self.assertRegex(source, r"Run-Check[^\n]*System One client and installer contracts")
        self.assertRegex(source, r"(?s)Get-Command python3.*Get-Command python.*test-systemone\.py")


class LayaServerTests(unittest.TestCase):
    def test_server_emits_answer_type(self):
        spec = importlib.util.spec_from_file_location("serve_laya", ROOT / "scripts/serve-laya.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        server = HTTPServer(("127.0.0.1", 0), module.SystemOneHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        payload = {"state": "Synthetic", "questions": {"decision": {"type": "noul", "instructions": "clear"}}}
        request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/v1/systemone",
                                         data=json.dumps(payload).encode(), method="POST")
        with urllib.request.urlopen(request) as response:
            answer = json.load(response)["answers"]["decision"]
        self.assertEqual(answer["type"], "noul")
        self.assertIsInstance(answer["noul"], float)


if __name__ == "__main__":
    unittest.main()
