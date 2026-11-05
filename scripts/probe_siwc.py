#!/usr/bin/env python3
"""One-time local SIWC sign-in and eligibility probe. Never prints credentials."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
from jwt import PyJWKClient

ISSUER = "https://auth.openai.com"
AUTH_URL = ISSUER + "/api/accounts/authorize"
TOKEN_URL = ISSUER + "/api/accounts/oauth/token"
RESOURCE = "https://api.openai.com/v1"
SCOPE = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
PLAN_SCOPE = "chatgpt.tokens.use.direct"
APP_NAME = "Dafeiyu Telegram"
CALLBACK_PATH = "/auth/callback"


class ProbeError(Exception):
    pass


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _atomic_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(path.parent, 0o700)
    # Never write secrets to a temporary directory outside the protected folder.
    tmp = path.with_name("." + path.name + "." + secrets.token_hex(8) + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(obj, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _load_record(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ProbeError("凭据文件不是 JSON 对象，已停止")
    return data


def _callback(server: HTTPServer, target_state: str, seconds: int = 300) -> dict:
    server.timeout = 1
    server.result = None
    deadline = time.monotonic() + seconds
    while server.result is None and time.monotonic() < deadline:
        server.handle_request()
    if server.result is None:
        raise ProbeError("等待浏览器授权超时")
    result = server.result
    if result.get("state") != target_state:
        raise ProbeError("OAuth state 不匹配")
    if result.get("error"):
        raise ProbeError("用户未授权或服务端拒绝：" + str(result["error"])[:60])
    if not result.get("code"):
        raise ProbeError("OAuth 回调缺少授权码")
    return result


def _handler_class():
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            if parts.path == "/auth/start":
                auth_url = getattr(self.server, "auth_url", None)
                if not auth_url:
                    self.send_error(503)
                    return
                self.send_response(302)
                self.send_header("Location", auth_url)
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return
            if parts.path != CALLBACK_PATH:
                self.send_error(404)
                return
            params = parse_qs(parts.query, keep_blank_values=True)
            result = {k: values[0] for k, values in params.items() if values}
            self.server.result = result
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write("已收到 ChatGPT 授权结果，可返回终端查看验证状态。".encode("utf-8"))

        def log_message(self, fmt: str, *args) -> None:
            # Request paths include OAuth codes. Do not log them.
            return

    return CallbackHandler


def _exchange(client: httpx.Client, client_id: str, code: str, verifier: str, redirect: str) -> dict:
    response = client.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect,
            "resource": RESOURCE,
        },
    )
    if response.status_code != 200:
        raise ProbeError(f"换取 Token 失败：HTTP {response.status_code}（响应内容已隐藏）")
    value = response.json()
    if not isinstance(value, dict):
        raise ProbeError("Token 响应不是对象")
    return value


def _verify_id_token(id_token: str, issued_id: str, nonce: str) -> dict:
    jwks = PyJWKClient(ISSUER + "/.well-known/jwks.json")
    key = jwks.get_signing_key_from_jwt(id_token)
    claims = jwt.decode(
        id_token,
        key.key,
        algorithms=["RS256"],
        audience=issued_id,
        issuer=ISSUER,
        options={"require": ["exp", "iss", "aud", "sub"]},
        leeway=120,
    )
    if claims.get("nonce") != nonce:
        raise ProbeError("ID Token nonce 不匹配")
    return claims


def _model_catalog(client: httpx.Client, bearer: str) -> list[dict]:
    r = client.get(RESOURCE + "/models", headers={"Authorization": "Bearer " + bearer})
    if r.status_code != 200:
        raise ProbeError(f"模型目录不可用：HTTP {r.status_code}")
    data = r.json()
    rows = data.get("models") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        raise ProbeError("模型目录缺少 models 数组")
    return [m for m in rows if isinstance(m, dict) and m.get("visibility") == "list" and isinstance(m.get("slug"), str)]


def _probe_response(client: httpx.Client, bearer: str, model: str) -> None:
    payload = {
        "model": model,
        "input": [{"role": "user", "content": "Say exactly: Hello, world!"}],
        "store": False,
        "stream": True,
    }
    completed = False
    event_lines: list[str] = []
    deadline = time.monotonic() + 120
    with client.stream(
        "POST", RESOURCE + "/responses",
        headers={"Authorization": "Bearer " + bearer, "Accept": "text/event-stream"},
        json=payload,
    ) as response:
        if response.status_code != 200:
            raise ProbeError(f"Responses 返回 HTTP {response.status_code}（响应内容已隐藏）")
        for line in response.iter_lines():
            if time.monotonic() > deadline:
                raise ProbeError("Responses 超过总耗时限制")
            if line.startswith("data:"):
                event_lines.append(line[5:].strip())
                continue
            if line or not event_lines:
                continue
            raw = "\n".join(event_lines)
            event_lines.clear()
            if raw == "[DONE]":
                continue
            try:
                event = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ProbeError("SSE 事件不是有效 JSON") from exc
            kind = event.get("type")
            if kind == "response.completed":
                completed = True
            elif kind in {"response.incomplete", "response.failed", "error"}:
                raise ProbeError(f"Responses 未成功终止：{kind}")
    if not completed:
        raise ProbeError("SSE 未收到 response.completed")


def main() -> int:
    parser = argparse.ArgumentParser(description="macOS 本机一次性 ChatGPT SIWC 登录与资格验证")
    parser.add_argument("--directory", type=Path, default=Path(__file__).resolve().parents[1] / "private" / "oauth")
    parser.add_argument("--model", help="从当前账号模型目录选择可见模型 slug；默认第一个可见模型")
    parser.add_argument("--phone-browser", action="store_true", help="通过 Termux SSH 端口转发，在手机浏览器完成授权")
    parser.add_argument("--phone-port", type=int, default=18765, help="手机 SSH 回调转发端口（默认 18765）")
    args = parser.parse_args()
    directory = args.directory.expanduser().resolve()
    credentials_path = directory / "credentials.json"
    host_path = directory / "host.json"

    # Persist the host ID before first sign-in, even if consent is declined.
    old = _load_record(credentials_path)
    host = _load_record(host_path)
    host_id = old.get("ext_agent_host_id") or host.get("ext_agent_host_id")
    if not host_id:
        host_id = "urn:uuid:" + str(uuid.uuid4())
        _atomic_json(host_path, {"ext_agent_host_id": host_id})
    client_id = old.get("client_id")
    verifier = _b64(secrets.token_bytes(48))
    challenge = _b64(hashlib.sha256(verifier.encode("ascii")).digest())
    state, nonce = _b64(secrets.token_bytes(32)), _b64(secrets.token_bytes(32))
    if args.phone_browser and not 1024 <= args.phone_port <= 65535:
        raise ProbeError("手机回调端口必须在 1024–65535 范围内")
    server = HTTPServer(("127.0.0.1", args.phone_port if args.phone_browser else 0), _handler_class())
    try:
        redirect = f"http://127.0.0.1:{server.server_port}{CALLBACK_PATH}"
        args_url = {
            "client_id": client_id or "dynamic_agent_client",
            "ext_agent_host_id": host_id,
            "response_type": "code",
            "redirect_uri": redirect,
            "scope": SCOPE,
            "resource": RESOURCE,
            "state": state,
            "nonce": nonce,
            "code_challenge_method": "S256",
            "code_challenge": challenge,
        }
        if not client_id:
            args_url["agent_name_hint"] = APP_NAME
        if old.get("id_token") and client_id and not args.phone_browser:
            args_url["id_token_hint"] = old["id_token"]
        url = AUTH_URL + "?" + urlencode(args_url)
        if args.phone_browser:
            server.auth_url = url
            print(f"手机授权模式：请保持 SSH -L 127.0.0.1:{args.phone_port}:127.0.0.1:{args.phone_port} 端口转发连接。", flush=True)
            print(f"用手机浏览器打开：http://127.0.0.1:{args.phone_port}/auth/start", flush=True)
            print("浏览器将跳转至 OpenAI 登录页，授权完成后自动回到本机回调。", flush=True)
        else:
            print("正在打开本机浏览器进行 ChatGPT 授权（不会输出授权 URL 或 Token）...", flush=True)
            if not webbrowser.open(url):
                raise ProbeError("无法打开浏览器。请在 Mac 图形桌面运行此命令")
        callback = _callback(server, state)
    finally:
        server.server_close()

    issued = callback.get("client_id") or client_id
    if not issued or (client_id and issued != client_id):
        raise ProbeError("OAuth client_id 缺失或与此前注册不一致")
    timeout = httpx.Timeout(connect=15, read=35, write=15, pool=10)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        tokens = _exchange(client, issued, callback["code"], verifier, redirect)
        scope = tokens.get("scope", "")
        scopes = scope.split() if isinstance(scope, str) else []
        if PLAN_SCOPE not in scopes:
            raise ProbeError("未获得 chatgpt.tokens.use.direct，不能进入 M1")
        if not tokens.get("id_token") or not tokens.get("access_token") or not tokens.get("refresh_token"):
            raise ProbeError("缺少必要的 ID/access/refresh Token")
        claims = _verify_id_token(tokens["id_token"], issued, nonce)
        if old.get("subject") and old["subject"] != claims["sub"]:
            raise ProbeError("此次登录的 ChatGPT 账号与已有凭据不一致")
        choices = _model_catalog(client, tokens["access_token"])
        if not choices:
            raise ProbeError("账号没有可用的列表模型")
        model_names = {m["slug"] for m in choices}
        selected = args.model or (old.get("model") if old.get("model") in model_names else choices[0]["slug"])
        if selected not in model_names:
            raise ProbeError("指定模型不在该账号的可用模型目录中")
        _probe_response(client, tokens["access_token"], selected)

    record = {
        "issuer": ISSUER,
        "subject": claims["sub"],
        "email": claims.get("email", ""),
        "client_id": issued,
        "ext_agent_host_id": host_id,
        "id_token": tokens["id_token"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_in": int(tokens.get("expires_in", 3600)),
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "scopes": scopes,
        "model": selected,
    }
    _atomic_json(credentials_path, record)
    print(f"M0-B 通过：scope、ID Token、模型 {selected} 与 response.completed 均已验证；凭据已存入私有目录。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProbeError, httpx.HTTPError, jwt.PyJWTError, OSError, ValueError) as exc:
        # Never print raw token response, callback URL or OAuth credentials.
        if isinstance(exc, ProbeError):
            print("M0-B 未通过：" + str(exc), file=sys.stderr)
        else:
            print(f"M0-B 未完成：{type(exc).__name__}（不代表账号永久不符合资格）", file=sys.stderr)
        sys.exit(1)
