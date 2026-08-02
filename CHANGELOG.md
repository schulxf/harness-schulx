# Changelog

## Unreleased

- Bundled the Graph Engineering skill with Harness-specific guidance for
  knowledge graphs, GraphRAG and bounded multi-agent task graphs.
- Made JSON writes atomic and protected task/queue read-modify-write operations
  with cross-process locks.
- Added unique run ids and Git baselines that preserve committed changes in
  evaluator evidence.
- Centralized completion gates for final sensors, context, security, PT-BR
  review, code review and hard budgets.
- Bound sensor reviews to a digest of the exact commands, tier and shell mode.
- Invalidated completion evidence whenever the source surface changes after a
  check.
- Prevented `queue done` from bypassing task approval.
- Added a plain-language PR template, PT-BR checklist and automatic PR comment.
- Added installable package metadata, Ruff checks and Linux/Windows CI coverage.

## 0.3.0

- Documented the official v0.3 Harness operating model.
- Added local dashboard, task queue and supervisor concepts.
- Added pixel-art multi-repo Harness Hub with live local polling.
- Added resume/checkpoint guidance for long-running work.
- Added GitHub Issues/PR helper model.
- Added budgets and profiles: `fast`, `standard`, `deep`.
- Added artifact viewer and artifact index guidance.
- Added explicit failure policy.
- Added project memory model.
- Added plugin registry model.
- Added security scanner expectations.
- Expanded Telegram from monitoring bridge to remote-control surface.

## 0.2.0

- Added Telegram notifications, inbox, mirror, Codex gateway and bridge modes.
- Added plain-language task summaries.
- Added sensor tiers: `smoke`, `affected`, `full`, `all`, `quick`.
- Added `quick-pass` and `full-pass`.
- Added `fix-brief` for P0/P1 review loops.
- Added `parallel-dispatch.md` for evaluator/reviewer parallelism.
- Added context preflight caching.
- Expanded tests and documentation.

## 0.1.5

- Added isolated evaluator and Greptile-style reviewer handoffs.
- Added review consolidation guide.
- Added context preflight and required-doc checks.
- Added branch protection safeguards.
- Added deterministic sensor execution.
