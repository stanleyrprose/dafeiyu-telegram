#!/usr/bin/env python3
"""Explicit deployment/rollback utility for the on-demand Mac Browser Plane bridge.

Do not run during Phase D. The launchd job runs only while a request is queued.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import sys

LABEL = "io.dafeiyu.browser-plane-read"


def _paths():
    repo = Path(__file__).resolve().parents[1]
    # A launchd Python process can stall on macOS TCC-protected Documents paths.
    # Keep the launched script and queue under user-owned Application Support.
    root = Path.home() / "Library" / "Application Support" / "dafeiyu-browser-plane"
    plist = Path.home() / "Library" / "LaunchAgents" / (LABEL + ".plist")
    runtime_bin = Path.home() / "agent-browser-runtime" / "app" / "venv" / "bin"
    return repo, root, plist, runtime_bin


def _launchctl(*args):
    return subprocess.run(["/bin/launchctl", *args], check=False, capture_output=True, text=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("install", "uninstall"))
    args = parser.parse_args()
    repo, root, plist, runtime_bin = _paths()
    domain = f"gui/{os.getuid()}"
    service = f"{domain}/{LABEL}"
    if args.action == "uninstall":
        _launchctl("bootout", service)
        plist.unlink(missing_ok=True)
        print("Browser Plane 桥接唤醒任务已卸载；请求队列和证据均保留。")
        return 0

    if plist.exists():
        raise SystemExit("LaunchAgent 已存在；请先核对运行状态，避免打断进行中的任务。")
    python = runtime_bin / "python"
    cli = runtime_bin / "mac-browser-mcp-call"
    worker = repo / "scripts" / "browser_plane_host_worker.py"
    installed_worker = root / "browser_plane_host_worker.py"
    if not python.is_file() or not cli.is_file() or not worker.is_file():
        raise SystemExit("Mac Browser Plane 已安装的运行时或桥接脚本不存在。")
    for directory in (root, root / "requests", root / "responses"):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        if directory.is_symlink():
            raise SystemExit("拒绝使用符号链接作为桥接目录。")
        directory.chmod(0o700)
    if installed_worker.is_symlink():
        raise SystemExit("拒绝覆盖符号链接形式的执行脚本。")
    # Copy reviewed source into the non-TCC runtime directory atomically.
    worker_temp = installed_worker.with_name("." + installed_worker.name + ".tmp")
    try:
        with worker.open("rb") as source, worker_temp.open("xb") as output:
            shutil.copyfileobj(source, output)
        os.chmod(worker_temp, 0o600)
        os.replace(worker_temp, installed_worker)
    finally:
        worker_temp.unlink(missing_ok=True)
    plist.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(python), str(installed_worker), str(root), str(cli)],
        "RunAtLoad": True,
        "WatchPaths": [str(root / "requests")],
        "ThrottleInterval": 10,
        "ProcessType": "Background",
        "Umask": 0o077,
        "StandardOutPath": str(root / "host-worker.stdout.log"),
        "StandardErrorPath": str(root / "host-worker.stderr.log"),
    }
    temporary = plist.with_name("." + plist.name + ".tmp")
    try:
        with temporary.open("wb") as handle:
            plistlib.dump(payload, handle)
        os.chmod(temporary, 0o600)
        os.replace(temporary, plist)
        started = _launchctl("bootstrap", domain, str(plist))
        if started.returncode:
            plist.unlink(missing_ok=True)
            raise SystemExit("launchd 未能注册本机桥接；请检查本机 LaunchAgent 配置。")
    finally:
        temporary.unlink(missing_ok=True)
    print("Mac Browser Plane 按需请求桥接已安装；尚需按发布流程启用 Docker 配置。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
