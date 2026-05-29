import { findPath } from "./pathfinding.js";
import { createAgentElement, updateAgentElement } from "./sprites.js";
import { WORLD_HEIGHT, WORLD_WIDTH } from "./world.js";
import { stateForAgent } from "./statemachine.js";

function distance(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function pointInRect(rect) {
  return {
    x: rect.x + 28 + Math.random() * Math.max(20, rect.w - 56),
    y: rect.y + 42 + Math.random() * Math.max(20, rect.h - 76),
  };
}

function jitter(point, index) {
  return {
    x: Math.max(24, Math.min(WORLD_WIDTH - 24, point.x + ((index % 5) - 2) * 14)),
    y: Math.max(46, Math.min(WORLD_HEIGHT - 24, point.y + ((index % 3) - 1) * 16)),
  };
}

export class AgentLayer {
  constructor(layer, options = {}) {
    this.layer = layer;
    this.entities = new Map();
    this.onSelect = options.onSelect || (() => {});
    this.stageKey = "";
  }

  reconcile(items, targetResolver, selectedAgentId, stageKey) {
    const seen = new Set();
    if (stageKey !== this.stageKey) {
      this.stageKey = stageKey;
      for (const entity of this.entities.values()) {
        entity.path = [];
        entity.pathIndex = 0;
      }
    }

    items.forEach((item, index) => {
      const agent = item.agent;
      const repo = item.repo;
      const id = `${repo.id}:${agent.id}`;
      seen.add(id);
      const targetInfo = targetResolver(item, index);
      const desired = jitter(targetInfo.point, index);
      let entity = this.entities.get(id);
      if (!entity) {
        const start = targetInfo.spawn || desired;
        const element = createAgentElement(agent);
        element.addEventListener("click", (event) => {
          event.stopPropagation();
          this.onSelect(agent, repo);
        });
        this.layer.appendChild(element);
        entity = {
          id,
          agent,
          repo,
          x: start.x,
          y: start.y,
          target: desired,
          homeRect: targetInfo.wanderRect,
          path: [],
          pathIndex: 0,
          speed: 78 + (index % 4) * 7,
          idleUntil: performance.now() + 1200 + index * 240,
          element,
        };
        this.entities.set(id, entity);
      }

      entity.agent = agent;
      entity.repo = repo;
      entity.homeRect = targetInfo.wanderRect;
      const targetChanged = distance(entity.target, desired) > 18 || stateForAgent(agent) === "walking";
      if (targetChanged) {
        entity.target = desired;
        entity.path = findPath({ x: entity.x, y: entity.y }, desired, {
          width: WORLD_WIDTH,
          height: WORLD_HEIGHT,
          blockedRects: targetInfo.blockedRects || [],
        });
        entity.pathIndex = 1;
      }
      updateAgentElement(entity.element, agent, agent.id === selectedAgentId);
    });

    for (const [id, entity] of this.entities) {
      if (!seen.has(id)) {
        entity.element.remove();
        this.entities.delete(id);
      }
    }
  }

  update(dt) {
    const now = performance.now();
    for (const entity of this.entities.values()) {
      const state = stateForAgent(entity.agent);
      if (state !== "offline" && entity.path.length > entity.pathIndex) {
        const next = entity.path[entity.pathIndex];
        const remaining = distance(entity, next);
        const step = entity.speed * dt;
        if (remaining <= step) {
          entity.x = next.x;
          entity.y = next.y;
          entity.pathIndex += 1;
        } else {
          entity.x += ((next.x - entity.x) / remaining) * step;
          entity.y += ((next.y - entity.y) / remaining) * step;
        }
      } else if (state === "idle" && entity.homeRect && now > entity.idleUntil) {
        const next = pointInRect(entity.homeRect);
        entity.target = next;
        entity.path = findPath({ x: entity.x, y: entity.y }, next, { width: WORLD_WIDTH, height: WORLD_HEIGHT });
        entity.pathIndex = 1;
        entity.idleUntil = now + 3200 + Math.random() * 4200;
      }
      entity.element.style.left = `${(entity.x / WORLD_WIDTH) * 100}%`;
      entity.element.style.top = `${(entity.y / WORLD_HEIGHT) * 100}%`;
      entity.element.dataset.state = entity.path.length > entity.pathIndex ? "walking" : state;
    }
  }

  paths() {
    return [...this.entities.values()]
      .filter((entity) => entity.path.length > entity.pathIndex)
      .map((entity) => ({
        from: { x: entity.x, y: entity.y },
        points: entity.path.slice(entity.pathIndex),
        color: getComputedStyle(entity.element).getPropertyValue("--agent-accent") || "#54a7c7",
      }));
  }
}
