function canUseWs() {
  return window.location.protocol === "http:" || window.location.protocol === "https:";
}

function wsUrl(agentId, token) {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = new URL(`${protocol}//${window.location.host}/ws/term`);
  url.searchParams.set("agent", agentId);
  if (token) url.searchParams.set("token", token);
  return url.toString();
}

export class TerminalOverlay {
  constructor(root, options = {}) {
    this.root = root;
    this.mount = root.querySelector("#terminalMount");
    this.title = root.querySelector("#terminalTitle");
    this.status = root.querySelector("#terminalStatus");
    this.input = root.querySelector("#terminalInput");
    this.form = root.querySelector("#terminalInputForm");
    this.reconnect = root.querySelector("#terminalReconnect");
    this.closeButton = root.querySelector("#terminalClose");
    this.onStatus = options.onStatus || (() => {});
    this.socket = null;
    this.agent = null;
    this.repo = null;
    this.token = "";
    this.xterm = null;

    this.closeButton.addEventListener("click", () => this.close());
    this.reconnect.addEventListener("click", () => this.connect());
    this.form.addEventListener("submit", (event) => {
      event.preventDefault();
      const value = this.input.value;
      if (!value) return;
      this.send(value.endsWith("\n") ? value : `${value}\n`);
      this.input.value = "";
    });
  }

  open(agent, repo, token) {
    this.agent = agent;
    this.repo = repo;
    this.token = token || "";
    this.root.hidden = false;
    this.title.textContent = `${agent.name || agent.id} / ${agent.cli || "cli"}`;
    this.mount.textContent = "";
    this.writeLine("Harness terminal");
    this.writeLine(`Agent: ${agent.id}`);
    this.writeLine(`Repo: ${repo.root}`);
    this.writeLine("Connected terminal stream");
    this.connect();
    window.setTimeout(() => this.input.focus(), 50);
  }

  close() {
    this.root.hidden = true;
    if (this.socket) this.socket.close();
    this.socket = null;
  }

  connect() {
    if (!this.agent) return;
    if (this.socket) this.socket.close();
    if (!canUseWs()) {
      this.setStatus("Offline preview");
      this.writeLine("WebSocket requires an http(s) hub origin.");
      return;
    }
    const url = wsUrl(this.agent.id, this.token);
    this.setStatus("Connecting");
    this.writeLine(`Connecting ${url}`);
    try {
      this.socket = new WebSocket(url);
    } catch (error) {
      this.setStatus("Connect failed");
      this.writeLine(String(error?.message || error));
      return;
    }
    this.socket.addEventListener("open", () => {
      this.setStatus("Connected");
      this.writeJson({ type: "attach", agent: this.agent.id, token: this.token });
      this.writeJson({ type: "resize", cols: 120, rows: 30 });
    });
    this.socket.addEventListener("message", (message) => this.handleMessage(message.data));
    this.socket.addEventListener("close", () => this.setStatus("Disconnected"));
    this.socket.addEventListener("error", () => {
      this.setStatus("Socket error");
      this.writeLine("Terminal socket failed. The Node sidecar may not be running yet.");
    });
  }

  send(data) {
    this.writeLine(`> ${data.trimEnd()}`);
    this.writeJson({ type: "input", data });
  }

  writeJson(frame) {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      this.writeLine(`queued ${JSON.stringify(frame)}`);
      return;
    }
    this.socket.send(JSON.stringify(frame));
  }

  handleMessage(data) {
    try {
      const frame = JSON.parse(data);
      if (frame.type === "output") this.write(frame.data || "");
      else if (frame.type === "exit") this.writeLine(`process exited: ${frame.code ?? ""}`);
      else this.writeLine(JSON.stringify(frame));
    } catch (error) {
      this.write(String(data));
    }
  }

  write(text) {
    this.mount.textContent += text;
    this.mount.scrollTop = this.mount.scrollHeight;
  }

  writeLine(text) {
    this.write(`${text}\n`);
  }

  setStatus(text) {
    this.status.textContent = text;
    this.onStatus(text);
  }
}
