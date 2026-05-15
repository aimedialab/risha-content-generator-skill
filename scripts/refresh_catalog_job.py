#!/usr/bin/env python3
"""Run a scheduled Risha capability catalog refresh."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import time


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Environment file not found: {path}")

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ[key] = value


def append_log(path: Path, message: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(message.rstrip() + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh the local Risha capability catalog.")
    parser.add_argument("--repo-dir", default=str(Path(__file__).resolve().parents[1]), help="Skill repository root.")
    parser.add_argument("--env-file", required=True, help="Path to the refresh environment file.")
    parser.add_argument("--log-file", help="Path to append scheduler logs.")
    parser.add_argument("--base-url", help="Optional override for RISHA_API_BASE_URL.")
    args = parser.parse_args()

    repo_dir = Path(args.repo_dir).resolve()
    env_file = Path(args.env_file).expanduser().resolve()
    log_file = Path(args.log_file).expanduser().resolve() if args.log_file else None

    try:
        load_env_file(env_file)
    except Exception as exc:  # pragma: no cover - protective logging
        if log_file:
            append_log(log_file, f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] Failed to load env file: {exc}")
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    script_path = repo_dir / "scripts" / "risha_api.py"
    json_path = repo_dir / "references" / "current-capabilities.json"
    markdown_path = repo_dir / "references" / "current-capabilities.md"

    command = [
        sys.executable,
        str(script_path),
        "catalog",
        "--quiet",
        "--write-json",
        str(json_path),
        "--write-markdown",
        str(markdown_path),
    ]
    if args.base_url:
        command.extend(["--base-url", args.base_url])

    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    if log_file:
        append_log(log_file, f"[{started_at}] Starting scheduled Risha catalog refresh.")

    result = subprocess.run(command, cwd=repo_dir, capture_output=True, text=True)

    if log_file:
        if result.stdout.strip():
            append_log(log_file, result.stdout)
        if result.stderr.strip():
            append_log(log_file, result.stderr)
        finished_at = time.strftime("%Y-%m-%d %H:%M:%S")
        status = "succeeded" if result.returncode == 0 else "failed"
        append_log(log_file, f"[{finished_at}] Scheduled Risha catalog refresh {status} with exit code {result.returncode}.")

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
