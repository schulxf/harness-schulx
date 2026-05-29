const bootstrap = document.getElementById("hub-bootstrap");
    const initialState = JSON.parse(bootstrap?.textContent || "{}");
    const refreshMs = Number(bootstrap?.dataset.refreshMs || 3000);
    let hubState = initialState;
    let selectedIndex = 0;
    let selectedAgentId = "";
    const roomSlots = [
      [32, 36], [708, 36], [32, 418], [708, 418],
      [370, 36], [370, 418], [32, 226], [708, 226]
    ];
    const phaseLabels = {
      queue: "Fila", build: "Implementacao", review: "Revisao",
      security: "Security", report: "Relatorio", idle: "Ocioso", offline: "Offline"
    };
    function esc(value) {
      return String(value ?? "").replace(/[&<>"']/g, char => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
      }[char]));
    }
    function roomPosition(index) {
      if (index < roomSlots.length) return roomSlots[index];
      const col = index % 3;
      const row = Math.floor(index / 3);
      return [32 + col * 338, 650 + row * 240];
    }
    function agentPosition(agent, agentIndex) {
      const phase = agent.phase || "idle";
      if (agent.state === "idle") return [112 + agentIndex * 28, 72 + (agentIndex % 2) * 16];
      if (phase === "review" || phase === "security") return [172, 92];
      if (phase === "report" || phase === "queue") return [74, 92];
      return [168, 92];
    }
    function renderAgent(agent, agentIndex, repoIndex) {
      const [left, top] = agentPosition(agent, agentIndex);
      const button = document.createElement("button");
      button.className = "agent-token";
      button.dataset.role = agent.role || "operator";
      button.dataset.state = agent.state || "idle";
      button.dataset.agentId = agent.id || "";
      button.style.left = left + "px";
      button.style.top = top + "px";
      button.style.animationDelay = (agentIndex * -0.45) + "s";
      button.title = (agent.name || "Agent") + (agent.task_id ? " - " + agent.task_id : "");
      button.setAttribute("aria-label", button.title);
      button.innerHTML = `
        <div class="speech-bubble">${esc(agent.speech || "Aguardando instrucao.")}</div>
        <div class="agent-shadow"></div>
        <div class="agent-sprite" aria-hidden="true">
          <div class="agent-head"></div>
          <div class="agent-body"></div>
          <div class="agent-legs"></div>
        </div>
      `;
      button.addEventListener("click", event => {
        event.stopPropagation();
        selectedIndex = repoIndex;
        selectedAgentId = agent.id || "";
        renderDetail();
      });
      return button;
    }
    function render() {
      document.getElementById("generated").textContent = "Atualizado " + (hubState.generated_at || "-");
      document.getElementById("repoCount").textContent = "Repos: " + (hubState.repo_count || 0);
      document.getElementById("activeCount").textContent = "Ativos: " + (hubState.active_repos || 0);
      document.getElementById("taskCount").textContent = "Tasks: " + (hubState.total_tasks || 0);
      document.getElementById("findingCount").textContent = "Findings: " + (hubState.total_findings || 0);
      const world = document.getElementById("world");
      world.querySelectorAll(".room,.path").forEach(node => node.remove());
      const repos = hubState.repos || [];
      const maxY = repos.reduce((max, repo, index) => Math.max(max, roomPosition(index)[1] + 250), 680);
      world.style.minHeight = maxY + "px";
      repos.forEach((repo, index) => {
        const [left, top] = roomPosition(index);
        const room = document.createElement("section");
        room.className = "room";
        room.dataset.phase = repo.phase || "idle";
        room.style.left = left + "px";
        room.style.top = top + "px";
        room.tabIndex = 0;
        room.setAttribute("role", "button");
        room.setAttribute("aria-label", "Abrir " + (repo.project || repo.root));
        room.innerHTML = `
          <div class="room-title">${esc(repo.project || "Projeto")}</div>
          <div class="room-meta">${esc(phaseLabels[repo.phase] || repo.phase)} - ${esc(repo.branch || "sem branch")}</div>
          <div class="metric-line">
            <div class="mini">T ${esc(repo.counts?.tasks ?? 0)}</div>
            <div class="mini">Q ${esc(repo.counts?.queued ?? 0)}</div>
            <div class="mini">A ${esc(repo.counts?.artifacts ?? 0)}</div>
            <div class="mini">S ${esc(repo.counts?.security_findings ?? 0)}</div>
          </div>
          <div class="console"></div>
          <div class="station"></div>
        `;
        (repo.agents || []).slice(0, 3).forEach((agent, agentIndex) => {
          room.appendChild(renderAgent(agent, agentIndex, index));
        });
        room.addEventListener("click", () => { selectedIndex = index; selectedAgentId = ""; renderDetail(); });
        room.addEventListener("keydown", event => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            selectedIndex = index;
            selectedAgentId = "";
            renderDetail();
          }
        });
        world.appendChild(room);
      });
      renderRepoList();
      renderDetail();
    }
    function renderRepoList() {
      const list = document.getElementById("repoList");
      list.innerHTML = "";
      (hubState.repos || []).forEach((repo, index) => {
        const button = document.createElement("button");
        button.className = "repo-button";
        button.innerHTML = `<strong>${esc(repo.project || repo.root)}</strong><br><span class="detail">${esc(phaseLabels[repo.phase] || repo.phase)} - ${esc(repo.root)}</span>`;
        button.addEventListener("click", () => { selectedIndex = index; selectedAgentId = ""; renderDetail(); });
        list.appendChild(button);
      });
    }
    function activeSurfaceId(wmux) {
      const surfaces = wmux.surfaces || [];
      const active = surfaces.find(surface => surface.isActive) || surfaces[0] || {};
      return active.id || wmux.surface_id || "";
    }
    function wmuxTerminalRows(wmux) {
      const surfaces = wmux.surfaces || [];
      if (!surfaces.length) return `<div class="detail">Nenhum terminal wmux listado.</div>`;
      return surfaces.map(surface => `
        <div class="terminal-row">
          <span>${esc(surface.id || "-")}<br><span class="detail">${esc(surface.type || "terminal")} / ${esc(surface.paneId || surface.pane_id || "-")}</span></span>
          <button class="terminal-button" data-wmux-focus-surface="${esc(surface.id || "")}">Focar</button>
        </div>
      `).join("");
    }
    function wmuxAgentRows(wmux) {
      const agents = wmux.agents || [];
      if (!agents.length) return `<div class="detail">Nenhum agent wmux listado.</div>`;
      return agents.map(agent => {
        const surfaceId = agent.surfaceId || agent.surface_id || "";
        return `
          <div class="terminal-row">
            <span>${esc(agent.label || agent.agentId || agent.id || "agent")}<br><span class="detail">${esc(agent.status || "-")} / ${esc(surfaceId || "sem surface")}</span></span>
            <button class="terminal-button" data-wmux-focus-surface="${esc(surfaceId)}" ${surfaceId ? "" : "disabled"}>Focar</button>
          </div>
        `;
      }).join("");
    }
    function eventTimeline(repo, selectedAgent) {
      const events = (repo.events || []).filter(event => {
        if (selectedAgent?.id && event.agent_id) return event.agent_id === selectedAgent.id;
        if (selectedAgent?.task_id && event.task_id) return event.task_id === selectedAgent.task_id;
        return true;
      }).slice(-12).reverse();
      if (!events.length) return `<li>Nenhum evento registrado ainda.</li>`;
      return events.map(event => {
        const payload = event.payload || {};
        const text = payload.summary || payload.message || event.type || "evento";
        return `<li><span class="event-time">${esc(event.ts || "")} - ${esc(event.type || "")}</span>${esc(event.task_id || "")} ${esc(text)}</li>`;
      }).join("");
    }
    async function postJson(path, payload) {
      const token = hubState.action_token || "";
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Harness-Hub-Token": token },
        body: JSON.stringify(payload || {})
      });
      const data = await response.json().catch(() => ({ ok: false, error: "Resposta invalida." }));
      if (!response.ok || data.ok === false) throw new Error(data.error || "Falha ao chamar wmux.");
      return data;
    }
    async function runWmuxAction(path, payload) {
      try {
        await postJson(path, payload);
        await refresh();
      } catch (error) {
        alert(error.message || String(error));
      }
    }
    function bindWmuxControls(repo, selectedSurfaceId) {
      const detail = document.getElementById("detail");
      detail.querySelectorAll("[data-wmux-focus-surface]").forEach(button => {
        button.addEventListener("click", () => {
          runWmuxAction("/wmux/focus", { surface_id: button.dataset.wmuxFocusSurface });
        });
      });
      const newTerminal = detail.querySelector("[data-wmux-new-terminal]");
      if (newTerminal) {
        newTerminal.addEventListener("click", () => {
          runWmuxAction("/wmux/new-terminal", { cwd: repo.root, direction: "down" });
        });
      }
      const sendButton = detail.querySelector("[data-wmux-send]");
      const input = detail.querySelector("#wmuxSendText");
      if (sendButton && input) {
        sendButton.addEventListener("click", () => {
          const text = input.value.trim();
          if (!text) return;
          runWmuxAction("/wmux/send", { surface_id: selectedSurfaceId, text, enter: true });
          input.value = "";
        });
      }
      const readButton = detail.querySelector("[data-wmux-read]");
      const screen = detail.querySelector("#wmuxScreen");
      if (readButton && screen) {
        readButton.addEventListener("click", async () => {
          screen.textContent = "Lendo terminal...";
          try {
            const data = await postJson("/wmux/read-screen", { surface_id: selectedSurfaceId, lines: 80 });
            screen.textContent = data.text || data.note || "wmux nao retornou texto de tela.";
          } catch (error) {
            screen.textContent = error.message || String(error);
          }
        });
      }
    }
    function renderDetail() {
      const repo = (hubState.repos || [])[selectedIndex];
      const detail = document.getElementById("detail");
      if (!repo) {
        detail.textContent = "Nenhum repo carregado.";
        return;
      }
      const activeTask = repo.active_task || {};
      const queue = repo.queue || [];
      const tasks = repo.tasks || [];
      const agents = repo.agents || [];
      const selectedAgent = agents.find(agent => agent.id === selectedAgentId) || agents[0] || {};
      const wmux = hubState.wmux || {};
      const selectedSurfaceId = activeSurfaceId(wmux);
      detail.innerHTML = `
        <strong>${esc(repo.project)}</strong><br>
        Fase: ${esc(phaseLabels[repo.phase] || repo.phase)}<br>
        Raiz: ${esc(repo.root)}<br>
        Branch: ${esc(repo.branch || "-")}<br>
        Profile: ${esc(repo.active_profile || "-")}<br>
        <br><strong>Agente</strong><br>
        Nome: ${esc(selectedAgent.name || "-")}<br>
        Estado: ${esc(selectedAgent.state || "-")}<br>
        Fala: ${esc(selectedAgent.speech || "-")}<br>
        Task do agente: ${esc(selectedAgent.task_id || "-")} ${esc(selectedAgent.task_title || "")}<br>
        Surface: ${esc(selectedAgent.surface_id || "-")}<br>
        <br><strong>Timeline</strong>
        <ul class="timeline">${eventTimeline(repo, selectedAgent)}</ul>
        <br><strong>Task ativa</strong><br>
        Task ativa: ${esc(activeTask.task_id || "-")} ${esc(activeTask.title || "")}<br>
        Run: ${esc(repo.latest_run || "-")}<br>
        Checkpoint: ${esc(repo.latest_checkpoint || "-")}<br>
        Security findings: ${esc(repo.counts?.security_findings ?? 0)}<br>
        <div class="terminal-panel">
          <strong>Terminal wmux</strong><br>
          Status: <span class="${wmux.available ? "status-ok" : "status-off"}">${wmux.available ? "conectado" : "desconectado"}</span><br>
          Comando: ${esc(wmux.command || "wmux")}<br>
          ${wmux.available ? `
            <div class="terminal-actions">
              <button class="terminal-button" data-wmux-new-terminal>Abrir terminal deste repo</button>
            </div>
            <input class="terminal-input" id="wmuxSendText" placeholder="Mensagem ou comando para o terminal ativo">
            <div class="terminal-actions">
              <button class="terminal-button" data-wmux-send data-surface-id="${esc(selectedSurfaceId)}">Enviar para terminal ativo</button>
              <button class="terminal-button" data-wmux-read>Ler tela</button>
            </div>
            <pre class="terminal-screen" id="wmuxScreen">Clique em "Ler tela" para carregar o terminal ativo.</pre>
            <strong>Terminais</strong>
            ${wmuxTerminalRows(wmux)}
            <br><strong>Agents wmux</strong>
            ${wmuxAgentRows(wmux)}
          ` : `<span class="detail">${esc(wmux.error || "wmux nao respondeu.")}</span>`}
        </div>
        <br><strong>Fila</strong>
        <ul class="task-list">${queue.slice(-5).map(item => `<li>${esc(item.id)} [${esc(item.status)}] ${esc(item.title)}</li>`).join("") || "<li>Fila vazia.</li>"}</ul>
        <br><strong>Tasks recentes</strong>
        <ul class="task-list">${tasks.slice(-5).map(task => `<li>${esc(task.task_id)} [${esc(task.status)}] ${esc(task.title)}</li>`).join("") || "<li>Nenhuma task.</li>"}</ul>
      `;
      bindWmuxControls(repo, selectedSurfaceId);
    }
    async function refresh() {
      try {
        const response = await fetch("hub-state.json?ts=" + Date.now(), {
          cache: "no-store",
          headers: { "X-Harness-Hub-Token": hubState.action_token || "" }
        });
        if (!response.ok) return;
        hubState = await response.json();
        render();
      } catch (error) {
        console.warn("Hub refresh failed", error);
      }
    }
    render();
    setInterval(refresh, refreshMs);
