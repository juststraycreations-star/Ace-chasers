// Render a downloadable share-card PNG from live-simulator state.
// Zero external deps — uses a plain HTML5 <canvas>.
//
// Two templates:
//   • "winner"     — Winner's Circle: hero the top individual/team
//   • "leaderboard"— Season Leaderboard: top-5 rank table
// Both include an "ACE CHASERS" watermark overlay at low opacity.
//
// 1080×1350 (Instagram vertical portrait). Returns a Promise<Blob>.

const W = 1080;
const H = 1350;
const GREEN = "#0f2e1c";
const GREEN_LIGHT = "#1f4d2e";
const GOLD = "#F5C542";
const CREAM = "#fdf8ec";
const RANK_COLORS = [GOLD, "#e5e7eb", "#d09666"];

function wrap(ctx, text, maxWidth) {
  const words = String(text || "").split(/\s+/);
  const lines = [];
  let line = "";
  for (const w of words) {
    const test = line ? `${line} ${w}` : w;
    if (ctx.measureText(test).width <= maxWidth) {
      line = test;
    } else {
      if (line) lines.push(line);
      line = w;
    }
  }
  if (line) lines.push(line);
  return lines;
}

function paintBackground(ctx) {
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, GREEN);
  bg.addColorStop(1, GREEN_LIGHT);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = GOLD;
  ctx.fillRect(0, 0, W, 12);
}

function paintWatermark(ctx) {
  // Big "AC" mark centered behind the content, subtle so it doesn't
  // fight the foreground copy. Provides the brand overlay called for
  // in the design spec without a raster asset.
  ctx.save();
  ctx.globalAlpha = 0.06;
  ctx.fillStyle = CREAM;
  ctx.font = "700 640px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("AC", W / 2, H / 2 + 40);
  ctx.restore();
}

function paintBrandHeader(ctx, sublabel) {
  ctx.fillStyle = CREAM;
  ctx.font = "600 34px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  ctx.fillText("ACE CHASERS", 60, 90);
  ctx.fillStyle = GOLD;
  ctx.font = "500 24px monospace";
  ctx.fillText(sublabel || "LIVE ROUND · PROJECTED", 60, 128);
}

function paintFooter(ctx, acePool) {
  const fy = H - 90;
  ctx.fillStyle = GOLD;
  ctx.fillRect(0, fy - 30, W, 4);
  ctx.font = "500 26px monospace";
  ctx.textAlign = "left";
  ctx.fillText(`ACE POOL  $${Math.round(acePool || 0)}`, 60, fy + 20);
  ctx.fillStyle = "#cfd8ce";
  ctx.textAlign = "right";
  ctx.font = "500 22px monospace";
  ctx.fillText("acechasers.net", W - 60, fy + 20);
}

// ═════════════════════════════════════════════════════════════════
// Template A — Winner's Circle
// ═════════════════════════════════════════════════════════════════
function renderWinnerTemplate(ctx, { roundName, leagueName, leaders, payouts, pool, acePool }) {
  paintBackground(ctx);
  paintWatermark(ctx);
  paintBrandHeader(ctx, "WINNER'S CIRCLE · LIVE");

  // League name
  ctx.fillStyle = "#dfe7dd";
  ctx.font = "500 28px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  const leagueLines = wrap(ctx, leagueName || "League", W - 120).slice(0, 1);
  let y = 200;
  leagueLines.forEach((l) => { ctx.fillText(l, 60, y); y += 36; });

  // Round name
  ctx.fillStyle = CREAM;
  ctx.font = "700 60px system-ui, -apple-system, sans-serif";
  const roundLines = wrap(ctx, roundName || "Round", W - 120).slice(0, 1);
  let ry = y + 20;
  roundLines.forEach((l) => { ctx.fillText(l, 60, ry); ry += 70; });

  const winner = leaders[0] || null;
  const heroTop = ry + 40;

  // Hero card
  ctx.fillStyle = "rgba(245,197,66,0.08)";
  ctx.strokeStyle = GOLD;
  ctx.lineWidth = 3;
  ctx.fillRect(60, heroTop, W - 120, 420);
  ctx.strokeRect(60, heroTop, W - 120, 420);

  // Trophy
  ctx.fillStyle = GOLD;
  ctx.font = "700 140px serif";
  ctx.textAlign = "center";
  ctx.fillText("🏆", W / 2, heroTop + 140);

  ctx.fillStyle = CREAM;
  ctx.font = "600 24px monospace";
  ctx.textAlign = "center";
  ctx.fillText("CURRENT LEADER", W / 2, heroTop + 200);

  ctx.fillStyle = CREAM;
  ctx.font = "700 68px system-ui, -apple-system, sans-serif";
  const nameLine = winner ? (winner.name || "—").slice(0, 22) : "—";
  ctx.fillText(nameLine, W / 2, heroTop + 280);

  ctx.fillStyle = GOLD;
  ctx.font = "700 80px monospace";
  if (winner) {
    const pm = winner.plusMinus || 0;
    const pmLabel = pm > 0 ? ` (+${pm})` : pm < 0 ? ` (${pm})` : "";
    ctx.fillText(`${winner.total || 0}${pmLabel}`, W / 2, heroTop + 372);
  } else {
    ctx.fillText("—", W / 2, heroTop + 372);
  }

  // Payout callout
  const firstPayout = payouts[0]?.cash || 0;
  const py = heroTop + 460;
  ctx.fillStyle = GOLD;
  ctx.font = "500 24px monospace";
  ctx.textAlign = "left";
  ctx.fillText("PROJECTED WINNINGS", 60, py);
  ctx.fillStyle = CREAM;
  ctx.font = "700 90px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "right";
  ctx.fillText(`$${firstPayout}`, W - 60, py + 50);
  ctx.fillStyle = "#a3d1a3";
  ctx.font = "500 22px monospace";
  ctx.fillText(`OF $${Math.round(pool || 0)} POOL`, W - 60, py + 88);

  paintFooter(ctx, acePool);
}

