const {
  STATUS_META,
  STAGE_LABELS,
  buildDashboardState,
  countsLine,
  mockState,
  taskPosition,
} = window.HarnessPresentation;

const app = document.getElementById("app");
const announcer = document.getElementById("announcer");
const bootstrap = document.getElementById("hub-bootstrap");
const refreshMs = Math.max(1000, Number(bootstrap?.dataset.refreshMs || 3000));

function parseBootstrap() {
  try {
    return JSON.parse(bootstrap?.textContent || "{}");
  } catch (_error) {
    return {};
  }
}

const bootstrapState = parseBootstrap();
if (!bootstrapState.action_token && window.HARNESS_HUB_TOKEN) {
  bootstrapState.action_token = String(window.HARNESS_HUB_TOKEN);
}
const hasBootstrapProjects = Array.isArray(bootstrapState.projects) || Array.isArray(bootstrapState.repos);
let dashboard = buildDashboardState(hasBootstrapProjects ? bootstrapState : mockState);
let eventSource = null;
let pollTimer = 0;
let refreshTimer = 0;

const uiState = {
  filter: "todos",
  selectedId: projectFromHash(),
  expandedTasks: new Set(),
  lastFetchAt: Date.now(),
  refreshing: false,
  connection: hasBootstrapProjects ? "active" : "demo",
  returnFocusId: "",
  managementOpen: false,
  managementLoading: false,
  managementBusyPath: "",
  managedRepos: [],
  managementMessage: null,
  removeCandidate: "",
};

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function selectorEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") return window.CSS.escape(String(value));
  return String(value).replace(/[^a-zA-Z0-9_-]/g, (char) => `\\${char}`);
}

function projectFromHash() {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  return params.get("projeto") || "";
}

function formatClock(value) {
  const date = value instanceof Date ? value : new Date(value);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", { hour: "2-digit", minute: "2-digit" }).format(date);
}

function formatDateTime(value) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Data não disponível";
  const today = new Date();
  const sameDay = date.toDateString() === today.toDateString();
  const dateText = sameDay
    ? "hoje"
    : new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short" }).format(date);
  return `${dateText} às ${formatClock(date)}`;
}

function relativeTime(value, now = Date.now()) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "sem atualização disponível";
  const seconds = Math.max(0, Math.floor((now - date.getTime()) / 1000));
  if (seconds < 5) return "agora mesmo";
  if (seconds < 60) return `há ${seconds} segundos`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes === 1 ? "há 1 minuto" : `há ${minutes} minutos`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return hours === 1 ? "há 1 hora" : `há ${hours} horas`;
  const days = Math.floor(hours / 24);
  return days === 1 ? "há 1 dia" : `há ${days} dias`;
}

function icon(name, className = "") {
  const paths = {
    brand: '<path d="M5 7.5h5.5v4H15v5h4"/><circle cx="5" cy="7.5" r="2"/><circle cx="10.5" cy="11.5" r="2"/><circle cx="15" cy="16.5" r="2"/><circle cx="19" cy="16.5" r="2"/>',
    refresh: '<path d="M20 6v5h-5"/><path d="M18.5 15a7 7 0 1 1-.6-7.7L20 11"/>',
    arrowLeft: '<path d="m15 18-6-6 6-6"/>',
    arrowRight: '<path d="m9 18 6-6-6-6"/>',
    play: '<path d="m9 7 8 5-8 5z"/>',
    target: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    list: '<path d="M9 6h11M9 12h11M9 18h11"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    alert: '<path d="M12 3 2.8 20h18.4L12 3Z"/><path d="M12 9v4M12 17h.01"/>',
    unavailable: '<circle cx="12" cy="12" r="9"/><path d="m5.7 5.7 12.6 12.6"/>',
    chevron: '<path d="m6 9 6 6 6-6"/>',
    folderPlus: '<path d="M3 7.5h6l2 2h10v9.5H3z"/><path d="M15 12v4M13 14h4"/>',
    eye: '<path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/>',
    eyeOff: '<path d="m3 3 18 18"/><path d="M10.6 6.1A10.7 10.7 0 0 1 12 6c6 0 9.5 6 9.5 6a17 17 0 0 1-2.2 2.8M6.4 6.4C3.8 8.1 2.5 12 2.5 12s3.5 6 9.5 6c1 0 2-.2 2.8-.5"/>',
    trash: '<path d="M4 7h16M9 7V4h6v3M7 7l1 13h8l1-13M10 11v5M14 11v5"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
  };
  return `<svg class="icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.list}</svg>`;
}

function statusChip(project) {
  const meta = STATUS_META[project.status] || STATUS_META.andamento;
  return `<span class="status-chip" data-tone="${meta.tone}"><span class="status-dot" aria-hidden="true"></span>${escapeHtml(project.statusLabel || meta.label)}</span>`;
}

