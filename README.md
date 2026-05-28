# Harness Schulx

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)
[![Zero runtime deps](https://img.shields.io/badge/runtime%20deps-zero-2E7D32)](#instalacao)
[![Tests](https://img.shields.io/badge/tests-pytest-0A66C2)](#desenvolvimento)

Harness Schulx is a local, deterministic runner for AI-assisted coding work.
It turns a loose prompt or issue into a small task with a contract, context
checks, reviewed sensors, isolated evaluator/reviewer handoffs, Telegram
monitoring, simple final summaries, and repeatable reports.

It is designed for long-running Codex workflows where you want speed without
losing evidence.

```text
Issue/Prompt
  -> Task
  -> Contract
  -> Run
  -> Quick sensors
  -> Implementation
  -> Full sensors
  -> Evaluator + Greptile-style reviewer in parallel
  -> Consolidation
  -> Plain-language report
```

## Why It Exists

AI coding sessions often fail in the same ways:

- the agent expands scope without noticing;
- tests are run late, or not at all;
- reviewers see too much chat history and inherit bias;
- final reports are too technical for a quick human read;
- long sessions are hard to monitor away from the terminal.

Harness Schulx puts a small protocol around the work:

- each task has a contract;
- important project context is ingested and checked by hash;
- sensors must be reviewed before execution;
- evaluator and reviewer receive isolated handoffs;
- P0/P1 findings stay in the same task through a fast fix loop;
- Telegram can mirror Codex and receive messages while a task runs.

## Installation

No runtime package dependencies are required. You only need Python 3.10+.

```powershell
git clone https://github.com/schulxf/harness-schulx.git
cd harness-schulx
python .\bin\harness.py --help
```

On Windows, you can also use the PowerShell wrapper:

```powershell
.\bin\harness.ps1 --help
```

For development tests:

```powershell
python -m pip install pytest
python -m pytest tests/
```

## Quick Start

Set the app repository you want Harness to manage:

```powershell
$HARNESS = "$PWD\bin\harness.py"
$APP_REPO = "C:\path\to\your-app"
```

Initialize Harness inside the app repo:

```powershell
python $HARNESS --repo $APP_REPO init
```

Import an issue:

```powershell
python $HARNESS --repo $APP_REPO task import "$APP_REPO\issues\001-login.md"
```

Create a contract with fast and final sensors:

```powershell
python $HARNESS --repo $APP_REPO contract TASK-001 `
  --criteria "usuario valido consegue autenticar" `
  --criteria "senha invalida mostra erro claro" `
  --smoke-sensor "npm test -- login" `
  --affected-sensor "npm run typecheck" `
  --full-sensor "npm test" `
  --full-sensor "npm run build" `
  --reviewed-sensors `
  --out "OAuth" `
  --out "recuperacao de senha"
```

Start a run:

```powershell
python $HARNESS --repo $APP_REPO start TASK-001
```

After implementation, run the fast loop:

```powershell
python $HARNESS --repo $APP_REPO quick-pass TASK-001 --reviewed
```

Before final approval, run the full loop:

```powershell
python $HARNESS --repo $APP_REPO full-pass TASK-001 --reviewed
```

Register the final decision and write the report:

```powershell
python $HARNESS --repo $APP_REPO evaluate TASK-001 --status pass --notes "Criterios atendidos e sensores passaram."
python $HARNESS --repo $APP_REPO report TASK-001
```

## Daily Flow

1. Create or import one task.
2. Create the contract before implementation.
3. Ingest required docs when the repo has project context or ADRs.
4. Start a run.
5. Implement only the contracted task.
6. Run quick sensors during the fix loop.
7. Run full sensors before approval.
8. Generate evaluator and reviewer handoffs.
9. Spawn the evaluator and Greptile-style reviewer in parallel.
10. Consolidate both answers.
11. Fix P0/P1 in the same task.
12. Register `pass`, `fail`, or `needs-work`.
13. Generate the report.

## Core Concepts

### Task

A small unit of work stored in:

```text
.harness/tasks/
```

Tasks can be created manually or imported from markdown issues.

```powershell
python $HARNESS --repo $APP_REPO task create "Login" --body "Criar login por email e senha"
python $HARNESS --repo $APP_REPO task import "$APP_REPO\issues\001-login.md"
```

### Contract

The contract is the binding agreement for the task:

```text
.harness/contracts/TASK-001.json
```

It stores:

- goal;
- acceptance criteria;
- expected files;
- required docs;
- sensor tiers;
- out-of-scope items.

### Run

A run is one execution attempt:

```text
.harness/runs/TASK-001/run-YYYYMMDDTHHMMSSZ/
```

It contains briefs, handoffs, sensor evidence, evaluations, fix briefs and
plain-language summaries.

### Sensors

Sensors are deterministic commands such as tests, type checks and builds. They
do not run unless the contract has reviewed sensors or you pass `--reviewed`.

Tiers:

```text
smoke     fastest targeted check
affected  checks related to the changed area
full      final test/build gate
all       all configured tiers
quick     first non-empty tier among smoke, affected, full
```

Examples:

```powershell
python $HARNESS --repo $APP_REPO sensors TASK-001 --tier quick --reviewed
python $HARNESS --repo $APP_REPO sensors TASK-001 --tier full --reviewed
```

### Evaluator

The evaluator checks whether the implementation satisfies the contract and
evidence. It should run as an isolated agent with no inherited chat context.

Generated file:

```text
evaluator-agent-handoff.md
```

### Greptile-Style Reviewer

The reviewer checks code risk: regressions, bugs, security issues and
inconsistencies. It starts with the changed surface and expands only when there
is concrete risk.

Generated file:

```text
greptile-reviewer-agent-handoff.md
```

### Parallel Dispatch

`evaluate TASK-001` also creates:

```text
parallel-dispatch.md
```

Use it to spawn the evaluator and reviewer at the same time. They do not depend
on each other, so this reduces wall-clock time.

### Fix Brief

If Greptile finds a blocking P0/P1, keep the fix inside the same task:

```powershell
python $HARNESS --repo $APP_REPO fix-brief TASK-001 --review-file reviewer-output.md
```

This writes:

```text
fix-brief-01.md
fix-brief-latest.md
```

Then fix only the blocker, run quick sensors, regenerate handoffs and finish
with full sensors.

### Plain Summary

At the end, Harness writes a non-technical explanation:

```text
plain-summary.md
```

It explains:

- what was done;
- why it was done;
- how it was checked;
- the result;
- what is pending.

The final report includes the same section.

## Context Preflight

Harness can ingest project documents and lock their hashes:

```powershell
python $HARNESS --repo $APP_REPO ingest "$APP_REPO\AGENTS.md" --kind context
python $HARNESS --repo $APP_REPO ingest "$APP_REPO\CONTEXT.md" --kind domain-context
python $HARNESS --repo $APP_REPO ingest "$APP_REPO\docs\adr\ADR-000-index.md" --kind adr
python $HARNESS --repo $APP_REPO preflight
```

If a required document changes after ingest, `start` blocks until the doc is
ingested again. Preflight results are cached when paths, sizes, mtimes and
manifest metadata remain the same.

## Telegram Integration

Harness can send notifications, receive prompts, mirror Codex sessions and act
as a Telegram-to-Codex bridge.

Create a Telegram bot with BotFather and set the token outside the repo:

```powershell
$env:HARNESS_TELEGRAM_BOT_TOKEN = "<telegram-bot-token>"
```

Configure chat access:

```powershell
python $HARNESS --repo $APP_REPO telegram configure `
  --enable `
  --chat-id "1832050069" `
  --allowed-chat-id "1832050069"
```

Send a test message:

```powershell
python $HARNESS --repo $APP_REPO telegram send "Harness conectado."
```

Receive Telegram messages:

```powershell
python $HARNESS --repo $APP_REPO telegram listen
```

Create tasks from Telegram:

```powershell
python $HARNESS --repo $APP_REPO telegram listen --create-tasks
```

Mirror a running Codex CLI session without interrupting it:

```powershell
python $HARNESS --repo $APP_REPO telegram mirror --include-tools
```

Run a combined mirror and inbox bridge:

```powershell
python $HARNESS --repo $APP_REPO telegram bridge --include-tools
```

By default, bridge messages are queued in:

```text
.harness/telegram/operator-messages.md
```

Use `/codex <message>` in Telegram when you intentionally want to call Codex in
parallel through `codex exec resume --last`.

Read the full guide in [docs/TELEGRAM.md](docs/TELEGRAM.md).

## Repository Layout

```text
bin/
  harness.py              Main CLI
  harness.ps1             Windows wrapper
docs/
  HARNESS_PROTOCOL.md     Full protocol details
  SPEED_LOOP.md           Fast-loop strategy
  TELEGRAM.md             Telegram setup and modes
examples/
  issue-login.md          Example issue
skills/
  harness-runner/         Codex skill copy
tests/
  test_cli_smoke.py
  test_pure.py
```

Generated state in app repositories:

```text
.harness/
  config.json
  tasks/
  contracts/
  runs/
  reports/
  telegram/
  inbox/telegram/
```

In this Harness repo itself, `.harness/` is ignored.

## Command Reference

```text
init                 Initialize .harness
ingest               Copy context docs into .harness/context
preflight            Validate required context
task create/import   Create or import tasks
contract             Create or update task contract
start                Start a run
sensors              Run deterministic sensors
quick-pass           Run quick sensors and generate parallel handoffs
full-pass            Run final sensors and generate parallel handoffs
evaluate             Generate handoffs or record final evaluation
fix-brief            Create a focused fix brief for P0/P1 findings
report               Write the final report
status               Show project state
telegram             Telegram integration commands
```

## Development

Run tests:

```powershell
python -m pytest tests/
```

Compile-check the CLI:

```powershell
python -m py_compile bin\harness.py
```

The project intentionally has no runtime dependencies. Tests use `pytest`.

## Security Notes

- Never commit Telegram bot tokens.
- Store `HARNESS_TELEGRAM_BOT_TOKEN` in the environment.
- Store `OPENAI_API_KEY` in the environment if optional media transcription is enabled.
- Do not use `--bypass` unless the environment is trusted.
- Version only the compact Harness protocol files in app repos.
- Keep `.harness/runs`, copied context, inbox media and logs local unless you explicitly need them.

## Status

Current version:

```text
0.2.0
```

Harness Schulx is an MVP, but the core protocol is already usable for real
local projects.
