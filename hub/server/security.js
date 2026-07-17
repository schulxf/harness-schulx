"use strict";

const crypto = require("crypto");

const LOOPBACK_HOSTS = new Set(["127.0.0.1", "::1", "localhost"]);

function normalizeHost(value) {
  if (!value) {
    return "";
  }
  let host = String(value).trim().toLowerCase();
  if (host.startsWith("[")) {
    const end = host.indexOf("]");
    host = end >= 0 ? host.slice(1, end) : host.slice(1);
  } else if (host.includes(":") && host.split(":").length === 2 && /^\d+\.\d+\.\d+\.\d+:/.test(host)) {
    host = host.split(":")[0];
  }
  if (host.startsWith("::ffff:")) {
    host = host.slice("::ffff:".length);
  }
  return host;
}

function isLoopbackAddress(value) {
  const host = normalizeHost(value);
  return LOOPBACK_HOSTS.has(host);
}

function remoteAddressFromRequest(req) {
  return normalizeHost(req.socket && req.socket.remoteAddress);
}

function fixedTimeEquals(left, right) {
  const a = Buffer.from(String(left || ""), "utf8");
  const b = Buffer.from(String(right || ""), "utf8");
  if (a.length !== b.length || a.length === 0) {
    return false;
  }
  return crypto.timingSafeEqual(a, b);
}

function tokenFromRequest(req) {
  const header = req.headers["x-harness-hub-token"];
  if (Array.isArray(header)) {
    return header[0] || "";
  }
  if (header) {
    return String(header);
  }
  return "";
}

function tokenFromRequestOrQuery(req, urlObject) {
  const headerToken = tokenFromRequest(req);
  if (headerToken) {
    return headerToken;
  }
  return urlObject && urlObject.searchParams.get("token") ? String(urlObject.searchParams.get("token")) : "";
}

function authorizeRequest(req, expectedToken, urlObject) {
  const remote = remoteAddressFromRequest(req);
  if (!isLoopbackAddress(remote)) {
    return { ok: false, status: 403, error: "loopback_required" };
  }
  if (!fixedTimeEquals(tokenFromRequest(req), expectedToken)) {
    return { ok: false, status: 403, error: "invalid_hub_token" };
  }
  return { ok: true };
}

function originAllowed(origin) {
  if (!origin) {
    return true;
  }
  try {
    const parsed = new URL(origin);
    return isLoopbackAddress(parsed.hostname);
  } catch (_err) {
    return false;
  }
}

function authorizeWebSocket(req, expectedToken, urlObject) {
  const remote = remoteAddressFromRequest(req);
  if (!isLoopbackAddress(remote)) {
    return { ok: false, status: 403, error: "loopback_required" };
  }
  if (!fixedTimeEquals(tokenFromRequestOrQuery(req, urlObject), expectedToken)) {
    return { ok: false, status: 403, error: "invalid_hub_token" };
  }
  if (!originAllowed(req.headers.origin || "")) {
    return { ok: false, status: 403, error: "invalid_origin" };
  }
  return { ok: true };
}

function remoteExecutionAllowed(repoConfig) {
  return Boolean(repoConfig && repoConfig.hub && repoConfig.hub.allow_remote_execution === true);
}

module.exports = {
  authorizeRequest,
  authorizeWebSocket,
  fixedTimeEquals,
  isLoopbackAddress,
  normalizeHost,
  originAllowed,
  remoteAddressFromRequest,
  remoteExecutionAllowed,
  tokenFromRequest,
  tokenFromRequestOrQuery,
};
