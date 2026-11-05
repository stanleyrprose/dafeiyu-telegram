#!/usr/bin/env python3
"""READ-ONLY template audit; legacy direct-to-main bootstrap disabled.

The former init_template.py wrote hardcoded AGENTS.md and README.md directly
to template main, overwriting accepted policy after a release. The default
is now inspection only: adopt policy changes through a development branch
and an explicitly approved PR/CI/merge gate.
"""
from __future__ import annotations

import json
import subprocess

REPO = "stanleyrprose/engineering-repo-template"
POLICY = "docs/DEV-WORKFLOW-v1.0.md"


def metadata(path: str) -> dict | None:
    proc = subprocess.run(
        ["gh", "api", f"repos/{REPO}/contents/{path}?ref=main"],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode:
        return None
    data = json.loads(proc.stdout)
    return {"path": path, "sha": data.get("sha"), "size": data.get("size")}


def main() -> None:
    print("TEMPLATE_AUDIT_ONLY: no GitHub content will be modified.")
    for path in ("AGENTS.md", POLICY, ".github/workflows/ci.yml", "README.md"):
        item = metadata(path)
        print("PRESENT" if item else "MISSING", path)
    print("To change template main: develop and Push a CI-safe branch, then")
    print("complete the user-approved test, PR, CI and Merge phase.")


if __name__ == "__main__":
    main()
