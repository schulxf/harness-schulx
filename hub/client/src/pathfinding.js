const CELL = 32;

function key(col, row) {
  return `${col},${row}`;
}

function cellFor(point) {
  return {
    col: Math.max(0, Math.floor(point.x / CELL)),
    row: Math.max(0, Math.floor(point.y / CELL)),
  };
}

function centerFor(cell) {
  return {
    x: cell.col * CELL + CELL / 2,
    y: cell.row * CELL + CELL / 2,
  };
}

function heuristic(a, b) {
  return Math.abs(a.col - b.col) + Math.abs(a.row - b.row);
}

function blockedCells(blockedRects, width, height) {
  const blocked = new Set();
  for (const rect of blockedRects || []) {
    const start = cellFor({ x: rect.x, y: rect.y });
    const end = cellFor({ x: rect.x + rect.w, y: rect.y + rect.h });
    for (let col = start.col; col <= end.col; col += 1) {
      for (let row = start.row; row <= end.row; row += 1) {
        if (col >= 0 && row >= 0 && col < width && row < height) blocked.add(key(col, row));
      }
    }
  }
  return blocked;
}

function reconstruct(cameFrom, current) {
  const path = [current];
  let cursor = key(current.col, current.row);
  while (cameFrom.has(cursor)) {
    const prev = cameFrom.get(cursor);
    path.push(prev);
    cursor = key(prev.col, prev.row);
  }
  return path.reverse().map(centerFor);
}

function compact(points) {
  if (points.length <= 2) return points;
  const out = [points[0]];
  for (let index = 1; index < points.length - 1; index += 1) {
    const prev = out[out.length - 1];
    const current = points[index];
    const next = points[index + 1];
    const sameX = Math.abs(prev.x - current.x) < 1 && Math.abs(current.x - next.x) < 1;
    const sameY = Math.abs(prev.y - current.y) < 1 && Math.abs(current.y - next.y) < 1;
    if (!sameX && !sameY) out.push(current);
  }
  out.push(points[points.length - 1]);
  return out;
}

export function findPath(start, end, options = {}) {
  const cols = Math.ceil((options.width || 1280) / CELL);
  const rows = Math.ceil((options.height || 720) / CELL);
  const startCell = cellFor(start);
  const endCell = cellFor(end);
  const blocked = blockedCells(options.blockedRects || [], cols, rows);
  blocked.delete(key(startCell.col, startCell.row));
  blocked.delete(key(endCell.col, endCell.row));

  const open = [startCell];
  const cameFrom = new Map();
  const gScore = new Map([[key(startCell.col, startCell.row), 0]]);
  const fScore = new Map([[key(startCell.col, startCell.row), heuristic(startCell, endCell)]]);
  const seen = new Set();

  while (open.length) {
    open.sort((a, b) => (fScore.get(key(a.col, a.row)) || Infinity) - (fScore.get(key(b.col, b.row)) || Infinity));
    const current = open.shift();
    const currentKey = key(current.col, current.row);
    if (current.col === endCell.col && current.row === endCell.row) {
      const points = compact(reconstruct(cameFrom, current));
      points[0] = { ...start };
      points[points.length - 1] = { ...end };
      return points;
    }
    seen.add(currentKey);
    const neighbors = [
      { col: current.col + 1, row: current.row },
      { col: current.col - 1, row: current.row },
      { col: current.col, row: current.row + 1 },
      { col: current.col, row: current.row - 1 },
    ];
    for (const neighbor of neighbors) {
      const neighborKey = key(neighbor.col, neighbor.row);
      if (
        neighbor.col < 0 ||
        neighbor.row < 0 ||
        neighbor.col >= cols ||
        neighbor.row >= rows ||
        blocked.has(neighborKey) ||
        seen.has(neighborKey)
      ) {
        continue;
      }
      const tentative = (gScore.get(currentKey) || 0) + 1;
      if (tentative >= (gScore.get(neighborKey) || Infinity)) continue;
      cameFrom.set(neighborKey, current);
      gScore.set(neighborKey, tentative);
      fScore.set(neighborKey, tentative + heuristic(neighbor, endCell));
      if (!open.some((item) => item.col === neighbor.col && item.row === neighbor.row)) {
        open.push(neighbor);
      }
    }
  }

  return [{ ...start }, { ...end }];
}
