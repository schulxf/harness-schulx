"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const http = require("node:http");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { createServer } = require("./index");

function makeControlRepo() {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harness-hub-index-"));
  fs.mkdirSync(path.join(root, ".harness"), { recursive: true });
  fs.writeFileSync(path.join(root, ".harness", "config.json"), JSON.stringify({ project_name: "Control" }), "utf8");
  return root;
}

function get(port, requestPath, headers = {}) {
  return new Promise((resolve, reject) => {
    http.get({ host: "127.0.0.1", port, path: requestPath, headers }, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body }));
    }).on("error", reject);
  });
}

test("served index injects the local hub token for same-origin browser actions", async (t) => {
  const { server } = createServer({
    repo: makeControlRepo(),
    watchRepos: [],
    token: "unit-token",
  });
  t.after(() => server.close());

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  const response = await get(port, "/");

  assert.equal(response.status, 200);
  assert.match(response.body, /window\.HARNESS_HUB_TOKEN="unit-token"/);
  assert.equal(response.headers["cache-control"], "no-store");
});

test("repo files endpoint requires token and lists registered repo files", async (t) => {
  const repo = makeControlRepo();
  fs.mkdirSync(path.join(repo, "src"), { recursive: true });
  fs.writeFileSync(path.join(repo, "src", "app.js"), "console.log('ok');\n", "utf8");
  const { server } = createServer({
    repo,
    watchRepos: [],
    token: "unit-token",
  });
  t.after(() => server.close());

  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address();
  const denied = await get(port, `/api/repo-files?repo=${encodeURIComponent(repo)}`);
  const allowed = await get(port, `/api/repo-files?repo=${encodeURIComponent(repo)}`, {
    "X-Harness-Hub-Token": "unit-token",
  });
  const payload = JSON.parse(allowed.body);

  assert.equal(denied.status, 403);
  assert.equal(allowed.status, 200);
  assert.ok(payload.files.some((file) => file.path === "src/app.js"));
});
