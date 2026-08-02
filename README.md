# Harness Schulx

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/)
[![Zero runtime deps](https://img.shields.io/badge/runtime%20deps-zero-2E7D32)](#instalacao)
[![Tests](https://img.shields.io/badge/tests-pytest-0A66C2)](#desenvolvimento)

Harness Schulx is a local, deterministic runner for AI-assisted coding work.
It turns a loose prompt, queue item or GitHub issue into a small task with a
contract, context checks, reviewed sensors, checkpoints, isolated
evaluator/reviewer handoffs, Telegram remote control, local dashboard visibility
and repeatable reports.

It is designed for long-running Codex workflows where you want speed without
losing evidence.

```text
Issue/Prompt
  -> Task
  -> Queue
  -> Contract
  -> Run
  -> Checkpoints
  -> Quick sensors
  -> Implementation
  -> Full sensors
  -> Security scan
  -> PT-BR text review
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
- queued tasks are visible before an agent starts work;
- important project context is ingested and checked by hash;
- sensors must be reviewed before execution;
- checkpoints make long runs resumable;
- evaluator and reviewer receive isolated handoffs;
- P0/P1 findings stay in the same task through a fast fix loop;
- Telegram can mirror Codex, send commands and receive messages while a task
  runs.

## v0.3 Operating Model

v0.3 is the official Harness shape: local-first, evidence-first, and
supervisor-driven. The CLI remains usable by hand, but the preferred workflow is
to operate from a local dashboard or task queue, let a supervisor enforce the
failure policy, and use Telegram as a remote-control surface when away from the
terminal.

Core v0.3 surfaces:

- local dashboard for queue, active run, sensors, checkpoints and artifacts;
- multi-project accompaniment hub for understanding current work, progress and attention points at a glance;
- task queue with one active implementation task per repo;
- supervisor that starts runs, watches budgets, records checkpoints and blocks
  unsafe transitions;
- resume/checkpoints for long Codex sessions and interrupted work;
- GitHub Issues/PR helpers for import, branch naming, PR summary and review
  handoff evidence;
- budgets/profiles for fast, standard and deep runs;
- artifact viewer for reports, logs, screenshots, media and handoffs;
- failure policy for sensor failure, stale context, budget exhaustion and
  blocking reviewer findings;
- project memory from required docs, ADRs, summaries and prior Harness reports;
- plugin registry for optional integrations and repo-local tools;
- security scanner for secrets, risky shell use and unsafe generated outputs;
- Telegram as remote control for status, queue actions, reports and Codex
  messages.

Read the full v0.3 model in [docs/V0_3_HARNESS.md](docs/V0_3_HARNESS.md).

## Installation

No runtime package dependencies are required. You only need Python 3.10+.

```powershell
git clone https://github.com/schulxf/harness-schulx.git
cd harness-schulx
python .\bin\harness.py --help
```

To install the `harness-schulx` command in a virtual environment:

```powershell
python -m pip install -e .
harness-schulx --help
```

On Windows, you can also use the PowerShell wrapper:

```powershell
.\bin\harness.ps1 --help
```

For development tests:

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff check bin/harness.py harness_core tests
python -m pytest tests/ --cov=harness --cov=harness_core --cov-report=term-missing
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

Record the security and PT-BR checks, then register the independent decisions:

```powershell
python $HARNESS --repo $APP_REPO security scan --task-id TASK-001 --fail-on-findings
python $HARNESS --repo $APP_REPO ptbr-review TASK-001 --status pass `
  --reviewer "nome do revisor" `
  --notes "Ortografia, acentuação e clareza conferidas."
python $HARNESS --repo $APP_REPO evaluate TASK-001 --status pass `
  --evaluator "agente avaliador" `
  --notes "Critérios atendidos e sensores passaram." `
  --reviewer "agente reviewer" `
  --review-file ".harness\runs\TASK-001\RUN\reviewer-output.md"
python $HARNESS --repo $APP_REPO report TASK-001
```

## Daily Flow

1. Create or import one task.
2. Put it in the queue with a profile and budget.
3. Create the contract before implementation.
4. Ingest required docs when the repo has project context or ADRs.
5. Start a run through the supervisor.
6. Implement only the contracted task.
7. Save checkpoints after meaningful progress.
8. Run quick sensors during the fix loop.
9. Run full sensors before approval.
10. Run the security scan for the current run.
11. Review spelling, accentuation and clarity of all PT-BR text.
12. Generate evaluator and reviewer handoffs.
13. Spawn the evaluator and Greptile-style reviewer in parallel.
14. Consolidate both answers and record the reviewer output.
15. Fix P0/P1 in the same task.
16. Register `pass`, `fail`, or `needs-work`.
17. Generate the report and artifact index.

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

### Queue

The task queue records work that is ready, blocked, active or complete. The
queue is intentionally local so a repo can be operated offline:

```text
.harness/queue/
```

Only one implementation task should be active per repo. Other queued tasks may
be planned, contracted or waiting for GitHub sync.

### Supervisor

The supervisor is the policy layer around the runner. It is responsible for:

- starting the next eligible task;
- refusing stale context or unreviewed sensors;
- saving checkpoints;
- enforcing budgets and profiles;
- applying the failure policy;
- exposing status to the dashboard and Telegram.

### Checkpoints And Resume

Long runs should write checkpoints whenever the task state changes:

```text
.harness/runs/<TASK>/<RUN>/checkpoints/
```

A checkpoint should capture current status, changed files, latest sensor
evidence, active blockers, budget use and next action. Resume always starts
from the latest checkpoint plus the task contract.

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

### Artifact Viewer

The dashboard artifact viewer indexes files produced by the run:

```text
builder-brief.md
evaluator-agent-handoff.md
greptile-reviewer-agent-handoff.md
parallel-dispatch.md
sensors.json
plain-summary.md
report.md
screenshots/
logs/
media/
```

Large artifacts remain local by default. Reports may link to them without
copying them into git.

### Multi-Project Accompaniment Hub

The hub is a calm, non-technical view of work happening across local Harness
projects. Each project card explains the current implementation, the active
task, its factual position in the plan, what is happening now and whether human
attention is needed. Open a card to follow the full task journey, completed
results and recent updates without exposing commands, logs or file details.

Register repos once:

```powershell
python $HARNESS --repo $APP_REPO dashboard hub-add-repo "C:\repo-a" "C:\repo-b"
python $HARNESS --repo $APP_REPO dashboard hub-hide-repo "C:\repo-b"
python $HARNESS --repo $APP_REPO dashboard hub-show-repo "C:\repo-b"
python $HARNESS --repo $APP_REPO dashboard hub-remove-repo "C:\repo-b"
python $HARNESS --repo $APP_REPO dashboard hub-list-repos
```

When an implementation starts, Harness also registers the target repository in
the central accompaniment panel automatically. Set `HARNESS_HUB_CONTROL_REPO`
to the panel's control repository; on Windows the local installation is
discovered at `%LOCALAPPDATA%\HarnessAcompanhamento\control`. Automatic
registration never duplicates a path and never makes a deliberately hidden
project visible again. Set `HARNESS_HUB_CONTROL_REPO=disabled` in isolated
automation that must not update the local panel.

Generate a static hub:

```powershell
python $HARNESS --repo $APP_REPO dashboard hub `
  --watch-repo "C:\repo-a" `
  --watch-repo "C:\repo-b"
```

Serve it with live polling:

```powershell
python $HARNESS --repo $APP_REPO dashboard hub-serve `
  --watch-repo "C:\repo-a" `
  --watch-repo "C:\repo-b" `
  --port 8899
```

Open:

```text
http://127.0.0.1:8899/
```

`hub-serve` recalculates `hub-state.json` from each repo's `.harness/` whenever
the browser polls it. The selected project remains open while the interface
updates task progress, review states and attention messages.

Harness actions also write a shared event stream:

```text
.harness/events.jsonl
.harness/agents/registry.json
```

The hub uses that stream for the clickable timeline and uses the registry to
show real agents when they register themselves:

```powershell
python $HARNESS --repo $APP_REPO agent register builder-1 `
  --role builder `
  --task-id TASK-001 `
  --speech "Working on the failing test."

python $HARNESS --repo $APP_REPO agent heartbeat builder-1 `
  --speech "Tests are green; preparing review."
```

If wmux is running, `hub-serve` also exposes a local wmux bridge:

- list visible wmux panes, terminal surfaces and wmux agents;
- focus an existing wmux terminal from the hub;
- open a new wmux terminal for the selected repo;
- send a short command or message to the active terminal;
- read the active terminal screen when the installed wmux renderer supports
  screen serialization.

The bridge uses the local wmux named pipe (`WMUX_PIPE`), binds actions to the
local server token and logs every hub terminal action into `.harness/events.jsonl`.

### Budgets And Profiles

Profiles define how much evidence and review depth a task needs:

```text
fast      small fix, quick sensors, tight budget
standard  normal feature slice, quick + full sensors
deep      risky change, extra docs, evaluator + reviewer + security scan
```

The CLI snapshots the selected profile and budget when a run starts. Elapsed
time and fix-attempt limits are hard completion gates: exceeding either blocks
`pass` until the run is explicitly replanned. Token and command usage can still
be recorded by integrations, but are not inferred by the core CLI.

### Project Memory

Project memory is not chat history. It is the durable repo-local context that
future agents may trust:

```text
.harness/memory/
```

Recommended inputs:

- required context docs and ADRs;
- task contracts;
- final reports;
- plain summaries;
- repeated failure notes;
- security and release decisions.

### GitHub Helpers

v0.3 treats GitHub as an external source of truth, not as required runtime
state. Helpers may:

- import GitHub Issues as Harness tasks;
- map task ids to branches and PRs;
- gerar uma descrição curta de PR a partir do resumo simples e das evidências finais;
- criar um comentário público simples no PR com conteúdo sanitizado e em linguagem direta;
- create follow-up issues for non-blocking P2 findings.

This repository also includes a PR template and an automation that validates a
short, plain-language summary, requires the PT-BR review checkbox and creates or
updates one simple comment on every new PR. The automation reads only the event
and the workflow from the default branch; it never checks out or executes code
from the PR.

`harness github pr-create TASK-001` usa a mesma política final de
`evaluate --status pass`: sensores finais, verificação de segurança da run, revisão PT-BR,
task/avaliação em `pass`, evidência atual do reviewer sem P0/P1 bloqueante e
nenhum `failure-decision` bloqueante. Ele grava
`.harness/github/TASK-001-pr-body.md` e
`.harness/github/TASK-001-pr-comment.md`, cria o PR com
`gh pr create --body-file`. Quando o repositório já tem a automação de
comentários do Harness, ela publica o resumo; nos demais casos, o CLI usa
`gh pr comment --body-file`, sem criar comentários duplicados.

### Plugin Registry

The plugin registry records optional integrations available to a repo:

```text
.harness/plugins/registry.json
```

Examples: GitHub, Telegram, security scanners, browser automation, artifact
renderers, mobile test runners and cloud CI bridges. A plugin must declare what
commands it can run, what files it writes and whether it can access secrets.

### Security Scanner

The built-in security scanner is a gate before final approval. It checks:

- common secret and credential patterns in tracked text files;
- untracked text files too when `--include-untracked` or `--task-id` is used;
- the exact scan result tied to the current run when `--task-id` is provided.

Any finding in the run-local report blocks final approval. Use
`--fail-on-findings` when the scan itself must return a failing exit code, such
as in CI.

Optional scanner plugins can cover the broader checks already described by the
protocol:

- secrets in changed files and artifacts;
- unsafe shell commands;
- generated files outside the repo;
- token or credential leakage into reports;
- suspicious dependency or network changes;
- Telegram and plugin permissions.

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

Harness can send notifications, receive prompts, mirror Codex sessions, control
the queue and act as a Telegram-to-Codex bridge.

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

Telegram saves inbound messages only from configured chats. Remote Codex
execution is disabled by default; enable it separately only for trusted chats:

```powershell
python $HARNESS --repo $APP_REPO telegram configure `
  --allow-remote-execution `
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

`telegram bridge` also forwards new Harness events from `.harness/events.jsonl`
unless you pass `--no-harness-events`. This keeps Telegram, the hub and CLI
status aligned on the same event stream.

By default, bridge messages are queued in:

```text
.harness/telegram/operator-messages.md
```

Use `/codex <message>` in Telegram when you intentionally want to call Codex in
parallel through `codex exec resume --last`. This requires
`allow_remote_execution=true` and an authorized chat.

Read the full guide in [docs/TELEGRAM.md](docs/TELEGRAM.md).

## Skill Compatibility

`bin/harness.py` is the stable entrypoint used by the Harness Runner skill. The
refactor is allowed to move implementation code, but not to remove that public
surface.

This repository also bundles the upstream Graph Engineering skill. It supplies
knowledge-graph, GraphRAG and agent task-graph guidance while Harness remains
responsible for execution state and approval gates. It is an agent skill, not an
executable plugin.

From this checkout, install or refresh the bundled skills in Codex with:

```powershell
$CODEX_SKILLS = Join-Path $env:USERPROFILE ".codex\skills"
$GRAPH_SKILL = Join-Path $CODEX_SKILLS "graph-engineering"
New-Item -ItemType Directory -Force $GRAPH_SKILL | Out-Null
Copy-Item -Recurse -Force ".\skills\graph-engineering\*" $GRAPH_SKILL
```

Invoke `$graph-engineering` only for graph-shaped work. The Harness-specific
boundary and artifact contract lives in
[`references/harness-integration.md`](skills/graph-engineering/references/harness-integration.md).
The original material is from
[`codejunkie99/graph-engineering`](https://github.com/codejunkie99/graph-engineering)
and remains under its MIT License.

Check the protected command surface:

```powershell
python $HARNESS compat manifest
```

Run a local safety smoke that creates a fake repo and exercises the main skill
flow through `bin/harness.py`:

```powershell
python $HARNESS compat skill-smoke
```

## Repository Layout

```text
bin/
  harness.py              Main CLI
  harness.ps1             Windows wrapper
docs/
  HARNESS_PROTOCOL.md     Full protocol details
  SPEED_LOOP.md           Fast-loop strategy
  TELEGRAM.md             Telegram setup and modes
  V0_3_HARNESS.md         v0.3 operating model
examples/
  issue-login.md          Example issue
skills/
  graph-engineering/      Vendored graph and GraphRAG specialist skill
  harness-runner/         Harness operational skill
tests/
  test_cli_smoke.py
  test_pure.py
```

Generated state in app repositories:

```text
.harness/
  config.json
  queue/
  tasks/
  contracts/
  runs/
  reports/
  memory/
  plugins/
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
security scan        Scan secrets and optionally bind evidence to a run
ptbr-review          Record spelling, accentuation and clarity review
quick-pass           Run quick sensors and generate parallel handoffs
full-pass            Run final sensors and generate parallel handoffs
evaluate             Generate handoffs or record final evaluation
fix-brief            Create a focused fix brief for P0/P1 findings
report               Write the final report
status               Show project state
telegram             Telegram integration commands
```

v0.3 command families also include dashboard, multi-project hub, queue, supervisor,
checkpoint, resume, github, profile, artifacts, memory, plugin and security
operations. Some installations expose these through plugins while the core CLI
remains local and deterministic.

## Development

Run tests:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests/ --cov=harness --cov=harness_core --cov-report=term-missing
```

Run static analysis and compile checks:

```powershell
python -m ruff check .
python -m compileall -q bin .github\scripts tests
```

The project intentionally has no runtime dependencies. Development checks use
`pytest`, `pytest-cov` and `ruff`.

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
0.3.0
```

Harness Schulx is a local-first Harness. The v0.3 protocol is the official
target for real local projects and supervised AI coding runs.
