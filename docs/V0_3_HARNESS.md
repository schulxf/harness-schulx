# Harness v0.3

This document defines the official v0.3-style Harness. It keeps the existing
local deterministic protocol, then adds a supervisor, queue, dashboard,
checkpoint/resume model, remote control and integration registry around it.

The goal is not to make the agent more autonomous by hiding evidence. The goal
is to make long-running AI coding work observable, resumable and governable.

## System Shape

```text
operator
  -> dashboard | telegram | cli
  -> supervisor
  -> task queue
  -> contract
  -> run
  -> checkpoints
  -> sensors
  -> evaluator + reviewer + security scanner
  -> report + artifact index + project memory
```

The CLI is still the source of deterministic operations. Dashboard, Telegram
and plugins are control surfaces around the same repo-local state.

## Local Dashboard

The dashboard is a local view over `.harness/`. It should not require cloud
state to show current work.

It should show:

- queue status and active task;
- contract summary and out-of-scope items;
- active run and last checkpoint;
- sensor tiers and latest result;
- evaluator, reviewer and security findings;
- budget/profile use;
- artifacts, reports, screenshots, logs and media;
- Telegram inbox/operator messages;
- GitHub issue or PR links when configured.

Dashboard actions must still respect the same policy gates as CLI actions.

## Pixel-Art Hub

The hub is the multi-repo dashboard mode. It uses the same local evidence as the
normal dashboard, but renders it as a top-down operations map:

- each watched repo is a room;
- queue/build/review/security/report are visible as room phases;
- agents are pixel characters with speech bubbles, idle walking and working
  animation;
- real agents can register in `.harness/agents/registry.json`; synthetic agents
  are only a fallback when no registry entry exists;
- the central core summarizes all monitored repos;
- clicking a room opens task, queue, checkpoint, run and security details;
- clicking an agent opens the task/state summary for that agent;
- the inspection panel shows recent `.harness/events.jsonl` timeline entries;
- when wmux is running, `hub-serve` can list/focus wmux terminals, open a
  terminal for the selected repo, send text to the active terminal and read
  screen text when the wmux renderer supports it.

Commands:

```powershell
python <harness.py> --repo C:\control-repo dashboard hub `
  --watch-repo C:\repo-a `
  --watch-repo C:\repo-b

python <harness.py> --repo C:\control-repo dashboard hub-serve `
  --watch-repo C:\repo-a `
  --watch-repo C:\repo-b `
  --port 8899

python <harness.py> --repo C:\control-repo dashboard hub-add-repo C:\repo-a C:\repo-b
python <harness.py> --repo C:\control-repo dashboard hub-hide-repo C:\repo-b
python <harness.py> --repo C:\control-repo dashboard hub-show-repo C:\repo-b
python <harness.py> --repo C:\control-repo dashboard hub-remove-repo C:\repo-b
python <harness.py> --repo C:\control-repo dashboard hub-list-repos
python <harness.py> --repo C:\repo-a agent register builder-1 --role builder --task-id TASK-001
python <harness.py> --repo C:\repo-a events list --limit 20
```

The control repo is where the hub HTML is written. Watched repos are read-only
inputs. `hub-serve` refreshes `hub-state.json` on demand, so the browser can
poll without a database, websocket server or external service.

The wmux bridge is local-only. It reads `WMUX_PIPE`/`WMUX_SURFACE_ID` from the
environment and talks to the wmux named pipe directly, avoiding the slower CLI
timeout path for live polling. Mutating wmux actions require the local
`hub-serve` action token and are logged back to `.harness/events.jsonl`.

## Event Stream And Agents

Every task, queue, run, sensor, review, report, Telegram and hub-control action
should append a small JSON object to:

```text
.harness/events.jsonl
```

That file is the shared operational feed for CLI status, the pixel hub and
Telegram. Long-running agents can also update:

```text
.harness/agents/registry.json
```

The registry stores `agent_id`, role, state, task, wmux surface, speech bubble
text and heartbeat. The hub reads it first; inferred/synthetic agents are only a
fallback for older repos.

## Task Queue

The queue stores planned, ready, active, blocked and completed tasks:

```text
.harness/queue/
```

Recommended states:

```text
planned
ready
active
blocked
needs_work
passed
failed
archived
```

Rules:

- one active implementation task per repo;
- ready tasks must have enough context to form a contract;
- blocked tasks must name the blocker and next required human decision;
- queue order is advisory unless the supervisor is in automatic mode.
- a linked queue item can become `done` only after its task is already `passed`.

## Supervisor

The supervisor is the control loop. It does not replace the implementer; it
keeps the run inside policy.

Responsibilities:

- select the next eligible queue item;
- create or validate contracts before work starts;
- run preflight before `start`;
- enforce branch and sensor review policy;
- preserve a unique run id and the initial Git commit as evaluation baseline;
- write checkpoints after meaningful transitions;
- stop or pause when budgets are exhausted;
- launch evaluator, reviewer and security checks;
- convert non-blocking findings into follow-ups;
- update dashboard and Telegram status.

The supervisor should never mark success without final evidence.

## Resume And Checkpoints

Every long run should be resumable from repo-local files, not from chat memory.

Checkpoint contents:

- task id and run id;
- current state;
- profile and budget use;
- latest changed-file list;
- latest sensor result;
- latest evaluator/reviewer/security status;
- blockers and decisions;
- next recommended action.

Checkpoints live under:

```text
.harness/runs/<TASK>/<RUN>/checkpoints/
```

Resume loads:

1. task contract;
2. latest checkpoint;
3. required project memory;
4. latest sensor and review evidence;
5. queued operator messages.

## GitHub Issues And PR Helpers

GitHub helpers are optional. Harness remains local-first when GitHub is absent.

Expected helpers:

- import issue title/body/labels into a Harness task;
- record upstream issue URL and id;
- suggest branch names from task ids;
- generate PR body from contract, files changed, sensors and report;
- attach evaluator/reviewer/security summaries;
- create follow-up issues for accepted non-blockers;
- sync final report back to the issue or PR when configured.

Do not let GitHub labels override the local contract. They are input context,
not approval evidence.

## Budgets And Profiles

Profiles express how much work a task is allowed to consume before the operator
must re-evaluate scope.

Recommended profiles:

```text
fast
  small fix, one quick sensor tier, minimal reviewer scope

