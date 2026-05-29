// Procedural town generator. Produces a THEME-INDEPENDENT model: ground cells
// and decoration carry semantic kinds, and render.js resolves them to tiles
// using the active theme's tileset. Laid out around a central plaza.

export const TILE = 32; // render size of a 16px source tile
export const COLS = 40;
export const ROWS = 23;
export const MAP_W = COLS * TILE; // 1280
export const MAP_H = ROWS * TILE; // 736 (canvas is 720, bottom row clipped)

function hash(value) {
  let h = 2166136261;
  for (const ch of String(value || "")) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (Math.imul(s, 1664525) + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

const SECTOR_ICON_KEY = {
  plan: "plan", implement: "implement", review: "review",
  research: "research", security: "security", report: "report",
};

// Building anchor (top-left tile) per sector, 3 wide x 3 tall.
const LAYOUT = [
  { key: "plan", label: "Planning", col: 4, row: 3 },
  { key: "implement", label: "Forge", col: 18, row: 1 },
  { key: "review", label: "Library", col: 31, row: 3 },
  { key: "research", label: "Research", col: 34, row: 10 },
  { key: "security", label: "Watchtower", col: 30, row: 16 },
  { key: "report", label: "Records", col: 4, row: 16 },
];

const PLAZA = { col: 15, row: 9, w: 9, h: 5 };

function carveLine(dirt, a, b) {
  let { col: c0, row: r0 } = a;
  const { col: c1, row: r1 } = b;
  const step = (x, y) => { dirt.add(`${x},${y}`); dirt.add(`${x + 1},${y}`); };
  while (c0 !== c1) { step(c0, r0); c0 += c0 < c1 ? 1 : -1; }
  while (r0 !== r1) { step(c0, r0); r0 += r0 < r1 ? 1 : -1; }
  step(c1, r1);
}

function plazaEdge(col, row) {
  const { col: pc, row: pr, w, h } = PLAZA;
  const left = col === pc, right = col === pc + w - 1;
  const top = row === pr, bottom = row === pr + h - 1;
  if (top && left) return "tl";
  if (top && right) return "tr";
  if (bottom && left) return "bl";
  if (bottom && right) return "br";
  if (top) return "t";
  if (bottom) return "b";
  if (left) return "l";
  if (right) return "r";
  return "c";
}

export function generateTown(repo) {
  const seed = hash(repo?.id || repo?.root || repo?.project || "demo");
  const rand = rng(seed);

  const ground = [];
  for (let r = 0; r < ROWS; r += 1) {
    const line = [];
    for (let c = 0; c < COLS; c += 1) {
      const roll = rand();
      line.push({ t: "grass", v: roll > 0.965 ? 2 : roll > 0.92 ? 1 : 0 });
    }
    ground.push(line);
  }

  const buildings = [];
  const stations = {};
  const blocked = new Set();
  const sectors = [];
  for (const def of LAYOUT) {
    const { key, label, col, row } = def;
    const doorCol = col + 1;
    const stationTile = { col: doorCol, row: row + 3 };
    const station = { x: stationTile.col * TILE + TILE / 2, y: stationTile.row * TILE + TILE / 2 };
    for (let dr = 0; dr < 3; dr += 1) {
      for (let dc = 0; dc < 3; dc += 1) blocked.add(`${col + dc},${row + dr}`);
    }
    const rect = { x: col * TILE, y: row * TILE, w: 3 * TILE, h: 3 * TILE };
    buildings.push({ key, label, col, row, doorCol, station, rect, icon: SECTOR_ICON_KEY[key] });
    stations[key] = station;
    sectors.push({ key, label, x: rect.x, y: rect.y, w: rect.w, h: rect.h + TILE, station });
  }

  const plazaCenter = { x: (PLAZA.col + PLAZA.w / 2) * TILE, y: (PLAZA.row + PLAZA.h / 2) * TILE };
  stations.idle = plazaCenter;
  sectors.push({
    key: "idle", label: "Plaza",
    x: PLAZA.col * TILE, y: PLAZA.row * TILE, w: PLAZA.w * TILE, h: PLAZA.h * TILE,
    station: plazaCenter,
  });

  // Dirt: plaza + paths from each station to the plaza centre.
  const dirt = new Set();
  for (let r = PLAZA.row; r < PLAZA.row + PLAZA.h; r += 1) {
    for (let c = PLAZA.col; c < PLAZA.col + PLAZA.w; c += 1) dirt.add(`${c},${r}`);
  }
  const plazaPort = { col: PLAZA.col + Math.floor(PLAZA.w / 2), row: PLAZA.row + Math.floor(PLAZA.h / 2) };
  for (const b of buildings) carveLine(dirt, { col: b.doorCol, row: b.row + 3 }, plazaPort);

  for (const cellKey of dirt) {
    const [c, r] = cellKey.split(",").map(Number);
    if (r < 0 || r >= ROWS || c < 0 || c >= COLS) continue;
    const inPlaza = c >= PLAZA.col && c < PLAZA.col + PLAZA.w && r >= PLAZA.row && r < PLAZA.row + PLAZA.h;
    ground[r][c] = inPlaza ? { t: "plaza", e: plazaEdge(c, r) } : { t: "path" };
  }

  // Decoration (semantic kinds).
  const deco = [];
  const occupied = (c, r) => blocked.has(`${c},${r}`) || dirt.has(`${c},${r}`);
  const decoCells = new Set();
  const scatter = (count, makeItem) => {
    let placed = 0, guard = 0;
    while (placed < count && guard < count * 12) {
      guard += 1;
      const c = 1 + Math.floor(rand() * (COLS - 2));
      const r = 2 + Math.floor(rand() * (ROWS - 4));
      const k = `${c},${r}`;
      if (occupied(c, r) || decoCells.has(k)) continue;
      if (dirt.has(`${c},${r + 1}`) || dirt.has(`${c},${r - 1}`)) continue;
      decoCells.add(k);
      deco.push(makeItem(c, r));
      placed += 1;
    }
  };
  scatter(16, (c, r) => { decoCells.add(`${c},${r - 1}`); return { kind: "tree", col: c, row: r, orange: rand() > 0.6 }; });
  scatter(10, (c, r) => ({ kind: "small", col: c, row: r }));
  scatter(12, (c, r) => ({ kind: "bush", col: c, row: r }));
  scatter(8, (c, r) => ({ kind: rand() > 0.5 ? "tuft" : "mush", col: c, row: r }));

  for (const b of buildings) deco.push({ kind: "sign", col: b.doorCol + 1, row: b.row + 3, sector: b.key });

  const blockedRects = buildings.map((b) => ({ x: b.rect.x, y: b.rect.y + TILE, w: b.rect.w, h: b.rect.h - TILE }));

  return {
    tile: TILE, cols: COLS, rows: ROWS, width: MAP_W, height: MAP_H,
    ground, buildings, deco, sectors, stations, blockedRects,
    plaza: { ...PLAZA, center: plazaCenter },
  };
}
