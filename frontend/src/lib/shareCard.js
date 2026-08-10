// Render a downloadable share-card PNG from live-simulator state.
// Zero external deps — uses a plain HTML5 <canvas>.
//
// The card is 1080×1350 (Instagram vertical portrait) so it looks great
// pasted into any social channel. Layout:
//   • Round name in Ace-Chasers green header
//   • Top-3 leader rows with names + totals
//   • Payout tiles (70 / 20 / 10)
//   • Ace pool footer
//
// Returns a Promise<Blob> so the caller can trigger `saveAs` or
// `navigator.share`.

const W = 1080;
const H = 1350;
const GREEN = "#0f2e1c";
const GREEN_LIGHT = "#1f4d2e";
const GOLD = "#F5C542";
const CREAM = "#fdf8ec";

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

export async function renderShareCard({
  roundName,
  leagueName,
  leaders = [], // [{ name, total, plusMinus }]
  payouts = [], // [{ rank, cash, pct }]
  acePool = 0,
  pool = 0,
}) {
  const canvas = document.createElement("canvas");
  canvas.width = W;
  canvas.height = H;
  const ctx = canvas.getContext("2d");

  // Background
  const bg = ctx.createLinearGradient(0, 0, 0, H);
  bg.addColorStop(0, GREEN);
  bg.addColorStop(1, GREEN_LIGHT);
  ctx.fillStyle = bg;
  ctx.fillRect(0, 0, W, H);

  // Header strip
  ctx.fillStyle = GOLD;
  ctx.fillRect(0, 0, W, 12);

  // Brand
  ctx.fillStyle = CREAM;
  ctx.font = "600 34px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText("ACE CHASERS", 60, 90);
  ctx.fillStyle = GOLD;
  ctx.font = "500 24px monospace";
  ctx.fillText("LIVE ROUND · PROJECTED", 60, 128);

  // League name
  ctx.fillStyle = "#dfe7dd";
  ctx.font = "500 32px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  const leagueLines = wrap(ctx, leagueName || "League", W - 120);
  let y = 200;
  for (const l of leagueLines.slice(0, 2)) {
    ctx.fillText(l, 60, y);
    y += 40;
  }

  // Round name (big)
  ctx.fillStyle = CREAM;
  ctx.font = "700 72px system-ui, -apple-system, sans-serif";
  const roundLines = wrap(ctx, roundName || "Round", W - 120);
  let ry = y + 30;
  for (const l of roundLines.slice(0, 2)) {
    ctx.fillText(l, 60, ry);
    ry += 84;
  }

  // Leaders block
  const blockY = Math.max(ry + 40, 480);
  ctx.fillStyle = "rgba(255,255,255,0.05)";
  ctx.strokeStyle = GOLD;
  ctx.lineWidth = 2;
  ctx.fillRect(60, blockY, W - 120, 400);
  ctx.strokeRect(60, blockY, W - 120, 400);

  ctx.fillStyle = GOLD;
  ctx.font = "600 22px monospace";
  ctx.textAlign = "left";
  ctx.fillText("LEADERS", 90, blockY + 42);

  const topLeaders = leaders.slice(0, 3);
  ctx.font = "600 36px system-ui, -apple-system, sans-serif";
  let ly = blockY + 100;
  const rankColors = [GOLD, "#e5e7eb", "#d09666"];
  topLeaders.forEach((row, i) => {
    // rank badge
    ctx.fillStyle = rankColors[i] || "#94a3b8";
    ctx.beginPath();
    ctx.arc(120, ly - 14, 26, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = GREEN;
    ctx.font = "700 28px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(String(i + 1), 120, ly - 5);

    // name
    ctx.fillStyle = CREAM;
    ctx.font = "600 36px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "left";
    const nameLine = (row.name || "Player").slice(0, 22);
    ctx.fillText(nameLine, 170, ly);

    // score
    ctx.fillStyle = GOLD;
    ctx.font = "700 40px monospace";
    ctx.textAlign = "right";
    const score = row.total || 0;
    const pm = row.plusMinus || 0;
    const pmLabel = pm > 0 ? ` (+${pm})` : pm < 0 ? ` (${pm})` : "";
    ctx.fillText(`${score}${pmLabel}`, W - 90, ly);

    ly += 96;
  });

  // Payouts row
  const py = blockY + 440;
  ctx.fillStyle = GOLD;
  ctx.font = "600 22px monospace";
  ctx.textAlign = "left";
  ctx.fillText(`PROJECTED PAYOUTS · POOL $${Math.round(pool || 0)}`, 60, py);

  const tileW = (W - 120 - 40) / 3;
  const tileH = 160;
  const tileY = py + 30;
  payouts.slice(0, 3).forEach((slot, i) => {
    const x = 60 + i * (tileW + 20);
    ctx.fillStyle = "rgba(245,197,66,0.12)";
    ctx.strokeStyle = GOLD;
    ctx.lineWidth = 2;
    ctx.fillRect(x, tileY, tileW, tileH);
    ctx.strokeRect(x, tileY, tileW, tileH);
    ctx.fillStyle = GOLD;
    ctx.font = "700 30px monospace";
    ctx.textAlign = "left";
    ctx.fillText(`#${slot.rank}`, x + 20, tileY + 42);
    ctx.fillStyle = CREAM;
    ctx.font = "700 56px system-ui, -apple-system, sans-serif";
    ctx.fillText(`$${slot.cash || 0}`, x + 20, tileY + 108);
    ctx.fillStyle = "#a3d1a3";
    ctx.font = "500 22px monospace";
    ctx.fillText(`${Math.round((slot.pct || 0) * 100)}%`, x + 20, tileY + 140);
  });

  // Ace pool footer
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
