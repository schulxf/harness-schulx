import { activityLabel, eventSummary, roleMeta, shortPath } from "./statemachine.js";

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[char]));
}

function option(value, label, selectedValue) {
  const selected = value === selectedValue ? "selected" : "";
  return `<option value="${esc(value)}" ${selected}>${esc(label)}</option>`;
}

function detailRows(rows) {
  return `<dl class="detail-grid">${rows.map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value || "-")}</dd>`).join("")}</dl>`;
}

function taskList(items, empty) {
  if (!items?.length) return `<ul class="task-list"><li>${esc(empty)}</li></ul>`;
  return `<ul class="task-list">${items.slice(-6).reverse().map((item) => (
    `<li><strong>${esc(item.task_id || item.id || "-")}</strong> <span class="muted">${esc(item.status || "")}</span><br>${esc(item.title || item.summary || "")}</li>`
  )).join("")}</ul>`;
}

function eventList(events) {
  if (!events?.length) return `<ul class="event-list"><li>No events yet.</li></ul>`;
  return `<ul class="event-list">${events.slice(-8).reverse().map((event) => (
    `<li><span class="muted">${esc(event.ts || event.time || "")} ${esc(event.type || "")}</span><br>${esc(eventSummary(event))}</li>`
  )).join("")}</ul>`;
}

function agentList(repo, selectedAgentId) {
  if (!repo?.agents?.length) return `<ul class="agent-list"><li>No agents registered for this repo.</li></ul>`;
  return `<ul class="agent-list">${repo.agents.map((agent) => {
    const meta = roleMeta(agent.role);
    const selected = agent.id === selectedAgentId ? "true" : "false";
    return `
      <li style="border-left-color:${esc(meta.color)}">
        <button type="button" data-agent-id="${esc(agent.id)}" aria-pressed="${selected}">
          <strong>${esc(agent.name || agent.id)}</strong> <span class="muted">${esc(meta.label)}</span><br>
          ${esc(activityLabel(agent))}
        </button>
      </li>
    `;
  }).join("")}</ul>`;
}

export class HubUI {
  constructor(options = {}) {
    this.connectionBadge = document.getElementById("connectionBadge");
    this.repoCount = document.getElementById("repoCount");
    this.agentCount = document.getElementById("agentCount");
    this.eventCount = document.getElementById("eventCount");
    this.repoStrip = document.getElementById("repoStrip");
    this.stageHint = document.getElementById("stageHint");
    this.inspectorTitle = document.getElementById("inspectorTitle");
    this.inspectorMeta = document.getElementById("inspectorMeta");
    this.inspectorBody = document.getElementById("inspectorBody");
    this.refreshButton = document.getElementById("refreshButton");
    this.openTerminalButton = document.getElementById("openTerminalButton");
    this.handlers = {
      selectRepo: options.selectRepo || (() => {}),
      selectAgent: options.selectAgent || (() => {}),
      refresh: options.refresh || (() => {}),
      toggleView: options.toggleView || (() => {}),
      spawnAgent: options.spawnAgent || (() => {}),
      addRepo: options.addRepo || (() => {}),
      sendMessage: options.sendMessage || (() => {}),
      openTerminal: options.openTerminal || (() => {}),
      killAgent: options.killAgent || (() => {}),
    };

    this.refreshButton.addEventListener("click", () => this.handlers.refresh());
    this.openTerminalButton.addEventListener("click", () => this.handlers.openTerminal());
    this.repoStrip.addEventListener("click", (event) => {
      const button = event.target.closest("[data-repo-id]");
      if (button) this.handlers.selectRepo(button.dataset.repoId);
    });
    this.inspectorBody.addEventListener("click", (event) => this.handleInspectorClick(event));
    this.inspectorBody.addEventListener("submit", (event) => this.handleInspectorSubmit(event));
  }

  setConnection(status) {
    this.connectionBadge.dataset.state = status.state || "connecting";
    this.connectionBadge.textContent = status.label || status.state || "Connecting";
  }

  render(context) {
    const { world, selectedRepo, selectedAgent, mode, selectedSector } = context;
    const agentTotal = world.repos.reduce((sum, repo) => sum + repo.agents.length, 0);
    this.repoCount.textContent = `Repos ${world.repos.length}`;
    this.agentCount.textContent = `Agents ${agentTotal}`;
    this.eventCount.textContent = `Events ${world.events?.length || 0}`;
    this.stageHint.textContent = `${selectedRepo?.project || "Repo map"}`;
    this.renderRepoStrip(world, selectedRepo);
    this.renderInspector(world, selectedRepo, selectedAgent, selectedSector);
    this.openTerminalButton.disabled = !selectedAgent;
  }

  renderRepoStrip(world, selectedRepo) {
    this.repoStrip.innerHTML = world.repos.map((repo) => `
      <button class="repo-tab" type="button" data-repo-id="${esc(repo.id)}" aria-pressed="${repo.id === selectedRepo?.id ? "true" : "false"}">
        <strong>${esc(repo.project)}</strong>
        <span>${esc(repo.phase || "idle")} / ${esc(shortPath(repo.root))}</span>
      </button>
    `).join("");
  }

  renderInspector(world, repo, agent, selectedSector) {
    if (!repo) {
      this.inspectorTitle.textContent = "No repository";
      this.inspectorMeta.textContent = "The world snapshot did not include repos.";
      this.inspectorBody.innerHTML = "";
      return;
    }

    if (agent) {
      this.inspectorTitle.textContent = agent.name || agent.id;
      this.inspectorMeta.textContent = `${activityLabel(agent)} / ${agent.cli || "cli"}`;
      this.inspectorBody.innerHTML = this.agentInspector(world, repo, agent);
      return;
    }

    this.inspectorTitle.textContent = repo.project;
    this.inspectorMeta.textContent = `${repo.phase || "idle"} / ${shortPath(repo.root)}`;
    this.inspectorBody.innerHTML = this.repoInspector(world, repo, selectedSector);
  }

  repoInspector(world, repo, selectedSector) {
    const sector = repo.sectors.find((item) => item.key === selectedSector);
    return `
      <section>
        <h3>Repo</h3>
        ${detailRows([
          ["Root", repo.root],
          ["Branch", repo.branch],
          ["Theme", repo.theme.label],
          ["Profile", repo.active_profile],
          ["Task count", repo.counts?.tasks ?? 0],
          ["Queued", repo.counts?.queued ?? 0],
          ["Findings", repo.counts?.security_findings ?? 0],
          ["Selected sector", sector ? `${sector.label} (${sector.key})` : "-"],
        ])}
      </section>
      <section>
        <h3>Agents</h3>
        ${agentList(repo, "")}
      </section>
      <section>
        <h3>Spawn Agent</h3>
        <form class="form-grid" data-action="spawn">
          <div class="form-row">
            <label class="field-label">Role
              <select class="field-control" name="role">
                ${option("builder", "Builder", "builder")}
                ${option("planner", "Planner", "")}
                ${option("reviewer", "Reviewer", "")}
                ${option("security", "Security", "")}
                ${option("research", "Research", "")}
                ${option("reporter", "Reporter", "")}
              </select>
            </label>
            <label class="field-label">CLI
              <select class="field-control" name="cli">
                ${option("shell", "PowerShell", "shell")}
                ${option("codex", "Codex", "")}
                ${option("claude", "Claude", "")}
              </select>
            </label>
          </div>
          <label class="field-label">Name
            <input class="field-control" name="name" placeholder="Optional agent name">
          </label>
          <button type="submit">Spawn agent</button>
        </form>
      </section>
      <section>
        <h3>Add Repo</h3>
        <form class="form-grid" data-action="add-repo">
          <label class="field-label">Absolute path
            <input class="field-control" name="path" placeholder="C:/path/to/repo">
          </label>
          <button type="submit">Add repo</button>
        </form>
      </section>
      <section>
        <h3>Queue</h3>
        ${taskList(repo.queue, "Queue is empty.")}
      </section>
      <section>
        <h3>Recent Events</h3>
        ${eventList(repo.events)}
      </section>
    `;
  }

  agentInspector(world, repo, agent) {
    const otherAgents = repo.agents.filter((item) => item.id !== agent.id);
    return `
      <section>
        <h3>Agent</h3>
        ${detailRows([
          ["ID", agent.id],
          ["Role", roleMeta(agent.role).label],
          ["State", agent.state],
          ["Sector", agent.sector],
          ["Task", `${agent.task_id || "-"} ${agent.task_title || ""}`],
          ["PTY", agent.pty_id],
          ["CWD", agent.cwd || repo.root],
          ["Transcript", agent.transcript_path],
          ["Speech", agent.speech],
        ])}
        <div class="form-row" style="margin-top:10px">
          <button class="control-button" type="button" data-action="open-terminal">Open terminal</button>
          <button class="control-button" type="button" data-action="kill-agent">Stop agent</button>
        </div>
      </section>
      <section>
        <h3>Message Agent</h3>
        <form class="form-grid" data-action="message">
          <label class="field-label">To
            <select class="field-control" name="to">
              ${otherAgents.map((item) => option(item.id, item.name || item.id, "")).join("")}
            </select>
          </label>
          <label class="field-label">Text
            <textarea class="field-control" name="text" placeholder="Ask another agent to coordinate."></textarea>
          </label>
          <button type="submit" ${otherAgents.length ? "" : "disabled"}>Send message</button>
        </form>
      </section>
      <section>
        <h3>Repo Agents</h3>
        ${agentList(repo, agent.id)}
      </section>
      <section>
        <h3>Active Task</h3>
        ${detailRows([
          ["Repo", repo.project],
          ["Run", repo.latest_run],
          ["Checkpoint", repo.latest_checkpoint],
          ["Task", repo.active_task ? `${repo.active_task.task_id || ""} ${repo.active_task.title || ""}` : "-"],
        ])}
      </section>
      <section>
        <h3>Recent Events</h3>
        ${eventList(repo.events.filter((event) => !event.payload?.agent_id || event.payload.agent_id === agent.id))}
      </section>
    `;
  }

  handleInspectorClick(event) {
    const agentButton = event.target.closest("[data-agent-id]");
    if (agentButton) {
      this.handlers.selectAgent(agentButton.dataset.agentId);
      return;
    }
    const action = event.target.closest("[data-action]")?.dataset.action;
    if (action === "open-terminal") this.handlers.openTerminal();
    if (action === "kill-agent") this.handlers.killAgent();
  }

  handleInspectorSubmit(event) {
    const form = event.target.closest("form[data-action]");
    if (!form) return;
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    if (form.dataset.action === "spawn") this.handlers.spawnAgent(data);
    if (form.dataset.action === "add-repo") this.handlers.addRepo(data);
    if (form.dataset.action === "message") this.handlers.sendMessage(data);
  }
}
