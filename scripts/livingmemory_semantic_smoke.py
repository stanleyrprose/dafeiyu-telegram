#!/usr/bin/env python3
"""Isolated LivingMemory semantic write/read acceptance using local Ollama.

Run inside the pinned v3 Docker image with official plugin mounted and no owner credentials.
Uses a disposable temporary SQLite + FAISS index; does not touch production memory.
"""
from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, "/AstrBot/data/plugins")
from astrbot.core.db.vec_db.faiss_impl.vec_db import FaissVecDB
from astrbot_plugin_livingmemory.core.managers.memory_engine import MemoryEngine


class OllamaEmbedding:
    provider_config = {"id": "isolated-bge-m3", "type": "openai_embedding"}

    def get_dim(self) -> int:
        return 1024

    async def get_embedding(self, value: str):
        def request():
            payload = json.dumps({"model": "bge-m3:latest", "input": value}).encode()
            req = urllib.request.Request(
                "http://host.docker.internal:11434/v1/embeddings",
                data=payload, headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=40) as reply:
                data = json.load(reply)
            return data["data"][0]["embedding"]
        result = await asyncio.to_thread(request)
        if len(result) != self.get_dim():
            raise RuntimeError("Unexpected embedding dimension")
        return result


async def verify():
    with tempfile.TemporaryDirectory(prefix="dafeiyu_lmem_isolated_") as tmp:
        base = Path(tmp)
        vector = FaissVecDB(
            str(base / "documents.sqlite3"),
            str(base / "memory.faiss"),
            OllamaEmbedding(),
        )
        await vector.initialize()
        engine = MemoryEngine(
            db_path=str(base / "engine.sqlite3"),
            faiss_db=vector,
            config={"atom_enabled": False, "graph_memory_enabled": False},
        )
        await engine.initialize()
        owner = "telegram_owner:FriendMessage:12345"
        other = "telegram_owner:FriendMessage:54321"
        try:
            doc_id = await engine.add_memory(
                "我喜欢传统回合制JRPG，特别喜欢勇者斗恶龙游戏。",
                session_id=owner, importance=0.9,
            )
            own = await engine.search_memories("我偏好的电子游戏是什么类型", k=5, session_id=owner)
            separate = await engine.search_memories("电子游戏偏好", k=5, session_id=other)
            print("memory_write_id_positive", isinstance(doc_id, int) and doc_id > 0)
            print("semantic_recall", len(own))
            print("session_isolation", len(separate) == 0)
            if not doc_id or not own or separate:
                raise AssertionError("Real semantic retrieval or session isolation failed")
        finally:
            await engine.close()


if __name__ == "__main__":
    asyncio.run(verify())
