#!/usr/bin/env python3
"""Typed System One decisions, using only the Python standard library."""
import argparse
import json
import math
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request


class ConfigurationError(Exception):
    pass


class AnswerError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    # Never forward the bearer credential to a redirect destination.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.HTTPError(req.full_url, code, "Redirect refused", headers, fp)


def opencode_db_path():
    override = os.environ.get("JEV_OPENCODE_DB")
    if override:
        return Path(override).expanduser().resolve()
    try:
        result = subprocess.run(
            ["opencode", "debug", "paths", "db"], capture_output=True,
            text=True, timeout=5, check=False,
        )
        output = result.stdout.strip()
        if result.returncode == 0 and output and "\n" not in output:
            path = Path(output).expanduser()
            if path.is_absolute():
                return path
    except (OSError, subprocess.SubprocessError):
        pass
    data = os.environ.get("XDG_DATA_HOME")
    return (Path(data).expanduser() if data else Path.home() / ".local/share") / "opencode/opencode.db"


def opencode_key():
    key = os.environ.get("OPENCODE_API_KEY", "").strip()
    if key:
        return key
    try:
        # mode=ro is important: a missing store must never create a database.
        path = opencode_db_path().resolve()
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as db:
            rows = db.execute("SELECT value FROM credential WHERE integration_id = ?", ("opencode",))
            for (value,) in rows:
                try:
                    credential = json.loads(value)
                except (ValueError, TypeError):
                    continue
                if isinstance(credential, dict):
                    key = credential.get("key")
                    if isinstance(key, str) and key.strip():
                        return key.strip()
    except (OSError, ValueError, sqlite3.Error):
        pass
    return None


def backend_config():
    backend = os.environ.get("JEV_BACKEND", "").strip()
    if backend and backend not in ("opencode-zen", "typesafe", "laya"):
        raise ConfigurationError("Invalid JEV_BACKEND")
    key = None
    if not backend:
        if os.environ.get("TYPESAFE_BASE_URL") or os.environ.get("TYPESAFE_BACKEND") == "laya":
            backend = "laya"
        else:
            key = opencode_key()
            backend = "opencode-zen" if key else "typesafe"
    if backend == "opencode-zen":
        key = key or opencode_key()
        if not key:
            raise ConfigurationError("Missing OpenCode Zen credential")
        return backend, key, "https://opencode.ai/zen/v1/systemone", os.environ.get("JEV_MODEL") or "jev-1.13-free"

    key = os.environ.get("TYPESAFE_API_KEY", "").strip()
    if backend == "typesafe" and not key:
        raise ConfigurationError("Missing TypeSafe credential; configure TypeSafe, OpenCode Zen, or Laya")
    base = os.environ.get("TYPESAFE_BASE_URL") or (
        "http://127.0.0.1:8000" if backend == "laya" else "https://api.typesafe.ai/v1"
    )
    base = base.rstrip("/")
    endpoint = base + ("/systemone" if base.endswith("/v1") else "/v1/systemone")
    model = os.environ.get("JEV_MODEL") or ("laya-421m" if backend == "laya" else "jev-1.13.0")
    return backend, key or "local", endpoint, model


def comma_tokens(value):
    tokens = [token.strip() for token in value.split(",")]
    if not all(tokens) or len(set(tokens)) != len(tokens):
        raise argparse.ArgumentTypeError("Expected distinct, non-empty comma-separated tokens")
    return tokens


def finite_number(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def request_answer(args, config):
    backend, key, endpoint, model = config
    question = {"type": "choice" if args.command == "pick" else args.command,
                "instructions": args.question}
    if args.command == "pick":
        question["criteria"] = {token: token for token in args.options}
    elif args.command == "score":
        question["criteria"] = {str(index): token for index, token in enumerate(args.criteria)}
    payload = {"model": model, "state": args.state, "questions": {"decision": question}}
    request = urllib.request.Request(
        endpoint, data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json",
                 "User-Agent": "opencode/jev-superpowers"},
    )
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=30) as response:
        result = json.load(response)
    answers = result.get("answers") if isinstance(result, dict) else None
    answer = answers.get("decision") if isinstance(answers, dict) else None
    field = "choice" if args.command == "pick" else args.command
    if not isinstance(answer, dict) or answer.get(field) is None:
        raise AnswerError("Missing answer")
    if answer.get("type") != field and not (backend == "laya" and "type" not in answer):
        raise AnswerError("Invalid answer")
    value = answer[field]
    if args.command == "pick":
        valid = (isinstance(value, str) and value in args.options and
                 "confidence" in answer and finite_number(answer["confidence"]) and
                 0 <= answer["confidence"] <= 1)
    elif args.command == "noul":
        valid = finite_number(value) and 0 <= value <= 1
    else:
        valid = finite_number(value)
    if not valid:
        raise AnswerError("Invalid answer")
    # Keep all raw fields (especially score vs confidence); never map confidence.
    try:
        output = json.dumps(answer, ensure_ascii=False, allow_nan=False)
    except ValueError as error:
        raise AnswerError("Invalid answer") from error
    if len(key) >= 16 and key != "local" and (key in output or json.dumps(key, ensure_ascii=False)[1:-1] in output):
        raise AnswerError("Unsafe answer")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-backend", action="store_true",
                        help="Validate credentials and print backend name only; no HTTP call (installer preflight)")
    commands = parser.add_subparsers(dest="command")
    for name in ("noul", "pick", "score"):
        command = commands.add_parser(name)
        command.add_argument("--question", required=True)
        command.add_argument("--state", required=True)
        if name == "pick":
            command.add_argument("--options", type=comma_tokens, required=True)
        if name == "score":
            command.add_argument("--criteria", type=comma_tokens, required=True)
    args = parser.parse_args()
    if not args.command and not args.check_backend:
        parser.error("Select noul, pick, score, or --check-backend")
    try:
        config = backend_config()
        print(config[0] if args.check_backend else request_answer(args, config))
        return 0
    except ConfigurationError as error:
        # Only fixed local messages; never interpolate credentials or server text.
        print(str(error), file=sys.stderr)
    except urllib.error.HTTPError as error:
        print(f"HTTP error ({error.code})", file=sys.stderr)
    except AnswerError as error:
        print(str(error), file=sys.stderr)
    except (ValueError, OSError, urllib.error.URLError):
        print("System One transport or response error", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
