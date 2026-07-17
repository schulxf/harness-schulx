"use strict";

const fs = require("fs");
const path = require("path");

const COMPLETE_STATUSES = new Set(["passed", "done"]);
const ATTENTION_STATUSES = new Set(["failed", "needs_work", "review_followup", "sensors_failed"]);
const WORKING_STATUSES = new Set(["in_progress", ...ATTENTION_STATUSES]);
const REVIEW_STATUSES = new Set(["sensors_passed"]);

function readJson(filePath, fallback = {}) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, ""));
  } catch (error) {
    if (error?.code === "ENOENT" || error instanceof SyntaxError) return fallback;
    throw error;
  }
}

function readText(filePath) {
  try {
    return fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
  } catch (error) {
    if (error?.code === "ENOENT") return "";
    throw error;
  }
}

function cleanText(value, fallback = "") {
  const text = String(value || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*[-*]\s*/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/^[-\s]+|[-\s]+$/g, "");
  return text || fallback;
}

function ensurePeriod(value) {
  const text = cleanText(value);
  if (!text) return "";
  return /[.!?]$/.test(text) ? text : `${text}.`;
}

function markdownSection(text, heading) {
  const escaped = heading.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = new RegExp(`^##\\s+${escaped}\\s*$([\\s\\S]*?)(?=^##\\s+|(?![\\s\\S]))`, "im").exec(text || "");
  if (!match) return "";
  const paragraph = match[1].trim().split(/\n\s*\n/).find(Boolean) || "";
  return cleanText(paragraph);
}

function safeTaskText(repoRoot, task) {
  const relative = String(task?.task_file || "").trim();
  if (!relative) return "";
  const root = path.resolve(repoRoot);
  const candidate = path.resolve(root, relative);
  if (candidate !== root && !candidate.startsWith(`${root}${path.sep}`)) return "";
  return readText(candidate);
}

function taskContract(repoRoot, taskId) {
  return readJson(path.join(repoRoot, ".harness", "contracts", `${taskId}.json`), {});
}

function latestRunDir(repoRoot, taskId) {
  const root = path.join(repoRoot, ".harness", "runs", taskId);
  try {
    const names = fs.readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name)
      .sort();
    return names.length ? path.join(root, names[names.length - 1]) : "";
  } catch (error) {
    if (error?.code === "ENOENT") return "";
    throw error;
  }
}

function taskResult(repoRoot, task) {
  const runDir = latestRunDir(repoRoot, String(task?.task_id || ""));
  if (runDir) {
    const plain = readText(path.join(runDir, "plain-summary.md"));
    const result = markdownSection(plain, "Resultado") || markdownSection(plain, "O que foi feito");
    if (result) return ensurePeriod(result);
    const notes = cleanText(readJson(path.join(runDir, "evaluation.json"), {}).notes);
    if (notes) return ensurePeriod(notes);
  }
  return "A task foi concluída e conferida.";
}

function taskDescription(repoRoot, task) {
  const direct = cleanText(task?.description || task?.body);
  if (direct) return ensurePeriod(direct);
  const section = markdownSection(safeTaskText(repoRoot, task), "O que construir");
  if (section) return ensurePeriod(section);
  return `O trabalho desta etapa é ${cleanText(task?.title, "esta etapa").toLowerCase()}.`;
}

function taskState(status, isCurrent) {
  const normalized = String(status || "planned").toLowerCase();
  if (COMPLETE_STATUSES.has(normalized)) return "done";
  if (isCurrent && (WORKING_STATUSES.has(normalized) || REVIEW_STATUSES.has(normalized))) return "doing";
  return "waiting";
}

