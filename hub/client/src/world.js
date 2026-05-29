import { SECTOR_KEYS, sectorForAgent, sectorForEvent, speechForAgent, stateForAgent } from "./statemachine.js";

export const WORLD_WIDTH = 1280;
export const WORLD_HEIGHT = 720;

export const THEMES = [
  {
    key: "tiny-town",
    label: "Tiny Town",
    ground: "#4f7545",
    groundAlt: "#3b5f3f",
    road: "#ad9863",
    roof: "#9b4c36",
    wall: "#d0b878",
    water: "#356d77",
  },
  {
    key: "urban",
    label: "RPG Urban",
    ground: "#4f5856",
    groundAlt: "#37403f",
    road: "#847d70",
    roof: "#3f566f",
    wall: "#b7b1a1",
    water: "#315f72",
  },
  {
    key: "dungeon",
    label: "Tiny Dungeon",
    ground: "#48443e",
    groundAlt: "#332f2a",
    road: "#6f6250",
    roof: "#573d45",
    wall: "#9a8b77",
    water: "#30485b",
  },
  {
    key: "archive",
    label: "Archive",
    ground: "#545235",
    groundAlt: "#3c3f2d",
    road: "#b4975b",
    roof: "#4a5b46",
    wall: "#c6bc88",
    water: "#44636f",
  },
];

const DEFAULT_REPO_ROOT = "C:/workspace/demo";

