"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const security = require("./security");

test("loopback address normalization covers Node socket forms", () => {
  assert.equal(security.isLoopbackAddress("127.0.0.1"), true);
  assert.equal(security.isLoopbackAddress("::1"), true);
  assert.equal(security.isLoopbackAddress("::ffff:127.0.0.1"), true);
  assert.equal(security.isLoopbackAddress("localhost"), true);
  assert.equal(security.isLoopbackAddress("192.168.1.10"), false);
});

test("origin validation allows loopback origins only", () => {
  assert.equal(security.originAllowed("http://127.0.0.1:8899"), true);
  assert.equal(security.originAllowed("http://localhost:8899"), true);
  assert.equal(security.originAllowed("http://example.com"), false);
  assert.equal(security.originAllowed("not a url"), false);
});

test("remote execution gate only reads hub.allow_remote_execution", () => {
  assert.equal(security.remoteExecutionAllowed({ hub: { allow_remote_execution: true } }), true);
  assert.equal(security.remoteExecutionAllowed({ hub: { allow_remote_execution: false } }), false);
  assert.equal(security.remoteExecutionAllowed({ telegram: { allow_remote_execution: true } }), false);
});

test("mutable request authorization requires the token header", () => {
  const req = { headers: {}, socket: { remoteAddress: "127.0.0.1" } };
  const url = new URL("http://127.0.0.1/api/agents/spawn?token=secret");
  assert.equal(security.authorizeRequest(req, "secret", url).ok, false);
  req.headers["x-harness-hub-token"] = "secret";
  assert.equal(security.authorizeRequest(req, "secret", url).ok, true);
});

test("websocket authorization accepts loopback query token for browser clients", () => {
  const req = { headers: { origin: "http://127.0.0.1:8899" }, socket: { remoteAddress: "127.0.0.1" } };
  const url = new URL("http://127.0.0.1/ws/term?agent=a&token=secret");
  assert.equal(security.authorizeWebSocket(req, "secret", url).ok, true);
});
