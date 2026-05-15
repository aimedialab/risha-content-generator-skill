#!/usr/bin/env python3
"""Install a daily scheduler that refreshes the Risha capability catalog."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys
from typing import Iterable


JOB_LABEL = "ai.risha.content-generator.catalog-refresh"


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_env_file(path: Path, values: dict[str, str]) -> None:
    ensure_parent(path)
    lines = [
        "# Managed by risha-content-generator/scripts/install_daily_refresh.py",
        "# File mode should remain 0600 because it may contain credentials.",
        "",
    ]
    for key, value in values.items():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        lines.append(f'{key}="{escaped}"')
    content = "\n".join(lines) + "\n"
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)


def run_command(command: Iterable[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), check=check, capture_output=True, text=True)


def install_launchd_job(
    *,
    repo_dir: Path,
    env_file: Path,
    log_file: Path,
    hour: int,
    minute: int,
) -> Path:
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{JOB_LABEL}.plist"
    plist_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "Label": JOB_LABEL,
        "ProgramArguments": [
            sys.executable,
            str(repo_dir / "scripts" / "refresh_catalog_job.py"),
            "--repo-dir",
            str(repo_dir),
            "--env-file",
            str(env_file),
            "--log-file",
            str(log_file),
        ],
        "RunAtLoad": True,
        "StartCalendarInterval": {
            "Hour": hour,
            "Minute": minute,
        },
        "WorkingDirectory": str(repo_dir),
        "StandardOutPath": str(log_file),
        "StandardErrorPath": str(log_file),
    }

    with plist_path.open("wb") as handle:
        plistlib.dump(payload, handle)

    run_command(["launchctl", "unload", str(plist_path)], check=False)
    run_command(["launchctl", "load", "-w", str(plist_path)])
    return plist_path


def build_cron_line(
    *,
    repo_dir: Path,
    env_file: Path,
    log_file: Path,
    hour: int,
    minute: int,
) -> str:
    command = " ".join(
        [
            shlex.quote(sys.executable),
            shlex.quote(str(repo_dir / "scripts" / "refresh_catalog_job.py")),
            "--repo-dir",
            shlex.quote(str(repo_dir)),
            "--env-file",
            shlex.quote(str(env_file)),
            "--log-file",
            shlex.quote(str(log_file)),
            ">>",
            shlex.quote(str(log_file)),
            "2>&1",
        ]
    )
    return f"{minute} {hour} * * * {command} # {JOB_LABEL}"


def install_cron_job(
    *,
    repo_dir: Path,
    env_file: Path,
    log_file: Path,
    hour: int,
    minute: int,
) -> Path:
    if shutil.which("crontab") is None:
        raise RuntimeError("crontab is not available on this system.")

    existing = run_command(["crontab", "-l"], check=False)
    lines = []
    if existing.returncode == 0 and existing.stdout.strip():
        lines = [line for line in existing.stdout.splitlines() if JOB_LABEL not in line]

    lines.append(build_cron_line(repo_dir=repo_dir, env_file=env_file, log_file=log_file, hour=hour, minute=minute))
    new_content = "\n".join(lines).rstrip() + "\n"
    subprocess.run(["crontab", "-"], input=new_content, text=True, check=True)
    return Path("crontab")


def resolve_default_paths(system_name: str) -> tuple[Path, Path]:
    if system_name == "darwin":
        config_dir = Path.home() / "Library" / "Application Support" / "risha-content-generator"
        log_dir = Path.home() / "Library" / "Logs" / "risha-content-generator"
    else:
        config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "risha-content-generator"
        log_dir = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state")) / "risha-content-generator"
    return config_dir / "refresh.env", log_dir / "catalog-refresh.log"


def collect_env_values(args: argparse.Namespace) -> dict[str, str]:
    values: dict[str, str] = {}

    auth_header = args.auth_header or os.environ.get("RISHA_AUTH_HEADER")
    email = args.email or os.environ.get("RISHA_EMAIL")
    password = args.password or os.environ.get("RISHA_PASSWORD")
    base_url = args.base_url or os.environ.get("RISHA_API_BASE_URL")

    if auth_header:
        values["RISHA_AUTH_HEADER"] = auth_header
    else:
        if not email or not password:
            raise RuntimeError(
                "Provide --auth-header or both --email and --password, or export RISHA_AUTH_HEADER / RISHA_EMAIL / RISHA_PASSWORD before running the installer."
            )
        values["RISHA_EMAIL"] = email
        values["RISHA_PASSWORD"] = password

    if base_url:
        values["RISHA_API_BASE_URL"] = base_url

    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Install a daily Risha capability refresh job.")
    parser.add_argument("--email", help="Risha email to store for the refresh job.")
    parser.add_argument("--password", help="Risha password to store for the refresh job.")
    parser.add_argument("--auth-header", help="Authorization header to store instead of email/password.")
    parser.add_argument("--base-url", help="Optional RISHA_API_BASE_URL override.")
    parser.add_argument("--hour", type=int, default=4, help="Hour of day for the refresh job (0-23).")
    parser.add_argument("--minute", type=int, default=0, help="Minute of hour for the refresh job (0-59).")
    parser.add_argument("--env-file", help="Override the path used to store scheduler credentials.")
    parser.add_argument("--log-file", help="Override the scheduler log file path.")
    parser.add_argument("--repo-dir", default=str(Path(__file__).resolve().parents[1]), help="Skill repository root.")
    parser.add_argument("--skip-run-now", action="store_true", help="Install the schedule without running an immediate refresh.")
    args = parser.parse_args()

    if not (0 <= args.hour <= 23):
        raise SystemExit("--hour must be between 0 and 23.")
    if not (0 <= args.minute <= 59):
        raise SystemExit("--minute must be between 0 and 59.")

    repo_dir = Path(args.repo_dir).resolve()
    system_name = sys.platform
    default_env_file, default_log_file = resolve_default_paths(system_name)
    env_file = Path(args.env_file).expanduser().resolve() if args.env_file else default_env_file
    log_file = Path(args.log_file).expanduser().resolve() if args.log_file else default_log_file

    values = collect_env_values(args)
    write_env_file(env_file, values)
    ensure_parent(log_file)

    if system_name == "darwin":
        scheduler_target = install_launchd_job(
            repo_dir=repo_dir,
            env_file=env_file,
            log_file=log_file,
            hour=args.hour,
            minute=args.minute,
        )
        scheduler_kind = "launchd"
    elif system_name.startswith("linux"):
        scheduler_target = install_cron_job(
            repo_dir=repo_dir,
            env_file=env_file,
            log_file=log_file,
            hour=args.hour,
            minute=args.minute,
        )
        scheduler_kind = "cron"
    else:
        raise SystemExit(f"Unsupported platform for scheduler install: {system_name}")

    if not args.skip_run_now:
        subprocess.run(
            [
                sys.executable,
                str(repo_dir / "scripts" / "refresh_catalog_job.py"),
                "--repo-dir",
                str(repo_dir),
                "--env-file",
                str(env_file),
                "--log-file",
                str(log_file),
            ],
            cwd=repo_dir,
            check=True,
        )

    print(
        "\n".join(
            [
                "Installed daily Risha capability refresh job.",
                f"Scheduler: {scheduler_kind}",
                f"Schedule: {args.hour:02d}:{args.minute:02d} every day",
                f"Credentials file: {env_file}",
                f"Log file: {log_file}",
                f"Scheduler target: {scheduler_target}",
            ]
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
