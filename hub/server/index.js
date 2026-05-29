"use strict";

const crypto = require("crypto");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { WebSocketServer } = require("ws");

const harness = require("./harness");
const { PtyManager } = require("./pty");
const security = require("./security");

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".gif": "image/gif",
  ".svg": "image/svg+xml",
  ".wasm": "application/wasm",
  ".md": "text/markdown; charset=utf-8",
};

function parseArgs(argv) {
  const options = {
    host: "127.0.0.1",
    port: 8899,
    repo: process.cwd(),
    watchRepos: [],
    token: process.env.HARNESS_HUB_TOKEN || crypto.randomBytes(24).toString("hex"),
  };
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--host") {
      options.host = argv[++index] || options.host;
    } else if (arg === "--port") {
      options.port = Number.parseInt(argv[++index], 10) || options.port;
    } else if (arg === "--repo") {
      options.repo = path.resolve(argv[++index] || options.repo);
    } else if (arg === "--watch-repo") {
      options.watchRepos.push(path.resolve(argv[++index] || ""));
    } else if (arg === "--token") {
      options.token = String(argv[++index] || options.token);
    }
  }
  options.repo = path.resolve(options.repo);
  options.watchRepos = options.watchRepos.filter(Boolean);
  return options;
}

function sendJson(res, status, payload) {
  const body = Buffer.from(`${JSON.stringify(payload, null, 2)}\n`, "utf8");
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "Content-Length": body.length,
  });
  res.end(body);
}

function applyCors(req, res) {
  const origin = req.headers.origin || "";
  if (!security.originAllowed(origin)) {
    return;
  }
  if (origin) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
  }
  res.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type, X-Harness-Hub-Token");
}

function sendError(res, err) {
  const status = err && err.status ? err.status : 500;
  const payload = {
    ok: false,
    error: err && err.message ? err.message : "internal_server_error",
  };
  if (err && err.details) {
    payload.details = err.details;
  }
  sendJson(res, status, payload);
}

function readJsonBody(req, maxBytes) {
  const limit = maxBytes || 1024 * 1024;
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > limit) {
        reject(new harness.HttpError(413, "request_body_too_large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      if (chunks.length === 0) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
      } catch (err) {
        reject(new harness.HttpError(400, "invalid_json", { error: err.message }));
      }
    });
    req.on("error", reject);
  });
}

function localApiOnly(req, res) {
  if (!security.isLoopbackAddress(security.remoteAddressFromRequest(req))) {
    sendJson(res, 403, { ok: false, error: "loopback_required" });
    return false;
  }
  return true;
}

function mutableAuthorized(req, res, token, urlObject) {
  const auth = security.authorizeRequest(req, token, urlObject);
  if (!auth.ok) {
    sendJson(res, auth.status, { ok: false, error: auth.error });
    return false;
  }
  return true;
}

function safeStaticPath(clientRoot, requestPath) {
  const pathname = requestPath === "/" ? "/index.html" : requestPath;
  const decoded = decodeURIComponent(pathname);
  const candidate = path.resolve(clientRoot, `.${decoded}`);
  if (candidate !== clientRoot && !candidate.startsWith(`${clientRoot}${path.sep}`)) {
    return "";
  }
  return candidate;
}

function serveStatic(req, res, clientRoot, urlObject) {
  const filePath = safeStaticPath(clientRoot, urlObject.pathname);
  if (!filePath || !fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
    sendJson(res, 404, { ok: false, error: "static_asset_not_found" });
    return;
  }
  const ext = path.extname(filePath).toLowerCase();
  res.writeHead(200, {
    "Content-Type": MIME_TYPES[ext] || "application/octet-stream",
    "Cache-Control": "no-store",
  });
  fs.createReadStream(filePath).pipe(res);
}

function requireRemoteExecution(repoRoot) {
  const config = harness.loadRepoConfig(repoRoot);
  if (!security.remoteExecutionAllowed(config)) {
    throw new harness.HttpError(403, "hub_remote_execution_disabled");
  }
  return harness.mergeHubConfig(config);
}

