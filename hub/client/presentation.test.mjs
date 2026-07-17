import assert from "node:assert/strict";
import test from "node:test";

import presentation from "../../harness_core/dashboard_hub_assets/presentation.js";

const { buildDashboardState, countsLine, mockState, taskPosition } = presentation;

test("mock state covers the complete accompaniment experience", () => {
  const dashboard = buildDashboardState(mockState);

  assert.equal(dashboard.projects.length, 7);
  const shop = dashboard.projects.find((project) => project.id === "loja");
  const stale = dashboard.projects.find((project) => project.id === "entregas");
  const unavailable = dashboard.projects.find((project) => project.id === "indicadores");

  assert.equal(taskPosition(shop), "Task 3 de 10");
  assert.equal(countsLine(shop), "2 concluídas · 1 em andamento · 7 aguardando");
  assert.equal(stale.stale, true);
  assert.equal(unavailable.status, "indisponivel");
});

test("real hub presentation is normalized without exposing implementation details", () => {
  const dashboard = buildDashboardState({
    action_token: "local-token",
    repos: [{
      root: "C:/workspace/loja",
      project: "Loja virtual",
      presentation: {
        status: "conferencia",
        status_label: "Em conferência",
        implementation: "Novo processo de pagamento",
        summary: "O novo pagamento está sendo conferido.",
        situation: "Conferindo o resultado",
        stage: 2,
        updated_at: "2026-07-17T14:42:00Z",
        current: {
          id: "TASK-003",
          number: 3,
          total: 4,
          title: "Conferir os cupons",
          what_doing: "Os cupons estão sendo conferidos.",
          why: "Isso evita descontos incorretos.",
          when_done: "Os descontos estarão prontos para uso.",
          last_update: "Os primeiros exemplos passaram.",
          remaining: "Falta conferir um cupom vencido.",
        },
        tasks: [
          { id: "TASK-001", number: 1, state: "done", title: "Preparar", description: "Tudo foi preparado.", result: "Preparação concluída." },
          { id: "TASK-003", number: 3, state: "doing", title: "Conferir os cupons", description: "Os cupons estão sendo conferidos." },
        ],
      },
    }],
  });

  assert.equal(dashboard.actionToken, "local-token");
  assert.equal(dashboard.projects[0].name, "Loja virtual");
  assert.equal(dashboard.projects[0].id, "loja-virtual-1");
  assert.equal(dashboard.projects[0].id.includes("workspace"), false);
  assert.equal(dashboard.projects[0].status, "conferencia");
  assert.equal(dashboard.projects[0].current.title, "Conferir os cupons");
  assert.equal(dashboard.projects[0].counts.completed, 1);
  assert.equal(dashboard.projects[0].counts.doing, 1);
});

test("empty input remains renderable", () => {
  const dashboard = buildDashboardState({});

  assert.deepEqual(dashboard.projects, []);
  assert.equal(dashboard.actionToken, "");
});
