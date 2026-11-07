"""Phase V only: Browser Plane bridge contract, owner-read transport and safety."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from plugin.astrbot_plugin_dafeiyu_local_life import browser_plane_client as client


def load_host_worker():
    config = types.ModuleType("browser_plane.config")
    config.RuntimePaths = type("RuntimePaths", (), {"discover": staticmethod(lambda: None)})
    package = types.ModuleType("browser_plane")
    package.__path__ = []
    path = Path(__file__).resolve().parents[1] / "scripts" / "browser_plane_host_worker.py"
    spec = importlib.util.spec_from_file_location("_dafeiyu_host_worker_under_test", path)
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"browser_plane": package, "browser_plane.config": config}):
        spec.loader.exec_module(module)
    return module


class BrowserPlaneClientTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "requests").mkdir()
        (self.root / "responses").mkdir()
        self.env = patch.dict(os.environ, {
            "DAFEIYU_BROWSER_PLANE_ENABLED": "true",
            "DAFEIYU_BROWSER_PLANE_DIR": str(self.root),
        })
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temporary.cleanup()

    def test_disabled_fails_closed(self):
        os.environ["DAFEIYU_BROWSER_PLANE_ENABLED"] = "false"
        with self.assertRaises(client.BrowserPlaneReadError):
            client.acquire_public_page("https://example.com")
        self.assertEqual(list((self.root / "requests").iterdir()), [])

    def test_owner_page_uses_file_queue_and_consumes_response(self):
        original = client._atomic_json

        def place_response(path, data):
            original(path, data)
            original(self.root / "responses" / (data["id"] + ".json"), {
                "id": data["id"],
                "ok": True,
                "url": "https://example.com/",
                "text": "Example Domain",
                "engine": "c0-fetch",
            })
        with patch.object(client, "_public_target", return_value=("", "", "")), patch.object(
            client, "_atomic_json", side_effect=place_response
        ):
            url, text, engine = client.acquire_public_page("https://example.com", timeout_sec=1)
        self.assertEqual((url, text, engine), ("https://example.com/", "Example Domain", "c0-fetch"))
        self.assertEqual(list((self.root / "requests").glob("*.json")), [])
        self.assertEqual(list((self.root / "responses").glob("*.json")), [])

    def test_bridge_failure_does_not_fallback_to_http(self):
        original = client._atomic_json

        def place_error(path, data):
            original(path, data)
            original(self.root / "responses" / (data["id"] + ".json"), {
                "id": data["id"], "ok": False, "error": "Mac Browser Plane 未完成任务",
            })
        with patch.object(client, "_public_target", return_value=("", "", "")), patch.object(
            client, "_atomic_json", side_effect=place_error
        ):
            with self.assertRaisesRegex(client.BrowserPlaneReadError, "未完成任务"):
                client.acquire_public_page("https://example.com", timeout_sec=1)


class MacWorkerTests(unittest.TestCase):
    def setUp(self):
        self.worker = load_host_worker()
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "requests").mkdir()
        (self.root / "responses").mkdir()

    def tearDown(self):
        self.temporary.cleanup()

    def test_public_url_guard(self):
        import socket
        for value in ("http://example.com", "https://127.0.0.1", "https://localhost", "https://user:pw@example.com"):
            with self.subTest(value=value), self.assertRaises(self.worker.ReadRejected):
                self.worker._public_https(value)
        with patch.object(socket, "getaddrinfo", return_value=[(None, None, None, None, ("10.0.0.8", 443))]):
            with self.assertRaises(self.worker.ReadRejected):
                self.worker._public_https("https://example.com")
        with patch.object(socket, "getaddrinfo", return_value=[(None, None, None, None, ("93.184.215.14", 443))]):
            self.assertEqual(self.worker._public_https("https://example.com"), "https://example.com")

    def test_browser_acquire_is_only_allowed_subprocess_tool(self):
        job_id = "11111111-1111-4111-8111-111111111111"
        artifact_dir = self.root / "evidence" / job_id
        artifact_dir.mkdir(parents=True)
        body = b"<html><body><h1>Example Domain</h1><p>Public page</p></body></html>"
        artifact = artifact_dir / "response.html"
        artifact.write_bytes(body)
        import hashlib
        self.worker.RuntimePaths = type("RuntimePaths", (), {
            "discover": staticmethod(lambda: types.SimpleNamespace(evidence_dir=self.root / "evidence"))
        })
        payload = {
            "ok": True,
            "structured_content": {
                "state": "SUCCEEDED",
                "job_id": job_id,
                "result": {
                    "status": 200, "url": "https://example.com",
                    "engine": "c0-fetch", "content_type": "text/html",
                    "artifact_path": str(artifact), "sha256": hashlib.sha256(body).hexdigest(),
                },
            },
        }
        fake = types.SimpleNamespace(returncode=0, communicate=lambda timeout=None: (json.dumps(payload), ""))
        with patch.object(self.worker, "_public_https", return_value="https://example.com"), patch.object(
            self.worker.subprocess, "Popen", return_value=fake
        ) as run:
            result = self.worker._acquire("https://example.com", self.root / "browser-command")
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:3], ["call", "browser_acquire"])
        self.assertEqual(result["text"], "Example Domain\nPublic page")
        self.assertEqual(result["engine"], "c0-fetch")


class HostLaunchdContractTests(unittest.TestCase):
    def test_installed_worker_and_queue_live_outside_documents(self):
        target = Path(__file__).resolve().parents[1] / "scripts" / "install_browser_plane_bridge.py"
        spec = importlib.util.spec_from_file_location("_dafeiyu_launchd_under_test", target)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with patch.object(Path, "home", return_value=Path("/Users/fixture")):
            _, root, _, _ = module._paths()
        self.assertEqual(
            root,
            Path("/Users/fixture/Library/Application Support/dafeiyu-browser-plane"),
        )
        compose = (Path(__file__).resolve().parents[1] / "deploy" / "telegram" / "compose.yaml").read_text()
        self.assertIn("DAFEIYU_BROWSER_PLANE_HOST_DIR", compose)
        self.assertIn('"WatchPaths": [str(root / "requests")]', target.read_text())
        self.assertNotIn("../../private/browser-plane-bridge:/AstrBot/browser-plane-bridge", compose)


if __name__ == "__main__":
    unittest.main()
