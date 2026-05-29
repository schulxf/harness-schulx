import { AgentLayer } from "./agents.js";
import { HubClient } from "./net.js";
import { drawOverworld, hitTestBuilding, repoBuildings } from "./overworld.js";
import { drawRepoMap, hitTestSector } from "./render.js";
import { detectSpriteAssets } from "./sprites.js";
import { TerminalOverlay } from "./terminal.js";
import { applyWorldEvent, buildWorldState, findRepo, sectorByKey, sectorCenter, WORLD_HEIGHT, WORLD_WIDTH } from "./world.js";
import { HubUI } from "./ui.js";

const canvas = document.getElementById("gameCanvas");
const viewport = document.getElementById("gameViewport");
const ctx = canvas.getContext("2d");

let world = buildWorldState();
let selectedRepoId = world.repos[0]?.id || "";
let selectedAgentId = "";
let selectedSector = "";
let mode = world.repos.length > 1 ? "overworld" : "map";
let lastTime = performance.now();
let connection = { state: "connecting", label: "Connecting" };

const hub = new HubClient({
  onStatus(status) {
    connection = status;
    ui.setConnection(status);
  },
  onEvent(event) {
    handleHubEvent(event);
  },
});

const terminal = new TerminalOverlay(document.getElementById("terminalOverlay"));

const agents = new AgentLayer(document.getElementById("agentLayer"), {
  onSelect(agent, repo) {
    selectedRepoId = repo.id;
    selectedAgentId = agent.id;
    mode = "map";
    renderUi();
  },
});

const ui = new HubUI({
  selectRepo(repoId) {
    selectedRepoId = repoId;
    selectedAgentId = "";
    selectedSector = "";
    mode = "map";
    renderUi();
  },
  selectAgent(agentId) {
    selectedAgentId = agentId;
    mode = "map";
    renderUi();
  },
  refresh: refreshWorld,
  toggleView() {
    mode = mode === "overworld" ? "map" : "overworld";
    selectedAgentId = "";
    renderUi();
  },
  spawnAgent: spawnAgent,
  addRepo: addRepo,
  sendMessage: sendMessage,
  openTerminal: openSelectedTerminal,
  killAgent: killSelectedAgent,
});

function selectedRepo() {
  return findRepo(world, selectedRepoId);
}

function selectedAgent() {
  const repo = selectedRepo();
  return repo?.agents.find((agent) => agent.id === selectedAgentId) || null;
}

function canvasPoint(event) {
  const rect = canvas.getBoundingClientRect();
  return {
    x: ((event.clientX - rect.left) / rect.width) * WORLD_WIDTH,
    y: ((event.clientY - rect.top) / rect.height) * WORLD_HEIGHT,
  };
}

function stageItems() {
  if (mode === "overworld") {
    const buildings = repoBuildings(world.repos);
    return buildings.flatMap((building) => (
      building.repo.agents.slice(0, 4).map((agent, index) => ({
        agent,
        repo: building.repo,
        building,
        localIndex: index,
      }))
    ));
  }
  const repo = selectedRepo();
  return (repo?.agents || []).map((agent, index) => ({ agent, repo, localIndex: index }));
}

function targetResolver(item, index) {
  if (mode === "overworld") {
    const point = {
      x: item.building.x + 36 + (item.localIndex % 4) * 44,
      y: item.building.y + item.building.h + 34,
    };
    return {
      point,
      spawn: { x: item.building.x + item.building.w / 2, y: item.building.y + item.building.h / 2 },
      wanderRect: { x: point.x - 28, y: point.y - 22, w: 72, h: 48 },
    };
  }
  const repo = item.repo;
  const sector = sectorByKey(repo, item.agent.sector) || sectorByKey(repo, "idle") || repo.sectors[0];
  return {
    point: sectorCenter(sector, index),
    spawn: sectorCenter(sectorByKey(repo, "idle") || sector, index),
    wanderRect: sector,
  };
}

function renderUi() {
  const repo = selectedRepo();
  ui.setConnection(connection);
  ui.render({
    world,
    selectedRepo: repo,
    selectedAgent: selectedAgent(),
    mode,
    selectedSector,
  });
}

function renderFrame(now) {
  const dt = Math.min(.05, (now - lastTime) / 1000);
  lastTime = now;

  const items = stageItems();
  const stageKey = `${mode}:${selectedRepoId}`;
  agents.reconcile(items, targetResolver, selectedAgentId, stageKey);
  agents.update(dt);

  if (mode === "overworld") {
    drawOverworld(ctx, world, selectedRepoId);
  } else {
    const repo = selectedRepo();
    if (repo) drawRepoMap(ctx, repo, { selectedSector, paths: agents.paths() });
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
  if (!findRepo(world, selectedRepoId)) selectedRepoId = world.repos[0]?.id || "";
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
      cli: data.cli || "codex",
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
    await hub.postJson(`/api/agents/${encodeURIComponent(agent.id)}/message`, {
      to: data.to,
      text: data.text,
    });
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

function openSelectedTerminal() {
  const agent = selectedAgent();
  const repo = selectedRepo();
  if (!agent || !repo) return;
  terminal.open(agent, repo, hub.token || world.action_token || "");
}

viewport.addEventListener("click", (event) => {
  const point = canvasPoint(event);
  if (mode === "overworld") {
    const building = hitTestBuilding(world.repos, point);
    if (building) {
      selectedRepoId = building.repo.id;
      selectedAgentId = "";
      selectedSector = "";
      mode = "map";
      renderUi();
    }
    return;
  }
  const repo = selectedRepo();
  const sector = hitTestSector(repo, point);
  selectedSector = sector?.key || "";
  if (!sector) selectedAgentId = "";
  renderUi();
});

viewport.addEventListener("keydown", (event) => {
  if (event.key === "Escape") {
    selectedAgentId = "";
    selectedSector = "";
    renderUi();
  }
  if (event.key.toLowerCase() === "w") {
    mode = "overworld";
    selectedAgentId = "";
    renderUi();
  }
});

detectSpriteAssets();
refreshWorld().then(() => {
  hub.startEvents(0);
  requestAnimationFrame(renderFrame);
});
