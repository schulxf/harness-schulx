"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

const PROJECT_ROOT = path.resolve(__dirname, "..", "..");
const HARNESS_DIR = ".harness";
const DEFAULT_SECTORS = [
  { key: "plan", label: "Planning Cabin", roleHints: ["planner"] },
  { key: "implement", label: "Forge", roleHints: ["builder", "operator"] },
  { key: "review", label: "Library", roleHints: ["reviewer"] },
  { key: "research", label: "Research Tower", roleHints: ["research"] },
  { key: "security", label: "Watch Tower", roleHints: ["security", "auditor"] },
  { key: "report", label: "Archive", roleHints: ["reporter"] },
  { key: "idle", label: "Courtyard", roleHints: [] },
];
const PYTHON_ROLE_CHOICES = new Set([
  "planner",
  "builder",
  "reviewer",
  "security",
  "auditor",
  "research",
  "researcher",
  "reporter",
  "operator",
]);

const DEFAULT_HUB_CONFIG = {
  allow_remote_execution: false,
  max_agents: 8,
  default_cli: "codex",
  clis: {
    codex: { cmd: ["codex"], args: [] },
    claude: { cmd: ["claude"], args: [] },
  },
  pty: {
    idle_timeout_s: 1800,
    scrollback_bytes: 262144,
  },
};

class HttpError extends Error {
  constructor(status, message, details) {
    super(message);
    this.name = "HttpError";
    this.status = status;
    this.details = details || undefined;
  }
}

function utcNow() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function normalizePathKey(value) {
  const resolved = path.resolve(String(value || ""));
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function harnessRoot(repoRoot) {
  return path.join(repoRoot, HARNESS_DIR);
}

function readJson(filePath, fallback) {
  try {
    const raw = fs.readFileSync(filePath, "utf8").replace(/^\uFEFF/, "");
    return JSON.parse(raw);
  } catch (err) {
    if (err && err.code === "ENOENT") {
      return fallback;
    }
    if (err instanceof SyntaxError) {
      return fallback;
    }
    throw err;
  }
}

function writeJsonAtomic(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  const tmp = path.join(path.dirname(filePath), `.${path.basename(filePath)}.${process.pid}.${Date.now()}.tmp`);
  fs.writeFileSync(tmp, `${JSON.stringify(payload, null, 2)}\n`, "utf8");
  fs.renameSync(tmp, filePath);
}

function appendJsonl(filePath, payload) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  fs.appendFileSync(filePath, `${JSON.stringify(payload)}\n`, "utf8");
}

function arrayFromPayload(payload, keys) {
  if (Array.isArray(payload)) {
    return payload;
  }
  if (!payload || typeof payload !== "object") {
    return [];
  }
  for (const key of keys) {
    if (Array.isArray(payload[key])) {
      return payload[key];
    }
  }
  return [];
}

function loadRepoConfig(repoRoot) {
  return readJson(path.join(harnessRoot(repoRoot), "config.json"), {});
}

function mergeHubConfig(config) {
  const hub = config && typeof config.hub === "object" && config.hub ? config.hub : {};
  const merged = {
    ...DEFAULT_HUB_CONFIG,
    ...hub,
    clis: {
      ...DEFAULT_HUB_CONFIG.clis,
      ...(hub.clis && typeof hub.clis === "object" ? hub.clis : {}),
    },
    pty: {
      ...DEFAULT_HUB_CONFIG.pty,
      ...(hub.pty && typeof hub.pty === "object" ? hub.pty : {}),
    },
  };
  merged.max_agents = Math.max(1, Number.parseInt(merged.max_agents, 10) || DEFAULT_HUB_CONFIG.max_agents);
  merged.default_cli = String(merged.default_cli || DEFAULT_HUB_CONFIG.default_cli);
  merged.pty.idle_timeout_s = Math.max(0, Number.parseInt(merged.pty.idle_timeout_s, 10) || DEFAULT_HUB_CONFIG.pty.idle_timeout_s);
  merged.pty.scrollback_bytes = Math.max(4096, Number.parseInt(merged.pty.scrollback_bytes, 10) || DEFAULT_HUB_CONFIG.pty.scrollback_bytes);
  return merged;
}

