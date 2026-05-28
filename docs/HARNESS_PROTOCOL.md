# Harness Protocol

This document describes the operational loop used by Harness Schulx.

## State Machine

```text
planned
  -> contracted
  -> in_progress
  -> sensors_passed | sensors_failed
  -> needs_work | failed | passed
```

`passed` should only be used after:

1. the contract exists;
2. context preflight passes;
3. final sensors pass;
4. evaluator accepts the contract;
5. Greptile-style reviewer has no blocking P0/P1;
6. final notes are recorded.

## One Task At A Time

Harness is optimized for small vertical slices. Each task should be narrow
enough that acceptance criteria, sensors and review comments all refer to the
same behavioral surface.

Avoid combining unrelated work in one task. If a reviewer finds unrelated
cleanup, record it as follow-up instead of expanding the current scope.

## Contracts

Contracts live in:

```text
.harness/contracts/<TASK_ID>.json
```

They should include:

- goal;
- acceptance criteria;
- expected file areas;
- required context docs;
- sensor tiers;
- explicit out-of-scope items.

The contract is binding for the evaluator. A reviewer may find code risks, but
the evaluator decides whether the contract was satisfied.

## Context Preflight

Context docs are copied into `.harness/context/` and recorded in a manifest with
size, mtime and SHA-256 metadata.

`start` runs preflight by default. If required context is missing, stale or
changed, the run is blocked.

## Sensors

Sensors are deterministic commands. They are blocked unless reviewed.

Recommended tiers:

```text
smoke     small test for the changed behavior
affected  typecheck or tests around the changed area
full      build and full test gate
```

The implementation loop should use `quick`. Final approval should use `full`.

## Parallel Review

After sensors pass, `evaluate TASK-001` generates:

```text
evaluator-brief.md
evaluator-agent-handoff.md
greptile-reviewer-agent-handoff.md
review-consolidation.md
parallel-dispatch.md
```

Spawn evaluator and reviewer at the same time. They do not depend on each other.

## Consolidation Rules

- Evaluator `FAIL` blocks.
- Reviewer P0 blocks.
- Reviewer P1 in the changed surface blocks.
- Reviewer P2 does not block by default.
- P2 should become follow-up unless there is evidence to promote severity.

## Fix Loop

Blocking P0/P1 findings are fixed in the same task:

```text
reviewer P0/P1
  -> fix-brief
  -> minimal fix
  -> quick sensors
  -> evaluate again
  -> full sensors before pass
```

Do not create a new task for a P0 introduced by the current task. New tasks are
for follow-ups, unrelated risks or non-blocking improvements.

## Final Report

`report TASK-001` writes:

```text
.harness/reports/TASK-001.md
```

It includes technical evidence and a plain-language summary.
