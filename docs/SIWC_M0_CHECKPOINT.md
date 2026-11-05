# M0 checkpoint — Dafeiyu Telegram + ChatGPT SIWC (2026-11-05)

**Status: M0 static portion prepared; M0-B live account eligibility NOT RUN. M1/M2 not authorized to start until M0 passes.**

## Project / rules

- Source: \`whyever77/dafeiyu-astrbot\` tag \`v2.11.1\` / shallow checkout \`fef1e99\`.
- Working tree: independent branch \`feat/telegram-siwc-v1.3\`, local checkout on Mac mini.
- Target AstrBot: verify against current upstream source and pin \`v4.29.4\` for the eventual single-container deployment. This target was released 2026-10-31; no runtime installation has occurred.
- Canonical scope: chat PRD v1.3 as supplied by the user; initial work limited to M0.
- No existing QQ runtime/data touched. No tests, PR, CI, Merge, remote push or production deploy.

## Source-verified compatibility

1. Upstream \`astrbot/core/platform/sources/telegram/tg_adapter.py\` already registers the native \`telegram\` adapter and runs a long-polling client. No NapCat required.
2. Upstream \`astrbot/core/provider/provider.py\` exposes \`Provider.text_chat\`, \`Provider.text_chat_stream\`, \`get_models\`, \`get_current_key\`, \`set_key\`; \`register.py\` defines \`register_provider_adapter\`; \`sources/openai_responses_source.py\` is a stateless Responses implementation. **The dynamic registration/load order for a custom provider from a Star plugin remains to be validated in M1**, not assumed.
3. The upstream pipeline includes \`WhitelistCheckStage\` before \`PreProcessStage\` and \`ProcessStage\`. Configure \`enable_id_white_list=true\`, \`id_whitelist_log=false\`, \`wl_ignore_admin_on_friend=false\`, \`wl_ignore_admin_on_group=false\`, and an *exact owner private-session UMO* (not only raw numeric owner ID). Ensure group and channel events cannot match. Telegram conversion precedes the whitelist, so raw DEBUG logs must not be enabled. An actual owner/private gate remains an acceptance requirement; do not claim pre-conversion rejection from the whitelist alone.
4. Source \`plugin/astrbot_plugin_bili_activity/memory_policy.py\` relies on \`.core\` and existing episode schema; \`rhythm.py\` assumes an activity \`runs\` table. They are **not** portable as drop-in, standalone modules. M2 should extract only no-network, no-core-patch logic into a new thin plugin.
5. Source \`deploy/compose.yaml\` has a NapCat service plus four direct AstrBot kernel patches. M1 must use a distinct compose/config and new data directory, not mutate the historical QQ runtime.
6. Mika \`ChatGptAuth.kt\` and \`ChatGptSession.kt\` corroborate PKCE, \`dynamic_agent_client\`, JWT/JWKS scope checking and serial refresh. \`ResponsesModel.kt\` confirms use of \`store:false\`, \`stream:true\`, terminal \`response.completed\` only.

## M0-B, human action required

The following commands are intended for the logged-in Mac mini desktop session, **not for unattended/background execution**:

\`\`\`sh
cd /Users/xu/Documents/mcpx-projects/dafeiyu-telegram
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements-siwc.txt
.venv/bin/python scripts/probe_siwc.py
\`\`\`

- The script opens the Mac system browser for the user to sign in, grant the requested permission and complete consent.
- It verifies issued \`client_id\`, OIDC identity and \`chatgpt.tokens.use.direct\`, queries the per-account \`/v1/models\` catalog, and requires \`response.completed\` from one minimal \`/v1/responses\` stream.
- On success the local private \`private/oauth/credentials.json\` is written atomically with owner-only permissions; \`private/\` is git-ignored.
- Credentials, authorization URLs, callback codes and token responses must never be pasted into ChatGPT or committed.
- On HTTP 403/scope denial: No-Go for current eligibility. On transient network errors: Inconclusive, not a permanent No-Go.
- The source code and Python syntax have been inspected; **no real OAuth, model invocation, package install or end-to-end test has been performed yet.**

## Next authorized step after successful M0-B

M1: dedicated single-container config with no NapCat and no old core patches; native Telegram owner/private entry control, SIWC text-only Provider reading and refreshing the above local credential file, preserved persona. M2: new local-life thin plugin for memory prompt and one rhythm notification. Full affected-path acceptance occurs after complete development and separately approved verification; PR/CI/merge only afterward.

## Git remote policy

The clone's \`origin\` points to a third-party repository. **Do not push to that origin.** Decide an owner-controlled SOT repository/fork through Mac \`gh\` before remote push; there is no implied permission to write upstream.