function loadHubRepoRegistry(controlRoot) {
  const payload = readJson(path.join(harnessRoot(controlRoot), "dashboard", "hub", "repos.json"), { repos: [] });
  return arrayFromPayload(payload, ["repos"]).map(String).filter(Boolean);
}

function resolveRepoPaths(controlRoot, watchRepos) {
  const explicit = Array.isArray(watchRepos) ? watchRepos.filter(Boolean) : [];
  const raw = explicit.length > 0 ? explicit : loadHubRepoRegistry(controlRoot);
  const candidates = raw.length > 0 ? raw : [controlRoot];
  const seen = new Set();
  const repos = [];
  for (const candidate of candidates) {
    const resolved = path.resolve(String(candidate));
    const key = normalizePathKey(resolved);
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    repos.push(resolved);
  }
  return repos;
}

function findConfiguredRepo(controlRoot, watchRepos, value) {
  const repos = resolveRepoPaths(controlRoot, watchRepos);
  if (!value && repos.length === 1) {
    return repos[0];
  }
  const needle = String(value || "").trim();
  if (!needle) {
    throw new HttpError(400, "repo_required");
  }
  const absolute = path.resolve(needle);
  const normalizedNeedle = normalizePathKey(absolute);
  const match = repos.find((repoRoot) => {
    return normalizePathKey(repoRoot) === normalizedNeedle || path.basename(repoRoot).toLowerCase() === needle.toLowerCase();
  });
  if (!match) {
    throw new HttpError(403, "repo_not_registered");
  }
  return match;
}

function loadAgents(repoRoot) {
  const payload = readJson(path.join(harnessRoot(repoRoot), "agents", "registry.json"), { agents: [] });
  return arrayFromPayload(payload, ["agents"]).filter((agent) => agent && typeof agent === "object");
}

function sectorForRole(role) {
  const normalized = String(role || "").toLowerCase();
  if (["planner", "plan"].includes(normalized)) {
    return "plan";
  }
  if (["reviewer", "review"].includes(normalized)) {
    return "review";
  }
  if (["research", "researcher"].includes(normalized)) {
    return "research";
  }
  if (["security", "auditor", "audit"].includes(normalized)) {
    return "security";
  }
  if (["reporter", "report"].includes(normalized)) {
    return "report";
  }
  if (["idle"].includes(normalized)) {
    return "idle";
  }
  return "implement";
}

function pythonRoleFor(role) {
  const normalized = String(role || "operator").toLowerCase();
  if (PYTHON_ROLE_CHOICES.has(normalized)) {
    return normalized;
  }
  return "operator";
}

function readJsonlTail(filePath, limit) {
  if (!fs.existsSync(filePath) || limit <= 0) {
    return [];
  }
  const raw = fs.readFileSync(filePath, "utf8");
  const lines = raw.split(/\r?\n/).filter(Boolean).slice(-limit);
  const events = [];
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line);
      if (parsed && typeof parsed === "object") {
        events.push(parsed);
      }
    } catch (_err) {
      // Ignore incomplete trailing writes; the next read will pick them up.
    }
  }
  return events;
}

function repoPhase(tasks, queue, agents) {
  if (agents.some((agent) => String(agent.state || agent.status || "") === "working")) {
    return "implement";
  }
  if (queue.some((item) => String(item.status || "") === "active")) {
    return "implement";
  }
  if (tasks.some((task) => String(task.status || "").includes("review"))) {
    return "review";
  }
  return "idle";
}

function decorateAgents(repoRoot, agents, ptyManager) {
  return agents.filter((agent) => {
    const state = String(agent.state || agent.status || "").toLowerCase();
    return !["done", "killed"].includes(state);
  }).map((agent) => {
    const ptyId = String(agent.pty_id || agent.surface_id || "");
    const hasLivePty =
      ptyManager && (ptyManager.hasAgent(String(agent.id || "")) || (ptyId && ptyManager.hasPty && ptyManager.hasPty(ptyId)));
    const decorated = {
      ...agent,
      role: String(agent.role || "operator"),
      sector: String(agent.sector || sectorForRole(agent.role)),
      cli: String(agent.cli || ""),
      pty_id: ptyId,
      repo_root: String(agent.repo_root || repoRoot),
      cwd: String(agent.cwd || repoRoot),
    };
    if (decorated.pty_id && !hasLivePty && !["done", "killed", "offline"].includes(String(decorated.state || ""))) {
      decorated.state = "offline";
      decorated.status = "offline";
    }
    return decorated;
  });
}