function timestamp(value, prefix = "Atualizado ") {
  if (!value) return `<span>${escapeHtml(prefix)}sem atualização disponível</span>`;
  return `<time datetime="${escapeHtml(value)}" data-relative-time="${escapeHtml(value)}" data-prefix="${escapeHtml(prefix)}">${escapeHtml(prefix + relativeTime(value))}</time>`;
}

function renderHeader() {
  const activeText = uiState.connection === "error" ? "Acompanhamento temporariamente indisponível" : "Acompanhamento ativo";
  const modalAttributes = uiState.managementOpen ? ' inert aria-hidden="true"' : "";
  return `
    <header class="topbar"${modalAttributes}>
      <div class="brand-block" aria-label="Harness — Acompanhamento">
        <span class="brand-mark">${icon("brand")}</span>
        <div class="brand-copy">
          <div class="brand-title"><strong>Harness</strong><span aria-hidden="true"> — </span><span>Acompanhamento</span></div>
          <div class="live-state"><span class="live-dot" aria-hidden="true"></span>${escapeHtml(activeText)}</div>
        </div>
      </div>
      <div class="topbar-actions">
        <div class="panel-update" aria-live="off">
          <span>Última atualização</span>
          <strong><time id="panelClock" datetime="${new Date(uiState.lastFetchAt).toISOString()}">${formatClock(uiState.lastFetchAt)}</time> · <span id="panelRelative">${relativeTime(uiState.lastFetchAt)}</span></strong>
        </div>
        <div class="header-buttons">
          <button class="button button--secondary" id="manageProjectsButton" type="button">
            ${icon("folderPlus")}
            <span>Gerenciar projetos</span>
          </button>
          <button class="button button--secondary" id="refreshButton" type="button" ${uiState.refreshing ? "disabled" : ""}>
            ${icon("refresh", uiState.refreshing ? "icon--spin" : "")}
            <span>${uiState.refreshing ? "Atualizando…" : "Atualizar agora"}</span>
          </button>
        </div>
      </div>
    </header>`;
}

function projectStats(projects) {
  const by = (status) => projects.filter((project) => project.status === status).length;
  return [
    { label: "Acompanhados", value: projects.length, tone: "neutral" },
    { label: "Em andamento", value: by("andamento"), tone: "mint" },
    { label: "Em revisão", value: by("revisao"), tone: "amber" },
    { label: "Precisa de atenção", value: by("atencao"), tone: "coral" },
    { label: "Concluídos", value: by("concluido"), tone: "green" },
  ];
}

function filters(projects) {
  const definitions = [
    ["todos", "Todos", () => true],
    ["andamento", "Em andamento", (project) => project.status === "andamento"],
    ["conferencia", "Em conferência", (project) => project.status === "conferencia"],
    ["revisao", "Em revisão", (project) => project.status === "revisao"],
    ["atencao", "Precisa de atenção", (project) => project.status === "atencao"],
    ["concluido", "Concluídos", (project) => project.status === "concluido"],
  ];
  return definitions.map(([key, label, match]) => ({ key, label, match, count: projects.filter(match).length }));
}

function cardTrail(project) {
  if (!project.tasks.length) return "";
  const maxVisible = 12;
  const tasks = project.tasks.slice(0, maxVisible);
  const hidden = Math.max(0, project.tasks.length - maxVisible);
  const completed = project.counts.completed;
  return `
    <ol class="card-trail" aria-label="Trilha de progresso: ${completed} de ${project.tasks.length} tasks concluídas">
      ${tasks.map((item) => `
        <li class="trail-item" data-state="${item.state}" title="Task ${item.number}: ${escapeHtml(item.title)}">
          <span class="trail-node" aria-hidden="true">${item.state === "done" ? icon("check") : ""}</span>
        </li>`).join("")}
      ${hidden ? `<li class="trail-more" aria-label="Mais ${hidden} tasks">+${hidden}</li>` : ""}
    </ol>`;
}

function specialCardNote(project) {
  if (project.status === "indisponivel") {
    return `<div class="project-note" data-tone="neutral">${icon("unavailable")}<span>${escapeHtml(project.unavailableMessage)}</span></div>`;
  }
  if (project.blocker) {
    return `<div class="project-note" data-tone="coral">${icon("alert")}<span>${escapeHtml(project.blocker.message)}</span></div>`;
  }
  if (project.stale) {
    return `<div class="project-note" data-tone="amber">${icon("clock")}<span>${escapeHtml(project.staleMessage)}</span></div>`;
  }
  return "";
}

