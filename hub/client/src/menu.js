// Game-style start menu / onboarding overlay.
// Pick a tileset theme, then either create a new project from zero (folder +
// init + first terminal) or spawn an agent in the current repo.
import { frameForRole } from "./sprites.js";

const THEMES = [
  { key: "tiny-town", name: "Tiny Town", blurb: "Sunny overworld — grass, houses, forests.", sample: "./assets/vendor/kenney_tiny-town/Sample.png" },
  { key: "tiny-dungeon", name: "Tiny Dungeon", blurb: "Stone halls and torchlight for darker work.", sample: "./assets/vendor/kenney_tiny-dungeon/Sample.png" },
];

const ROLES = [
  { key: "builder", label: "Builder", desc: "Works at the Forge" },
  { key: "planner", label: "Planner", desc: "Designs at Planning" },
  { key: "reviewer", label: "Reviewer", desc: "Checks at the Library" },
  { key: "research", label: "Research", desc: "Digs at Research" },
  { key: "security", label: "Security", desc: "Guards the Watchtower" },
  { key: "reporter", label: "Reporter", desc: "Files at Records" },
];

const SPRITE_SHEET = "./assets/sprites/agents.png";

function spriteStyle(role) {
  const frame = frameForRole(role);
  return `background-image:url('${SPRITE_SHEET}');background-size:600% 100%;background-position:${(frame / 5) * 100}% 0;`;
}

function parentOf(p) {
  const s = String(p || "").replace(/[\\/]+$/, "");
  const i = Math.max(s.lastIndexOf("/"), s.lastIndexOf("\\"));
  return i > 0 ? s.slice(0, i) : s;
}

