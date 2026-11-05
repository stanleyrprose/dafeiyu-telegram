# M0 checkpoint — Dafeiyu Telegram + ChatGPT SIWC (2026-11-05)

**Status (2026-11-05): M0-B passed (user-reported scope + model gpt-6.1-sol + response.completed; private credential file verified present without reading it). M1/M2 development source drafted locally; no runtime acceptance or deployment yet.**

## Project / rules

- Source: `whyever77/dafeiyu-astrbot` tag `v2.11.1` / shallow checkout `fef1e99`.
- Working tree: independent branch `feat/telegram-siwc-v1.3`, local checkout on Mac mini.
- Target AstrBot: verify against current upstream source and pin `v4.29.4` for the eventual single-container deployment. This target was released 2026-10-31; no runtime installation has occurred.
- Canonical scope: chat PRD v1.3 as supplied by the user; initial work limited to M0.
- No existing QQ runtime/data touched. No tests, PR, CI, Merge, remote push or production deploy.

## Source-verified compatibility

1. Upstream `astrbot/core/platform/sources/telegram/tg_adapter.py` already registers the native `telegram` adapter and runs a long-polling client. No NapCat required.
2. Upstream `astrbot/core/provider/provider.py` exposes `Provider.text_chat`, `Provider.text_chat_stream`, `get_models`, `get_current_key`, `set_key`; `register.py` defines `register_provider_adapter`; `sources/openai_responses_source.py` is a stateless Responses implementation. **The dynamic registration/load order for a custom provider from a Star plugin remains to be validated in M1**, not assumed.
3. The upstream pipeline includes `WhitelistCheckStage` before `PreProcessStage` and `ProcessStage`. Configure `enable_id_white_list=true`, `id_whitelist_log=false`, `wl_ignore_admin_on_friend=false`, `wl_ignore_admin_on_group=false`, and an *exact owner private-session UMO* (not only raw numeric owner ID). Ensure group and channel events cannot match. Telegram conversion precedes the whitelist, so raw DEBUG logs must not be enabled. An actual owner/private gate remains an acceptance requirement; do not claim pre-conversion rejection from the whitelist alone.
4. Source `plugin/astrbot_plugin_bili_activity/memory_policy.py` relies on `.core` and existing episode schema; `rhythm.py` assumes an activity `runs` table. They are **not** portable as drop-in, standalone modules. M2 should extract only no-network, no-core-patch logic into a new thin plugin.
5. Source `deploy/compose.yaml` has a NapCat service plus four direct AstrBot kernel patches. M1 must use a distinct compose/config and new data directory, not mutate the historical QQ runtime.
6. Mika `ChatGptAuth.kt` and `ChatGptSession.kt` corroborate PKCE, `dynamic_agent_client`, JWT/JWKS scope checking and serial refresh. `ResponsesModel.kt` confirms use of `store:false`, `stream:true`, terminal `response.completed` only.

## M0-B, human action required

The CLI supports both local Mac desktop login and Android Termux over SSH. The script and credentials always run/stay on the Mac. Python virtualenv and dependencies are already installed locally.

**Mac desktop browser:**

```sh
cd /Users/xu/Documents/mcpx-projects/dafeiyu-telegram
.venv/bin/python scripts/probe_siwc.py
```

**Android Termux → SSH → Mac mini (phone browser):**

First, stop any existing Mac probe with Ctrl+C and exit the old SSH session. Then start a **new** SSH session with local TCP forwarding (run this in Termux on the phone):

```sh
ssh -o ExitOnForwardFailure=yes -L 127.0.0.1:18765:127.0.0.1:18765 macmini
```

In that SSH session run:

```sh
cd /Users/xu/Documents/mcpx-projects/dafeiyu-telegram
.venv/bin/python scripts/probe_siwc.py --phone-browser
```

The script listens on the Mac's `127.0.0.1:18765` and serves the short local URL `http://127.0.0.1:18765/auth/start`. Open this URL in the **phone** browser; it redirects directly to the OpenAI authorization page without printing the full URL. Its `http://127.0.0.1:18765/auth/callback` redirect goes into Termux's SSH forwarded port, then to the Mac's listener. Keep the SSH session alive until the probe returns. Do not paste or screenshot the authorization URL, callback code, or credentials. Phone mode suppresses the optional `id_token_hint`; the full authorization URL stays inside the Mac process.

If the tunnel fails or the callback times out, re-establish the `ssh -L` session and rerun the script; each attempt uses fresh PKCE/state/nonce. Neither phone nor container stores the OAuth tokens.
- It verifies issued `client_id`, OIDC identity and `chatgpt.tokens.use.direct`, queries the per-account `/v1/models` catalog, and requires `response.completed` from one minimal `/v1/responses` stream.
- On success the local private `private/oauth/credentials.json` is written atomically with owner-only permissions; `private/` is git-ignored.
- Credentials, authorization URLs, callback codes and token responses must never be pasted into ChatGPT or committed.
- On HTTP 403/scope denial: No-Go for current eligibility. On transient network errors: Inconclusive, not a permanent No-Go.
- On 2026-11-05 user completed phone-assisted SIWC login and reported `M0-B 通过` with `gpt-6.1-sol` and `response.completed`. No production Telegram, Docker, or provider integration acceptance was run.

## M1/M2 development checkpoint

A dedicated Compose, native Telegram owner-only adapter, SIWC text Provider, revised persona, and local memory/rhythm plugin have been authored in `feat/telegram-siwc-v1.3`. They are **not yet runtime-verified or deployed**. Exact deployment and rollback procedure is in `deploy/telegram/README.md`. Final affected-path acceptance and subsequent PR/CI/merge remain separate gates.

## Git remote policy

**2026-11-05:** Public SOT created at `https://github.com/stanleyrprose/dafeiyu-telegram` using the Mac `gh new-safe` template workflow. Local `origin` now points to that user-owned repository; `upstream` points to `whyever77/dafeiyu-astrbot`. Development branch `feat/telegram-siwc-v1.3` is pushed at `400437f`. Public `main` remains the unmodified engineering template, so the development code is visible **on the feature branch only**. The source history and template `main` are unrelated; reconcile a clean PR baseline only in the final acceptance phase, without force-pushing or prematurely running application CI. The template's own `main` scaffold workflow ran once on repository creation and succeeded; the feature-branch push did not trigger CI. No PR or Merge was created. Local OAuth and Telegram credentials remain git-ignored under `private/`.
