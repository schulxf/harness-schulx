"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const harness = require("./harness");

function makeRepo() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-hub-"));
  fs.mkdirSync(path.join(root, ".harness", "agents"), { recursive: true });
  fs.mkdirSync(path.join(root, ".harness", "tasks"), { recursive: true });
  fs.mkdirSync(path.join(root, ".harness", "queue"), { recursive: true });
  fs.writeFileSync(
    path.join(root, ".harness", "config.json"),
    JSON.stringify({
      project_name: "Demo Repo",
      hub: { allow_remote_execution: true, max_agents: 2, default_cli: "codex" },
    }),
    "utf8"
  );
  fs.writeFileSync(path.join(root, ".harness", "tasks", "index.json"), JSON.stringify({ tasks: [{ task_id: "TASK-1" }] }), "utf8");
  fs.writeFileSync(path.join(root, ".harness", "queue", "index.json"), JSON.stringify({ queue: [] }), "utf8");
  return root;
}

test("collectWorld reads .harness state and marks dead PTY agents offline", () => {
  const repo = makeRepo();
  harness.augmentAgent(repo, "builder-1", {
    name: "Builder",
    role: "builder",
    state: "working",
    status: "working",
    pty_id: "pty-dead",
  });
  harness.augmentAgent(repo, "done-1", {
    name: "Done",
    role: "reviewer",
    state: "done",
    status: "done",
  });
  harness.augmentAgent(repo, "stale-done-1", {
    name: "Stale Done",
    role: "reviewer",
    state: "done",
    status: "done",
  });
  const registryPath = path.join(repo, ".harness", "agents", "registry.json");
  const registry = JSON.parse(fs.readFileSync(registryPath, "utf8"));
  registry.agents.find((agent) => agent.id === "stale-done-1").updated_at = "2000-01-01T00:00:00Z";
  fs.writeFileSync(registryPath, JSON.stringify(registry), "utf8");
  const world = harness.collectWorld({ controlRoot: repo, watchRepos: [], ptyManager: { available: false, hasAgent: () => false } });
  assert.equal(world.repo_count, 1);
  assert.equal(world.repos[0].project, "Demo Repo");
  assert.equal(world.repos[0].agents.length, 2);
  assert.equal(world.repos[0].agents[0].state, "offline");
  assert.equal(world.repos[0].agents[0].sector, "implement");
  assert.equal(world.repos[0].agents[1].state, "done");
});

test("readNewEventsForRepos tails events.jsonl by offset", () => {
  const repo = makeRepo();
  harness.appendHarnessEvent(repo, "agent_message", { from_agent: "a", to_agent: "b", text: "hello" }, { agentId: "a" });
  const first = harness.readNewEventsForRepos([repo], "0");
  assert.equal(first.events.length, 1);
  assert.equal(first.events[0].type, "agent_message");
  const second = harness.readNewEventsForRepos([repo], String(first.offset));
  assert.equal(second.events.length, 0);
});

test("listRepoFiles returns useful files and skips generated state", () => {
  const repo = makeRepo();
  fs.mkdirSync(path.join(repo, "src"), { recursive: true });
  fs.mkdirSync(path.join(repo, "node_modules", "pkg"), { recursive: true });
  fs.writeFileSync(path.join(repo, "README.md"), "# Demo\n", "utf8");
  fs.writeFileSync(path.join(repo, "src", "app.js"), "console.log('ok');\n", "utf8");
  fs.writeFileSync(path.join(repo, "node_modules", "pkg", "index.js"), "", "utf8");
  fs.writeFileSync(path.join(repo, ".harness", "internal.txt"), "", "utf8");

  const files = harness.listRepoFiles(repo, { limit: 20 }).map((file) => file.path);

  assert.ok(files.includes("README.md"));
  assert.ok(files.includes("src/app.js"));
  assert.equal(files.some((file) => file.startsWith(".harness/")), false);
  assert.equal(files.some((file) => file.startsWith("node_modules/")), false);
});

test("repo registry can hide, show and remove a path without touching its files", async () => {
  const control = makeRepo();
  const watched = fs.mkdtempSync(path.join(os.tmpdir(), "harness-hub-watched-"));
  const marker = path.join(watched, "preservar.txt");
  fs.writeFileSync(marker, "conteúdo do usuário", "utf8");

  await harness.addRepo(control, watched);
  harness.setRepoHidden(control, watched, true);

  assert.deepEqual(harness.loadHubRepoRegistry(control), [control]);
  assert.deepEqual(harness.listHubRepos(control).find((entry) => entry.path === watched), {
    path: watched,
    hidden: true,
  });

  harness.setRepoHidden(control, watched, false);
  assert.ok(harness.loadHubRepoRegistry(control).includes(watched));

  harness.removeRepo(control, watched);
  assert.equal(fs.readFileSync(marker, "utf8"), "conteúdo do usuário");
  assert.equal(harness.listHubRepos(control).some((entry) => entry.path === watched), false);
});

test("reactivateAgent starts a new PTY for an existing offline agent", () => {
  const repo = makeRepo();
  harness.augmentAgent(repo, "builder-1", {
    name: "Builder",
    role: "builder",
    state: "offline",
    status: "offline",
    cli: "shell",
    sector: "implement",
    pty_id: "pty-old",
    cwd: repo,
  });
  const fakePty = {
    available: true,
    hasAgent: () => false,
    get: () => null,
    spawnSession(options) {
      return {
        ok: true,
        session: {
          id: "pty-new",
          agent_id: options.agentId,
          command: options.command,
          args: options.args,
          cwd: options.cwd,
          exit_code: null,
        },
      };
    },
  };

  const result = harness.reactivateAgent(repo, "builder-1", harness.mergeHubConfig(harness.loadRepoConfig(repo)), fakePty);
  const updated = harness.loadAgents(repo).find((agent) => agent.id === "builder-1");

  assert.equal(result.ok, true);
  assert.equal(result.agent.id, "builder-1");
  assert.equal(result.agent.state, "working");
  assert.equal(result.agent.pty_id, "pty-new");
  assert.equal(result.event.type, "agent_reactivated");
  assert.equal(updated.pty_id, "pty-new");
  assert.equal(updated.status, "working");
});
