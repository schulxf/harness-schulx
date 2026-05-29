// Agent pop-up: full info panel + a real interactive terminal (xterm.js) wired
// to the agent's PTY over WebSocket. You can type, see live output, Ctrl+C, etc.
import { Terminal } from "../assets/vendor/xterm/xterm.mjs";
import { FitAddon } from "../assets/vendor/xterm/addon-fit.mjs";
import { roleMeta, activityLabel, shortPath } from "./statemachine.js";
import { frameForRole } from "./sprites.js";

const THEME = {
  background: "#0c100c",
  foreground: "#e8e4d2",
  cursor: "#d9a441",
  selectionBackground: "#3a4a32",
  black: "#1b211a", red: "#e15b4f", green: "#5cd06a", yellow: "#d9a441",
  blue: "#54a7c7", magenta: "#9b84d8", cyan: "#4fb9a8", white: "#e8e4d2",
  brightBlack: "#5b6356", brightRed: "#f08077", brightGreen: "#86e08f",
  brightYellow: "#ecc46b", brightBlue: "#79c0db", brightMagenta: "#b6a4e6",
  brightCyan: "#79d3c4", brightWhite: "#ffffff",
};

function canUseWs() {
  return window.location.protocol === "http:" || window.location.protocol === "https:";
}

function wsUrl(agentId, token, hub) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const baseUrl = hub && typeof hub.wsUrl === "function" ? hub.wsUrl("/ws/term") : "";
  const url = new URL(baseUrl || `${protocol}//${window.location.host}/ws/term`);
  url.searchParams.set("agent", agentId);
  if (token) url.searchParams.set("token", token);
  return url.toString();
}

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export class AgentTerminal {
  constructor(root, handlers = {}) {
    this.root = root;
    this.handlers = handlers;
    this.socket = null;
    this.agent = null;
    this.repo = null;
    this.token = "";
    this.term = null;
    this.fit = null;
    this.connected = false;

    this.els = {
      avatar: root.querySelector("#amAvatar"),
      name: root.querySelector("#amName"),
      sub: root.querySelector("#amSub"),
      status: root.querySelector("#amStatus"),
      info: root.querySelector("#amInfo"),
      termTitle: root.querySelector("#amTermTitle"),
      mount: root.querySelector("#amTerm"),
    };

    root.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => this.close()));
    root.querySelector("#amReconnect").addEventListener("click", () => this.connect());
    root.querySelector("#amClear").addEventListener("click", () => this.term && this.term.clear());
    root.querySelector("#amInterrupt").addEventListener("click", () => { this.sendInput("\x03"); this.focus(); });
    root.querySelector("#amKill").addEventListener("click", () => this.kill());
    window.addEventListener("resize", () => this.refit());
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !this.root.hidden) this.close(); });
  }

  ensureTerm() {
    if (this.term) return;
    this.term = new Terminal({
      fontFamily: "'Cascadia Mono', 'Consolas', ui-monospace, monospace",
      fontSize: 13,
      cursorBlink: true,
      convertEol: false,
      scrollback: 5000,
      theme: THEME,
    });
    this.fit = new FitAddon();
    this.term.loadAddon(this.fit);
    this.term.open(this.els.mount);
    this.term.onData((data) => this.sendInput(data));
  }

  open(agent, repo, token) {
    this.agent = agent;
    this.repo = repo;
    this.token = token || "";
    this.root.hidden = false;
    this.renderHeader();
    this.ensureTerm();
    requestAnimationFrame(() => { this.refit(); this.focus(); });
    this.connect();
  }

  renderHeader() {
    const a = this.agent;
    const meta = roleMeta(a.role);
    const frame = frameForRole(a.role);
    this.els.avatar.style.cssText = `background-image:url('./assets/sprites/agents.png');background-size:600% 100%;background-position:${(frame / 5) * 100}% 0;`;
    this.els.name.textContent = a.name || a.id;
    this.els.sub.innerHTML = `<span style="color:${meta.color}">${esc(meta.label)}</span> · ${esc(activityLabel(a))}`;
    this.els.termTitle.textContent = `${a.cli || "terminal"} — ${this.repo?.project || ""}`;
    this.els.info.innerHTML = this.infoHtml(a);
  }

  infoHtml(a) {
    const rows = [
      ["ID", a.id],
      ["Role", roleMeta(a.role).label],
      ["State", a.state],
      ["Sector", a.sector],
      ["CLI", a.cli],
      ["Task", `${a.task_id || "-"} ${a.task_title || ""}`.trim()],
      ["PTY", a.pty_id || "-"],
      ["CWD", shortPath(a.cwd || this.repo?.root)],
      ["Transcript", shortPath(a.transcript_path)],
    ];
    return `
      <div class="am-info-block">
        <h3>Agent</h3>
        <dl class="am-grid">${rows.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v || "-")}</dd>`).join("")}</dl>
      </div>
      ${a.speech ? `<div class="am-speech">“${esc(a.speech)}”</div>` : ""}
      <div class="am-hint">Type directly in the terminal. <b>Ctrl+C</b> interrupts. Run <code>claude</code> or <code>codex</code> to start an LLM session.</div>`;
  }

  focus() { try { this.term && this.term.focus(); } catch (_) { /* */ } }

  refit() {
    if (!this.fit || this.root.hidden) return;
    try {
      this.fit.fit();
      const { cols, rows } = this.term;
      this.sendFrame({ type: "resize", cols, rows });
    } catch (_) { /* mount not measurable yet */ }
  }

  setStatus(text, state) {
    this.els.status.textContent = text;
    this.els.status.dataset.state = state || "idle";
  }

  connect() {
    if (!this.agent) return;
    this.ensureTerm();
    if (this.socket) { try { this.socket.close(); } catch (_) { /* */ } this.socket = null; }
    if (!canUseWs()) {
      this.setStatus("Offline", "offline");
      this.term.writeln("\x1b[33mWebSocket requires an http(s) hub origin.\x1b[0m");
      return;
    }
    this.setStatus("Connecting…", "connecting");
    let socket;
    try {
      socket = new WebSocket(wsUrl(this.agent.id, this.token, this.handlers.hub));
    } catch (error) {
      this.setStatus("Failed", "error");
      this.term.writeln(`\x1b[31m${String(error?.message || error)}\x1b[0m`);
      return;
    }
    this.socket = socket;
    socket.addEventListener("open", () => {
      this.connected = true;
      this.setStatus("Live", "live");
      this.refit();
      this.focus();
    });
    socket.addEventListener("message", (m) => this.onFrame(m.data));
    socket.addEventListener("close", () => {
      this.connected = false;
      this.setStatus("Disconnected", "offline");
    });
    socket.addEventListener("error", () => {
      this.setStatus("No terminal", "error");
      this.term.writeln("\r\n\x1b[31mNo live terminal for this agent.\x1b[0m");
      this.term.writeln("\x1b[90mThe PTY only exists while the sidecar that spawned it runs,\x1b[0m");
      this.term.writeln("\x1b[90mand the repo needs hub.allow_remote_execution = true.\x1b[0m");
    });
  }

  onFrame(data) {
    let frame;
    try { frame = JSON.parse(data); } catch (_) { this.term.write(String(data)); return; }
    if (frame.type === "output") this.term.write(frame.data || "");
    else if (frame.type === "exit") this.term.writeln(`\r\n\x1b[90m[process exited${frame.code != null ? `: ${frame.code}` : ""}]\x1b[0m`);
  }

  sendFrame(frame) {
    if (this.socket && this.socket.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(frame));
  }

  sendInput(data) {
    this.sendFrame({ type: "input", data });
  }

  kill() {
    if (this.agent && this.handlers.onKill) this.handlers.onKill(this.agent.id);
    this.setStatus("Stopping…", "offline");
  }

  close() {
    this.root.hidden = true;
    if (this.socket) { try { this.socket.close(); } catch (_) { /* */ } this.socket = null; }
  }
}