async function handleSpawn(body, context) {
  const repoRoot = harness.findConfiguredRepo(context.controlRoot, context.watchRepos, body.repo);
  const hubConfig = requireRemoteExecution(repoRoot);
  if (context.ptyManager.liveCount() >= hubConfig.max_agents) {
    throw new harness.HttpError(409, "hub_max_agents_reached", { max_agents: hubConfig.max_agents });
  }
  const role = String(body.role || "operator").trim() || "operator";
  const cliLaunch = harness.normalizeCliDefinition(hubConfig, body.cli || hubConfig.default_cli);
  const agentId = harness.makeAgentId(role);
  const sector = String(body.sector || harness.sectorForRole(role));
  const name = String(body.name || `${role}-${agentId.slice(-6)}`);
  const cwd = repoRoot;
  const ptyResult = context.ptyManager.spawnSession({
    agentId,
    command: cliLaunch.command,
    args: cliLaunch.args,
    cwd,
    idleTimeoutMs: hubConfig.pty.idle_timeout_s * 1000,
    scrollbackBytes: hubConfig.pty.scrollback_bytes,
  });
  if (!ptyResult.ok) {
    throw new harness.HttpError(503, "pty_unavailable", ptyResult);
  }
  const ptyId = ptyResult.session.id;
  const transcriptPath = path.join(".harness", "agents", agentId, "transcript.jsonl");
  const agent = {
    id: agentId,
    name,
    role,
    state: "working",
    status: "working",
    cli: cliLaunch.cli,
    sector,
    pty_id: ptyId,
    repo_root: repoRoot,
    cwd,
    transcript_path: transcriptPath,
    spawned_by: "ui",
    speech: "Agent spawned from harness-hub.",
  };
  try {
    const registered = await harness.registerAgent(repoRoot, agent);
    const attachedEvent = harness.appendHarnessEvent(
      repoRoot,
      "agent_terminal_attached",
      { agent_id: agentId, pty_id: ptyId, summary: "Terminal attached." },
      { agentId }
    );
    return {
      ok: true,
      agent: registered,
      pty: ptyResult.session,
      event: attachedEvent,
    };
  } catch (err) {
    context.ptyManager.kill(agentId);
    throw err;
  }
}

async function repoForAgentOrBody(agentId, body, context) {
  const fromRegistry = harness.findAgentRepo(context.controlRoot, context.watchRepos, agentId);
  if (fromRegistry) {
    return fromRegistry;
  }
  if (body.repo) {
    return harness.findConfiguredRepo(context.controlRoot, context.watchRepos, body.repo);
  }
  throw new harness.HttpError(404, "agent_not_found");
}

async function handleMessage(agentId, body, context) {
  const repoRoot = await repoForAgentOrBody(agentId, body, context);
  requireRemoteExecution(repoRoot);
  const to = String(body.to || "").trim();
  const text = String(body.text || "").trim();
  if (!to) {
    throw new harness.HttpError(400, "message_target_required");
  }
  if (!text) {
    throw new harness.HttpError(400, "message_text_required");
  }
  if (text.length > 4000) {
    throw new harness.HttpError(413, "message_text_too_large");
  }
  const message = await harness.sendAgentMessage(repoRoot, agentId, to, text);
  return { ok: true, message };
}

async function handleKill(agentId, body, context) {
  const repoRoot = await repoForAgentOrBody(agentId, body, context);
  requireRemoteExecution(repoRoot);
  const killedPty = context.ptyManager.kill(agentId);
  let agent = null;
  try {
    agent = await harness.killAgent(repoRoot, agentId, "Agent killed by harness-hub.");
  } catch (err) {
    if (!(err instanceof harness.HttpError)) {
      throw err;
    }
  }
  return { ok: true, killed_pty: killedPty, agent };
}

async function handleAddRepo(body, context) {
  const repoPath = body.path;
  if (!repoPath) {
    throw new harness.HttpError(400, "repo_path_required");
  }
  const repos = await harness.addRepo(context.controlRoot, repoPath);
  return { ok: true, repos };
}

async function handleCreateProject(body, context) {
  if (!body.parent) {
    throw new harness.HttpError(400, "parent_dir_required");
  }
  if (!body.name) {
    throw new harness.HttpError(400, "project_name_required");
  }
  const result = await harness.createProject(context.controlRoot, body.parent, body.name);
  return { ok: true, ...result };
}

function writeSse(res, eventName, payload, id) {
  if (id) {
    res.write(`id: ${id}\n`);
  }
  if (eventName) {
    res.write(`event: ${eventName}\n`);
  }
  const data = JSON.stringify(payload);
  for (const line of data.split(/\r?\n/)) {
    res.write(`data: ${line}\n`);
  }
  res.write("\n");
}

function handleEvents(req, res, urlObject, context) {
  if (!localApiOnly(req, res)) {
    return;
  }
  const repoRoots = harness.resolveRepoPaths(context.controlRoot, context.watchRepos);
  let cursor = urlObject.searchParams.get("cursor") || urlObject.searchParams.get("offset") || "0";
  res.writeHead(200, {
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-store, no-transform",
    Connection: "keep-alive",
    "X-Accel-Buffering": "no",
  });
  writeSse(res, "hello", { ok: true, repo_count: repoRoots.length }, undefined);
  const tick = () => {
    const batch = harness.readNewEventsForRepos(repoRoots, cursor);
    cursor = batch.cursor;
    if (batch.events.length > 0) {
      writeSse(res, "events", batch, batch.cursor);
    } else {
      res.write(": heartbeat\n\n");
    }
  };
  tick();
  const timer = setInterval(tick, 1000);
  req.on("close", () => clearInterval(timer));
}