// ═════════════════════════════════════════════════════════════════
// Template B — Season Leaderboard
// ═════════════════════════════════════════════════════════════════
function renderLeaderboardTemplate(ctx, { roundName, leagueName, leaders, acePool, divisionLabel }) {
  paintBackground(ctx);
  paintWatermark(ctx);
  const sublabel = divisionLabel
    ? `${divisionLabel.toUpperCase()} · LEADERBOARD · LIVE`
    : "SEASON LEADERBOARD · LIVE";
  paintBrandHeader(ctx, sublabel);

  ctx.fillStyle = "#dfe7dd";
  ctx.font = "500 28px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  const leagueLines = wrap(ctx, leagueName || "League", W - 120).slice(0, 1);
  let y = 200;
  leagueLines.forEach((l) => { ctx.fillText(l, 60, y); y += 36; });

  ctx.fillStyle = CREAM;
  ctx.font = "700 52px system-ui, -apple-system, sans-serif";
  const title = divisionLabel
    ? `${divisionLabel} · ${String(roundName || "Standings").slice(0, 24)}`
    : String(roundName || "Standings").slice(0, 28);
  ctx.fillText(title.slice(0, 32), 60, y + 40);

  // Division pill under the title, when provided
  if (divisionLabel) {
    const pillY = y + 60;
    ctx.fillStyle = GOLD;
    const pillW = ctx.measureText(divisionLabel).width + 40;
    ctx.beginPath();
    if (typeof ctx.roundRect === "function") {
      ctx.roundRect(60, pillY, pillW, 40, 20);
    } else {
      ctx.rect(60, pillY, pillW, 40);
    }
    ctx.fill();
    ctx.fillStyle = GREEN;
    ctx.font = "700 22px monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "middle";
    ctx.fillText(divisionLabel.toUpperCase(), 80, pillY + 20);
    ctx.textBaseline = "alphabetic";
  }

  const rows = leaders.slice(0, 5);
  const rowsY = y + (divisionLabel ? 160 : 100);
  const rowH = 130;

  rows.forEach((row, i) => {
    const rY = rowsY + i * rowH;
    // row background
    ctx.fillStyle = i === 0 ? "rgba(245,197,66,0.12)" : "rgba(255,255,255,0.04)";
    ctx.strokeStyle = i === 0 ? GOLD : "rgba(255,255,255,0.12)";
    ctx.lineWidth = 2;
    ctx.fillRect(60, rY, W - 120, rowH - 20);
    ctx.strokeRect(60, rY, W - 120, rowH - 20);

    // rank badge
    ctx.fillStyle = RANK_COLORS[i] || "#94a3b8";
    ctx.beginPath();
    ctx.arc(130, rY + (rowH - 20) / 2, 36, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = GREEN;
    ctx.font = "700 34px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(String(i + 1), 130, rY + (rowH - 20) / 2 + 2);

    // name
    ctx.fillStyle = CREAM;
    ctx.font = "600 42px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "left";
    ctx.fillText((row.name || "Player").slice(0, 22), 200, rY + (rowH - 20) / 2 + 4);

    // score
    ctx.fillStyle = GOLD;
    ctx.font = "700 44px monospace";
    ctx.textAlign = "right";
    const pm = row.plusMinus || 0;
    const pmLabel = pm > 0 ? ` (+${pm})` : pm < 0 ? ` (${pm})` : "";
    ctx.fillText(`${row.total || 0}${pmLabel}`, W - 90, rY + (rowH - 20) / 2 + 4);
  });

  ctx.textBaseline = "alphabetic";
  paintFooter(ctx, acePool);
}

export async function renderShareCard({
  roundName,
  leagueName,
  leaders = [],
  payouts = [],
  acePool = 0,
  pool = 0,
  template = "winner", // "winner" | "leaderboard"
  divisionLabel = null,
}) {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");

  if (template === "leaderboard") {
    renderLeaderboardTemplate(ctx, { roundName, leagueName, leaders, acePool, divisionLabel });
  } else {
    renderWinnerTemplate(ctx, { roundName, leagueName, leaders, payouts, pool, acePool });
  }

  return new Promise((resolve) => {
    canvas.toBlob((b) => resolve(b), "image/png", 0.95);
  });
}

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 3000);
}

/**
 * renderDivisionCards — emit one Leaderboard PNG per division.
 *
 * `divisions` is an array of `{ divisionLabel, leaders }` where `leaders`
 * is already top-N sorted for that division. Returns an ordered array of
 * `{ divisionLabel, blob }` so the caller can label the download.
 */
export async function renderDivisionCards({
  roundName,
  leagueName,
  divisions = [],
  acePool = 0,
}) {
  const out = [];
  for (const d of divisions) {
    const blob = await renderShareCard({
      roundName,
      leagueName,
      leaders: d.leaders || [],
      acePool,
      template: "leaderboard",
      divisionLabel: d.divisionLabel,
    });
    out.push({ divisionLabel: d.divisionLabel, blob });
  }
  return out;
}