function collectRepoState(repoRoot, index, ptyManager) {
  const base = {
    index,
    project: path.basename(repoRoot),
    root: repoRoot,
    sectors: DEFAULT_SECTORS,
    tasks: [],
    queue: [],
    agents: [],
    events: [],
  };
  if (!fs.existsSync(repoRoot) || !fs.statSync(repoRoot).isDirectory()) {
    return { ...base, error: "repo_missing", phase: "offline" };
  }
  const configPath = path.join(harnessRoot(repoRoot), "config.json");
  if (!fs.existsSync(configPath)) {
    return { ...base, error: "harness_not_initialized", phase: "offline" };
  }
  const config = loadRepoConfig(repoRoot);
  const tasks = arrayFromPayload(readJson(path.join(harnessRoot(repoRoot), "tasks", "index.json"), { tasks: [] }), ["tasks"]);
  const queue = arrayFromPayload(readJson(path.join(harnessRoot(repoRoot), "queue", "index.json"), { queue: [] }), ["queue", "items"]);
  const agents = decorateAgents(repoRoot, loadAgents(repoRoot), ptyManager);
  const hubConfig = mergeHubConfig(config);
  return {
    ...base,
    project: String(config.project_name || path.basename(repoRoot)),
    branch: "",
    phase: repoPhase(tasks, queue, agents),
    active_profile: String(config.active_profile || "balanced"),
    theme: String((config.hub && config.hub.theme) || "tiny-town"),
    hub: {
      allow_remote_execution: hubConfig.allow_remote_execution,
      max_agents: hubConfig.max_agents,
      default_cli: hubConfig.default_cli,
      pty_available: Boolean(ptyManager && ptyManager.available),
    },
    counts: {
      tasks: tasks.length,
      queued: queue.filter((item) => String(item.status || "") === "queued").length,
      active: queue.filter((item) => String(item.status || "") === "active").length,
      agents: agents.length,
    },
    tasks: tasks.slice(-10),
    queue: queue.slice(-10),
    agents,
    events: readJsonlTail(path.join(harnessRoot(repoRoot), "events.jsonl"), 30),
  };
}

function collectWorld(options) {
  const controlRoot = path.resolve(options.controlRoot || process.cwd());
  const watchRepos = options.watchRepos || [];
  const repos = resolveRepoPaths(controlRoot, watchRepos).map((repoRoot, index) =>
    collectRepoState(repoRoot, index, options.ptyManager)
  );
  return {
    generated_at: utcNow(),
    control_root: controlRoot,
    repo_count: repos.length,
    repos,
  };
}

function decodeOffsets(rawOffset, repoRoots) {
  const defaultOffsets = Object.fromEntries(repoRoots.map((repoRoot) => [repoRoot, 0]));
  if (!rawOffset) {
    return defaultOffsets;
  }
  const numeric = Number.parseInt(String(rawOffset), 10);
  if (Number.isFinite(numeric) && String(rawOffset).match(/^\d+$/)) {
    return Object.fromEntries(repoRoots.map((repoRoot) => [repoRoot, Math.max(0, numeric)]));
  }
  try {
    const decoded = JSON.parse(Buffer.from(String(rawOffset), "base64url").toString("utf8"));
    for (const repoRoot of repoRoots) {
      defaultOffsets[repoRoot] = Math.max(0, Number.parseInt(decoded[repoRoot], 10) || 0);
    }
  } catch (_err) {
    return defaultOffsets;
  }
  return defaultOffsets;
}

function encodeOffsets(offsets) {
  return Buffer.from(JSON.stringify(offsets), "utf8").toString("base64url");
}

