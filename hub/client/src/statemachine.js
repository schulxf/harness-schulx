export const SECTOR_KEYS = ["idle", "plan", "implement", "review", "research", "security", "report"];

export const ROLE_META = {
  builder: { label: "Builder", sector: "implement", color: "#54a7c7" },
  implementer: { label: "Implementer", sector: "implement", color: "#54a7c7" },
  planner: { label: "Planner", sector: "plan", color: "#d9a441" },
  reviewer: { label: "Reviewer", sector: "review", color: "#9b84d8" },
  research: { label: "Research", sector: "research", color: "#4fb9a8" },
  researcher: { label: "Researcher", sector: "research", color: "#4fb9a8" },
  security: { label: "Security", sector: "security", color: "#e15b4f" },
  auditor: { label: "Auditor", sector: "security", color: "#e15b4f" },
  reporter: { label: "Reporter", sector: "report", color: "#58b86d" },
  operator: { label: "Operator", sector: "idle", color: "#d9a441" },
};

const PHASE_TO_SECTOR = {
  queue: "plan",
  contract: "plan",
  build: "implement",
  implement: "implement",
  review: "review",
  evaluation: "review",
  research: "research",
  security: "security",
  report: "report",
  done: "report",
  idle: "idle",
  offline: "idle",
};

const EVENT_TO_SECTOR = {
  agent_spawned: "idle",
  contract_created: "plan",
  run_started: "implement",
  sensors_started: "implement",
  sensors_failed: "implement",
  sensors_passed: "review",
  evaluation_brief_created: "review",
  security_scan_started: "security",
  security_scan_completed: "security",
  report_created: "report",
};

export function roleMeta(role) {
  return ROLE_META[String(role || "").toLowerCase()] || ROLE_META.operator;
}

export function sectorForRole(role) {
  return roleMeta(role).sector;
}

export function sectorForEvent(type) {
  return EVENT_TO_SECTOR[String(type || "")] || "";
}

export function sectorForAgent(agent) {
  const explicit = String(agent?.sector || "").toLowerCase();
  if (SECTOR_KEYS.includes(explicit)) return explicit;
  const phaseSector = PHASE_TO_SECTOR[String(agent?.phase || "").toLowerCase()];
  if (phaseSector) return phaseSector;
  return sectorForRole(agent?.role);
}

export function stateForAgent(agent) {
  const raw = String(agent?.state || agent?.status || "").toLowerCase();
  if (raw.includes("offline") || raw.includes("dead")) return "offline";
  if (raw.includes("walk") || raw.includes("move")) return "walking";
  if (raw.includes("talk") || raw.includes("message")) return "talking";
  if (raw.includes("work") || raw.includes("run") || raw.includes("active")) return "working";
  if (agent?.task_id || agent?.task_title) return "working";
  return "idle";
}

export function activityLabel(agent) {
  const state = stateForAgent(agent);
  const sector = sectorForAgent(agent);
  if (state === "offline") return "Offline";
  if (state === "talking") return "Talking";
  if (state === "walking") return `Walking to ${sector}`;
  if (state === "working") return `Working in ${sector}`;
  return `Idle in ${sector}`;
}

export function speechForAgent(agent) {
  const speech = String(agent?.speech || "").trim();
  if (speech) return speech;
  if (agent?.task_title) return `On ${agent.task_title}`;
  if (agent?.task_id) return `Working ${agent.task_id}`;
  if (stateForAgent(agent) === "offline") return "Session offline.";
  return "Waiting for work.";
}

export function shortPath(path) {
  const value = String(path || "");
  if (value.length <= 44) return value || "-";
  return `${value.slice(0, 18)}...${value.slice(-22)}`;
}

export function eventSummary(event) {
  const payload = event?.payload || {};
  return (
    payload.summary ||
    payload.message ||
    payload.text ||
    event?.message ||
    event?.type ||
    "event"
  );
}
