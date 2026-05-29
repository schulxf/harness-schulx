import { WORLD_HEIGHT, WORLD_WIDTH, pointInRect } from "./world.js";
import { roleMeta } from "./statemachine.js";

function tile(ctx, x, y, size, color) {
  ctx.fillStyle = color;
  ctx.fillRect(x, y, size, size);
}

function drawPixelGrid(ctx, theme) {
  for (let x = 0; x < WORLD_WIDTH; x += 32) {
    for (let y = 0; y < WORLD_HEIGHT; y += 32) {
      const alternate = (x / 32 + y / 32) % 2 === 0;
      tile(ctx, x, y, 32, alternate ? theme.ground : theme.groundAlt);
      if ((x + y) % 128 === 0) {
        ctx.fillStyle = "rgba(255,255,255,.08)";
        ctx.fillRect(x + 5, y + 8, 4, 4);
        ctx.fillRect(x + 18, y + 22, 3, 3);
      }
    }
  }
}

function drawRoads(ctx, sectors, theme) {
  const idle = sectors.find((sector) => sector.key === "idle") || { x: 492, y: 300, w: 290, h: 180 };
  const hub = { x: idle.x + idle.w / 2, y: idle.y + idle.h / 2 };
  ctx.strokeStyle = theme.road;
  ctx.lineWidth = 28;
  ctx.lineCap = "square";
  for (const sector of sectors) {
    const center = { x: sector.x + sector.w / 2, y: sector.y + sector.h / 2 };
    ctx.beginPath();
    ctx.moveTo(hub.x, hub.y);
    ctx.lineTo(center.x, hub.y);
    ctx.lineTo(center.x, center.y);
    ctx.stroke();
  }
  ctx.strokeStyle = "rgba(0,0,0,.22)";
  ctx.lineWidth = 3;
  for (const sector of sectors) {
    const center = { x: sector.x + sector.w / 2, y: sector.y + sector.h / 2 };
    ctx.beginPath();
    ctx.moveTo(hub.x, hub.y);
    ctx.lineTo(center.x, hub.y);
    ctx.lineTo(center.x, center.y);
    ctx.stroke();
  }
}

function drawSector(ctx, sector, theme, selected) {
  const roofHeight = Math.min(38, sector.h * .28);
  const tone = sector.tone || theme.roof;
  ctx.fillStyle = "rgba(0,0,0,.24)";
  ctx.fillRect(sector.x + 8, sector.y + sector.h - 2, sector.w, 18);
  if (sector.key === "idle") {
    ctx.fillStyle = "rgba(22, 42, 26, .74)";
    ctx.fillRect(sector.x, sector.y, sector.w, sector.h);
    ctx.strokeStyle = "#24361f";
    ctx.lineWidth = 4;
    ctx.strokeRect(sector.x, sector.y, sector.w, sector.h);
  } else {
    ctx.fillStyle = theme.wall;
    ctx.fillRect(sector.x, sector.y + roofHeight, sector.w, sector.h - roofHeight);
    ctx.fillStyle = tone;
    ctx.fillRect(sector.x - 8, sector.y + 16, sector.w + 16, roofHeight);
    ctx.fillStyle = "#101410";
    ctx.fillRect(sector.x + sector.w / 2 - 18, sector.y + sector.h - 42, 36, 42);
    ctx.fillStyle = "rgba(255,255,255,.16)";
    ctx.fillRect(sector.x + 22, sector.y + roofHeight + 22, 36, 28);
    ctx.fillRect(sector.x + sector.w - 58, sector.y + roofHeight + 22, 36, 28);
    ctx.strokeStyle = selected ? "#f0ead7" : "#050706";
    ctx.lineWidth = selected ? 7 : 4;
    ctx.strokeRect(sector.x, sector.y + roofHeight, sector.w, sector.h - roofHeight);
  }

  ctx.fillStyle = "rgba(5,7,6,.82)";
  ctx.fillRect(sector.x + 10, sector.y + 10, Math.min(sector.w - 20, 190), 28);
  ctx.fillStyle = "#f0ead7";
  ctx.font = "700 13px monospace";
  ctx.textBaseline = "top";
  ctx.fillText(sector.label || sector.key, sector.x + 18, sector.y + 17, sector.w - 28);
}

function drawPaths(ctx, paths) {
  for (const path of paths || []) {
    if (!path.points.length) continue;
    ctx.strokeStyle = path.color || "#54a7c7";
    ctx.lineWidth = 4;
    ctx.setLineDash([10, 10]);
    ctx.beginPath();
    ctx.moveTo(path.from.x, path.from.y);
    for (const point of path.points) ctx.lineTo(point.x, point.y);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawLegend(ctx, repo) {
  ctx.fillStyle = "rgba(5,7,6,.82)";
  ctx.fillRect(28, 28, 368, 72);
  ctx.fillStyle = "#f0ead7";
  ctx.font = "700 16px monospace";
  ctx.fillText(repo.project || "Repository", 46, 46);
  ctx.fillStyle = "#a7ad9b";
  ctx.font = "12px monospace";
  ctx.fillText(`${repo.branch || "no branch"} / ${repo.theme.label}`, 46, 68);
  const roles = ["builder", "planner", "reviewer", "security"];
  roles.forEach((role, index) => {
    const meta = roleMeta(role);
    ctx.fillStyle = meta.color;
    ctx.fillRect(46 + index * 76, 84, 10, 10);
    ctx.fillStyle = "#a7ad9b";
    ctx.fillText(meta.label.slice(0, 7), 60 + index * 76, 82);
  });
}

export function drawRepoMap(ctx, repo, options = {}) {
  ctx.clearRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
  drawPixelGrid(ctx, repo.theme);
  ctx.fillStyle = repo.theme.water;
  ctx.fillRect(0, WORLD_HEIGHT - 58, WORLD_WIDTH, 58);
  ctx.fillStyle = "rgba(255,255,255,.12)";
  for (let x = 0; x < WORLD_WIDTH; x += 48) ctx.fillRect(x, WORLD_HEIGHT - 40 + (x % 96 ? 6 : 0), 28, 3);
  drawRoads(ctx, repo.sectors, repo.theme);
  drawPaths(ctx, options.paths || []);
  for (const sector of repo.sectors) {
    drawSector(ctx, sector, repo.theme, sector.key === options.selectedSector);
  }
  drawLegend(ctx, repo);
}

export function hitTestSector(repo, point) {
  return [...(repo?.sectors || [])].reverse().find((sector) => pointInRect(point, sector));
}
