import { WORLD_HEIGHT, WORLD_WIDTH } from "./world.js";

export function repoBuildings(repos) {
  const columns = Math.max(1, Math.min(4, Math.ceil(Math.sqrt(repos.length || 1))));
  const rows = Math.max(1, Math.ceil((repos.length || 1) / columns));
  const cellW = WORLD_WIDTH / columns;
  const cellH = WORLD_HEIGHT / rows;
  return repos.map((repo, index) => {
    const col = index % columns;
    const row = Math.floor(index / columns);
    const w = Math.min(250, cellW * .58);
    const h = Math.min(170, cellH * .52);
    return {
      repo,
      x: col * cellW + cellW / 2 - w / 2,
      y: row * cellH + cellH / 2 - h / 2,
      w,
      h,
    };
  });
}

export function hitTestBuilding(repos, point) {
  return repoBuildings(repos).find((building) => (
    point.x >= building.x &&
    point.x <= building.x + building.w &&
    point.y >= building.y &&
    point.y <= building.y + building.h
  ));
}

function drawText(ctx, text, x, y, maxWidth) {
  ctx.save();
  ctx.font = "700 15px monospace";
  ctx.fillStyle = "#f0ead7";
  ctx.textBaseline = "top";
  const value = String(text || "");
  const clipped = value.length > 28 ? `${value.slice(0, 25)}...` : value;
  ctx.fillText(clipped, x, y, maxWidth);
  ctx.restore();
}

export function drawOverworld(ctx, world, selectedRepoId) {
  ctx.clearRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);
  ctx.fillStyle = "#2e4632";
  ctx.fillRect(0, 0, WORLD_WIDTH, WORLD_HEIGHT);

  for (let x = 0; x < WORLD_WIDTH; x += 32) {
    for (let y = 0; y < WORLD_HEIGHT; y += 32) {
      ctx.fillStyle = (x / 32 + y / 32) % 2 ? "#355138" : "#3b5f3f";
      ctx.fillRect(x, y, 32, 32);
    }
  }

  ctx.fillStyle = "#ad9863";
  ctx.fillRect(0, WORLD_HEIGHT / 2 - 18, WORLD_WIDTH, 36);
  ctx.fillRect(WORLD_WIDTH / 2 - 18, 0, 36, WORLD_HEIGHT);

  for (const building of repoBuildings(world.repos)) {
    const theme = building.repo.theme;
    const selected = building.repo.id === selectedRepoId;
    ctx.fillStyle = "rgba(0,0,0,.24)";
    ctx.fillRect(building.x + 10, building.y + building.h - 4, building.w, 18);
    ctx.fillStyle = theme.wall;
    ctx.fillRect(building.x, building.y + 38, building.w, building.h - 38);
    ctx.fillStyle = theme.roof;
    ctx.fillRect(building.x - 12, building.y + 18, building.w + 24, 34);
    ctx.fillStyle = "#111711";
    ctx.fillRect(building.x + building.w / 2 - 18, building.y + building.h - 42, 36, 42);
    ctx.fillStyle = theme.water;
    ctx.fillRect(building.x + 22, building.y + 68, 42, 28);
    ctx.fillRect(building.x + building.w - 64, building.y + 68, 42, 28);
    ctx.strokeStyle = selected ? "#d9a441" : "#050706";
    ctx.lineWidth = selected ? 7 : 4;
    ctx.strokeRect(building.x, building.y + 38, building.w, building.h - 38);
    drawText(ctx, building.repo.project, building.x + 12, building.y + building.h + 12, building.w);
  }

  ctx.fillStyle = "rgba(5,7,6,.82)";
  ctx.fillRect(28, 28, 326, 58);
  ctx.fillStyle = "#d9a441";
  ctx.font = "700 16px monospace";
  ctx.fillText("Overworld", 46, 48);
  ctx.fillStyle = "#a7ad9b";
  ctx.font = "12px monospace";
  ctx.fillText(`${world.repos.length} repository map${world.repos.length === 1 ? "" : "s"}`, 46, 68);
}
