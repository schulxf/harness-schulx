"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");
const presentation = require("./presentation");

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
  default_cli: "shell",
  clis: {
    // On Windows node-pty needs a real .exe; the LLM CLIs are .cmd shims, so we
    // launch them through PowerShell (which also keeps the shell alive on exit).
    shell: { cmd: ["powershell.exe"], args: ["-NoLogo"] },
    claude: { cmd: ["powershell.exe"], args: ["-NoLogo", "-NoExit", "-Command", "claude"] },
    codex: { cmd: ["powershell.exe"], args: ["-NoLogo", "-NoExit", "-Command", "codex"] },
  },
  pty: {
    idle_timeout_s: 1800,
    scrollback_bytes: 262144,
  },
};
const DONE_AGENT_VISIBLE_MS = 30 * 60 * 1000;

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

function hubRepoRegistryPath(controlRoot) {
  return path.join(harnessRoot(controlRoot), "dashboard", "hub", "repos.json");
}

function normalizeRepoPaths(values) {
  const seen = new Set();
  const repos = [];
  for (const value of Array.isArray(values) ? values : []) {
    if (!String(value || "").trim()) continue;
    const resolved = path.resolve(String(value));
    const key = normalizePathKey(resolved);
    if (seen.has(key)) continue;
    seen.add(key);
    repos.push(resolved);
  }
  return repos;
}

function loadHubRepoRegistryState(controlRoot) {
  const registryPath = hubRepoRegistryPath(controlRoot);
  const exists = fs.existsSync(registryPath);
  const payload = readJson(registryPath, { repos: [], hidden_repos: [] });
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return { exists, repos: [], hidden_repos: [] };
  }
  return {
    exists,
    repos: normalizeRepoPaths(arrayFromPayload(payload, ["repos"])),
    hidden_repos: normalizeRepoPaths(arrayFromPayload(payload, ["hidden_repos"])),
  };
}

function saveHubRepoRegistryState(controlRoot, state) {
  const repos = normalizeRepoPaths(state.repos);
  const repoKeys = new Set(repos.map(normalizePathKey));
  const hidden = normalizeRepoPaths(state.hidden_repos).filter((entry) => repoKeys.has(normalizePathKey(entry)));
  writeJsonAtomic(hubRepoRegistryPath(controlRoot), {
    repos,
    hidden_repos: hidden,
    updated_at: utcNow(),
  });
}

function listHubRepos(controlRoot) {
  const state = loadHubRepoRegistryState(controlRoot);
  const hiddenKeys = new Set(state.hidden_repos.map(normalizePathKey));
  return state.repos.map((repoPath) => ({
    path: repoPath,
    hidden: hiddenKeys.has(normalizePathKey(repoPath)),
  }));
}

function loadHubRepoRegistry(controlRoot) {
  return listHubRepos(controlRoot).filter((entry) => !entry.hidden).map((entry) => entry.path);
}

