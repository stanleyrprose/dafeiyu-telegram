"""Verify local-life backup paths without touching the running Docker Volume.

Run only during Phase V. All inputs are temporary test fixtures.
"""
from __future__ import annotations

import importlib.util
import json
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "scripts" / "backup_sqlite_db.py"
SPEC = importlib.util.spec_from_file_location("dafeiyu_backup", SOURCE)
assert SPEC and SPEC.loader
backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(backup)


class BackupLifeStateTests(unittest.TestCase):
    def test_preserves_sqlite_and_legacy_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            plugin = root / "life"
            destination = root / "backup"
            plugin.mkdir()
            destination.mkdir()
            state_file = plugin / "state.sqlite3"
            with sqlite3.connect(state_file) as db:
                db.execute("CREATE TABLE reminders (name TEXT NOT NULL)")
                db.execute("INSERT INTO reminders(name) VALUES(?)", ("Read later",))
            notes = ["用户喜欢传统回合制游戏"]
            (plugin / "notes.json").write_text(json.dumps(notes), encoding="utf-8")
            backup.backup_life_state(plugin, destination)
            exported = list(destination.glob("life-state-*.sqlite3"))
            note_files = list(destination.glob("life-notes-*.json"))
            self.assertEqual(len(exported), 1)
            self.assertEqual(len(note_files), 1)
            with sqlite3.connect(exported[0]) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                self.assertEqual(db.execute("SELECT name FROM reminders").fetchone()[0], "Read later")
            self.assertEqual(json.loads(note_files[0].read_text(encoding="utf-8")), notes)
            for artifact in exported + note_files:
                self.assertFalse(stat.S_IMODE(artifact.stat().st_mode) & 0o077)


if __name__ == "__main__":
    unittest.main()