function eventMessage(event) {
  const payload = event?.payload && typeof event.payload === "object" ? event.payload : {};
  const fixed = {
    task_created: "Uma nova task foi preparada.",
    queue_item_added: "A task entrou na sequência de trabalho.",
    queue_item_activated: "O trabalho da task começou.",
    run_started: "A implementação desta task começou.",
    evaluation_brief_created: "O resultado ficou pronto para revisão.",
    fix_brief_created: "Os ajustes necessários foram organizados.",
    report_created: "O resultado final da task foi registrado.",
    agent_done: "O trabalho desta etapa foi encerrado.",
  };
  if (event?.type === "sensors_completed") {
    return payload.passed
      ? "A conferência terminou sem encontrar problemas."
      : "A conferência encontrou pontos que precisam de ajuste.";
  }
  if (event?.type === "evaluation_recorded") {
    return String(payload.status || "").toLowerCase() === "pass"
      ? "A revisão confirmou que a task está pronta."
      : "A revisão pediu alguns ajustes antes da conclusão.";
  }
  return fixed[event?.type] || "";
}

function recentUpdates(events) {
  const updates = [];
  for (const event of [...(events || [])].reverse()) {
    const text = eventMessage(event);
    if (!text) continue;
    updates.push({ at: String(event.ts || ""), text });
    if (updates.length === 4) break;
  }
  return updates;
}

function latestIso(values) {
  const dates = values
    .map((value) => new Date(String(value || "")))
    .filter((value) => Number.isFinite(value.getTime()));
  if (!dates.length) return "";
  return new Date(Math.max(...dates.map((value) => value.getTime()))).toISOString();
}

function unavailablePresentation(project, error = "") {
  return {
    status: "indisponivel",
    status_label: "Indisponível",
    implementation: "Informações temporariamente indisponíveis",
    summary: "",
    situation: "Indisponível",
    updated_at: "",
    stage: 0,
    tasks: [],
    current: null,
    last_completed: null,
    recent_updates: [],
    unavailable_message: error === "harness_not_initialized"
      ? "Este projeto ainda não foi preparado para o acompanhamento."
      : "Não foi possível receber informações deste projeto no momento.",
  };
}