standard
  normal vertical slice, quick + full sensors, evaluator + reviewer

deep
  risky or broad change, required docs, full sensors, evaluator, reviewer,
  security scanner and richer artifact capture
```

Budget dimensions:

- elapsed time;
- token budget;
- command count;
- external reviewer/evaluator count;
- network/plugin calls;
- artifact size.

Budget exhaustion moves the task to `needs_work` unless a stricter failure
policy says to fail.

## Artifact Viewer

The artifact viewer indexes evidence without forcing it into git.

Typical artifacts:

- builder briefs;
- evaluator and reviewer handoffs;
- parallel dispatch;
- sensor JSON and logs;
- screenshots and rendered documents;
- Telegram media;
- security scan reports;
- plain summaries and final reports.

The artifact index should store path, kind, task id, run id, created time,
source command and whether the artifact is safe to share.

## Failure Policy

The policy must be explicit and boring.

Blocking by default:

- stale required context;
- unreviewed sensors;
- failed full sensors before pass;
- evaluator `FAIL`;
- reviewer P0;
- reviewer P1 in changed surface;
- critical security finding;
- missing or failed PT-BR spelling and clarity review;
- missing reviewer evidence;
- elapsed-time or fix-attempt budget exhausted;
- missing final evidence.

Usually non-blocking:

- reviewer P2;
- cosmetic follow-up outside changed surface;
- budget warning before hard limit;
- optional plugin failure when core evidence is complete.

Non-blockers should become follow-up tasks or PR notes. They should not silently
disappear.

## Project Memory

Project memory is durable evidence and decisions. It is not the full chat log.

Recommended sources:

- `AGENTS.md`, `CONTEXT.md`, ADRs and testing docs;
- task contracts;
- final reports;
- plain summaries;
- repeated failure notes;
- accepted security exceptions;
- release decisions.

Memory entries should include source path, hash, date and reason. When source
docs change, preflight should force re-ingest before the next run.

## Plugin Registry

The registry describes optional integrations:

```text
.harness/plugins/registry.json
```

Each plugin should declare:

- name and version;
- commands or capabilities;
- files it may read/write;
- secrets it requires;
- network access;
- whether it can affect pass/fail decisions;
- owner and update source.

Examples: GitHub, Telegram, security scanner, browser automation, artifact
renderer, CI bridge, mobile test runner.

## Security Scanner

The built-in scanner runs before final approval in every default profile. It
scans common secret and credential patterns in tracked text files and can
include untracked files explicitly.

Optional scanner integrations may add broader checks:

- secrets in changed files and reports;
- `.env`, token, key and credential patterns;
- unsafe shell execution or bypass flags;
- writes outside repo boundaries;
- unexpected network or dependency changes;
- artifacts that should not be shared;
- Telegram/plugin permission drift.

Critical findings block. Medium findings should either be fixed or explicitly
accepted with a note in the report.

## Telegram Remote Control

Telegram is a remote-control surface, not just notifications.

Supported operator intents:

- check status;
- list and pick queue items;
- see active task, budget and checkpoint;
- request latest report or artifact summary;
- send an operator message into the run;
- explicitly call Codex with `/codex`;
- pause, resume or mark blocked when the supervisor supports it.

Default bridge mode should queue normal messages instead of interrupting an
active Codex turn. `/codex` is the explicit escape hatch for active remote
commands.

## Versioned State

Recommended to version:

```text
.harness/config.json
.harness/progress.md
.harness/tasks/**
.harness/contracts/**
.harness/reports/**
```

Keep local by default:

```text
.harness/runs/**
.harness/context/**
.harness/inbox/**
.harness/telegram/**
.harness/plugins/secrets/**
large artifacts and logs
```

## Definition Of Done

A v0.3 task is done when:

1. the contract exists and matches the task;
2. required context preflight passed;
3. the latest run has checkpoints and evidence;
4. final sensors passed;
5. the exact sensor plan has a recorded review digest;
6. PT-BR spelling, accentuation and clarity were reviewed;
7. evaluator accepted with a short decision note;
8. reviewer evidence exists and has no blocking finding;
9. the current run's security scanner has no finding;
10. hard run budgets are within their limits;
11. report and plain summary exist;
12. follow-ups were created for accepted non-blockers;
13. dashboard/queue state matches the final decision.
