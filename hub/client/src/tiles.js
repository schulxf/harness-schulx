// Kenney tileset loader + per-theme semantic tile maps.
// Both packed sheets are a 12x11 grid of 16px tiles; mapgen emits semantic
// cells/deco and render resolves them to indices via the active theme's tileset.

export const SRC_TILE = 16;
export const SHEET_COLS = 12;

const SHEETS = {
  "tiny-town": "./assets/vendor/kenney_tiny-town/Tilemap/tilemap_packed.png",
  "tiny-dungeon": "./assets/vendor/kenney_tiny-dungeon/Tilemap/tilemap_packed.png",
};

// One coherent tile vocabulary per theme.
export const TILESETS = {
  "tiny-town": {
    sheet: "tiny-town",
    ground: { plain: 0, detail: 1, flower: 2 },
    path: 25,
    plaza9: { tl: 12, t: 13, tr: 14, l: 24, c: 25, r: 26, bl: 36, b: 37, br: 38 },
    usePlaza9: true,
    kits: {
      red: { roof: [52, 53, 54], eave: [64, 65, 66], wall: [84, 86, 84] },
      blue: { roof: [48, 49, 50], eave: [60, 61, 62], wall: [88, 90, 88] },
      stone: { roof: [99, 100, 101], eave: [111, 112, 113], wall: [123, 124, 125] },
    },
    sectorKit: { plan: "blue", implement: "red", review: "blue", research: "stone", security: "stone", report: "red" },
    tree: { tallTop: { green: 4, orange: 3 }, tallBot: { green: 16, orange: 15 }, small: 28, bush: 5, tuft: 17, mush: 29 },
    sign: 83,
    sectorIcon: { plan: 92, implement: 115, review: 103, research: 117, security: 95, report: 107 },
  },
  "tiny-dungeon": {
    sheet: "tiny-dungeon",
    ground: { plain: 0, detail: 24, flower: 12 },
    path: 48,
    plaza9: null,
    usePlaza9: false,
    kits: {
      torch: { roof: [57, 58, 59], eave: [57, 28, 59], wall: [57, 46, 59] },
      plain: { roof: [57, 58, 59], eave: [57, 58, 59], wall: [57, 45, 59] },
    },
    sectorKit: { plan: "plain", implement: "torch", review: "plain", research: "torch", security: "torch", report: "plain" },
    tree: { tallTop: { green: 18, orange: 18 }, tallBot: { green: 30, orange: 30 }, small: 67, bush: 66, tuft: 24, mush: 12 },
    sign: 127,
    sectorIcon: { plan: 64, implement: 117, review: 103, research: 114, security: 118, report: 54 },
  },
};

export function getTileset(themeKey) {
  return TILESETS[themeKey] || TILESETS["tiny-town"];
}

const images = new Map();
const ready = new Map();

export function loadSheet(themeKey) {
  const key = SHEETS[themeKey] ? themeKey : "tiny-town";
  if (images.has(key)) return images.get(key);
  const img = new Image();
  ready.set(key, false);
  img.onload = () => ready.set(key, true);
  img.onerror = () => ready.set(key, false);
  img.src = SHEETS[key];
  images.set(key, img);
  return img;
}

export function sheetReady(themeKey) {
  const key = SHEETS[themeKey] ? themeKey : "tiny-town";
  return ready.get(key) === true;
}

export function drawTile(ctx, themeKey, index, dx, dy, size) {
  const key = SHEETS[themeKey] ? themeKey : "tiny-town";
  if (ready.get(key) !== true) return;
  const img = images.get(key);
  const sx = (index % SHEET_COLS) * SRC_TILE;
  const sy = Math.floor(index / SHEET_COLS) * SRC_TILE;
  ctx.drawImage(img, sx, sy, SRC_TILE, SRC_TILE, dx, dy, size, size);
}
