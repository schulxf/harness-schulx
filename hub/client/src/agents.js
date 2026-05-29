// Canvas-based agent entities: pathfind between sector stations, render sprites.
import { findPath } from "./pathfinding.js";
import { drawAgentSprite } from "./sprites.js";
import { roundRect } from "./render.js";
import { TILE, MAP_W, MAP_H } from "./mapgen.js";
import { roleMeta, sectorForAgent, speechForAgent, stateForAgent } from "./statemachine.js";

const SPRITE = 46;

function dist(a, b) {
  return Math.hypot(a.x - b.x, a.y - b.y);
}

function plazaRect(town) {
  const p = town.plaza;
  return { x: p.col * TILE + 6, y: p.row * TILE + 6, w: p.w * TILE - 12, h: p.h * TILE - 12 };
}

function pointInRect(rect, seed) {
  const rx = (Math.sin(seed * 12.9898) * 43758.5453) % 1;
  const ry = (Math.sin(seed * 78.233) * 12345.678) % 1;
  return {
    x: rect.x + (Math.abs(rx)) * rect.w,
    y: rect.y + (Math.abs(ry)) * rect.h,
  };
}

export class AgentLayer {
  constructor() {
    this.entities = new Map();
    this.now = 0;
  }

  sync(repo, town) {
    const seen = new Set();
    (repo?.agents || []).forEach((agent, index) => {
      seen.add(agent.id);
      let e = this.entities.get(agent.id);
      const sector = sectorForAgent(agent);
      const station = town.stations[sector] || town.stations.idle || town.plaza.center;
      if (!e) {
        const start = town.stations.idle || town.plaza.center;
        e = {
          id: agent.id, agent, x: start.x + (index % 4) * 22 - 33, y: start.y + ((index % 3) - 1) * 18,
          target: { ...start }, path: [], pathIndex: 0,
          speed: 72 + (index % 4) * 8, bobPhase: index * 1.3,
          idleUntil: 0, sector: null, pathTargetSector: null,
        };
        this.entities.set(agent.id, e);
      }
      e.agent = agent;
      const state = stateForAgent(agent);
      // Only (re)path when the target sector changes — not every frame.
      if (state !== "idle" && e.pathTargetSector !== sector) {
        e.target = { ...station };
        e.path = findPath({ x: e.x, y: e.y }, e.target, { width: MAP_W, height: MAP_H, blockedRects: town.blockedRects });
        e.pathIndex = 1;
        e.pathTargetSector = sector;
      }
      if (state === "idle") e.pathTargetSector = null; // allow re-path when work resumes
      e.sector = sector;
    });
    for (const [id, e] of this.entities) {
      if (!seen.has(id)) this.entities.delete(id);
    }
  }

  update(dt, town) {
    this.now += dt;
    const plaza = plazaRect(town);
    for (const e of this.entities.values()) {
      const state = stateForAgent(e.agent);
      const moving = e.path.length > e.pathIndex;
      if (state !== "offline" && moving) {
        const next = e.path[e.pathIndex];
        const remaining = dist(e, next);
        const step = e.speed * dt;
        if (remaining <= step) {
          e.x = next.x; e.y = next.y; e.pathIndex += 1;
        } else {
          e.x += ((next.x - e.x) / remaining) * step;
          e.y += ((next.y - e.y) / remaining) * step;
        }
        e.bobPhase += dt * 10;
      } else if (state === "idle" && this.now > e.idleUntil) {
        const target = pointInRect(plaza, this.now + e.bobPhase);
        e.target = target;
        e.path = findPath({ x: e.x, y: e.y }, target, { width: MAP_W, height: MAP_H, blockedRects: town.blockedRects });
        e.pathIndex = 1;
        e.idleUntil = this.now + 3 + Math.abs(Math.sin(e.bobPhase)) * 4;
      }
    }
  }

  hitTest(point) {
    let hit = null;
    for (const e of this.entities.values()) {
      const left = e.x - SPRITE / 2, top = e.y - SPRITE;
      if (point.x >= left && point.x <= left + SPRITE && point.y >= top && point.y <= e.y + 6) hit = e.id;
    }
    return hit;
  }