function projectCard(project) {
  const href = `#projeto=${encodeURIComponent(project.id)}`;
  const unavailable = project.status === "indisponivel";
  return `
    <article class="project-card-wrap" data-status="${project.status}">
      <a class="project-card" href="${href}" data-project-link="${escapeHtml(project.id)}" aria-label="Abrir ${escapeHtml(project.name)}, ${escapeHtml(project.statusLabel)}">
        <div class="card-heading">
          <div>
            <h2>${escapeHtml(project.name)}</h2>
            <p><span>Implementação:</span> ${escapeHtml(project.implementation)}</p>
          </div>
          ${statusChip(project)}
        </div>
        ${unavailable ? `
          <div class="unavailable-card-body">
            ${icon("unavailable")}
            <p>${escapeHtml(project.unavailableMessage)}</p>
          </div>` : `
          <div class="task-line">
            <span class="task-position">${escapeHtml(taskPosition(project))}</span>
            <span>${escapeHtml(project.situation)}</span>
          </div>
          <div class="card-current">
            <span class="eyebrow">O que está sendo feito</span>
            <p>${escapeHtml(project.current?.whatDoing || project.summary)}</p>
          </div>
          ${cardTrail(project)}
          <div class="card-facts">
            <strong>Etapa ${project.stage + 1} de 5 · ${escapeHtml(STAGE_LABELS[project.stage])}</strong>
            <span>${escapeHtml(countsLine(project))}</span>
          </div>
          ${specialCardNote(project)}
        `}
        <div class="card-footer">
          <span class="card-update">${icon("clock")}${timestamp(project.updatedAt)}</span>
          <span class="open-cue" aria-hidden="true">Ver detalhes ${icon("arrowRight")}</span>
        </div>
      </a>
    </article>`;
}

function renderOverview() {
  const projects = dashboard.projects;
  const filterList = filters(projects);
  const active = filterList.find((item) => item.key === uiState.filter) || filterList[0];
  const visible = projects.filter(active.match);
  return `
    <main id="conteudo-principal" class="main-content" tabindex="-1"${uiState.managementOpen ? ' inert aria-hidden="true"' : ""}>
      <h1 class="sr-only">Visão geral dos projetos acompanhados</h1>
      <section class="stats-grid" aria-label="Resumo dos projetos">
        ${projectStats(projects).map((item) => `
          <div class="stat-card" data-tone="${item.tone}">
            <strong>${item.value}</strong>
            <span>${escapeHtml(item.label)}</span>
          </div>`).join("")}
      </section>
      <nav class="filters" aria-label="Filtrar projetos">
        ${filterList.map((item) => `
          <button class="filter-button" type="button" data-filter="${item.key}" aria-pressed="${item.key === active.key}">
            <span>${escapeHtml(item.label)}</span><span class="filter-count" aria-label="${item.count} projetos">${item.count}</span>
          </button>`).join("")}
      </nav>
      <section class="projects-section" aria-label="Projetos acompanhados">
        <div class="projects-grid">
          ${visible.map(projectCard).join("")}
        </div>
        ${visible.length ? "" : `
          <div class="empty-state">
            <h2>${projects.length ? "Nenhum projeto neste filtro" : "Nenhum projeto acompanhado"}</h2>
            <p>${projects.length ? "Escolha outro filtro para continuar acompanhando os projetos." : "Adicione um projeto ao acompanhamento para ver o trabalho por aqui."}</p>
            ${projects.length ? '<button class="button button--secondary" type="button" data-filter="todos">Mostrar todos</button>' : ""}
          </div>`}
      </section>
    </main>`;
}

function callout(project) {
  if (project.blocker) return { tone: "coral", icon: "alert", title: project.blocker.title, text: project.blocker.message };
  if (project.stale) return { tone: "amber", icon: "clock", title: "Sem atualização recente", text: project.staleMessage };
  if (project.status === "concluido") return { tone: "green", icon: "check", title: "Implementação concluída", text: "Todas as tasks desta implementação foram concluídas e conferidas." };
  return null;
}

function currentTaskCard(project) {
  const current = project.current;
  if (!current) return "";
  const complete = project.status === "concluido";
  const blocks = [
    { icon: "play", label: complete ? "O que foi feito" : "O que está sendo feito agora", text: current.whatDoing, tone: "accent" },
    { icon: "target", label: "Por que isso está sendo feito", text: current.why, tone: "muted" },
    { icon: "check", label: complete ? "O que já está pronto" : "Quando esta task terminar", text: current.whenDone, tone: "green" },
    { icon: "clock", label: "Última atualização", text: current.lastUpdate, tone: "muted" },
    { icon: "list", label: complete ? "Pendências" : "O que falta nesta task", text: current.remaining, tone: project.blocker ? "coral" : "muted" },
  ];
  return `
    <section class="panel current-task" aria-labelledby="currentTaskTitle">
      <div class="current-task-heading">
        <div>
          <span class="section-kicker"><span class="pulse-dot" aria-hidden="true"></span>Task atual</span>
          <h2 id="currentTaskTitle">${escapeHtml(current.title)}</h2>
        </div>
        <span class="task-position task-position--accent">${escapeHtml(taskPosition(project))}</span>
      </div>
      <div class="task-info-grid">
        ${blocks.map((block) => `
          <div class="task-info-block" data-tone="${block.tone}">
            <div class="info-label">${icon(block.icon)}<span>${escapeHtml(block.label)}</span></div>
            <p>${escapeHtml(block.text)}</p>
          </div>`).join("")}
      </div>
    </section>`;
}

