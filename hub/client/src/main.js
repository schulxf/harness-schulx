import { AgentLayer } from "./agents.js";
import { HubClient } from "./net.js";
import { drawRepoMap, hitTestSector, ensureTown, sheetKeyForRepo, WORLD_WIDTH, WORLD_HEIGHT } from "./render.js";
import { AgentTerminal } from "./terminal.js";
import { applyWorldEvent, buildWorldState, findRepo } from "./world.js";
import { HubUI } from "./ui.js";
import { GameMenu } from "./menu.js";

const canvas = document.getElementById("gameCanvas");
const viewport = document.getElementById("gameViewport");
const ctx = canvas.getContext("2d");

let world = buildWorldState();
let selectedRepoId = world.repos[0]?.id || "";
let selectedAgentId = "";
let selectedSector = "";
let lastTime = performance.now();
let connection = { state: "connecting", label: "Connecting" };

const hub = new HubClient({
  onStatus(status) { connection = status; ui.setConnection(status); },
  onEvent(event) { handleHubEvent(event); },
});

const terminal = new AgentTerminal(document.getElementById("agentModal"), {
  onKill: killAgentById,
  hub,
});
const agents = new AgentLayer();

const ui = new HubUI({
  selectRepo(repoId) { selectedRepoId = repoId; selectedAgentId = ""; selectedSector = ""; renderUi(); },
  selectAgent(agentId) {
    selectedAgentId = agentId;
    renderUi();
    openTerminalFor(agentId);
  },
  refresh: refreshWorld,
  toggleView() {},
  spawnAgent,
  addRepo,
  sendMessage,
  openTerminal: openSelectedTerminal,
  killAgent: killSelectedAgent,
});

const menu = new GameMenu(document.getElementById("menuRoot"), {
  onSpawn: spawnFromMenu,
  onCreateProject: createProjectFromMenu,
  onAddRepo: addRepoFromMenu,
  onTheme: setRepoTheme,
  onEnter: renderUi,
});

document.getElementById("menuButton").addEventListener("click", () => {
  const repo = selectedRepo();
  menu.show({ repo, theme: repo ? sheetKeyForRepo(repo) : "tiny-town" });
});

function selectedRepo() { return findRepo(world, selectedRepoId); }
function selectedAgent() {
  const repo = selectedRepo();
  return repo?.agents.find((a) => a.id === selectedAgentId) || null;
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * WORLD_WIDTH,
    y: ((event.clientY - rect.top) / rect.height) * WORLD_HEIGHT,
  };
}

function renderUi() {
  ui.setConnection(connection);
  ui.render({ world, selectedRepo: selectedRepo(), selectedAgent: selectedAgent(), mode: "map", selectedSector });
}

function renderFrame(now) {
  const dt = Math.min(0.05, (now - lastTime) / 1000);
  lastTime = now;
  const repo = selectedRepo();
  if (repo) {
    const town = ensureTown(repo);
    agents.sync(repo, town);
    agents.update(dt, town);
    drawRepoMap(ctx, repo, { selectedSector });
    agents.draw(ctx, town, selectedAgentId);
  }
  requestAnimationFrame(renderFrame);
}

function handleHubEvent(event) {
  const snapshot = event?.world || (Array.isArray(event?.repos) ? event : null);
  world = snapshot ? buildWorldState(snapshot) : applyWorldEvent(world, event);
  if (!findRepo(world, selectedRepoId)) selectedRepoId = world.repos[0]?.id || "";
  renderUi();
}

async function refreshWorld() {
  world = buildWorldState(await hub.loadWorld());
  const selectedStillExists = world.repos.some((repo) => repo.id === selectedRepoId || repo.root === selectedRepoId);
  if (!selectedStillExists) {
    selectedRepoId = world.repos.find((repo) => repo.agents?.length)?.id || world.repos[0]?.id || "";
  }
  hub.setToken(world.action_token);
  renderUi();
}

async function spawnAgent(data) {
  const repo = selectedRepo();
  if (!repo) return;
  try {
    await hub.postJson("/api/agents/spawn", {
      repo: repo.root,
      role: data.role || "builder",
      cli: data.cli || "shell",
      name: data.name || undefined,
    });
    await refreshWorld();
  } catch (error) {
    connection = { state: "error", label: error.message || "Spawn failed" };
    ui.setConnection(connection);
  }
}

async function addRepo(data) {
  try {
    await hub.postJson("/api/repos/add", { path: data.path });
    await refreshWorld();
  } catch (error) {
    connection = { state: "error", label: error.message || "Add repo failed" };
    ui.setConnection(connection);
  }
}

async function sendMessage(data) {
  const agent = selectedAgent();
  if (!agent || !data.to || !data.text) return;
  try {
    await hub.postJson(`/api/agents/${encodeURIComponent(agent.id)}/message`, { to: data.to, text: data.text });
    applyWorldEvent(world, {
      type: "agent_message",
      payload: { from_agent: agent.id, to_agent: data.to, text: data.text, repo_root: selectedRepo()?.root },
    });
    renderUi();
  } catch (error) {
    connection = { state: "error", label: error.message || "Message failed" };
    ui.setConnection(connection);
  }
}

