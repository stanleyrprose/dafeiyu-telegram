#!/usr/bin/env python3
"""Sanitized AstrBot diagnostic; never emit dashboard passwords or Bot API URLs."""
from __future__ import annotations

import re
import subprocess

proc = subprocess.run(
    ["docker", "logs", "--since", "10m", "dafeiyu-telegram"],
    capture_output=True,
    text=True,
    timeout=20,
    check=False,
)
lines = (proc.stdout + "\n" + proc.stderr).splitlines()
needles = {
    "siwc_registration": ("dafeiyu_siwc", "SIWC"),
    "telegram_owner": ("telegram_owner", "OwnerTelegram"),
    "local_life": ("dafeiyu_local_life", "local_life"),
    "provider_failure": ("Failed to load provider", "Provider adapter not found"),
    "platform_failure": ("Failed to initialize platform", "Platform adapter not found"),
    "plugin_failure": ("Failed to load plugin", "Plugin load failed"),
}
for key, candidates in needles.items():
    relevant = [s for s in lines if any(token.lower() in s.lower() for token in candidates)]
    print(f"{key}: {len(relevant)} diagnostic line(s)")
errors = []
for s in lines:
    if any(x in s for x in ("ERROR", "CRITICAL", "Traceback", "ImportError", "ModuleNotFoundError")):
        # Show only a generic error class, not arbitrary exception strings.
        label = next((x for x in ("ImportError", "ModuleNotFoundError", "Traceback", "CRITICAL", "ERROR") if x in s), "ERROR")
        errors.append(label)
print("observed_error_classes:", ",".join(sorted(set(errors))) if errors else "none")
print("container_logs_available:", proc.returncode == 0)