function stageProgress(project) {
  return `
    <section class="panel stage-panel" aria-labelledby="stageTitle">
      <div class="panel-heading-row">
        <h2 id="stageTitle">Progresso por etapas</h2>
        <span>Etapa ${project.stage + 1} de 5 · ${escapeHtml(STAGE_LABELS[project.stage])}</span>
      </div>
      <ol class="stage-track">
        ${STAGE_LABELS.map((label, index) => {
          const state = project.status === "concluido" || index < project.stage ? "done" : index === project.stage ? "current" : "waiting";
          return `
            <li class="stage-item" data-state="${state}">
              <span class="stage-node" aria-hidden="true">${state === "done" ? icon("check") : state === "current" ? '<span class="stage-current-dot"></span>' : ""}</span>
              <span class="stage-label"><span class="stage-state-text">${state === "done" ? "Concluída: " : state === "current" ? "Atual: " : "Ainda não iniciada: "}</span>${escapeHtml(label)}</span>
            </li>`;
        }).join("")}
      </ol>
    </section>`;
}

function taskList(project) {
  return `
    <section class="panel tasks-panel" aria-labelledby="tasksTitle">
      <h2 id="tasksTitle">Todas as tasks desta implementação</h2>
      <p class="panel-description">A trilha completa da jornada, na ordem planejada. Abra uma task concluída para ver o resultado.</p>
      <ol class="task-journey">
        ${project.tasks.map((item, index) => {
          const key = `${project.id}:${item.id || item.number}`;
          const open = uiState.expandedTasks.has(key);
          const last = index === project.tasks.length - 1;
          const node = item.state === "done" ? icon("check") : String(item.number);
          return `
            <li class="journey-item" data-state="${item.state}">
              <div class="journey-rail" aria-hidden="true"><span class="journey-node">${node}</span>${last ? "" : '<span class="journey-line"></span>'}</div>
              <div class="journey-content">
                ${item.state === "done" && item.result ? `
                  <button class="journey-toggle" type="button" data-task-toggle="${escapeHtml(key)}" aria-expanded="${open}">
                    <span>${item.number}. ${escapeHtml(item.title)}</span>${icon("chevron", open ? "icon--open" : "")}
                  </button>` : `<h3>${item.number}. ${escapeHtml(item.title)}</h3>`}
                <p>${escapeHtml(item.description)}</p>
                ${item.state === "doing" ? '<span class="current-label"><span class="pulse-dot" aria-hidden="true"></span>Acontecendo agora</span>' : ""}
                ${open ? `<div class="task-result"><strong>Resultado</strong><p>${escapeHtml(item.result)}</p></div>` : ""}
              </div>
            </li>`;
        }).join("")}
      </ol>
    </section>`;
}

function lastCompleted(project) {
  if (!project.lastCompleted) return "";
  return `
    <section class="panel side-panel" aria-labelledby="lastCompletedTitle">
      <div class="side-heading"><span class="side-icon" data-tone="green">${icon("check")}</span><h2 id="lastCompletedTitle">Última task concluída</h2></div>
      <h3>${escapeHtml(project.lastCompleted.title)}</h3>
      <p>${escapeHtml(project.lastCompleted.result)}</p>
      <span class="side-meta">Concluída ${escapeHtml(formatDateTime(project.lastCompleted.completedAt))}.</span>
    </section>`;
}

function recentUpdates(project) {
  if (!project.recentUpdates.length) return "";
  return `
    <section class="panel side-panel" aria-labelledby="recentUpdatesTitle">
      <h2 id="recentUpdatesTitle">Atualizações recentes</h2>
      <ol class="updates-timeline">
        ${project.recentUpdates.map((item, index) => `
          <li>
            <span class="update-marker" aria-hidden="true"></span>
            <div><time datetime="${escapeHtml(item.at)}">${formatClock(item.at)}</time><p>${escapeHtml(item.text)}</p></div>
            ${index === project.recentUpdates.length - 1 ? "" : '<span class="update-line" aria-hidden="true"></span>'}
          </li>`).join("")}
      </ol>
    </section>`;
}