function resolveRepoPaths(controlRoot, watchRepos) {
  const explicit = Array.isArray(watchRepos) ? watchRepos.filter(Boolean) : [];
  const state = loadHubRepoRegistryState(controlRoot);
  const raw = explicit.length > 0 ? explicit : loadHubRepoRegistry(controlRoot);
  const candidates = explicit.length > 0 || state.exists ? raw : [controlRoot];
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

const FILE_BROWSER_IGNORED_DIRS = new Set([
  ".git",
  ".harness",
  ".next",
  ".nuxt",
  ".svelte-kit",
  ".venv",
  "__pycache__",
  "build",
  "coverage",
  "dist",
  "node_modules",
  "target",
]);

const FILE_BROWSER_PRIORITY_NAMES = new Set([
  "README.md",
  "package.json",
  "pyproject.toml",
  "requirements.txt",
  "vite.config.js",
  "next.config.js",
  "tsconfig.json",
]);

const FILE_BROWSER_PRIORITY_EXTS = new Set([
  ".js",
  ".jsx",
  ".ts",
  ".tsx",
  ".py",
  ".md",
  ".json",
  ".css",
  ".html",
  ".toml",
  ".yml",
  ".yaml",
]);

function repoRelativePath(repoRoot, fullPath) {
  return path.relative(repoRoot, fullPath).split(path.sep).join("/");
}

function fileBrowserScore(file) {
  let score = file.depth * 20;
  if (FILE_BROWSER_PRIORITY_NAMES.has(file.name)) {
    score -= 80;
  }
  if (FILE_BROWSER_PRIORITY_EXTS.has(file.ext)) {
    score -= 30;
  }
  if (file.path.includes("/src/") || file.path.startsWith("src/")) {
    score -= 20;
  }
  if (file.path.includes("/test") || file.path.includes("/tests/")) {
    score += 10;
  }
  return score;
}

function listRepoFiles(repoRoot, options = {}) {
  const root = path.resolve(String(repoRoot || ""));
  const limit = Math.max(1, Math.min(500, Number.parseInt(options.limit, 10) || 180));
  const maxDepth = Math.max(1, Math.min(10, Number.parseInt(options.maxDepth, 10) || 6));
  const found = [];
  let visited = 0;
  const maxVisited = Math.max(limit * 25, 1000);

  function walk(dir, depth) {
    if (depth > maxDepth || visited >= maxVisited) {
      return;
    }
    let entries = [];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch (_err) {
      return;
    }
    entries.sort((left, right) => {
      if (left.isDirectory() !== right.isDirectory()) {
        return left.isDirectory() ? -1 : 1;
      }
      return left.name.localeCompare(right.name);
    });
    for (const entry of entries) {
      if (visited >= maxVisited) {
        break;
      }
      const fullPath = path.join(dir, entry.name);
      visited += 1;
      if (entry.isDirectory()) {
        if (!FILE_BROWSER_IGNORED_DIRS.has(entry.name)) {
          walk(fullPath, depth + 1);
        }
        continue;
      }
      if (!entry.isFile()) {
        continue;
      }
      const relative = repoRelativePath(root, fullPath);
      found.push({
        path: relative,
        name: entry.name,
        ext: path.extname(entry.name).toLowerCase(),
        depth,
      });
    }
  }

  walk(root, 0);
  return found
    .sort((left, right) => fileBrowserScore(left) - fileBrowserScore(right) || left.path.localeCompare(right.path))
    .slice(0, limit);
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
    if (state === "killed") {
      return false;
    }
    if (state === "done") {
      const updatedAt = Date.parse(String(agent.updated_at || agent.heartbeat_at || ""));
      return Number.isFinite(updatedAt) && Date.now() - updatedAt < DONE_AGENT_VISIBLE_MS;
    }
    return true;
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
    return {
      ...base,
      error: "repo_missing",
      phase: "offline",
      presentation: presentation.unavailablePresentation(base.project, "repo_missing"),
    };
  }
  const configPath = path.join(harnessRoot(repoRoot), "config.json");
  if (!fs.existsSync(configPath)) {
    return {
      ...base,
      error: "harness_not_initialized",
      phase: "offline",
      presentation: presentation.unavailablePresentation(base.project, "harness_not_initialized"),
    };
  }
  const config = loadRepoConfig(repoRoot);
  const tasks = arrayFromPayload(readJson(path.join(harnessRoot(repoRoot), "tasks", "index.json"), { tasks: [] }), ["tasks"]);
  const queue = arrayFromPayload(readJson(path.join(harnessRoot(repoRoot), "queue", "index.json"), { queue: [] }), ["queue", "items"]);
  const agents = decorateAgents(repoRoot, loadAgents(repoRoot), ptyManager);
  const hubConfig = mergeHubConfig(config);
  const events = readJsonlTail(path.join(harnessRoot(repoRoot), "events.jsonl"), 30);
  const security = readJson(path.join(harnessRoot(repoRoot), "security", "scan-latest.json"), {});
  const projectPresentation = presentation.buildProjectPresentation(repoRoot, config, tasks, queue, events, security);
  const activeTaskId = String((projectPresentation.current && projectPresentation.current.id) || "");
  const activeTask = tasks.find((task) => String(task.task_id || "") === activeTaskId) || null;
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
      done: tasks.filter((task) => ["passed", "done"].includes(String(task.status || ""))).length,
      agents: agents.length,
      security_findings: Array.isArray(security.findings) ? security.findings.length : 0,
    },
    active_task: activeTask,
    tasks: tasks.slice(-10),
    queue: queue.slice(-10),
    security,
    agents,
    events,
    presentation: projectPresentation,
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
  const name = String(cliName || hubConfig.default_cli || DEFAULT_HUB_CONFIG.default_cli);
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
    agent.cli || DEFAULT_HUB_CONFIG.default_cli,
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

