"""AstrBot SIWC text Provider extension (no embedded credentials)."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import httpx

from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.provider.sources.openai_responses_source import ProviderOpenAIResponses
from astrbot.core.exceptions import EmptyModelOutputError
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.provider.entities import LLMResponse, TokenUsage
from openai import AuthenticationError
import secrets
from datetime import datetime, timezone

RESOURCE = "https://api.openai.com/v1"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
ISSUER = "https://auth.openai.com"
TIMEOUT = httpx.Timeout(connect=10, read=30, write=10, pool=10)

class SIWCError(RuntimeError):
    """Safe operational error without exposing provider response content."""


def load_record(path: Path) -> dict:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SIWCError("本机授权记录不存在或无法读取") from exc
    if not isinstance(record, dict) or not record.get("model"):
        raise SIWCError("授权记录结构无效")
    if PLAN_SCOPE not in record.get("scopes", []):
        raise SIWCError("SIWC 缺少订阅推理授权 scope")
    return record

def _atomic_save(path: Path, record: dict) -> None:
    temp = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            json.dump(record, writer, ensure_ascii=False)
            writer.write("\n")
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temp, path)
        os.chmod(path, 0o600)
    finally:
        temp.unlink(missing_ok=True)


def _expires_soon(record: dict) -> bool:
    try:
        stored = datetime.fromisoformat(record["saved_at"].replace("Z", "+00:00"))
        if stored.tzinfo is None:
            return True
        return (datetime.now(timezone.utc) - stored).total_seconds() >= max(0, int(record["expires_in"]) - 300)
    except (ValueError, TypeError, KeyError):
        return True


def _history(provider, contexts) -> list[dict]:
    history = provider._ensure_message_to_dicts(contexts)
    cleaned = []
    for message in history:
        if not isinstance(message, dict) or message.get("role") not in {"user", "assistant"}:
            continue
        raw = message.get("content")
        if isinstance(raw, str):
            text = raw
        elif isinstance(raw, list):
            text = "\n".join(
                part["text"] for part in raw
                if isinstance(part, dict) and part.get("type") in {"text", "input_text", "output_text"}
                and isinstance(part.get("text"), str)
            )
        else:
            continue
        if text.strip():
            cleaned.append({"role": message["role"], "content": text})
    return cleaned

@register_provider_adapter(
    "dafeiyu_siwc", "ChatGPT subscription via local SIWC",
    default_config_tmpl={
        "id": "dafeiyu_siwc",
        "type": "dafeiyu_siwc",
        "provider_type": "chat_completion",
        "enable": False,
        "model": "",
    },
)
class DafeiyuSIWCProvider(ProviderOpenAIResponses):
    """Uses AstrBot's Responses adapter; no Function Tool path."""

    def __init__(self, provider_config: dict, provider_settings: dict):
        self.credentials_path = Path(os.getenv("DAFEIYU_SIWC_CREDENTIALS", "/AstrBot/private/oauth/credentials.json"))
        record = load_record(self.credentials_path)
        config = dict(provider_config)
        config.update({"api_base": RESOURCE, "key": ["unused"], "model": record["model"], "timeout": 120})
        super().__init__(config, provider_settings)
        self.client.timeout = TIMEOUT
        self._refresh_lock = asyncio.Lock()
        self._request_gate = asyncio.Semaphore(1)

    async def get_models(self) -> list[str]:
        return [load_record(self.credentials_path)["model"]]

    @property
    def busy(self) -> bool:
        return self._request_gate.locked()

    def get_current_key(self) -> str:
        return "SIWC account"

    def get_keys(self) -> list[str]:
        return []

    def set_key(self, key: str) -> None:
        raise SIWCError("请使用 Mac 上的授权 CLI，Provider 不接受 API Key")

    async def _credential_for_request(self, *, renew: bool = False) -> str:
        async with self._refresh_lock:
            current = load_record(self.credentials_path)
            if not renew and not _expires_soon(current) and current.get("access_token"):
                return current["access_token"]
            if not current.get("refresh_token") or not current.get("client_id"):
                raise SIWCError("缺少刷新凭据，请在 Mac 重新授权")
            async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False) as client:
                try:
                    result = await client.post(
                        ISSUER + "/api/accounts/oauth/token",
                        data={
                            "grant_type": "refresh_token",
                            "client_id": current["client_id"],
                            "refresh_token": current["refresh_token"],
                            "resource": RESOURCE,
                        },
                    )
                except httpx.HTTPError as exc:
                    raise SIWCError("刷新连接失败，原凭据保持不变") from exc
            if result.status_code != 200:
                if result.status_code in (400, 401, 403):
                    raise SIWCError("订阅授权已失效或被拒，请在 Mac 重新授权")
                raise SIWCError(f"刷新服务暂不可用 (HTTP {result.status_code})")
            try:
                response = result.json()
            except ValueError as exc:
                raise SIWCError("刷新服务返回格式错误") from exc
            if not isinstance(response, dict) or not response.get("access_token"):
                raise SIWCError("刷新响应缺少访问凭据")
            granted = response.get("scope")
            scopes = granted.split() if isinstance(granted, str) and granted else current.get("scopes", [])
            if PLAN_SCOPE not in scopes:
                raise SIWCError("刷新后失去订阅推理权限")
            current.update({
                "access_token": response["access_token"],
                "refresh_token": response.get("refresh_token") or current["refresh_token"],
                "id_token": response.get("id_token") or current.get("id_token", ""),
                "scopes": scopes,
                "expires_in": int(response.get("expires_in", 3600)),
                "saved_at": datetime.now(timezone.utc).isoformat(),
            })
            _atomic_save(self.credentials_path, current)
            return current["access_token"]

    async def _parse_response(self, response, tools):
        if self._field(response, "status") != "completed":
            raise SIWCError("Responses 没有成功完成；部分流不能作为完成回答")
        try:
            return await super()._parse_response(response, None)
        except EmptyModelOutputError:
            # Some SIWC models emit text deltas but omit output[] in the
            # response.completed object. Only reconstruct AFTER completion.
            text = "".join(self._streamed_text_chunks)
            if not text.strip():
                raise
            usage = self._field(response, "usage")
            input_details = self._field(usage, "input_tokens_details")
            cached = self._field(input_details, "cached_tokens", 0) or 0
            input_count = self._field(usage, "input_tokens", 0) or 0
            output_count = self._field(usage, "output_tokens", 0) or 0
            return LLMResponse(
                "assistant", result_chain=MessageChain().message(text),
                id=self._field(response, "id"), raw_completion=response,
                usage=TokenUsage(
                    input_other=max(0, input_count - cached),
                    input_cached=cached, output=output_count,
                ),
            )

    async def text_chat_stream(
        self, prompt=None, session_id=None, image_urls=None, audio_urls=None,
        func_tool=None, contexts=None, system_prompt=None, tool_calls_result=None,
        model=None, tool_choice="auto", request_max_retries=None, **kwargs,
    ):
        if image_urls or audio_urls or tool_calls_result:
            raise SIWCError("首版只支持纯文本，已禁用多模态和工具调用")
        # A single total deadline covers queueing, refresh and the entire SSE stream.
        async with asyncio.timeout(120):
            async with self._request_gate:
                self._streamed_text_chunks = []
                previous = _history(self, contexts)
                request, _ = await self._prepare_chat_payload(
                    prompt=prompt,
                    contexts=previous,
                    system_prompt=system_prompt,
                    model=load_record(self.credentials_path)["model"],
                )
                # Ignore toolset parameters; never send tools/function_call.
                for retry in range(2):
                    bearer = await self._credential_for_request(renew=retry != 0)
                    self.client.api_key = bearer
                    emitted = False
                    try:
                        async for response in self._query_stream(request.copy(), None, request_max_retries=1):
                            if response.is_chunk and response.completion_text:
                                self._streamed_text_chunks.append(response.completion_text)
                            emitted = True
                            yield response
                        return
                    except AuthenticationError as exc:
                        if retry or emitted:
                            raise SIWCError("认证被拒，请在 Mac 重新授权") from exc

    async def text_chat(
        self, prompt=None, session_id=None, image_urls=None, audio_urls=None,
        func_tool=None, contexts=None, system_prompt=None, tool_calls_result=None,
        model=None, extra_user_content_parts=None, tool_choice="auto",
        request_max_retries=None, **kwargs,
    ):
        final = None
        async for response in self.text_chat_stream(
            prompt=prompt,
            session_id=session_id,
            image_urls=image_urls,
            audio_urls=audio_urls,
            contexts=contexts,
            system_prompt=system_prompt,
            tool_calls_result=tool_calls_result,
            model=model,
        ):
            if not response.is_chunk:
                final = response
        if final is None:
            raise SIWCError("Responses 未出现完成事件")
        return final