function unavailableDetail(project) {
  return `
    <section class="panel unavailable-detail" aria-labelledby="unavailableTitle">
      <span class="unavailable-icon">${icon("unavailable")}</span>
      <h2 id="unavailableTitle">Projeto indisponível</h2>
      <p>${escapeHtml(project.unavailableMessage)}</p>
      <button class="button button--secondary" type="button" data-retry>${icon("refresh")}Tentar novamente</button>
    </section>`;
}

function missingProjectDetail() {
  return `
    <main id="conteudo-principal" class="main-content" tabindex="-1"${uiState.managementOpen ? ' inert aria-hidden="true"' : ""}>
      <a class="back-link" href="#">${icon("arrowLeft")}Voltar para todos os projetos</a>
      <section class="panel unavailable-detail">
        <span class="unavailable-icon">${icon("unavailable")}</span>
        <h1 id="detailTitle" tabindex="-1">Projeto não encontrado</h1>
        <p>Este projeto não faz mais parte do acompanhamento atual.</p>
      </section>
    </main>`;
}

function renderDetail(project) {
  if (!project) return missingProjectDetail();
  const notice = callout(project);
  const unavailable = project.status === "indisponivel";
  return `
    <main id="conteudo-principal" class="main-content detail-page" tabindex="-1"${uiState.managementOpen ? ' inert aria-hidden="true"' : ""}>
      <a class="back-link" href="#" data-back>${icon("arrowLeft")}Voltar para todos os projetos</a>
      <header class="detail-header">
        <div class="detail-heading-copy">
          <div class="title-with-status"><h1 id="detailTitle" tabindex="-1">${escapeHtml(project.name)}</h1>${statusChip(project)}</div>
          <p class="implementation-line"><span>Implementação:</span> <strong>${escapeHtml(project.implementation)}</strong></p>
          ${project.summary ? `<p class="detail-summary">${escapeHtml(project.summary)}</p>` : ""}
        </div>
        <dl class="detail-facts">
          <div><dt>Task atual</dt><dd>${escapeHtml(taskPosition(project))}</dd></div>
          <div><dt>Última atualização</dt><dd>${project.updatedAt ? timestamp(project.updatedAt, "") : "—"}</dd></div>
        </dl>
      </header>
      ${unavailable ? unavailableDetail(project) : `
        ${notice ? `<div class="detail-callout" data-tone="${notice.tone}"><span class="callout-icon">${icon(notice.icon)}</span><div><strong>${escapeHtml(notice.title)}</strong><p>${escapeHtml(notice.text)}</p></div></div>` : ""}
        <div class="detail-layout">
          <div class="detail-main-column">
            ${currentTaskCard(project)}
            ${stageProgress(project)}
            ${taskList(project)}
          </div>
          <aside class="detail-sidebar" aria-label="Resumo e atualizações do projeto">
            ${lastCompleted(project)}
            ${recentUpdates(project)}
          </aside>
        </div>`}
    </main>`;
}

function managedRepoStatus(repo) {
  if (!repo.available) return "Pasta não encontrada neste computador";
  if (!repo.configured) return "Ainda sem informações de acompanhamento";
  if (repo.hidden) return "Oculta da visão geral";
  return "Visível na visão geral";
}

function renderManagedRepo(repo) {
  const isBusy = uiState.managementBusyPath === repo.path;
  const isConfirming = uiState.removeCandidate === repo.path;
  return `
    <li class="managed-repo" data-state="${repo.hidden ? "hidden" : repo.available ? "visible" : "missing"}">
      <div class="managed-repo-copy">
        <strong>${escapeHtml(repo.name || repo.path)}</strong>
        <span class="managed-repo-path">${escapeHtml(repo.path)}</span>
        <span class="managed-repo-status">${escapeHtml(managedRepoStatus(repo))}</span>
      </div>
      ${isConfirming ? `
        <div class="remove-confirmation" role="group" aria-label="Confirmar remoção de ${escapeHtml(repo.name || repo.path)}">
          <p>A pasta e seus arquivos continuarão no computador. Somente o acompanhamento será removido.</p>
          <div class="managed-repo-actions">
            <button class="button button--quiet" type="button" data-cancel-remove>Cancelar</button>
            <button class="button button--danger" type="button" data-confirm-remove data-path="${escapeHtml(repo.path)}">Remover do painel</button>
          </div>
        </div>` : `
        <div class="managed-repo-actions">
          <button class="button button--quiet" type="button" data-repo-action="${repo.hidden ? "show" : "hide"}" data-path="${escapeHtml(repo.path)}" ${isBusy ? "disabled" : ""}>
            ${icon(repo.hidden ? "eye" : "eyeOff")}
            <span>${repo.hidden ? "Mostrar novamente" : "Ocultar"}</span>
          </button>
          <button class="button button--quiet button--remove" type="button" data-request-remove data-path="${escapeHtml(repo.path)}" ${isBusy ? "disabled" : ""} aria-label="Remover ${escapeHtml(repo.name || repo.path)} do painel">
            ${icon("trash")}
            <span>Remover</span>
          </button>
        </div>`}
    </li>`;
}