function esc(v) {
  return String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

export class GameMenu {
  constructor(root, handlers = {}) {
    this.root = root;
    this.handlers = handlers;
    this.open = false;
    this.selectedTheme = "tiny-town";
    this.selectedRole = "builder";
    this.repo = null;
    root.addEventListener("click", (e) => this.onClick(e));
    root.addEventListener("submit", (e) => this.onSubmit(e));
  }

  show(context = {}) {
    this.repo = context.repo || null;
    this.selectedTheme = context.theme || this.selectedTheme;
    this.open = true;
    this.render();
  }

  hide() { this.open = false; this.root.hidden = true; this.root.innerHTML = ""; }

  render() {
    if (!this.open) return;
    this.root.hidden = false;
    const repoName = this.repo?.project || "";
    const defaultParent = this.repo?.root ? parentOf(this.repo.root) : "";
    this.root.innerHTML = `
      <div class="menu-scrim" data-act="enter"></div>
      <div class="menu-panel" role="dialog" aria-modal="true">
        <button class="menu-x" data-act="enter" aria-label="Close menu">✕</button>
        <div class="menu-head">
          <span class="menu-kicker">HARNESS HUB</span>
          <h1 class="menu-title">Start a town <small>spawn an agent, watch it work</small></h1>
        </div>

        <section class="menu-section">
          <h2><span class="menu-step">1</span> Theme</h2>
          <div class="theme-grid">
            ${THEMES.map((t) => `
              <button class="theme-card" data-theme="${t.key}" aria-pressed="${t.key === this.selectedTheme}">
                <span class="theme-thumb" style="background-image:url('${t.sample}')"></span>
                <span class="theme-name">${esc(t.name)}</span>
                <span class="theme-blurb">${esc(t.blurb)}</span>
              </button>`).join("")}
          </div>
        </section>

        <section class="menu-section">
          <h2><span class="menu-step">2</span> Agent</h2>
          <div class="role-grid">
            ${ROLES.map((r) => `
              <button class="role-card" data-role="${r.key}" aria-pressed="${r.key === this.selectedRole}">
                <span class="role-sprite" style="${spriteStyle(r.key)}"></span>
                <span class="role-label">${esc(r.label)}</span>
                <span class="role-desc">${esc(r.desc)}</span>
              </button>`).join("")}
          </div>
          <div class="menu-row">
            <label class="menu-field">Terminal
              <select id="menuCli">
                <option value="shell">PowerShell (you drive)</option>
                <option value="claude">Claude (LLM)</option>
                <option value="codex">Codex (LLM)</option>
              </select>
            </label>
            <label class="menu-field">Agent name
              <input id="menuName" placeholder="optional" autocomplete="off">
            </label>
          </div>
        </section>

        <section class="menu-section menu-start">
          <h2><span class="menu-step">3</span> Go</h2>
          <form class="menu-create" data-form="create">
            <div class="menu-row">
              <label class="menu-field">New project folder in
                <input id="menuParent" value="${esc(defaultParent)}" placeholder="C:/Users/you/Desktop" autocomplete="off">
              </label>
              <label class="menu-field">Project name
                <input id="menuProjName" placeholder="my-new-project" autocomplete="off">
              </label>
            </div>
            <button class="menu-cta" type="submit">▶ Create project &amp; open terminal</button>
          </form>
          ${repoName ? `
          <div class="menu-or">or</div>
          <form class="menu-spawn" data-form="spawn">
            <button class="menu-cta menu-cta--ghost" type="submit">Spawn in “${esc(repoName)}” &amp; open terminal</button>
          </form>` : ""}
          <p class="menu-error" id="menuError" hidden></p>
        </section>

        <footer class="menu-foot">
          <form class="menu-add" data-form="addrepo">
            <input name="path" placeholder="Add an existing repo: C:/path/to/repo" autocomplete="off">
            <button type="submit">+ Add repo</button>
          </form>
          <button class="menu-skip" data-act="enter">Enter hub →</button>
        </footer>
      </div>`;
  }

  onClick(e) {
    const theme = e.target.closest(".theme-card[data-theme]");
    if (theme) {
      this.selectedTheme = theme.dataset.theme;
      this.root.querySelectorAll(".theme-card[data-theme]").forEach((el) => { el.setAttribute("aria-pressed", String(el.dataset.theme === this.selectedTheme)); });
      this.handlers.onTheme?.(this.selectedTheme);
      return;
    }
    const role = e.target.closest("[data-role]");
    if (role) {
      this.selectedRole = role.dataset.role;
      this.root.querySelectorAll("[data-role]").forEach((el) => { el.setAttribute("aria-pressed", String(el.dataset.role === this.selectedRole)); });
      return;
    }
    if (e.target.closest("[data-act]")?.dataset.act === "enter") { this.hide(); this.handlers.onEnter?.(); }
  }

  setError(msg) {
    const el = this.root.querySelector("#menuError");
    if (!el) return;
    el.hidden = !msg;
    el.textContent = msg || "";
  }

  setBusy(button, busy, label) {
    if (!button) return;
    button.disabled = busy;
    if (busy) { button.dataset.label = button.textContent; button.textContent = label || "Working…"; }
    else if (button.dataset.label) { button.textContent = button.dataset.label; }
  }

  async onSubmit(e) {
    const form = e.target.closest("[data-form]");
    if (!form) return;
    e.preventDefault();
    this.setError("");
    const cli = this.root.querySelector("#menuCli")?.value || "shell";
    const name = this.root.querySelector("#menuName")?.value || "";
    const btn = form.querySelector("button[type=submit]");
    try {
      if (form.dataset.form === "create") {
        const parent = this.root.querySelector("#menuParent")?.value?.trim();
        const projName = this.root.querySelector("#menuProjName")?.value?.trim();
        if (!parent || !projName) { this.setError("Folder and project name are required."); return; }
        this.setBusy(btn, true, "Creating…");
        await this.handlers.onCreateProject?.({ parent, name: projName, theme: this.selectedTheme, role: this.selectedRole, cli });
        this.hide(); this.handlers.onEnter?.();
      } else if (form.dataset.form === "spawn") {
        this.setBusy(btn, true, "Spawning…");
        await this.handlers.onSpawn?.({ role: this.selectedRole, cli, name, theme: this.selectedTheme });
        this.hide(); this.handlers.onEnter?.();
      } else if (form.dataset.form === "addrepo") {
        const path = new FormData(form).get("path");
        if (!path) return;
        await this.handlers.onAddRepo?.({ path });
      }
    } catch (err) {
      this.setBusy(btn, false);
      this.setError(err?.message || "Action failed. Check that the sidecar is running and the path is valid.");
    }
  }
}