function hashString(value) {
  let hash = 0;
  for (const char of String(value || "")) {
    hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  }
  return hash;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

export function themeForRepo(repo, index = 0) {
  if (repo?.theme) {
    const found = THEMES.find((theme) => theme.key === repo.theme || theme.label === repo.theme);
    if (found) return found;
  }
  return THEMES[(hashString(repo?.root || repo?.project || index) + index) % THEMES.length];
}

export function defaultSectors() {
  return [
    { key: "plan", label: "Planning Cabin", x: 88, y: 88, w: 220, h: 150, tone: "#d9a441" },
    { key: "implement", label: "Forge", x: 386, y: 78, w: 246, h: 154, tone: "#54a7c7" },
    { key: "review", label: "Library", x: 714, y: 82, w: 230, h: 150, tone: "#9b84d8" },
    { key: "research", label: "Research Tower", x: 1012, y: 104, w: 188, h: 144, tone: "#4fb9a8" },
    { key: "idle", label: "Courtyard", x: 492, y: 300, w: 290, h: 180, tone: "#58b86d" },
    { key: "report", label: "Records Office", x: 122, y: 462, w: 260, h: 148, tone: "#58b86d" },
    { key: "security", label: "Watch Tower", x: 908, y: 430, w: 250, h: 156, tone: "#e15b4f" },
  ];
}

export function sectorCenter(sector, index = 0) {
  const offset = (index % 5) * 12;
  return {
    x: clamp(sector.x + sector.w / 2 + offset - 24, 26, WORLD_WIDTH - 26),
    y: clamp(sector.y + sector.h / 2 + ((index % 3) - 1) * 16, 52, WORLD_HEIGHT - 26),
  };
}

export function pointInRect(point, rect) {
  return point.x >= rect.x && point.x <= rect.x + rect.w && point.y >= rect.y && point.y <= rect.y + rect.h;
}

function normalizeAgent(agent, repo, index) {
  const id = String(agent?.id || `${repo.id}-agent-${index + 1}`);
  const normalized = {
    id,
    name: String(agent?.name || agent?.label || id),
    role: String(agent?.role || "operator"),
    cli: String(agent?.cli || repo.default_cli || "shell"),
    state: stateForAgent(agent),
    status: String(agent?.status || ""),
    sector: sectorForAgent(agent),
    task_id: String(agent?.task_id || ""),
    task_title: String(agent?.task_title || ""),
    phase: String(agent?.phase || repo.phase || "idle"),
    speech: speechForAgent(agent),
    pty_id: String(agent?.pty_id || ""),
    surface_id: String(agent?.surface_id || ""),
    cwd: String(agent?.cwd || repo.root || ""),
    repo_root: String(agent?.repo_root || repo.root || ""),
    transcript_path: String(agent?.transcript_path || ""),
    synthetic: Boolean(agent?.synthetic),
    updated_at: String(agent?.updated_at || ""),
    raw: agent || {},
  };
  return normalized;
}

function normalizeRepo(repo, index) {
  const root = String(repo?.root || repo?.repo_root || repo?.path || `${DEFAULT_REPO_ROOT}-${index + 1}`);
  const id = String(repo?.id || root || repo?.project || `repo-${index + 1}`);
  const theme = themeForRepo(repo, index);
  const normalized = {
    id,
    index,
    project: String(repo?.project || repo?.name || root.split(/[\\/]/).filter(Boolean).pop() || `repo-${index + 1}`),
    root,
    branch: String(repo?.branch || ""),
    phase: String(repo?.phase || "idle"),
    active_profile: String(repo?.active_profile || ""),
    active_task: repo?.active_task || null,
    latest_run: String(repo?.latest_run || ""),
    latest_checkpoint: String(repo?.latest_checkpoint || ""),
    counts: repo?.counts || {},
    tasks: Array.isArray(repo?.tasks) ? repo.tasks : [],
    queue: Array.isArray(repo?.queue) ? repo.queue : [],
    events: Array.isArray(repo?.events) ? repo.events : [],
    sectors: Array.isArray(repo?.sectors) && repo.sectors.length ? repo.sectors : defaultSectors(),
    theme,
    agents: [],
    raw: repo || {},
  };
  const sourceAgents = Array.isArray(repo?.agents) ? repo.agents : [];
  normalized.agents = sourceAgents.map((agent, agentIndex) => normalizeAgent(agent, normalized, agentIndex));
  return normalized;
}

function sourceRepos(raw) {
  if (Array.isArray(raw?.repos)) return raw.repos;
  if (Array.isArray(raw?.world?.repos)) return raw.world.repos;
  if (Array.isArray(raw?.repositories)) return raw.repositories;
  if (raw?.repo || raw?.project || raw?.root) return [raw];
  return [];
}

export function demoWorld() {
  return {
    generated_at: new Date().toISOString(),
    source: "demo",
    repo_count: 2,
    active_repos: 2,
    total_tasks: 9,
    total_findings: 2,
    repos: [
      {
        id: "demo-core",
        project: "harness-core",
        root: "C:/workspace/harness-core",
        branch: "feature/hub-agents-wmux-bridge",
        phase: "build",
        counts: { tasks: 5, queued: 2, active: 1, done: 2, security_findings: 1, artifacts: 4 },
        active_task: { task_id: "TASK-014", title: "Implement pixel hub client" },
        queue: [
          { id: "QUEUE-018", title: "Wire hub APIs", status: "active" },
          { id: "QUEUE-019", title: "Add PTY transport", status: "queued" },
        ],
        tasks: [
          { task_id: "TASK-014", title: "Implement pixel hub client", status: "working" },
          { task_id: "TASK-013", title: "Design sidecar contract", status: "done" },
        ],
        events: [
          { type: "agent_spawned", ts: "now", payload: { agent_id: "builder-1", role: "builder" } },
          { type: "agent_sector_changed", ts: "now", payload: { agent_id: "builder-1", sector: "implement" } },
        ],
        agents: [
          {
            id: "builder-1",
            name: "Forge Runner",
            role: "builder",
            cli: "codex",
            state: "working",
            sector: "implement",
            task_id: "TASK-014",
            task_title: "Implement pixel hub client",
            speech: "Rendering repos as maps.",
            pty_id: "pty-demo-1",
          },
          {
            id: "reviewer-1",
            name: "Library Watch",
            role: "reviewer",
            cli: "claude",
            state: "idle",
            sector: "review",
            speech: "Waiting for a diff.",
          },
          {
            id: "security-1",
            name: "Gate Auditor",
            role: "security",
            cli: "codex",
            state: "working",
            sector: "security",
            speech: "Checking RCE gates.",
          },
        ],
      },
      {
        id: "demo-client",
        project: "hub-client",
        root: "C:/workspace/hub-client",
        branch: "main",
        phase: "review",
        counts: { tasks: 4, queued: 1, active: 1, done: 2, security_findings: 1, artifacts: 3 },
        active_task: { task_id: "TASK-022", title: "QA playable prototype" },
        agents: [
          {
            id: "planner-1",
            name: "Plan Keeper",
            role: "planner",
            state: "idle",
            sector: "plan",
            speech: "Map sectors are ready.",
          },
          {
            id: "research-1",
            name: "Signal Scout",
            role: "research",
            state: "talking",
            sector: "research",
            speech: "Assets can land later.",
          },
        ],
      },
    ],
    wmux: { available: false },
    action_token: "",
  };
}

export function buildWorldState(raw = {}) {
  const base = raw && Object.keys(raw).length ? raw : demoWorld();
  const repos = sourceRepos(base).map(normalizeRepo);
  const normalized = {
    generated_at: String(base.generated_at || new Date().toISOString()),
    source: String(base.source || "api"),
    repo_count: Number(base.repo_count || repos.length),
    active_repos: Number(base.active_repos || repos.filter((repo) => repo.phase !== "idle" && repo.phase !== "offline").length),
    total_tasks: Number(base.total_tasks || repos.reduce((sum, repo) => sum + Number(repo.counts?.tasks || 0), 0)),
    total_findings: Number(base.total_findings || repos.reduce((sum, repo) => sum + Number(repo.counts?.security_findings || 0), 0)),
    repos,
    wmux: base.wmux || {},
    action_token: String(base.action_token || ""),
    events: Array.isArray(base.events) ? base.events : repos.flatMap((repo) => repo.events || []),
    raw: base,
  };
  return normalized.repos.length ? normalized : buildWorldState(demoWorld());
}

export function findRepo(world, repoIdOrRoot) {
  return world.repos.find((repo) => repo.id === repoIdOrRoot || repo.root === repoIdOrRoot) || world.repos[0] || null;
}

function repoForPayload(world, payload) {
  const root = payload.repo_root || payload.repo || payload.root || payload.cwd;
  if (root) return findRepo(world, String(root));
  return world.repos[0] || null;
}

function upsertAgent(repo, incoming) {
  const id = String(incoming.id || incoming.agent_id || incoming.from_agent || "");
  if (!id) return;
  const index = repo.agents.findIndex((agent) => agent.id === id);
  const existing = index >= 0 ? repo.agents[index] : {};
  const next = normalizeAgent({ ...existing, ...incoming, id }, repo, index >= 0 ? index : repo.agents.length);
  if (index >= 0) repo.agents.splice(index, 1, next);
  else repo.agents.push(next);
}

export function applyWorldEvent(world, event) {
  if (!event || typeof event !== "object") return world;
  if (Array.isArray(event.repos) || event.world?.repos) return buildWorldState({ ...world.raw, ...event });

  const payload = event.payload || event;
  const repo = repoForPayload(world, payload);
  if (!repo) return world;

  if (event.type === "agent_killed") {
    const id = String(payload.agent_id || payload.id || "");
    repo.agents = repo.agents.filter((agent) => agent.id !== id);
  } else if (event.type === "agent_spawned") {
    upsertAgent(repo, {
      id: payload.agent_id || payload.id,
      name: payload.name,
      role: payload.role,
      cli: payload.cli,
      sector: payload.sector || sectorForEvent(event.type),
      state: "idle",
      speech: payload.speech || "Spawned and ready.",
      repo_root: payload.repo_root || repo.root,
      cwd: payload.cwd || repo.root,
      pty_id: payload.pty_id,
    });
  } else if (event.type === "agent_sector_changed") {
    upsertAgent(repo, {
      id: payload.agent_id || payload.id,
      sector: payload.sector || sectorForEvent(event.type),
      state: "walking",
      speech: payload.speech || `Moving to ${payload.sector || "sector"}.`,
    });
  } else if (event.type === "agent_message") {
    const from = payload.from_agent || payload.agent_id;
    const to = payload.to_agent || payload.to;
    if (from) upsertAgent(repo, { id: from, state: "talking", speech: payload.text || payload.message || "Message sent." });
    if (to) upsertAgent(repo, { id: to, state: "talking", speech: payload.text || payload.message || "Message received." });
  } else if (event.type === "agent_terminal_attached") {
    upsertAgent(repo, { id: payload.agent_id || payload.id, pty_id: payload.pty_id, speech: "Terminal attached." });
  } else if (event.type === "agent_done") {
    upsertAgent(repo, {
      id: payload.agent_id || payload.id,
      state: payload.state || "done",
      status: payload.state || "done",
      speech: payload.summary || payload.speech || "Done.",
    });
  } else {
    const sector = sectorForEvent(event.type);
    const id = payload.agent_id || payload.id;
    if (sector && id) upsertAgent(repo, { id, sector, state: "walking" });
  }

  repo.events = [...(repo.events || []), event].slice(-40);
  world.events = [...(world.events || []), event].slice(-80);
  return world;
}

export function sectorByKey(repo, key) {
  return (repo?.sectors || []).find((sector) => sector.key === key) || (repo?.sectors || []).find((sector) => SECTOR_KEYS.includes(sector.key));
}
