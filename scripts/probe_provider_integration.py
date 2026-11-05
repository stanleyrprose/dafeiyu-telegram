"""One-off SIWC Provider integration probe; hides credentials, output and message IDs."""
from __future__ import annotations
import asyncio
import json
from pathlib import Path
from data.plugins.astrbot_plugin_dafeiyu_siwc.provider import DafeiyuSIWCProvider

async def main():
    cfg = json.loads(Path("/AstrBot/data/cmd_config.json").read_text(encoding="utf-8-sig"))
    source = next((p for p in cfg.get("provider", []) if p.get("id") == "dafeiyu_siwc"), None)
    if not source:
        print("provider_config_missing")
        return
    provider = DafeiyuSIWCProvider(source, cfg.get("provider_settings", {}))
    chunk_count = 0
    final_count = 0
    final_chars = 0
    try:
        async for part in provider.text_chat_stream(prompt="Say exactly: OK", session_id="private-acceptance"):
            if part.is_chunk:
                chunk_count += 1
            else:
                final_count += 1
                final_chars += len(part.completion_text or "")
    finally:
        await provider.client.close()
    print("text_chunk_count:", chunk_count)
    print("final_response_count:", final_count)
    print("final_characters:", final_chars)
    print("provider_success:", final_count == 1 and final_chars > 0)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print("provider_error_type:", type(exc).__name__)
        print("http_status:", getattr(exc, "status_code", "unavailable"))
