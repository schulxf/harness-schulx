"use strict";

const { EventEmitter } = require("events");

let nodePty = null;
let loadError = null;
try {
  nodePty = require("node-pty");
} catch (err) {
  loadError = err;
}

function byteLength(value) {
  return Buffer.byteLength(String(value || ""), "utf8");
}

function trimToBytes(value, limit) {
  let text = String(value || "");
  while (byteLength(text) > limit && text.length > 0) {
    text = text.slice(Math.max(1, Math.floor(text.length / 4)));
  }
  return text;
}

class PtyManager {
  constructor(options) {
    this.available = Boolean(nodePty);
    this.loadError = loadError ? loadError.message : "";
    this.sessions = new Map();
    this.defaultScrollbackBytes = Math.max(4096, Number(options && options.scrollbackBytes) || 262144);
    this.defaultIdleTimeoutMs = Math.max(0, Number(options && options.idleTimeoutMs) || 1800 * 1000);
    this.reaper = setInterval(() => this.reapIdle(), 30000);
    if (this.reaper.unref) {
      this.reaper.unref();
    }
  }

  spawnSession(options) {
    if (!this.available) {
      return {
        ok: false,
        error: "node-pty is not installed or could not be loaded",
        details: this.loadError,
      };
    }
    const agentId = String(options.agentId || "");
    if (!agentId) {
      return { ok: false, error: "agent_id_required" };
    }
    const ptyId = options.ptyId || `pty-${Date.now().toString(36)}-${Math.random().toString(16).slice(2, 8)}`;
    const session = {
      id: ptyId,
      agentId,
      command: String(options.command),
      args: Array.isArray(options.args) ? options.args.map(String) : [],
      cwd: String(options.cwd || process.cwd()),
      process: null,
      emitter: new EventEmitter(),
      scrollback: "",
      scrollbackBytes: Math.max(4096, Number(options.scrollbackBytes) || this.defaultScrollbackBytes),
      idleTimeoutMs: Math.max(0, Number(options.idleTimeoutMs) || this.defaultIdleTimeoutMs),
      createdAt: new Date().toISOString(),
      lastActivity: Date.now(),
      exitCode: null,
      clients: new Set(),
    };
    try {
      session.process = nodePty.spawn(session.command, session.args, {
        name: "xterm-color",
        cols: Number(options.cols) || 100,
        rows: Number(options.rows) || 30,
        cwd: session.cwd,
        env: { ...process.env, ...(options.env || {}) },
      });
    } catch (err) {
      return { ok: false, error: "pty_spawn_failed", details: err.message };
    }
    session.process.onData((data) => {
      session.lastActivity = Date.now();
      session.scrollback = trimToBytes(session.scrollback + data, session.scrollbackBytes);
      session.emitter.emit("data", data);
    });
    session.process.onExit((event) => {
      session.exitCode = event.exitCode;
      session.lastActivity = Date.now();
      session.emitter.emit("exit", event.exitCode);
    });
    this.sessions.set(agentId, session);
    return { ok: true, session: this.publicSession(session) };
  }

  publicSession(session) {
    return {
      id: session.id,
      agent_id: session.agentId,
      command: session.command,
      args: session.args,
      cwd: session.cwd,
      created_at: session.createdAt,
      exit_code: session.exitCode,
    };
  }

  get(agentId) {
    return this.sessions.get(String(agentId)) || null;
  }

  hasAgent(agentId) {
    const session = this.get(agentId);
    return Boolean(session && session.exitCode === null);
  }

  hasPty(ptyId) {
    for (const session of this.sessions.values()) {
      if (session.id === ptyId && session.exitCode === null) {
        return true;
      }
    }
    return false;
  }

  activeAgentIds() {
    return [...this.sessions.values()].filter((session) => session.exitCode === null).map((session) => session.agentId);
  }

  liveCount() {
    return this.activeAgentIds().length;
  }

  attach(agentId, ws) {
    const session = this.get(agentId);
    if (!session) {
      return false;
    }
    session.clients.add(ws);
    if (session.scrollback) {
      ws.send(JSON.stringify({ type: "output", data: session.scrollback }));
    }
    if (session.exitCode !== null) {
      ws.send(JSON.stringify({ type: "exit", code: session.exitCode }));
    }
    const onData = (data) => {
      if (ws.readyState === ws.OPEN) {
        ws.send(JSON.stringify({ type: "output", data }));
      }
    };
    const onExit = (code) => {
      if (ws.readyState === ws.OPEN) {
        ws.send(JSON.stringify({ type: "exit", code }));
      }
    };
    session.emitter.on("data", onData);
    session.emitter.on("exit", onExit);
    ws.on("message", (raw) => {
      this.handleClientFrame(session, raw);
    });
    ws.on("close", () => {
      session.clients.delete(ws);
      session.emitter.off("data", onData);
      session.emitter.off("exit", onExit);
    });
    return true;
  }

  handleClientFrame(session, raw) {
    let frame = null;
    try {
      frame = JSON.parse(raw.toString("utf8"));
    } catch (_err) {
      return;
    }
    if (!frame || typeof frame !== "object" || !session.process || session.exitCode !== null) {
      return;
    }
    session.lastActivity = Date.now();
    if (frame.type === "input") {
      session.process.write(String(frame.data || ""));
      return;
    }
    if (frame.type === "resize") {
      const cols = Math.max(10, Math.min(300, Number.parseInt(frame.cols, 10) || 100));
      const rows = Math.max(5, Math.min(120, Number.parseInt(frame.rows, 10) || 30));
      session.process.resize(cols, rows);
    }
  }

  kill(agentId) {
    const session = this.get(agentId);
    if (!session) {
      return false;
    }
    if (session.process && session.exitCode === null) {
      try {
        session.process.kill();
      } catch (_err) {
        // node-pty can throw if the child has already exited.
      }
    }
    session.exitCode = session.exitCode === null ? -1 : session.exitCode;
    session.emitter.emit("exit", session.exitCode);
    this.sessions.delete(String(agentId));
    return true;
  }

  reapIdle(now) {
    const current = now || Date.now();
    for (const session of [...this.sessions.values()]) {
      if (session.idleTimeoutMs > 0 && session.exitCode === null && current - session.lastActivity > session.idleTimeoutMs) {
        this.kill(session.agentId);
      }
    }
  }

  close() {
    clearInterval(this.reaper);
    for (const session of [...this.sessions.values()]) {
      this.kill(session.agentId);
    }
  }
}

module.exports = {
  PtyManager,
};
