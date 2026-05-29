// Tile-based town renderer for a single repo map. Theme-aware via tilesets.
import { drawTile, loadSheet, sheetReady, getTileset, TILESETS } from "./tiles.js";
import { generateTown, TILE, COLS, ROWS, MAP_W, MAP_H } from "./mapgen.js";

export const WORLD_WIDTH = MAP_W;
export const WORLD_HEIGHT = 720;

const townCache = new Map();

export function ensureTown(repo) {
  const id = repo?.id || repo?.root || "demo";
  if (!townCache.has(id)) townCache.set(id, generateTown(repo));
  return townCache.get(id);
}

export function sheetKeyForRepo(repo) {
  try {
    const override = window.localStorage.getItem("hubTheme:" + (repo?.id || ""));
    if (TILESETS[override]) return override;
  } catch (_) { /* ignore */ }
  const key = String(repo?.theme?.key || repo?.theme || "");
  return key === "dungeon" || key === "tiny-dungeon" ? "tiny-dungeon" : "tiny-town";
}

const SECTOR_ACCENT = {
  plan: "#d9a441", implement: "#54a7c7", review: "#9b84d8",
  research: "#4fb9a8", security: "#e15b4f", report: "#58b86d", idle: "#cbb994",
};

function groundIndex(ts, cell) {
  if (cell.t === "grass") return cell.v === 2 ? ts.ground.flower : cell.v === 1 ? ts.ground.detail : ts.ground.plain;
  if (cell.t === "path") return ts.path;
  if (cell.t === "plaza") return ts.usePlaza9 ? ts.plaza9[cell.e] : ts.path;
  return ts.ground.plain;
}

function decoIndex(ts, kind) {
  if (kind === "small") return ts.tree.small;
  if (kind === "bush") return ts.tree.bush;
  if (kind === "tuft") return ts.tree.tuft;
  if (kind === "mush") return ts.tree.mush;
  return null;
}

function drawShadowEllipse(ctx, x, y, rx, ry) {
  ctx.save();
  ctx.fillStyle = "rgba(0,0,0,.22)";
  ctx.beginPath();
  ctx.ellipse(x, y, rx, ry, 0, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawHouse(ctx, sheet, ts, b) {
  const kitName = ts.sectorKit[b.key] || Object.keys(ts.kits)[0];
  const kit = ts.kits[kitName] || ts.kits[Object.keys(ts.kits)[0]];
  const x = b.col * TILE;
  const y = b.row * TILE;
  drawShadowEllipse(ctx, x + 1.5 * TILE, y + 3 * TILE - 4, TILE * 1.4, TILE * 0.4);
  for (let dc = 0; dc < 3; dc += 1) {
    drawTile(ctx, sheet, kit.roof[dc], x + dc * TILE, y, TILE);
    drawTile(ctx, sheet, kit.eave[dc], x + dc * TILE, y + TILE, TILE);
    drawTile(ctx, sheet, kit.wall[dc], x + dc * TILE, y + 2 * TILE, TILE);
  }
}

function drawTreeTall(ctx, sheet, ts, t) {
  const top = t.orange ? ts.tree.tallTop.orange : ts.tree.tallTop.green;
  const bot = t.orange ? ts.tree.tallBot.orange : ts.tree.tallBot.green;
  const x = t.col * TILE;
  const y = t.row * TILE;
  drawShadowEllipse(ctx, x + TILE / 2, y + TILE - 3, TILE * 0.5, TILE * 0.22);
  drawTile(ctx, sheet, bot, x, y, TILE);
  drawTile(ctx, sheet, top, x, y - TILE, TILE);
}

export function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function pixelLabel(ctx, text, cx, topY, accent) {
  ctx.save();
  ctx.font = "700 12px 'Segoe UI', system-ui, sans-serif";
  const w = Math.max(48, ctx.measureText(text).width + 16);
  const x = Math.round(cx - w / 2);
  ctx.fillStyle = "rgba(12,16,12,.82)";
  roundRect(ctx, x, topY, w, 20, 5);
  ctx.fill();
  ctx.fillStyle = accent || "#f3ecd8";
  ctx.fillRect(x, topY, 3, 20);
  ctx.fillStyle = "#f3ecd8";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText(text, cx, topY + 10);
  ctx.restore();
}

function drawSelection(ctx, sector) {
  ctx.save();
  ctx.strokeStyle = "rgba(243,236,216,.9)";
  ctx.lineWidth = 3;
  ctx.setLineDash([8, 6]);
  roundRect(ctx, sector.x - 4, sector.y - 4, sector.w + 8, sector.h + 8, 8);
  ctx.stroke();
  ctx.restore();
}

export function drawRepoMap(ctx, repo, options = {}) {
  const town = ensureTown(repo);
  const sheet = sheetKeyForRepo(repo);
  const ts = getTileset(sheet);
  loadSheet(sheet);

  ctx.imageSmoothingEnabled = false;
  ctx.clearRect(0, 0, MAP_W, MAP_H);

  if (!sheetReady(sheet)) {
    ctx.fillStyle = sheet === "tiny-dungeon" ? "#3a2b2b" : "#3b5f3f";
    ctx.fillRect(0, 0, MAP_W, MAP_H);
    ctx.fillStyle = "#f3ecd8";
    ctx.font = "16px system-ui";
    ctx.fillText("Loading tiles…", 24, 36);
    return town;
  }

  for (let r = 0; r < ROWS; r += 1) {
    for (let c = 0; c < COLS; c += 1) {
      drawTile(ctx, sheet, groundIndex(ts, town.ground[r][c]), c * TILE, r * TILE, TILE);
    }
  }

  for (const d of town.deco) {
    if (d.kind === "tree") continue;
    if (d.kind === "sign") continue;
    const idx = decoIndex(ts, d.kind);
    if (idx != null) drawTile(ctx, sheet, idx, d.col * TILE, d.row * TILE, TILE);
  }

  if (options.selectedSector) {
    const sector = town.sectors.find((s) => s.key === options.selectedSector);
    if (sector) drawSelection(ctx, sector);
  }

  const objects = [
    ...town.buildings.map((b) => ({ y: (b.row + 3) * TILE, type: "house", ref: b })),
    ...town.deco.filter((d) => d.kind === "tree").map((t) => ({ y: (t.row + 1) * TILE, type: "tree", ref: t })),
  ].sort((a, b) => a.y - b.y);
  for (const obj of objects) {
    if (obj.type === "house") drawHouse(ctx, sheet, ts, obj.ref);
    else drawTreeTall(ctx, sheet, ts, obj.ref);
  }

  for (const d of town.deco) {
    if (d.kind !== "sign") continue;
    drawTile(ctx, sheet, ts.sign, d.col * TILE, d.row * TILE, TILE);
    const icon = ts.sectorIcon[d.sector];
    if (icon != null) drawTile(ctx, sheet, icon, d.col * TILE, (d.row - 1) * TILE, TILE);
  }

  for (const b of town.buildings) {
    pixelLabel(ctx, b.label, (b.col + 1.5) * TILE, b.row * TILE - 18, SECTOR_ACCENT[b.key]);
  }

  return town;
}

export function hitTestSector(repo, point) {
  const town = ensureTown(repo);
  return [...town.sectors].reverse().find((s) => (
    point.x >= s.x && point.x <= s.x + s.w && point.y >= s.y && point.y <= s.y + s.h
  ));
}
