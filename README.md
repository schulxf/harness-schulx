# Runvero

**A local development workflow for coding agents, with explicit rules,
reviewed checks, and approvals backed by evidence.**

[![Tests](https://github.com/schulxf/runvero/actions/workflows/tests.yml/badge.svg)](https://github.com/schulxf/runvero/actions/workflows/tests.yml)
[![Skill compatibility](https://github.com/schulxf/runvero/actions/workflows/compat.yml/badge.svg)](https://github.com/schulxf/runvero/actions/workflows/compat.yml)
[![JEV observer](https://github.com/schulxf/runvero/actions/workflows/jev-observer.yml/badge.svg)](https://github.com/schulxf/runvero/actions/workflows/jev-observer.yml)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)

Runvero helps teams run coding-agent work without losing the parts that make a
change reviewable: the task, the project rules, the acceptance criteria, the
commands that were actually checked, and the independent review evidence. It
wraps a deterministic local Python CLI around an application repository and
stores task state in that repository's `.harness/` directory.

The project was previously named **Harness Schulx**. The full `bin/harness.py`
CLI, the `harness-schulx` package entry point, and existing `.harness/`
workspaces remain compatible. `bin/runvero.py` is the lean entry point for the
common prepare -> implement -> verify -> finish workflow.

## What It Does

- Creates a local task contract from a goal, acceptance criteria, out-of-scope
  notes, required project documents, and reviewed sensor commands.
- Generates an implementation brief for a coding agent while preserving the
  project's rules and required context.
- Runs quick or final sensor commands and binds their evidence to the current
  source state.
- Runs a local secret scan before final approval.
- Produces review handoff files that require an independent reviewer, and a
  second independent evaluator for critical changes.
- Detects stale source, contract, config, sensor, review, and security evidence.
- Keeps optional surfaces available for the full protocol: queues, checkpoints,
  reports, GitHub helpers, Telegram control, a local dashboard, a multi-project
  hub, plugins, and JEV failure observation.

Runvero does not implement code changes, authenticate reviewer identities, merge
pull requests, deploy applications, or provide a sandbox. It records and validates
local evidence; repository permissions, CI, branch protection, and production
approval still belong outside this tool.

## Requirements

- Python 3.10 or newer.
- Git.
- A target application repository on a non-protected feature branch.
- The target application's own test, build, and architecture-check commands.
- Optional: Node.js for the JEV worker and hub components.
- Optional: `gh` for the GitHub helper commands.
- Optional: Telegram bot credentials for Telegram integration.

The Python core has no runtime package dependencies. Development checks use the
packages listed in `requirements-dev.txt`.

## Quick Start

Clone Runvero and choose the application repository you want to manage:

```powershell
git clone https://github.com/schulxf/runvero.git
cd runvero

$RUNVERO = "$PWD\bin\runvero.py"
$APP = "C:\path\to\your-app"
python $RUNVERO --help
```

Start from a clean worktree in the application repository, on a feature branch:

```powershell
git -C $APP switch -c feature/fix-registration
```

Prepare the task. Replace the example scripts with real commands from your
application and review them before using `--reviewed-sensors`.

```powershell
python $RUNVERO --repo $APP prepare "Fix registration persistence" `
  --builder "builder-session-1" `
  --criteria "A valid registration remains saved after reload" `
  --criteria "Invalid input is not persisted" `
  --required-doc "docs/architecture.md" `
  --sensor "npm run test:registration" `
  --sensor "npm run typecheck" `
  --architecture-sensor "npm run check:architecture" `
  --quick-sensor "npm run test:registration" `
  --out "Changing the authentication provider" `
  --reviewed-sensors
```

`prepare` initializes `.harness/` if needed, imports the required context, creates
the task and contract, starts a run, and writes an implementation brief in:

```text
.harness/runs/<TASK>/<RUN>/builder-brief.md
```

During implementation, use `check` for the fastest configured sensor tier:

```powershell
python $RUNVERO --repo $APP check TASK-001
```

When the change is ready for review, run the final verification:

```powershell
python $RUNVERO --repo $APP verify TASK-001
```

`verify` runs final sensors and the security scan, then creates review materials
under:

```text
.harness/runs/<TASK>/<RUN>/lean/
  verification.json
  review-request.json
  review-handoff.md
```

An independent reviewer copies `review-request.json` to `review.json`, fills in
the evidence, and records a decision. Critical changes also require a separate
`evaluation.json` from another independent session.

Finish the task after the required review files exist:

```powershell
python $RUNVERO --repo $APP finish TASK-001 `
  --review "$APP\.harness\runs\TASK-001\<RUN>\lean\review.json"
```

For critical changes:

```powershell
python $RUNVERO --repo $APP finish TASK-001 `
  --review "$APP\.harness\runs\TASK-001\<RUN>\lean\review.json" `
  --evaluation "$APP\.harness\runs\TASK-001\<RUN>\lean\evaluation.json"
```

`finish` validates freshness, review coverage, security evidence, PT-BR language
review applicability, and the existing completion gates. It records the result
and generates the task report. It does not merge, publish, or deploy.

## Core Workflow

```text
Goal, criteria, scope, project rules, reviewed sensors
        |
      prepare
        |
 Coding agent implements and runs quick checks
        |
      verify
        |
 Final sensors, secret scan, evidence snapshot
        |
 Independent review, plus evaluator for critical risk
        |
      finish
        |
 Local report and recorded task decision
```

The lean workflow is intentionally proportional. Ordinary tasks use one
independent final review. Sensitive paths and explicit `--risk critical` require
an additional independent evaluator. The path-based risk rules are conservative
hints; reviewers can still escalate based on the actual diff.

## Full CLI

The full protocol remains available through `bin/harness.py`:

```powershell
python .\bin\harness.py --help
python .\bin\harness.py compat manifest
python .\bin\harness.py compat skill-smoke
```

Use the full CLI when you need queues, checkpoints, resume plans, supervisor
loops, long-running task management, explicit replanning, GitHub PR helpers,
Telegram control, dashboards, artifact indexes, memory, or plugin registry
operations.

## Optional JEV Observer

JEV support is disabled by default and runs only in advisory shadow mode. It can
inspect failed sensor evidence after explicit project consent and suggest whether
the failure looks repetitive, environment-related, or under-evidenced. It never
approves work, changes task state, runs diagnostics, chooses models, or sends a
fix.

Preview the state before enabling remote observation:

```powershell
python -m harness_core.jev_observer --repo C:\path\to\your-app --task TASK-001 --action preview
```

Manual observation and status use the same module:

```powershell
python -m harness_core.jev_observer --repo C:\path\to\your-app --task TASK-001 --action observe
python -m harness_core.jev_observer --repo C:\path\to\your-app --task TASK-001 --action status
```

See [docs/JEV_OBSERVER.md](docs/JEV_OBSERVER.md) for consent, privacy, redaction,
timeouts, budgets, and worker setup.

## Repository Layout

```text
bin/runvero.py                  Lean prepare/check/verify/finish entry point
bin/harness.py                  Compatible full-protocol CLI
harness_core/lean.py            Lean workflow adapter over existing gates
harness_core/                   Tasks, contracts, sensors, policy, evidence, integrations
integrations/jev-worker/        Optional JEV Gateway worker
hub/                            Optional multi-project hub
skills/                         Agent workflow guidance
docs/                           Operating guides and design notes
tests/                          CLI, policy, integration, and regression tests
```

Application state is written to the target repository's `.harness/` directory.
Keep run evidence, logs, copied context, and credentials out of public commits
unless they have been reviewed for sharing.

## Development

Install development dependencies and run the local checks:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check bin/harness.py bin/runvero.py harness_core tests
python -m pytest tests/ --cov=harness --cov=harness_core --cov-report=term-missing
node --test integrations/jev-worker/worker.test.mjs
```

The JEV tests use simulated providers. They validate integration behavior and
failure handling, not model accuracy, latency, or productivity gains.

## Documentation

| Guide | Contents |
| --- | --- |
| [Lean workflow](docs/LEAN_WORKFLOW.md) | Prepare, check, verify, finish, escalation, and JEV triggers. |
| [Full protocol](docs/HARNESS_PROTOCOL.md) | Original task lifecycle and completion gates. |
| [v0.3 operating model](docs/V0_3_HARNESS.md) | Queue, supervisor, checkpoints, budgets, hub, memory, and optional surfaces. |
| [JEV observer](docs/JEV_OBSERVER.md) | Optional installation, consent, privacy, redaction, and limits. |
| [Speed loop](docs/SPEED_LOOP.md) | Sensor tiers and review flow in the full protocol. |
| [Telegram](docs/TELEGRAM.md) | Bot setup, authorized chats, inbox, bridge, and remote modes. |
| [Accompaniment UI](docs/HARNESS_ACOMPANHAMENTO_UI.md) | Dashboard and multi-project monitoring behavior. |
| [Contributing](CONTRIBUTING.md) | Local development practices and checks. |

## Trust Boundaries

Runvero validates local evidence and structured attestations. It is not an
agent-identity system, a secret-management system, or a containment boundary. A
user or agent with write access to `.harness/` can alter local records. Use fresh
independent review sessions, protect branches in GitHub, keep secrets in
environment variables, inspect sensor commands before reviewing them, and treat
redaction as a reduction of exposure rather than complete data-loss prevention.