function renderProjectManager() {
  if (!uiState.managementOpen) return "";
  const count = uiState.managedRepos.length;
  const message = uiState.managementMessage;
  return `
    <div class="project-manager-layer" id="projectManagerLayer">
      <button class="project-manager-backdrop" type="button" data-manager-close aria-label="Fechar gerenciamento de projetos"></button>
      <section class="project-manager" id="projectManager" role="dialog" aria-modal="true" aria-labelledby="projectManagerTitle" aria-describedby="projectManagerDescription" tabindex="-1">
        <header class="project-manager-header">
          <div>
            <span class="section-kicker">Pastas locais</span>
            <h2 id="projectManagerTitle">Gerenciar projetos</h2>
            <p id="projectManagerDescription">Escolha quais pastas aparecem no acompanhamento.</p>
          </div>
          <button class="icon-button" type="button" data-manager-close aria-label="Fechar">${icon("close")}</button>
        </header>

        <form class="add-path-form" id="addRepoForm">
          <label for="repoPath">Adicionar uma pasta</label>
          <div class="add-path-row">
            <input id="repoPath" name="path" type="text" autocomplete="off" spellcheck="false" placeholder="Ex.: D:\\Sync\\meu-projeto" required>
            <button class="button button--primary" type="submit" ${uiState.managementLoading || uiState.managementBusyPath === "__adding__" ? "disabled" : ""}>
              ${icon("plus")}
              <span>Adicionar</span>
            </button>
          </div>
          <p class="field-help">Informe o caminho completo de uma pasta que já existe neste computador.</p>
        </form>

        ${message ? `<p class="manager-message" data-tone="${escapeHtml(message.tone || "neutral")}" role="status">${escapeHtml(message.text)}</p>` : ""}

        <div class="managed-list-heading">
          <h3>Pastas acompanhadas</h3>
          <span>${count} ${count === 1 ? "pasta" : "pastas"}</span>
        </div>
        <div class="managed-list-scroll">
          ${uiState.managementLoading && !count ? '<p class="manager-empty">Carregando as pastas…</p>' : ""}
          ${!uiState.managementLoading && !count ? '<p class="manager-empty">Nenhuma pasta foi adicionada ainda.</p>' : ""}
          ${count ? `<ul class="managed-repo-list">${uiState.managedRepos.map(renderManagedRepo).join("")}</ul>` : ""}
        </div>

        <footer class="project-manager-footer">
          Ocultar ou remover afeta somente este painel. Nenhuma pasta ou arquivo será apagado.
        </footer>
      </section>
    </div>`;
}

function render(options = {}) {
  const selected = uiState.selectedId
    ? dashboard.projects.find((project) => project.id === uiState.selectedId)
    : null;
  app.innerHTML = `${renderHeader()}${uiState.selectedId ? renderDetail(selected) : renderOverview()}${renderProjectManager()}`;
  document.body.classList.toggle("has-open-manager", uiState.managementOpen);
  updateTimeLabels();
  if (options.focusSelector) {
    requestAnimationFrame(() => document.querySelector(options.focusSelector)?.focus());
  }
}

function updateTimeLabels() {
  const now = Date.now();
  document.querySelectorAll("[data-relative-time]").forEach((element) => {
    const prefix = element.dataset.prefix || "";
    element.textContent = prefix + relativeTime(element.dataset.relativeTime, now);
  });
  const panelClock = document.getElementById("panelClock");
  const panelRelative = document.getElementById("panelRelative");
  if (panelClock) panelClock.textContent = formatClock(uiState.lastFetchAt);
  if (panelRelative) panelRelative.textContent = relativeTime(uiState.lastFetchAt, now);
}

function announce(message) {
  announcer.textContent = "";
  window.setTimeout(() => { announcer.textContent = message; }, 30);
}

async function requestJson(url, options = {}) {
  const headers = { Accept: "application/json", ...(options.headers || {}) };
  if (dashboard.actionToken) headers["X-Harness-Hub-Token"] = dashboard.actionToken;
  if (options.body) headers["Content-Type"] = "application/json";
  const response = await fetch(url, { cache: "no-store", ...options, headers });
  let payload = {};
  try {
    payload = await response.json();
  } catch (_error) {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload.error || `Não foi possível concluir a ação (${response.status}).`);
  }
  return payload;
}