function readNewEvents(repoRoot, offset) {
  const filePath = path.join(harnessRoot(repoRoot), "events.jsonl");
  if (!fs.existsSync(filePath)) {
    return { events: [], offset: 0 };
  }
  const stats = fs.statSync(filePath);
  let start = Math.max(0, Number.parseInt(offset, 10) || 0);
  if (start > stats.size) {
    start = 0;
  }
  const fd = fs.openSync(filePath, "r");
  try {
    const length = stats.size - start;
    const buffer = Buffer.alloc(length);
    if (length > 0) {
      fs.readSync(fd, buffer, 0, length, start);
    }
    const events = [];
    const raw = buffer.toString("utf8");
    for (const line of raw.split(/\r?\n/)) {
      if (!line.trim()) {
        continue;
      }
      try {
        const event = JSON.parse(line);
        if (event && typeof event === "object") {
          event.repo_root = event.repo_root || repoRoot;
          events.push(event);
        }
      } catch (_err) {
        // Ignore incomplete tail lines.
      }
    }
    return { events, offset: stats.size };
  } finally {
    fs.closeSync(fd);
  }
}

function readNewEventsForRepos(repoRoots, rawOffset) {
  const offsets = decodeOffsets(rawOffset, repoRoots);
  const nextOffsets = {};
  const events = [];
  for (const repoRoot of repoRoots) {
    const result = readNewEvents(repoRoot, offsets[repoRoot] || 0);
    nextOffsets[repoRoot] = result.offset;
    events.push(...result.events);
  }
  events.sort((a, b) => String(a.ts || "").localeCompare(String(b.ts || "")));
  const maxOffset = Object.values(nextOffsets).reduce((max, value) => Math.max(max, Number(value) || 0), 0);
  return {
    events,
    offset: maxOffset,
    offsets: nextOffsets,
    cursor: encodeOffsets(nextOffsets),
  };
}

function makeEvent(repoRoot, type, payload, options) {
  const event = {
    id: `EVT-${new Date().toISOString().replace(/[-:.]/g, "").slice(0, 15)}-${crypto.randomBytes(4).toString("hex")}`,
    ts: utcNow(),
    type,
    source: (options && options.source) || "hub",
    project: path.basename(repoRoot),
    root: repoRoot,
    task_id: String((payload && payload.task_id) || ""),
    agent_id: String((options && options.agentId) || (payload && payload.agent_id) || ""),
    run_dir: String((payload && payload.run_dir) || ""),
    payload: payload || {},
  };
  return event;
}

function appendHarnessEvent(repoRoot, type, payload, options) {
  const event = makeEvent(repoRoot, type, payload, options);
  appendJsonl(path.join(harnessRoot(repoRoot), "events.jsonl"), event);
  return event;
}

function augmentAgent(repoRoot, agentId, fields) {
  const registryPath = path.join(harnessRoot(repoRoot), "agents", "registry.json");
  const registry = readJson(registryPath, { agents: [] });
  const agents = arrayFromPayload(registry, ["agents"]).filter((agent) => agent && typeof agent === "object");
  let agent = agents.find((item) => String(item.id || "") === String(agentId));
  if (!agent) {
    agent = { id: String(agentId), created_at: utcNow() };
    agents.push(agent);
  }
  Object.assign(agent, fields, { updated_at: utcNow() });
  registry.agents = agents;
  registry.updated_at = utcNow();
  writeJsonAtomic(registryPath, registry);
  return agent;
}

function harnessPython() {
  return process.env.HARNESS_PYTHON || process.env.PYTHON || "python";
}

function runHarnessCli(repoRoot, args, options) {
  const timeoutMs = (options && options.timeoutMs) || 30000;
  const harnessPy = path.join(PROJECT_ROOT, "bin", "harness.py");
  const argv = [harnessPy, "--repo", repoRoot, ...args.map(String)];
  return new Promise((resolve, reject) => {
    const child = spawn(harnessPython(), argv, {
      cwd: PROJECT_ROOT,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill();
      reject(new HttpError(504, "harness_cli_timeout", { args }));
    }, timeoutMs);
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString("utf8");
    });
    child.stderr.on("data", (chunk) => {
      stderr += chunk.toString("utf8");
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      reject(new HttpError(500, "harness_cli_failed_to_start", { error: err.message }));
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) {
        resolve({ stdout, stderr, code });
      } else {
        reject(new HttpError(500, "harness_cli_failed", { args, code, stdout, stderr }));
      }
    });
  });
}