function buildProjectPresentation(repoRoot, config, tasks, queue, events, security = {}) {
  const taskById = new Map(tasks.map((task) => [String(task.task_id || ""), task]));
  const ordered = [];
  for (const item of queue) {
    const task = taskById.get(String(item.task_id || ""));
    if (task && !ordered.includes(task)) ordered.push(task);
  }
  for (const task of tasks) if (!ordered.includes(task)) ordered.push(task);

  const active = queue.find((item) => String(item.status || "") === "active");
  let current = taskById.get(String(active?.task_id || ""));
  if (!current) {
    current = ordered.find((task) => {
      const status = String(task.status || "");
      return WORKING_STATUSES.has(status) || REVIEW_STATUSES.has(status);
    });
  }
  if (!current && ordered.length) {
    current = ordered.find((task) => !COMPLETE_STATUSES.has(String(task.status || ""))) || ordered[ordered.length - 1];
  }
  const currentId = String(current?.task_id || "");
  const currentStatus = String(current?.status || "planned").toLowerCase();

  const details = ordered.map((task, index) => {
    const id = String(task.task_id || "");
    const state = taskState(task.status, id === currentId);
    return {
      id,
      number: index + 1,
      title: cleanText(task.title, `Task ${index + 1}`),
      description: taskDescription(repoRoot, task),
      state,
      result: state === "done" ? taskResult(repoRoot, task) : "",
      updated_at: String(task.updated_at || task.created_at || ""),
    };
  });

  const completed = details.length > 0 && details.every((task) => task.state === "done");
  const findings = Array.isArray(security.findings) ? security.findings : [];
  const blocked = queue.find((item) => String(item.status || "") === "blocked");
  const needsAttention = ATTENTION_STATUSES.has(currentStatus) || findings.length > 0 || Boolean(blocked);
  const recentEventTypes = new Set(events.slice(-8).map((event) => String(event.type || "")));
  let status = "andamento";
  if (completed) status = "concluido";
  else if (needsAttention) status = "atencao";
  else if (REVIEW_STATUSES.has(currentStatus)) {
    status = recentEventTypes.has("evaluation_brief_created") ? "revisao" : "conferencia";
  }
  const statusLabel = {
    andamento: "Em andamento",
    conferencia: "Em conferência",
    revisao: "Em revisão",
    atencao: "Precisa de atenção",
    concluido: "Concluído",
  }[status];

  let stage = 0;
  if (completed) stage = 4;
  else if (REVIEW_STATUSES.has(currentStatus)) stage = recentEventTypes.has("evaluation_brief_created") ? 3 : 2;
  else if (ATTENTION_STATUSES.has(currentStatus) && recentEventTypes.has("sensors_completed")) stage = 2;
  else if (WORKING_STATUSES.has(currentStatus)) stage = 1;

  const hubConfig = config?.hub && typeof config.hub === "object" ? config.hub : {};
  const contract = currentId ? taskContract(repoRoot, currentId) : {};
  const currentTitle = cleanText(current?.title, "Acompanhamento da implementação");
  const implementation = cleanText(
    hubConfig.implementation_name || config?.implementation_name || current?.implementation || currentTitle,
    "Implementação em acompanhamento"
  );
  const goal = cleanText(contract.goal || current?.goal || currentTitle);
  const summary = ensurePeriod(
    hubConfig.implementation_summary || config?.implementation_summary || goal || `Acompanhar ${implementation.toLowerCase()}`
  );
  const criteria = (Array.isArray(contract.acceptance_criteria) ? contract.acceptance_criteria : [])
    .map((item) => ensurePeriod(item))
    .filter(Boolean);
  const currentDetail = details.find((task) => task.id === currentId);
  const recent = recentUpdates(events);
  const whatDoing = completed
    ? "Todas as tasks desta implementação foram concluídas e conferidas."
    : currentDetail?.description || `O trabalho atual é ${currentTitle.toLowerCase()}.`;
  const whenDone = completed
    ? "A implementação está pronta para a próxima decisão da equipe."
    : criteria[0] || `A task ${currentTitle.toLowerCase()} ficará pronta para conferência.`;
  const remaining = completed
    ? "Nada ficou pendente."
    : criteria.length
      ? `Falta conferir: ${criteria.slice(0, 3).join(" ")}`
      : "Falta concluir esta task e conferir o resultado.";

  let blocker = null;
  if (needsAttention) {
    const message = findings.length
      ? "A conferência encontrou um problema que precisa ser corrigido antes da conclusão."
      : blocked
        ? "O trabalho está aguardando a resolução de um bloqueio antes de continuar."
        : "A conferência encontrou pontos que precisam de ajuste. O trabalho de correção está em andamento.";
    blocker = { title: "Precisa de atenção", message };
  }

  const lastCompleted = details.filter((task) => task.state === "done").at(-1) || null;
  const stageLabels = ["Preparando", "Construindo", "Conferindo", "Revisando", "Concluído"];
  return {
    status,
    status_label: statusLabel,
    implementation,
    summary,
    situation: status === "atencao" ? "Precisa de atenção" : stageLabels[stage],
    updated_at: latestIso([
      ...tasks.map((task) => task.updated_at || task.created_at),
      ...events.map((event) => event.ts),
    ]),
    stage,
    tasks: details,
    current: {
      id: currentId,
      number: currentDetail?.number || details.length || 1,
      total: details.length,
      title: currentTitle,
      what_doing: ensurePeriod(whatDoing),
      why: goal ? ensurePeriod(`Isso está sendo feito para ${goal.toLowerCase()}`) : summary,
      when_done: ensurePeriod(whenDone),
      last_update: recent[0]?.text || "O acompanhamento está aguardando uma nova atualização.",
      remaining: ensurePeriod(remaining),
    },
    last_completed: lastCompleted ? {
      title: lastCompleted.title,
      result: lastCompleted.result,
      completed_at: lastCompleted.updated_at,
    } : null,
    recent_updates: recent,
    blocker,
    stale_after_seconds: 300,
  };
}

module.exports = {
  buildProjectPresentation,
  unavailablePresentation,
};
