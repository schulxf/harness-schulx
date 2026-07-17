// Canvas agent sprite sheet (agents.png = 6 frames of 48x48, one per role).
const SHEET_SRC = "./assets/sprites/agents.png";
const FRAME = 48;
const FRAMES = 6;

const ROLE_FRAME = {
  builder: 0, implementer: 0,
  planner: 1,
  reviewer: 2,
  security: 3, auditor: 3,
  research: 4, researcher: 4,
  reporter: 5, operator: 5,
};

const image = new Image();
let ready = false;
image.onload = () => { ready = true; };
image.onerror = () => { ready = false; };
image.src = SHEET_SRC;

export function spritesReady() {
  return ready;
}

export function frameForRole(role) {
  const f = ROLE_FRAME[String(role || "").toLowerCase()];
  return Number.isInteger(f) ? f : 0;
}

// Draw an agent centred horizontally at x, feet at y.
export function drawAgentSprite(ctx, role, x, y, size, opts = {}) {
  const bob = opts.bob || 0;
  const top = y - size + bob;
  const left = x - size / 2;
  if (ready) {
    const frame = frameForRole(role);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(image, frame * FRAME, 0, FRAME, FRAME, left, top, size, size);
  } else {
    // fallback blob until the sheet loads
    ctx.fillStyle = opts.color || "#d9a441";
    ctx.beginPath();
    ctx.arc(x, top + size / 2, size * 0.32, 0, Math.PI * 2);
    ctx.fill();
  }
}
