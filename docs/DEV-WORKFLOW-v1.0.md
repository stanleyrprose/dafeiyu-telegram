# Agent Development Policy v1.0

Status: accepted on template main; deployment into additional agents and legacy repositories is tracked separately.
Scope: code-writing agents on Mac, remote Android/Linux nodes, and connected IDE/cloud sessions.
Owner: repository maintainer. Effective only where explicitly loaded.
Canonical location: stanleyrprose/engineering-repo-template, main, docs/DEV-WORKFLOW-v1.0.md.

## 1. Invariants and precedence

- This is a **development workflow policy**, not permission to access secrets, alter devices, deploy, or perform production writes.
- Respect system and tool instructions, applicable project AGENTS.md / CLAUDE.md / local rules, PRD, secrets/privacy and safety gates. If policies conflict, apply the stricter safety constraint and ask before proceeding.
- Preserve project-specific production/rollback/approval rules. Do not disable scheduled operational workflows or change production state just to satisfy this policy.
- No private source media, customer information, credentials or machine-specific paths in Git, generated public templates or logs.

## 2. Phase D — development (default)

1. Inspect current branch, Git remote, project AGENTS.md, approved PRD and every relevant workflow or deploy trigger. Distinguish GitHub Actions from Cloudflare/Vercel/GitHub Apps and push-to-deploy integrations.
2. Create or use a separate **feature/development branch**, never unfinished work on main.
3. Implement all requested changes, and conduct **static inspection only** (read, diff, format review, syntax review without executing programs). Do **not** run unit, integration, smoke or acceptance tests during active development.
4. Make incremental **local commits and push the development branch to GitHub** as the work-in-progress SOT. The push must not trigger GitHub CI, an existing PR synchronize action, or an automatic deployment. If safety cannot be confirmed, **do not push**; explain what needs remediation. Never use "[skip ci]" as a substitute for verified triggers.
5. During Phase D: **NO tests; NO PR; NO CI/workflow_dispatch; NO Merge; NO deployment**. Do not run project test hooks as a side effect of local commits; if hooks execute tests, pause and obtain approval for a safe local-only alternative. Never bypass mandatory security hooks without an appropriate review.
6. Record unfinished work, human feedback and gate state without treating untested code as accepted.

## 3. Phase V — concentrated verification (after implementation and required human review complete)

- Only after the agreed implementation and feedback are complete and the user authorizes this phase, run tests covering changed paths, safety invariants and regressions. Fix failures on the development branch and revalidate.
- Test approval does **not** imply production publish/deploy approval. Preserve evidence and distinguish local test success from final PR CI success.

## 4. Phase R — PR / CI / merge (release closure)

- After Phase V passes and the user authorizes release closure, open PR targeting main, allow configured PR CI, review results and merge only with passing required checks and satisfied project acceptance gates.
- Deployment remains a distinct approval/procedure and requires rollback/reconciliation evidence per project.

## 5. CI/deployment trigger contract

- Repositories created from this template: GitHub Actions may start on push to main, PR targeting main, or explicit workflow_dispatch. **No CI on development-branch push**.
- For existing repositories, inspect **all** active workflows, GitHub branch rules and outside deploy hooks *before* pushing. Never assume all legacy repos match the template.
- Existing schedule- and manual-triggered operational jobs (alerts, backups, data collection) remain enabled and are **not** development CI; do not modify them unless separately authorized.
- Before a safe push, check the development branch has no open PR (whose synchronize event would run CI). Recheck whenever workflow/branch rules change.

## 6. Agent adapter and repository rules

- Each Agent must use its supported instruction-loading mechanism. A mere Markdown link is **not** evidence that the policy was loaded.
- Add a short enforceable summary in every project AGENTS.md, retaining project-specific restrictions. Tools using other formats should get equivalent adapters (e.g. Claude CLAUDE.md, Gemini GEMINI.md, Pi agent instructions, Codex home instructions).
- Mac and mobile Debian/chroot are **separate hosts**: paths and global configs do not synchronize by themselves.
- In new repositories, copy this policy and the template's concise AGENTS.md. For updates, maintain one authoritative version and reconcile adapters; avoid independent hand-edited copies.

## 7. Audit and non-compliance

- If any active workflow listens to feat/**, feature/**, fix/**, research/** or unrestricted push, mark that repository **PUSH_BLOCKED_PENDING_CI_REMEDIATION**.
- Confirm trigger changes are approved before editing production repositories. Do not auto-remove unrelated cron, dispatch or business workflows.
- Record a per-repository status: READY, NEEDS_CI_REMEDIATION, NEEDS_DEPLOY_CHECK, or REMOTE_UNVERIFIED.
- This document defines a workflow. It does not override repository branch protections, product permissions or release controls.