async function killSelectedAgent() {
  const agent = selectedAgent();
  if (!agent) return;
  try {
    await hub.postJson(`/api/agents/${encodeURIComponent(agent.id)}/kill`, {});
    applyWorldEvent(world, { type: "agent_killed", payload: { agent_id: agent.id, repo_root: selectedRepo()?.root } });
    selectedAgentId = "";
    renderUi();
  } catch (error) {
    connection = { state: "error", label: error.message || "Kill failed" };
    ui.setConnection(connection);
  }
}

function setRepoTheme(themeKey) {
  const repo = selectedRepo();
  if (!repo) return;
  try { window.localStorage.setItem("hubTheme:" + repo.id, themeKey); } catch (_) { /* ignore */ }
}

// --- shared helpers ---
function token() { return hub.token || world.action_token || ""; }

function openTerminalFor(agentId, repoId) {
  const repo = repoId ? findRepo(world, repoId) : selectedRepo();
  const agent = repo?.agents.find((a) => a.id === agentId);
  if (!agent || !repo) return;
  selectedRepoId = repo.id;
  selectedAgentId = agent.id;
  terminal.open(agent, repo, token());
  renderUi();
}

async function killAgentById(agentId) {
  try {
    await hub.postJson(`/api/agents/${encodeURIComponent(agentId)}/kill`, {});
  } catch (_) { /* ignore; refresh reflects reality */ }
  if (selectedAgentId === agentId) selectedAgentId = "";
  terminal.close();
  await refreshWorld();
}

// Spawn an agent in a repo and return the freshly-registered agent object.
async function doSpawn(repoRoot, { role, cli, name }) {
  const res = await hub.postJson("/api/agents/spawn", {
    repo: repoRoot, role: role || "builder", cli: cli || "shell", name: name || undefined,
  });
  await refreshWorld();
  const id = res?.agent?.id;
  const repo = findRepo(world, repoRoot);
  return repo?.agents.find((a) => a.id === id) || null;
}

// Throwing variants used by the menu so it can show inline errors.
async function spawnFromMenu({ role, cli, name, theme }) {
  const repo = selectedRepo();
  if (!repo) throw new Error("No repo selected");
  if (theme) setRepoTheme(theme);
  const agent = await doSpawn(repo.root, { role, cli, name });
  if (agent) openTerminalFor(agent.id, repo.id);
  return agent;
}

// Full from-zero flow: create folder -> init -> enable exec -> spawn -> terminal.
async function createProjectFromMenu({ parent, name, theme, role, cli }) {
  const res = await hub.postJson("/api/projects/create", { parent, name });
  await refreshWorld();
  const repo = findRepo(world, res.repo);
  if (!repo) throw new Error("Project created but not found in world");
  selectedRepoId = repo.id;
  if (theme) try { window.localStorage.setItem("hubTheme:" + repo.id, theme); } catch (_) { /* */ }
  const agent = await doSpawn(repo.root, { role: role || "builder", cli: cli || "shell", name: "" });
  renderUi();
  if (agent) openTerminalFor(agent.id, repo.id);
  return { repo, agent };
}

async function addRepoFromMenu({ path }) {
  if (!path) return;
  await hub.postJson("/api/repos/add", { path });
  await refreshWorld();
}

function openSelectedTerminal() {
  const agent = selectedAgent();
  if (agent) openTerminalFor(agent.id);
}

viewport.addEventListener("click", (event) => {
  const point = canvasPoint(event);
  const repo = selectedRepo();
  if (!repo) return;
  const agentId = agents.hitTest(point);
  if (agentId) {
    selectedAgentId = agentId;
    const sector = hitTestSector(repo, point);
    selectedSector = sector?.key || selectedSector;
    renderUi();
    openTerminalFor(agentId, repo.id); // click an agent -> open its pop-up + terminal
    return;
  }
  const sector = hitTestSector(repo, point);
  selectedSector = sector?.key || "";
  selectedAgentId = "";
  renderUi();
});

function switchRepoByIndex(i) {
  const repo = world.repos[i];
  if (!repo) return;
  selectedRepoId = repo.id;
  selectedAgentId = "";
  selectedSector = "";
  renderUi();
}

// Quick repo/map switching with number keys 1-9 (when not typing in a field).
window.addEventListener("keydown", (event) => {
  const tag = (event.target?.tagName || "").toLowerCase();
  if (tag === "input" || tag === "textarea" || tag === "select") return;
  if (event.key === "Escape") { selectedAgentId = ""; selectedSector = ""; renderUi(); return; }
  if (/^[1-9]$/.test(event.key)) switchRepoByIndex(Number(event.key) - 1);
});

refreshWorld().then(() => {
  hub.startEvents(0);
  const repo = selectedRepo();
  if (!repo || (repo.agents?.length || 0) === 0) {
    menu.show({ repo, theme: repo ? sheetKeyForRepo(repo) : "tiny-town" });
  }
  requestAnimationFrame(renderFrame);
});
