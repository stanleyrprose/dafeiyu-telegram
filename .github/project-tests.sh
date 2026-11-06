#!/usr/bin/env bash
set -euo pipefail
# Pure-Python tests run on GitHub; AstrBot-only tests explicitly skip without their pinned runtime.
python3 -m unittest discover -s tests -v
python3 -m py_compile scripts/probe_siwc.py scripts/setup_telegram_credentials.py scripts/provision_telegram_runtime.py scripts/telegram_smoke.py scripts/inspect_runtime.py scripts/backup_sqlite_db.py scripts/verify_sqlite_persistence.py plugin/astrbot_plugin_dafeiyu_siwc/provider.py plugin/astrbot_plugin_dafeiyu_siwc/main.py plugin/astrbot_plugin_dafeiyu_local_life/main.py plugin/astrbot_plugin_dafeiyu_local_life/state.py plugin/astrbot_plugin_dafeiyu_local_life/policy.py plugin/astrbot_plugin_dafeiyu_local_life/web_read.py
