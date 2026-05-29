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
  const world = harness.collectWorld({ controlRoot: repo, watchRepos: [], ptyManager: { available: false, hasAgent: () => false } });
  assert.equal(world.repo_count, 1);
  assert.equal(world.repos[0].project, "Demo Repo");
  assert.equal(world.repos[0].agents.length, 1);
  assert.equal(world.repos[0].agents[0].state, "offline");
  assert.equal(world.repos[0].agents[0].sector, "implement");
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
