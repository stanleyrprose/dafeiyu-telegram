# Repository engineering rules (template)

Project-wide default: follow [Agent Development Policy v1.0](docs/DEV-WORKFLOW-v1.0.md).
A compatible summary is deliberately repeated here for agents that read only AGENTS.md.

- **Phase D (default):** Read branch, PRD, project rules and all CI/deploy triggers; work on a development branch. During development use static inspections only, **do not run tests**.
- **Commit locally, then push the development branch to GitHub as work-in-progress SOT**. Push only after verifying that it does **not** trigger GitHub CI, an existing PR synchronize event or an auto-deploy hook. If uncertain, **stop and report**. Never push unfinished work to main.
- **No PR, CI, Merge or deployment in Phase D.**
- **Phase V:** After implementation and required human feedback are complete, with user authorization run affected-path tests and fix failures.
- **Phase R:** After tests pass and release closure is authorized, PR -> CI -> required checks -> Merge; deployment remains a separately approved project operation.
- Template CI must only trigger on push to main, PR targeting main or explicit workflow_dispatch. Existing scheduled operational workflows must not be disabled or altered by this policy.
- Do not weaken project-specific safety gates, access limits or deployment safeguards. Keep secrets, internal business/health data and original media outside Git.
- Before the final PR add .github/project-tests.sh with real project tests; template scaffold-only CI cannot prove application readiness.
- Confirm the event selector and repository visibility in every new repo, including copies of this template.
