"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { buildProjectPresentation, unavailablePresentation } = require("./presentation");

function makeRepo() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-presentation-"));
  fs.mkdirSync(path.join(root, ".harness", "tasks"), { recursive: true });
  fs.mkdirSync(path.join(root, ".harness", "contracts"), { recursive: true });
  return root;
}

function makeTask(root, number, title, status) {
  const taskId = `TASK-${String(number).padStart(3, "0")}`;
  const relative = path.join(".harness", "tasks", `${taskId}.md`);
  fs.writeFileSync(
    path.join(root, relative),
    `# ${taskId} - ${title}\n\n## O que construir\n\nEntregar ${title.toLowerCase()} para as pessoas usuárias.\n`,
    "utf8"
  );
  return {
    task_id: taskId,
    title,
    status,
    task_file: relative,
    updated_at: `2026-07-17T14:${String(number).padStart(2, "0")}:00Z`,
  };
}

test("buildProjectPresentation creates the non-technical task journey", () => {
  const root = makeRepo();
  const tasks = [
    makeTask(root, 1, "Organizar o pedido", "done"),
    makeTask(root, 2, "Adicionar cupom de desconto", "in_progress"),
    makeTask(root, 3, "Conferir o novo valor", "planned"),
  ];
  fs.writeFileSync(
    path.join(root, ".harness", "contracts", "TASK-002.json"),
    JSON.stringify({
      goal: "permitir que clientes utilizem descontos antes da compra",
      acceptance_criteria: ["O novo valor aparece antes da confirmação"],
    }),
    "utf8"
  );
  const queue = [
    { task_id: "TASK-001", status: "done" },
    { task_id: "TASK-002", status: "active" },
    { task_id: "TASK-003", status: "queued" },
  ];

  const result = buildProjectPresentation(
    root,
    { hub: { implementation_name: "Novo processo de pagamento" } },
    tasks,
    queue,
    [{ type: "run_started", ts: "2026-07-17T14:03:00Z", payload: {} }],
    {}
  );

  assert.equal(result.status, "andamento");
  assert.equal(result.implementation, "Novo processo de pagamento");
  assert.equal(result.current.number, 2);
  assert.equal(result.current.total, 3);
  assert.match(result.current.why, /clientes utilizem descontos/);
  assert.deepEqual(result.tasks.map((item) => item.state), ["done", "doing", "waiting"]);
  assert.equal(result.recent_updates[0].text, "A implementação desta task começou.");
});

test("buildProjectPresentation distinguishes review, attention and completion", () => {
  const root = makeRepo();
  const base = makeTask(root, 1, "Conferir relatório", "sensors_passed");
  const review = buildProjectPresentation(
    root,
    {},
    [base],
    [{ task_id: "TASK-001", status: "active" }],
    [{ type: "evaluation_brief_created", ts: "2026-07-17T15:00:00Z" }],
    {}
  );
  assert.equal(review.status, "revisao");
  assert.equal(review.stage, 3);

  const attention = buildProjectPresentation(
    root,
    {},
    [{ ...base, status: "needs_work" }],
    [{ task_id: "TASK-001", status: "active" }],
    [],
    {}
  );
  assert.equal(attention.status, "atencao");
  assert.equal(attention.blocker.title, "Precisa de atenção");

  const complete = buildProjectPresentation(root, {}, [{ ...base, status: "done" }], [], [], {});
  assert.equal(complete.status, "concluido");
  assert.equal(complete.current.remaining, "Nada ficou pendente.");
});

test("unavailablePresentation never exposes a technical error code", () => {
  const result = unavailablePresentation("Projeto", "harness_not_initialized");
  assert.equal(result.status, "indisponivel");
  assert.match(result.unavailable_message, /ainda não foi preparado/);
  assert.equal(JSON.stringify(result).includes("harness_not_initialized"), false);
});
