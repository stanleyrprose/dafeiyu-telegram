# Engineering Repository Template

Template itself is private; repositories created with `gh new-safe <repo-name>` on Mac mini are PUBLIC by default.

## Git and CI lifecycle

1. Develop on a feature branch; Commit and Push it as work-in-progress SOT only after verifying no CI or automatic deployment triggers.
2. During development, perform static inspection only and DO NOT run tests. Finish human review and all code first.
3. After implementation and human review, request authorization for verification, run affected-path tests, fix failures and then seek approval for PR.
4. After PR review, successful CI, all acceptance gates and user authorization, Merge to main; deployment remains a separate approval.
5. Explicit manual `workflow_dispatch` is supported.

See the versioned policy at docs/DEV-WORKFLOW-v1.0.md. The template's workflow initially checks repository scaffolding; a green main-branch scaffold check **is not** an application test result. Before final review add `.github/project-tests.sh` with real checks. PR will fail until this script is present. Check other workflows separately if you add them.

Default generated repository visibility is **PUBLIC**. Template repository stays PRIVATE. Always check before committing private data, tokens, health records, credentials, or internal business details. For a private project explicitly use the standard `gh repo create --private --template ...` invocation.