async function fetchJson(url) {
  return requestJson(url);
}

function normalizeManagedRepos(payload) {
  return (Array.isArray(payload?.repos) ? payload.repos : []).map((repo) => ({
    path: String(repo.path || ""),
    name: String(repo.name || String(repo.path || "").split(/[\\/]/).filter(Boolean).pop() || repo.path || "Pasta"),
    hidden: Boolean(repo.hidden),
    available: repo.available !== false,
    configured: repo.configured !== false,
  })).filter((repo) => repo.path);
}

async function openProjectManager() {
  uiState.managementOpen = true;
  uiState.managementLoading = true;
  uiState.managementMessage = null;
  uiState.removeCandidate = "";
  render({ focusSelector: "#projectManager" });
  if (!/^https?:$/.test(window.location.protocol)) {
    uiState.managementLoading = false;
    uiState.managementMessage = {
      tone: "attention",
      text: "O gerenciamento de pastas fica disponível quando a interface é aberta pelo atalho do Harness.",
    };
    render({ focusSelector: "[data-manager-close]" });
    return;
  }
  try {
    const payload = await requestJson("/api/repos");
    uiState.managedRepos = normalizeManagedRepos(payload);
    uiState.managementLoading = false;
    render({ focusSelector: "#repoPath" });
  } catch (error) {
    uiState.managementLoading = false;
    uiState.managementMessage = {
      tone: "attention",
      text: error.message || "Não foi possível carregar as pastas acompanhadas.",
    };
    render({ focusSelector: "[data-manager-close]" });
  }
}

function closeProjectManager() {
  uiState.managementOpen = false;
  uiState.managementLoading = false;
  uiState.managementBusyPath = "";
  uiState.removeCandidate = "";
  render({ focusSelector: "#manageProjectsButton" });
}

async function changeManagedRepo(action, path) {
  const endpoints = {
    add: "/api/repos/add",
    hide: "/api/repos/hide",
    show: "/api/repos/show",
    remove: "/api/repos/remove",
  };
  const actionLabels = {
    add: "Pasta adicionada ao acompanhamento.",
    hide: "Pasta ocultada da visão geral.",
    show: "Pasta mostrada novamente na visão geral.",
    remove: "Pasta removida do painel. Os arquivos foram preservados.",
  };
  uiState.managementBusyPath = action === "add" ? "__adding__" : path;
  uiState.managementMessage = null;
  render({ focusSelector: "#projectManager" });
  try {
    const payload = await requestJson(endpoints[action], {
      method: "POST",
      body: JSON.stringify({ path }),
    });
    uiState.managedRepos = normalizeManagedRepos(payload);
    uiState.managementMessage = { tone: "success", text: actionLabels[action] };
    uiState.removeCandidate = "";
    uiState.managementBusyPath = "";
    await refresh({ silent: true });
    render({ focusSelector: action === "add" ? "#repoPath" : "#projectManager" });
    announce(actionLabels[action]);
  } catch (error) {
    uiState.managementBusyPath = "";
    uiState.managementMessage = {
      tone: "attention",
      text: error.message || "Não foi possível atualizar esta pasta.",
    };
    render({ focusSelector: action === "add" ? "#repoPath" : "#projectManager" });
  }
}

async function fetchSnapshot() {
  if (!/^https?:$/.test(window.location.protocol)) return null;
  const candidates = ["/api/world", "./hub-state.json", "./state.json"];
  let lastError = null;
  for (const candidate of candidates) {
    try {
      const data = await fetchJson(candidate);
      if (Array.isArray(data?.repos) || Array.isArray(data?.projects) || Array.isArray(data?.world?.repos)) return data;
    } catch (error) {
      lastError = error;
    }
  }
  if (lastError) throw lastError;
  return null;
}

async function refresh({ manual = false, silent = false } = {}) {
  if (uiState.refreshing) return;
  uiState.refreshing = true;
  if (manual) render({ focusSelector: "#refreshButton" });
  try {
    const snapshot = await fetchSnapshot();
    if (snapshot) {
      const actionToken = dashboard.actionToken;
      dashboard = buildDashboardState(snapshot);
      if (!dashboard.actionToken) dashboard.actionToken = actionToken;
      uiState.connection = "active";
    } else if (!dashboard.projects.length && !hasBootstrapProjects) {
      dashboard = buildDashboardState(mockState);
      uiState.connection = "demo";
    }
    uiState.lastFetchAt = Date.now();
    uiState.refreshing = false;
    render(manual ? { focusSelector: "#refreshButton" } : {});
    if (!silent) announce("Acompanhamento atualizado.");
  } catch (_error) {
    uiState.refreshing = false;
    uiState.connection = dashboard.projects.length ? "active" : "error";
    render(manual ? { focusSelector: "#refreshButton" } : {});
    if (!silent) announce("Não foi possível atualizar agora. As últimas informações continuam visíveis.");
  }
}

