import { roleMeta, speechForAgent, stateForAgent } from "./statemachine.js";

let spriteSheetReady = false;

export function detectSpriteAssets() {
  return new Promise((resolve) => {
    const image = new Image();
    image.onload = () => {
      spriteSheetReady = true;
      document.body.classList.add("has-agent-sheet");
      resolve(true);
    };
    image.onerror = () => {
      spriteSheetReady = false;
      document.body.classList.remove("has-agent-sheet");
      resolve(false);
    };
    image.src = "./assets/sprites/agents.png";
  });
}

export function createAgentElement(agent) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "agent-token";
  button.innerHTML = `
    <span class="agent-bubble"></span>
    <span class="agent-shadow" aria-hidden="true"></span>
    <span class="agent-css-sprite" aria-hidden="true">
      <span class="agent-head"></span>
      <span class="agent-body"></span>
      <span class="agent-arm-left"></span>
      <span class="agent-arm-right"></span>
      <span class="agent-leg-left"></span>
      <span class="agent-leg-right"></span>
    </span>
  `;
  updateAgentElement(button, agent, false);
  return button;
}

export function updateAgentElement(element, agent, selected) {
  const meta = roleMeta(agent.role);
  element.dataset.agentId = agent.id;
  element.dataset.role = agent.role || "operator";
  element.dataset.state = stateForAgent(agent);
  element.dataset.selected = selected ? "true" : "false";
  element.style.setProperty("--agent-accent", meta.color);
  element.setAttribute("aria-label", `${agent.name || agent.id}, ${meta.label}, ${stateForAgent(agent)}`);
  element.title = `${agent.name || agent.id} - ${agent.task_id || agent.sector || meta.label}`;
  const bubble = element.querySelector(".agent-bubble");
  if (bubble) bubble.textContent = speechForAgent(agent);
  if (spriteSheetReady) {
    const sprite = element.querySelector(".agent-css-sprite");
    if (sprite) {
      const roleIndex = ["builder", "planner", "reviewer", "security", "research", "operator"].indexOf(String(agent.role || "").toLowerCase());
      sprite.style.backgroundPosition = `${Math.min(0, -48 * Math.max(0, roleIndex))}px 0`;
    }
  }
}
