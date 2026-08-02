# Harness Schulx Integration

Use this reference only when Harness Schulx controls the repository workflow.

## Boundary

- Graph Engineering defines the knowledge model, extraction/fusion pipeline, retrieval design,
  or agent task topology.
- Harness owns task intake, contracts, queue state, runs, checkpoints, budgets, sensors,
  security scans, independent evaluation, code review, and the final report.
- Keep the Harness queue and run artifacts as the operational source of truth. A diagram is a
  plan, not runtime state.
- Do not register this skill as a Harness plugin. It has no executable command; it is an agent
  capability used within a Harness task.

## Knowledge-Graph Work

Start with the skill's scope-and-value test. If a table, normal search, or vector retrieval is
enough, record that decision in the task evidence and stop the graph pipeline.

When a graph is justified, make the Harness contract name the observable outputs. A useful
contract normally covers:

- competency questions the graph must answer;
- a versioned ontology or schema;
- provenance on every extracted fact;
- a small end-to-end pilot before bulk ingestion;
- sampled precision and explicit rejection rules;
- reversible entity-fusion decisions;
- a retrieval evaluation against a simpler baseline.

Prefer narrow vertical tasks over one large nine-stage task. A practical sequence is:

1. scope, representation, and ontology;
2. pilot extraction, quality gate, and fusion;
3. GraphRAG serving and comparative evaluation.

Suggested durable artifacts are `docs/graph/competency-questions.md`,
`docs/graph/ontology.yaml`, `docs/graph/provenance.md`, and
`docs/graph/evaluation.md`. Adapt names to repository conventions and list them in the task
contract.

Use deterministic Harness sensors where possible: schema validation, extraction fixtures,
domain/range checks, duplicate-resolution cases, retrieval evaluation, tests, type checks, and
builds. Semantic review supplements these checks; it does not replace them.

## Agent Task Graphs

Draw an edge only when the downstream node consumes the upstream result. Parallelize only
independent nodes, and give mutating nodes disjoint file ownership. Each node must have a bounded
input, an owned output artifact, and an explicit stop condition.

Map the graph into Harness execution as follows:

```text
graph plan
  -> bounded agent handoffs or queued tasks
  -> separate verifier contexts
  -> one coordinator-owned merge
  -> Harness sensors and approval gates
```

Harness v0.3 permits parallel evaluator and reviewer lanes, but keeps one active implementation
task per repository. Do not claim arbitrary DAG execution; keep sequential implementation state
in the Harness queue unless a future runtime explicitly supports more.

Place human approval immediately before irreversible actions such as deploy, publish, send,
delete, or external writes. Normal local, reversible work continues through Harness without an
extra gate.

## Completion

Graph-specific evaluation becomes evidence inside the normal Harness flow. It never bypasses
final sensors, security scanning, independent evaluator/reviewer handoffs, budget checks, or the
final report.