function scheduleRefresh() {
  window.clearTimeout(refreshTimer);
  refreshTimer = window.setTimeout(() => refresh({ silent: true }), 250);
}

function stopRealtime() {
  if (eventSource) eventSource.close();
  eventSource = null;
  window.clearInterval(pollTimer);
  pollTimer = 0;
}

function startPolling() {
  if (pollTimer) return;
  pollTimer = window.setInterval(() => refresh({ silent: true }), Math.max(2500, refreshMs));
}

function startRealtime() {
  stopRealtime();
  if (!/^https?:$/.test(window.location.protocol) || typeof EventSource === "undefined") {
    startPolling();
    return;
  }
  const url = new URL("/api/events", window.location.origin);
  url.searchParams.set("offset", "0");
  if (dashboard.actionToken) url.searchParams.set("token", dashboard.actionToken);
  eventSource = new EventSource(url);
  eventSource.onopen = () => { uiState.connection = "active"; };
  eventSource.onmessage = scheduleRefresh;
  eventSource.addEventListener("events", scheduleRefresh);
  eventSource.onerror = () => {
    eventSource?.close();
    eventSource = null;
    startPolling();
  };
}

app.addEventListener("click", (event) => {
  if (event.target.closest("#manageProjectsButton")) {
    openProjectManager();
    return;
  }
  if (event.target.closest("[data-manager-close]")) {
    closeProjectManager();
    return;
  }
  const repoAction = event.target.closest("[data-repo-action]");
  if (repoAction) {
    changeManagedRepo(repoAction.dataset.repoAction, repoAction.dataset.path || "");
    return;
  }
  const requestRemove = event.target.closest("[data-request-remove]");
  if (requestRemove) {
    uiState.removeCandidate = requestRemove.dataset.path || "";
    render({ focusSelector: "[data-cancel-remove]" });
    return;
  }
  if (event.target.closest("[data-cancel-remove]")) {
    uiState.removeCandidate = "";
    render({ focusSelector: "#projectManager" });
    return;
  }
  const confirmRemove = event.target.closest("[data-confirm-remove]");
  if (confirmRemove) {
    changeManagedRepo("remove", confirmRemove.dataset.path || "");
    return;
  }
  const filterButton = event.target.closest("[data-filter]");
  if (filterButton) {
    uiState.filter = filterButton.dataset.filter || "todos";
    render({ focusSelector: `[data-filter="${selectorEscape(uiState.filter)}"]` });
    return;
  }
  if (event.target.closest("#refreshButton") || event.target.closest("[data-retry]")) {
    refresh({ manual: true });
    return;
  }
  const toggle = event.target.closest("[data-task-toggle]");
  if (toggle) {
    const key = toggle.dataset.taskToggle;
    if (uiState.expandedTasks.has(key)) uiState.expandedTasks.delete(key);
    else uiState.expandedTasks.add(key);
    render({ focusSelector: `[data-task-toggle="${selectorEscape(key)}"]` });
    return;
  }
  const back = event.target.closest("[data-back]");
  if (back) uiState.returnFocusId = uiState.selectedId;
});

app.addEventListener("submit", (event) => {
  if (event.target.id !== "addRepoForm") return;
  event.preventDefault();
  const form = new FormData(event.target);
  const path = String(form.get("path") || "").trim();
  if (!path) return;
  changeManagedRepo("add", path);
});

document.addEventListener("keydown", (event) => {
  if (!uiState.managementOpen) return;
  if (event.key === "Escape") {
    event.preventDefault();
    closeProjectManager();
    return;
  }
  if (event.key !== "Tab") return;
  const modal = document.getElementById("projectManager");
  if (!modal) return;
  const focusable = [...modal.querySelectorAll('button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])')]
    .filter((element) => !element.hasAttribute("hidden"));
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});

window.addEventListener("hashchange", () => {
  const previous = uiState.selectedId;
  uiState.selectedId = projectFromHash();
  if (!uiState.selectedId && previous) uiState.returnFocusId = previous;
  const selector = uiState.selectedId
    ? "#detailTitle"
    : uiState.returnFocusId
      ? `[data-project-link="${selectorEscape(uiState.returnFocusId)}"]`
      : "#conteudo-principal";
  render({ focusSelector: selector });
});

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") refresh({ silent: true });
});

window.addEventListener("beforeunload", stopRealtime);

render(uiState.selectedId ? { focusSelector: "#detailTitle" } : {});
window.setInterval(updateTimeLabels, 1000);
startRealtime();
refresh({ silent: true });
