#!/usr/bin/env python3
"""Remove the installed daily Risha capability refresh scheduler."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


JOB_LABEL = "ai.risha.content-generator.catalog-refresh"


def main() -> int:
    if sys.platform == "darwin":
        plist_path = Path.home() / "Library" / "LaunchAgents" / f"{JOB_LABEL}.plist"
        if plist_path.exists():
            subprocess.run(["launchctl", "unload", str(plist_path)], check=False)
            plist_path.unlink()
            print(f"Removed launchd job: {plist_path}")
        else:
            print(f"No launchd job found at: {plist_path}")
        return 0

    if not sys.platform.startswith("linux"):
        raise SystemExit(f"Unsupported platform for scheduler uninstall: {sys.platform}")

    crontab = subprocess.run(["crontab", "-l"], capture_output=True, text=True, check=False)
    if crontab.returncode != 0:
        print("No crontab installed for this user.")
        return 0

    lines = [line for line in crontab.stdout.splitlines() if JOB_LABEL not in line]
    content = "\n".join(lines).rstrip() + ("\n" if lines else "")
    subprocess.run(["crontab", "-"], input=content, text=True, check=True)
    print("Removed cron entry for daily Risha capability refresh.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