async function routeRequest(req, res, context) {
  applyCors(req, res);
  const urlObject = new URL(req.url, `http://${req.headers.host || "127.0.0.1"}`);
  if (req.method === "OPTIONS") {
    res.writeHead(204, { "Cache-Control": "no-store" });
    res.end();
    return;
  }
  if (req.method === "GET" && urlObject.pathname === "/api/world") {
    if (!localApiOnly(req, res)) {
      return;
    }
    sendJson(res, 200, harness.collectWorld(context));
    return;
  }
  if (req.method === "GET" && urlObject.pathname === "/api/events") {
    handleEvents(req, res, urlObject, context);
    return;
  }
  if (req.method === "POST") {
    if (!mutableAuthorized(req, res, context.token, urlObject)) {
      return;
    }
    const body = await readJsonBody(req);
    if (urlObject.pathname === "/api/agents/spawn") {
      sendJson(res, 201, await handleSpawn(body, context));
      return;
    }
    const messageMatch = urlObject.pathname.match(/^\/api\/agents\/([^/]+)\/message$/);
    if (messageMatch) {
      sendJson(res, 200, await handleMessage(decodeURIComponent(messageMatch[1]), body, context));
      return;
    }
    const killMatch = urlObject.pathname.match(/^\/api\/agents\/([^/]+)\/kill$/);
    if (killMatch) {
      sendJson(res, 200, await handleKill(decodeURIComponent(killMatch[1]), body, context));
      return;
    }
    if (urlObject.pathname === "/api/repos/add") {
      sendJson(res, 200, await handleAddRepo(body, context));
      return;
    }
    if (urlObject.pathname === "/api/projects/create") {
      sendJson(res, 201, await handleCreateProject(body, context));
      return;
    }
    sendJson(res, 404, { ok: false, error: "not_found" });
    return;
  }
  if (req.method === "GET") {
    serveStatic(req, res, context.clientRoot, urlObject);
    return;
  }
  sendJson(res, 405, { ok: false, error: "method_not_allowed" });
}

function rejectUpgrade(socket, status, message) {
  socket.write(`HTTP/1.1 ${status} ${message}\r\nConnection: close\r\n\r\n`);
  socket.destroy();
}

function createServer(options) {
  const ptyManager = new PtyManager();
  const context = {
    controlRoot: options.repo,
    watchRepos: options.watchRepos,
    token: options.token,
    clientRoot: path.resolve(__dirname, "..", "client"),
    ptyManager,
  };
  const server = http.createServer((req, res) => {
    routeRequest(req, res, context).catch((err) => sendError(res, err));
  });
  const wss = new WebSocketServer({ noServer: true });
  server.on("upgrade", (req, socket, head) => {
    const urlObject = new URL(req.url, `http://${req.headers.host || "127.0.0.1"}`);
    if (urlObject.pathname !== "/ws/term") {
      rejectUpgrade(socket, 404, "Not Found");
      return;
    }
    const auth = security.authorizeWebSocket(req, context.token, urlObject);
    if (!auth.ok) {
      rejectUpgrade(socket, auth.status, auth.error);
      return;
    }
    const agentId = urlObject.searchParams.get("agent");
    if (!agentId || !context.ptyManager.get(agentId)) {
      rejectUpgrade(socket, 404, "Agent Not Found");
      return;
    }
    wss.handleUpgrade(req, socket, head, (ws) => {
      context.ptyManager.attach(agentId, ws);
    });
  });
  server.on("close", () => ptyManager.close());
  return { server, context };
}

function main() {
  const options = parseArgs(process.argv.slice(2));
  const { server, context } = createServer(options);
  server.listen(options.port, options.host, () => {
    const address = server.address();
    const port = typeof address === "object" && address ? address.port : options.port;
    console.log(`Harness Hub listening on http://${options.host}:${port}/`);
    console.log(`Control repo: ${context.controlRoot}`);
    for (const repoRoot of harness.resolveRepoPaths(context.controlRoot, context.watchRepos)) {
      console.log(`Watching repo: ${repoRoot}`);
    }
    console.log(`Hub token: ${context.token}`);
    if (!context.ptyManager.available) {
      console.log(`PTY unavailable: ${context.ptyManager.loadError}`);
    }
  });
}

if (require.main === module) {
  main();
}

module.exports = {
  createServer,
  parseArgs,
};
