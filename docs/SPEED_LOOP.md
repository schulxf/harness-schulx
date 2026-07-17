# Speed Loop

Harness Schulx reduces wall-clock time without removing evidence.

## Main Ideas

1. Run evaluator and Greptile-style reviewer in parallel.
2. Use sensor tiers instead of always running the full suite.
3. Keep P0/P1 fixes inside the same task.
4. Ask Greptile to start from the changed surface.
5. Cache context preflight results when nothing changed.
6. Resume from checkpoints instead of reconstructing state from chat.
7. Use `fast`, `standard` and `deep` profiles so small tasks do not pay the
   cost of large tasks.

## Sensor Tiers

Configure tiers in the contract:

```powershell
python $HARNESS --repo $APP_REPO contract TASK-001 `
  --criteria "login funciona" `
  --smoke-sensor "npm test -- login" `
  --affected-sensor "npm run typecheck" `
  --full-sensor "npm test" `
  --full-sensor "npm run build" `
  --reviewed-sensors
```

Run the fastest available tier:

```powershell
python $HARNESS --repo $APP_REPO sensors TASK-001 --tier quick --reviewed
```

Run final sensors before approval:

```powershell
python $HARNESS --repo $APP_REPO sensors TASK-001 --tier full --reviewed
```

## Quick Pass

`quick-pass` runs quick sensors and then generates evaluator/reviewer handoffs:

```powershell
python $HARNESS --repo $APP_REPO quick-pass TASK-001 --reviewed
```

Use it while the task is still being shaped.

## Full Pass

`full-pass` runs final sensors and then generates evaluator/reviewer handoffs:

```powershell
python $HARNESS --repo $APP_REPO full-pass TASK-001 --reviewed
```

Use it before final consolidation. It does not skip the run-local security scan,
PT-BR review or reviewer evidence required by the completion gate.

## Parallel Dispatch

After `evaluate`, open:

```text
.harness/runs/<TASK>/<RUN>/parallel-dispatch.md
```

Spawn both agents at the same time:

```text
evaluator-agent-handoff.md
greptile-reviewer-agent-handoff.md
```

Do not wait for one to finish before starting the other.

## Fix Brief

When Greptile reports P0/P1:

```powershell
python $HARNESS --repo $APP_REPO fix-brief TASK-001 --review-file reviewer-output.md
```

Then:

```text
minimal fix
quick sensors
evaluate again
full sensors
final pass
```

This keeps the loop fast and avoids turning one task into a new planning cycle.

## v0.3 Fast Path

Recommended fast path for a small issue:

```text
queue ready
standard or fast profile
contract
start through supervisor
checkpoint after first useful diff
quick sensors
parallel evaluator/reviewer handoffs
full sensors
security scan tied to the run
PT-BR spelling and clarity review
record evaluator and reviewer decisions
report
```

If the task is interrupted, resume from the latest checkpoint and run the
smallest useful sensor tier before continuing.

## Budgets

Budgets keep speed honest. A budget warning should trigger a checkpoint and a
short decision: continue, narrow scope, or mark `needs_work`. Do not convert
budget exhaustion into a silent pass.