function reactivateAgent(repoRoot, agentId, hubConfig, ptyManager) {
  const id = String(agentId || "");
  const existing = loadAgents(repoRoot).find((item) => String(item.id || "") === id);
  if (!existing) {
    throw new HttpError(404, "agent_not_found");
  }
  if (!ptyManager || !ptyManager.available) {
    throw new HttpError(503, "pty_unavailable", { error: ptyManager && ptyManager.loadError });
  }
  const liveSession = ptyManager.hasAgent(id) ? ptyManager.get(id) : null;
  if (liveSession) {
    return {
      ok: true,
      already_live: true,
      agent: existing,
      pty: ptyManager.publicSession ? ptyManager.publicSession(liveSession) : { id: existing.pty_id, agent_id: id },
      event: null,
    };
  }
  const cliLaunch = normalizeCliDefinition(hubConfig, existing.cli || hubConfig.default_cli);
  const cwd = String(existing.cwd || existing.repo_root || repoRoot);
  const ptyResult = ptyManager.spawnSession({
    agentId: id,
    command: cliLaunch.command,
    args: cliLaunch.args,
    cwd,
    idleTimeoutMs: hubConfig.pty.idle_timeout_s * 1000,
    scrollbackBytes: hubConfig.pty.scrollback_bytes,
  });
  if (!ptyResult.ok) {
    throw new HttpError(503, "pty_unavailable", ptyResult);
  }
  const ptyId = ptyResult.session.id;
  const updated = augmentAgent(repoRoot, id, {
    name: existing.name || id,
    role: existing.role || "operator",
    state: "working",
    status: "working",
    cli: cliLaunch.cli,
    sector: existing.sector || sectorForRole(existing.role),
    pty_id: ptyId,
    repo_root: repoRoot,
    cwd,
    transcript_path: existing.transcript_path || path.join(".harness", "agents", id, "transcript.jsonl"),
    spawned_by: existing.spawned_by || "ui",
    speech: "Agent reactivated from harness-hub.",
  });
  const event = appendHarnessEvent(
    repoRoot,
    "agent_reactivated",
    { agent_id: id, pty_id: ptyId, state: "working", sector: updated.sector, summary: "Agent reactivated." },
    { agentId: id }
  );
  return { ok: true, already_live: false, agent: updated, pty: ptyResult.session, event };
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
  const state = loadHubRepoRegistryState(controlRoot);
  if (!state.exists && fs.existsSync(controlRoot)) state.repos.push(path.resolve(controlRoot));
  const key = normalizePathKey(resolved);
  if (!state.repos.some((entry) => normalizePathKey(entry) === key)) state.repos.push(resolved);
  state.hidden_repos = state.hidden_repos.filter((entry) => normalizePathKey(entry) !== key);
  saveHubRepoRegistryState(controlRoot, state);
  return loadHubRepoRegistry(controlRoot);
}

function setRepoHidden(controlRoot, repoPath, hidden) {
  const resolved = path.resolve(String(repoPath || ""));
  const key = normalizePathKey(resolved);
  const state = loadHubRepoRegistryState(controlRoot);
  if (!state.repos.some((entry) => normalizePathKey(entry) === key)) {
    throw new HttpError(404, "repo_not_registered");
  }
  state.hidden_repos = state.hidden_repos.filter((entry) => normalizePathKey(entry) !== key);
  if (hidden) state.hidden_repos.push(resolved);
  saveHubRepoRegistryState(controlRoot, state);
  return listHubRepos(controlRoot);
}

function removeRepo(controlRoot, repoPath) {
  const key = normalizePathKey(path.resolve(String(repoPath || "")));
  const state = loadHubRepoRegistryState(controlRoot);
  state.repos = state.repos.filter((entry) => normalizePathKey(entry) !== key);
  state.hidden_repos = state.hidden_repos.filter((entry) => normalizePathKey(entry) !== key);
  saveHubRepoRegistryState(controlRoot, state);
  return listHubRepos(controlRoot);
}

function setRemoteExecution(repoRoot, enabled) {
  const cfgPath = path.join(harnessRoot(repoRoot), "config.json");
  const cfg = readJson(cfgPath, {});
  cfg.hub = { ...(cfg.hub && typeof cfg.hub === "object" ? cfg.hub : {}), allow_remote_execution: Boolean(enabled) };
  writeJsonAtomic(cfgPath, cfg);
  return cfg.hub;
}

// Create a brand-new project folder from zero: mkdir, harness init, enable the
// hub remote-execution gate, and register it with the control repo.
async function createProject(controlRoot, parentDir, name) {
  const safeName = String(name || "").trim();
  if (!safeName || /[\\/:*?"<>|]/.test(safeName)) {
    throw new HttpError(400, "invalid_project_name");
  }
  const parent = path.resolve(String(parentDir || ""));
  if (!fs.existsSync(parent) || !fs.statSync(parent).isDirectory()) {
    throw new HttpError(400, "parent_dir_missing", { parent });
  }
  const target = path.join(parent, safeName);
  fs.mkdirSync(target, { recursive: true });
  if (!fs.existsSync(path.join(harnessRoot(target), "config.json"))) {
    await runHarnessCli(target, ["init", "--name", safeName]);
  }
  setRemoteExecution(target, true);
  await runHarnessCli(controlRoot, ["dashboard", "hub-add-repo", target]);
  return { repo: target, repos: loadHubRepoRegistry(controlRoot) };
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
  createProject,
  setRemoteExecution,
  appendHarnessEvent,
  augmentAgent,
  collectWorld,
  findAgentRepo,
  findConfiguredRepo,
  harnessRoot,
  listRepoFiles,
  loadAgents,
  loadHubRepoRegistry,
  listHubRepos,
  loadRepoConfig,
  makeAgentId,
  mergeHubConfig,
  removeRepo,
  normalizeCliDefinition,
  setRepoHidden,
  normalizePathKey,
  readNewEventsForRepos,
  reactivateAgent,
  registerAgent,
  resolveRepoPaths,
  runHarnessCli,
  sectorForRole,
  killAgent,
  utcNow,
  sendAgentMessage,
};