function normalizeCliDefinition(hubConfig, cliName) {
  const name = String(cliName || hubConfig.default_cli || "codex");
  const definition = hubConfig.clis[name];
  if (!definition) {
    throw new HttpError(400, "unknown_cli", { cli: name, known: Object.keys(hubConfig.clis) });
  }
  const cmd = definition.cmd || [name];
  const cmdParts = Array.isArray(cmd) ? cmd.map(String).filter(Boolean) : [String(cmd)];
  if (!cmdParts[0]) {
    throw new HttpError(400, "invalid_cli_command", { cli: name });
  }
  const extraArgs = Array.isArray(definition.args) ? definition.args.map(String) : [];
  return {
    cli: name,
    command: cmdParts[0],
    args: [...cmdParts.slice(1), ...extraArgs],
  };
}

async function registerAgent(repoRoot, agent) {
  const pythonRole = pythonRoleFor(agent.role);
  const args = [
    "agent",
    "register",
    agent.id,
    "--name",
    agent.name,
    "--role",
    pythonRole,
    "--state",
    agent.state || "working",
    "--phase",
    agent.sector || sectorForRole(agent.role),
    "--speech",
    agent.speech || "Agent spawned from harness-hub.",
    "--cli",
    agent.cli || "codex",
    "--sector",
    agent.sector || sectorForRole(agent.role),
    "--cwd",
    agent.cwd || repoRoot,
    "--spawned-by",
    agent.spawned_by || "ui",
  ];
  if (agent.pty_id) {
    args.push("--pty-id", agent.pty_id);
  }
  if (agent.transcript_path) {
    args.push("--transcript-path", agent.transcript_path);
  }
  await runHarnessCli(repoRoot, args);
  const registered = loadAgents(repoRoot).find((item) => String(item.id || "") === String(agent.id));
  if (!registered) {
    throw new HttpError(500, "agent_registration_missing", { agent_id: agent.id });
  }
  return registered;
}

async function sendAgentMessage(repoRoot, fromAgent, toAgent, text) {
  await runHarnessCli(repoRoot, ["agent", "message", fromAgent, "--to", toAgent, "--text", text]);
  return {
    ts: utcNow(),
    from_agent: fromAgent,
    to_agent: toAgent,
    text,
  };
}

async function killAgent(repoRoot, agentId, reason) {
  const args = ["agent", "kill", agentId];
  if (reason) {
    args.push("--reason", reason);
  }
  await runHarnessCli(repoRoot, args);
  return loadAgents(repoRoot).find((item) => String(item.id || "") === String(agentId)) || null;
}

function findAgentRepo(controlRoot, watchRepos, agentId) {
  for (const repoRoot of resolveRepoPaths(controlRoot, watchRepos)) {
    if (loadAgents(repoRoot).some((agent) => String(agent.id || "") === String(agentId))) {
      return repoRoot;
    }
  }
  return "";
}

async function addRepo(controlRoot, repoPath) {
  const resolved = path.resolve(String(repoPath || ""));
  if (!fs.existsSync(resolved) || !fs.statSync(resolved).isDirectory()) {
    throw new HttpError(400, "repo_path_missing");
  }
  if (!fs.existsSync(path.join(harnessRoot(resolved), "config.json"))) {
    await runHarnessCli(resolved, ["init", "--name", path.basename(resolved)]);
  }
  await runHarnessCli(controlRoot, ["dashboard", "hub-add-repo", resolved]);
  return loadHubRepoRegistry(controlRoot);
}

function makeAgentId(role) {
  const safeRole = String(role || "agent").toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, "") || "agent";
  return `${safeRole}-${Date.now().toString(36)}-${crypto.randomBytes(3).toString("hex")}`;
}

module.exports = {
  DEFAULT_HUB_CONFIG,
  DEFAULT_SECTORS,
  HttpError,
  addRepo,
  appendHarnessEvent,
  augmentAgent,
  collectWorld,
  findAgentRepo,
  findConfiguredRepo,
  harnessRoot,
  loadAgents,
  loadHubRepoRegistry,
  loadRepoConfig,
  makeAgentId,
  mergeHubConfig,
  normalizeCliDefinition,
  normalizePathKey,
  readNewEventsForRepos,
  registerAgent,
  resolveRepoPaths,
  runHarnessCli,
  sectorForRole,
  killAgent,
  utcNow,
  sendAgentMessage,
};
