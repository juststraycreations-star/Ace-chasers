import { Ghost } from "@phosphor-icons/react";

function scoreDiff(playerScore, ghostScore, par) {
  if (!playerScore && !ghostScore) return 0;
  return (playerScore || 0) - (ghostScore || 0);
}

export default function GhostOverlay({ playerScorecard, ghostScorecard, ghostName, parPerHole, currentHole, onClose }) {
  if (!ghostScorecard || !playerScorecard) return null;
  const holes = parPerHole.length;
  const throughHole = currentHole;

  let playerRunning = 0;
  let ghostRunning = 0;
  const rows = [];
  for (let i = 0; i < holes; i++) {
    const ps = playerScorecard.scores[i] || 0;
    const gs = ghostScorecard.scores[i] || 0;
    if (ps > 0) playerRunning += ps;
    if (gs > 0) ghostRunning += gs;
    const diff = playerRunning - ghostRunning;
    rows.push({ hole: i + 1, par: parPerHole[i], ps, gs, diff });
  }
  const finalDiff = playerRunning - ghostRunning;
  const status = finalDiff === 0 ? "AS" : (finalDiff < 0 ? `${Math.abs(finalDiff)} UP` : `${finalDiff} DOWN`);
  const statusColor = finalDiff < 0 ? "text-emerald-400" : finalDiff > 0 ? "text-red-400" : "text-zinc-300";

  return (
    <div className="card-surface p-5 mb-4" data-testid="ghost-overlay">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Ghost size={22} weight="duotone" className="text-[#FF9E00]" />
          <div>
            <div className="font-mono-data text-[10px] text-zinc-500">GHOST MATCH-PLAY</div>
            <div className="font-display text-lg">vs {ghostName}</div>
          </div>
        </div>
        <div className="text-right">
          <div className="font-mono-data text-[10px] text-zinc-500">STATUS THRU {throughHole}</div>
          <div className={`font-mega text-2xl ${statusColor}`} data-testid="ghost-status">{status}</div>
        </div>
        {onClose && (
          <button data-testid="ghost-close-btn" onClick={onClose} className="text-zinc-500 hover:text-white text-xl leading-none ml-4">×</button>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs border-collapse">
          <thead>
            <tr className="text-zinc-500 font-mono-data text-[10px]">
              <th className="text-left py-1 px-2">HOLE</th>
              {rows.map((r) => (
                <th key={r.hole} className={`px-1 py-1 ${r.hole === currentHole ? "text-[#FF9E00]" : ""}`}>{r.hole}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="text-zinc-500 py-1 px-2">Par</td>
              {rows.map((r) => <td key={r.hole} className="text-center text-zinc-500 px-1">{r.par}</td>)}
            </tr>
            <tr>
              <td className="text-emerald-300 py-1 px-2 font-medium">You</td>
              {rows.map((r) => (
                <td key={r.hole} className={`text-center px-1 py-1 ${r.hole === currentHole ? "bg-[#FF5C00]/12" : ""}`}>
                  {r.ps || "—"}
                </td>
              ))}
            </tr>
            <tr>
              <td className="text-purple-300 py-1 px-2 font-medium">Ghost</td>
              {rows.map((r) => (
                <td key={r.hole} className={`text-center px-1 py-1 ${r.hole === currentHole ? "bg-[#FF5C00]/12" : ""}`}>
                  {r.gs || "—"}
                </td>
              ))}
            </tr>
            <tr className="border-t border-white/10">
              <td className="text-zinc-400 py-1 px-2 font-mono-data text-[10px]">Δ</td>
              {rows.map((r) => (
                <td key={r.hole} className={`text-center px-1 py-1 font-mono-data text-[10px] ${r.diff < 0 ? "text-emerald-400" : r.diff > 0 ? "text-red-400" : "text-zinc-500"}`}>
                  {r.diff === 0 ? "—" : (r.diff > 0 ? `+${r.diff}` : r.diff)}
                </td>
              ))}
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