  draw(ctx, town, selectedId) {
    const list = [...this.entities.values()].sort((a, b) => a.y - b.y);
    for (const e of list) {
      const state = stateForAgent(e.agent);
      const meta = roleMeta(e.agent.role);
      const moving = e.path.length > e.pathIndex;
      const bob = moving ? Math.sin(e.bobPhase) * 2.5 : Math.sin(this.now * 2 + e.bobPhase) * 1.2;

      // shadow
      ctx.fillStyle = "rgba(0,0,0,.25)";
      ctx.beginPath();
      ctx.ellipse(e.x, e.y - 2, SPRITE * 0.28, SPRITE * 0.12, 0, 0, Math.PI * 2);
      ctx.fill();

      // selection ring
      if (e.id === selectedId) {
        ctx.strokeStyle = meta.color;
        ctx.lineWidth = 2.5;
        ctx.beginPath();
        ctx.ellipse(e.x, e.y - 2, SPRITE * 0.34, SPRITE * 0.16, 0, 0, Math.PI * 2);
        ctx.stroke();
      }

      ctx.globalAlpha = state === "offline" ? 0.45 : 1;
      drawAgentSprite(ctx, e.agent.role, e.x, e.y, SPRITE, { bob, color: meta.color });
      ctx.globalAlpha = 1;

      // name tag
      drawNameTag(ctx, e.agent.name || e.agent.id, meta.color, e.x, e.y + 4);

      // speech bubble
      const speech = speechForAgent(e.agent);
      if (speech && (e.id === selectedId || state === "working" || state === "talking")) {
        drawSpeech(ctx, speech, e.x, e.y - SPRITE - 6 + bob);
      }

      // state dot
      drawStateDot(ctx, state, e.x + SPRITE * 0.28, e.y - SPRITE + 4);
    }
  }
}

function drawNameTag(ctx, text, color, cx, topY) {
  ctx.save();
  ctx.font = "700 10px 'Segoe UI', system-ui, sans-serif";
  const label = text.length > 16 ? `${text.slice(0, 15)}…` : text;
  const w = ctx.measureText(label).width + 14;
  const x = Math.round(cx - w / 2);
  ctx.fillStyle = "rgba(12,16,12,.78)";
  roundRect(ctx, x, topY, w, 15, 4);
  ctx.fill();
  ctx.fillStyle = color;
  ctx.beginPath();
  ctx.arc(x + 6, topY + 7.5, 3, 0, Math.PI * 2);
  ctx.fill();
  ctx.fillStyle = "#f3ecd8";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(label, x + 12, topY + 8);
  ctx.restore();
}

function drawSpeech(ctx, text, cx, bottomY) {
  ctx.save();
  ctx.font = "600 11px 'Segoe UI', system-ui, sans-serif";
  const label = text.length > 30 ? `${text.slice(0, 29)}…` : text;
  const w = ctx.measureText(label).width + 16;
  const h = 22;
  const x = Math.round(cx - w / 2);
  const y = bottomY - h;
  ctx.fillStyle = "rgba(248,244,232,.96)";
  roundRect(ctx, x, y, w, h, 7);
  ctx.fill();
  ctx.beginPath();
  ctx.moveTo(cx - 5, y + h);
  ctx.lineTo(cx + 5, y + h);
  ctx.lineTo(cx, y + h + 6);
  ctx.closePath();
  ctx.fill();
  ctx.fillStyle = "#23301f";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(label, cx, y + h / 2);
  ctx.restore();
}

const STATE_COLOR = { working: "#5cd06a", walking: "#54a7c7", talking: "#d9a441", idle: "#9aa08c", offline: "#6b6b6b" };
function drawStateDot(ctx, state, x, y) {
  ctx.save();
  ctx.fillStyle = STATE_COLOR[state] || "#9aa08c";
  ctx.beginPath();
  ctx.arc(x, y, 3.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(0,0,0,.4)";
  ctx.lineWidth = 1;
  ctx.stroke();
  ctx.restore();
}
