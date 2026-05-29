import { demoWorld } from "./world.js";

function canUseApi() {
  return window.location.protocol === "http:" || window.location.protocol === "https:";
}

function configuredHubBase() {
  const params = new URLSearchParams(window.location.search);
  const configured = params.get("hub") || params.get("sidecar") || window.HARNESS_HUB_URL || "";
  if (!configured) return "";
  try {
    return new URL(configured, window.location.origin).origin;
  } catch (_error) {
    return "";
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, { cache: "no-store", ...options });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  return response.json();
}

export class HubClient {
  constructor(options = {}) {
    this.onStatus = options.onStatus || (() => {});
    this.onEvent = options.onEvent || (() => {});
    this.token = new URLSearchParams(window.location.search).get("token") || "";
    this.baseUrl = configuredHubBase();
    this.eventSource = null;
    this.pollTimer = 0;
  }

  setToken(token) {
    if (token && !this.token) this.token = token;
  }

  headers(extra = {}) {
    return {
      ...extra,
      ...(this.token ? { "X-Harness-Hub-Token": this.token } : {}),
    };
  }

  apiUrl(path) {
    if (!this.baseUrl) return path;
    return new URL(path, this.baseUrl).toString();
  }

  wsUrl(path) {
    const base = this.baseUrl ? new URL(this.baseUrl) : new URL(window.location.origin);
    base.protocol = base.protocol === "https:" ? "wss:" : "ws:";
    return new URL(path, base).toString();
  }

  async loadWorld() {
    const candidates = canUseApi()
      ? [this.apiUrl("/api/world"), "./hub-state.json", "./state.json"]
      : ["./hub-state.json", "./state.json"];
    for (const candidate of candidates) {
      try {
        const data = await fetchJson(candidate, { headers: this.headers() });
        this.setToken(data.action_token);
        this.onStatus({ state: candidate.includes("/api/") ? "live" : "Live" });
        return data;
      } catch (error) {
        this.onStatus({ state: "connecting", label: "Connecting" });
      }
    }
    const demo = demoWorld();
    this.onStatus({ state: "fallback", label: "Demo" });
    return demo;
  }

  startEvents(offset = 0) {
    this.stopEvents();
    if (!canUseApi() || !window.EventSource) {
      this.startPolling();
      this.onStatus({ state: "fallback", label: "Fallback" });
      return;
    }

    const url = new URL(this.apiUrl("/api/events"), window.location.origin);
    url.searchParams.set("offset", String(offset || 0));
    if (this.token) url.searchParams.set("token", this.token);
    this.eventSource = new EventSource(url.toString());
    this.eventSource.onopen = () => this.onStatus({ state: "live", label: "Live" });
    this.eventSource.onerror = () => {
      this.onStatus({ state: "fallback", label: "Fallback" });
      this.startPolling();
    };
    this.eventSource.onmessage = (message) => {
      const parsed = this.parseEventMessage(message.data);
      for (const event of parsed) this.onEvent(event);
    };
  }

  parseEventMessage(data) {
    if (!data) return [];
    try {
      const parsed = JSON.parse(data);
      if (Array.isArray(parsed)) return parsed;
      if (Array.isArray(parsed.events)) return parsed.events;
      return [parsed];
    } catch (error) {
      return [{ type: "log", payload: { text: String(data) } }];
    }
  }

  startPolling() {
    if (this.pollTimer) return;
    this.pollTimer = window.setInterval(async () => {
      try {
        const world = await this.loadWorld();
        this.onEvent({ type: "world_snapshot", world, repos: world.repos });
      } catch (error) {
        this.onStatus({ state: "error", label: "Polling failed" });
      }
    }, 5000);
  }

  stopEvents() {
    if (this.eventSource) this.eventSource.close();
    this.eventSource = null;
    if (this.pollTimer) window.clearInterval(this.pollTimer);
    this.pollTimer = 0;
  }

  async postJson(path, payload = {}) {
    if (!canUseApi()) throw new Error("POST actions require the hub sidecar.");
    const data = await fetchJson(this.apiUrl(path), {
      method: "POST",
      headers: this.headers({ "Content-Type": "application/json" }),
      body: JSON.stringify(payload),
    });
    if (data?.action_token) this.setToken(data.action_token);
    return data;
  }
}
