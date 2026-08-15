import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import VictoryCard from "./VictoryCard";
import {
  Trophy, Coins, Sparkle, MoneyWavy, ShareNetwork,
  Package, SlidersHorizontal, PencilSimple,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import JSZip from "jszip";
import {
  renderDivisionCards,
  renderDivisionPayoutCards,
  renderShareCard,
  downloadBlob,
} from "@/lib/shareCard";

// Payout curve preset shapes. Each entry sums to 1.0 and matches the
// validation the backend enforces on PATCH /leagues/{id}/payout-curve.
const CURVE_PRESETS = {
  "50/30/20": [0.5, 0.3, 0.2],
  "60/25/15": [0.6, 0.25, 0.15],
};

function curveKey(curve) {
  if (!Array.isArray(curve)) return "custom";
  const rounded = curve.map((c) => Math.round(c * 100) / 100);
  for (const [label, preset] of Object.entries(CURVE_PRESETS)) {
    if (preset.length !== rounded.length) continue;
    if (preset.every((v, i) => Math.abs(v - rounded[i]) < 0.005)) return label;
  }
  return "custom";
}

function formatCurve(curve) {
  return (curve || []).map((c) => `${Math.round(c * 100)}`).join("/");
}

export default function PayoutDistribution({ roundId, leagueId, leagueName, isDirector, onClose }) {
  const [data, setData] = useState(null);
  const [victoryFor, setVictoryFor] = useState(null); // {name, division, total, plus_minus}
  const [finalizing, setFinalizing] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [bundling, setBundling] = useState(false);
  const [savingCurve, setSavingCurve] = useState(false);
  const [customCurveInput, setCustomCurveInput] = useState("");
  const [showCustomInput, setShowCustomInput] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get(`/rounds/${roundId}/payout`);
      setData(data);
    } catch { /* payout endpoint optional — panel just stays empty */ }
  };
  useEffect(() => { load(); }, [roundId]);

  const activeCurve = useMemo(
    () => (data?.payout_curve && data.payout_curve.length ? data.payout_curve : [0.5, 0.3, 0.2]),
    [data]
  );
  const activeCurveKey = useMemo(() => curveKey(activeCurve), [activeCurve]);

  const finalize = async () => {
    if (!window.confirm("Finalize payouts? This posts debit entries against the Weekly Payout pool.")) return;
    setFinalizing(true);
    try {
      await api.post(`/rounds/${roundId}/finalize-payout`);
      await load();
    } finally { setFinalizing(false); }
  };

  // ── Payout curve preset selector ─────────────────────────────────
  // Saves the chosen curve on the LEAGUE so it applies to every round.
  const saveCurve = async (curve) => {
    if (!leagueId) return;
    setSavingCurve(true);
    try {
      await api.patch(`/leagues/${leagueId}/payout-curve`, { payout_curve: curve });
      toast.success(`Payout curve saved · ${formatCurve(curve)}`);
      setShowCustomInput(false);
      setCustomCurveInput("");
      // Re-fetch so all downstream $ amounts + share-card curves refresh.
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save payout curve");
    } finally {
      setSavingCurve(false);
    }
  };

  const onPresetChange = (key) => {
    if (key === "custom") {
      setShowCustomInput(true);
      // Seed the input with the currently active curve so the manager
      // can edit rather than retype from scratch.
      setCustomCurveInput(activeCurve.map((c) => Math.round(c * 100)).join("/"));
      return;
    }
    setShowCustomInput(false);
    saveCurve(CURVE_PRESETS[key]);
  };

  const applyCustomCurve = () => {
    // Accept "60/25/15", "60,25,15", or decimal "0.5,0.3,0.2".
    const parts = customCurveInput
      .split(/[\/,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean)
      .map(Number);
    if (parts.some((n) => !Number.isFinite(n) || n < 0)) {
      toast.error("Custom curve must be non-negative numbers");
      return;
    }
    // Auto-normalize: treat 60/25/15 as 0.6/0.25/0.15.
    const total = parts.reduce((a, b) => a + b, 0);
    const curve = total > 1.5 ? parts.map((n) => n / total) : parts;
    saveCurve(curve);
  };

  // ── Payout share cards ───────────────────────────────────────────
  const buildDivisionPayoutInputs = () =>
    Object.entries(data.divisions || {})
      .map(([divisionLabel, block]) => ({
        divisionLabel,
        poolTotal: block.pool || 0,
        players: (block.players || []).map((p) => ({
          name: p.name,
          total: p.total || 0,
          plusMinus: p.plus_minus || 0,
          payout: p.payout || 0,
        })),
      }))
      .filter((d) => d.players.length > 0 && d.poolTotal > 0);

  const buildDivisionLeaderboardInputs = () =>
    Object.entries(data.divisions || {})
      .map(([divisionLabel, block]) => ({
        divisionLabel,
        leaders: (block.players || []).slice(0, 5).map((p) => ({
          name: p.name,
          total: p.total || 0,
          plusMinus: p.plus_minus || 0,
        })),
      }))
      .filter((d) => d.leaders.length > 0);

  const downloadPayoutCards = async () => {
    if (sharing || !data) return;
    setSharing(true);
    try {
      const divisions = buildDivisionPayoutInputs();
      if (divisions.length === 0) { toast.error("No payouts to share yet"); return; }
      const cards = await renderDivisionPayoutCards({
        roundName: data.round_name, leagueName, divisions, curve: activeCurve,
      });
      let count = 0;
      const safeR = (data.round_name || "round").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
      for (const { divisionLabel, blob } of cards) {
        if (!blob) continue;
        const safeD = divisionLabel.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
        downloadBlob(blob, `ace-chasers-${safeR}-${safeD}-payouts.png`);
        count += 1;
      }
      toast.success(`Downloaded ${count} payout card${count === 1 ? "" : "s"}`);
    } catch {
      toast.error("Payout cards failed");
    } finally {
      setSharing(false);
    }
  };

  // ── Combined Post Bundle ─────────────────────────────────────────
  // Generates Winner + Leaderboard + Payout PNGs for every division and
  // ships them as a single .zip. Naming convention keeps the graphics
  // grouped by division so a manager can pull them into a post in order.
  const downloadPostBundle = async () => {
    if (bundling || !data) return;
    setBundling(true);
    try {
      const leaderboardInputs = buildDivisionLeaderboardInputs();
      const payoutInputs = buildDivisionPayoutInputs();
      if (leaderboardInputs.length === 0) { toast.error("Nothing to bundle yet"); return; }

      const zip = new JSZip();
      const safeR = (data.round_name || "round").replace(/[^a-z0-9]+/gi, "-").toLowerCase();
      let fileCount = 0;

      // Leaderboard PNG per division.
      const lbCards = await renderDivisionCards({
        roundName: data.round_name, leagueName, divisions: leaderboardInputs,
      });
      for (const { divisionLabel, blob } of lbCards) {
        if (!blob) continue;
        const safeD = divisionLabel.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
        zip.file(`${safeD}/leaderboard.png`, blob);
        fileCount += 1;
      }

      // Winner PNG per division (uses the leaderboard template on top-3
      // subset for a compact "Winner's Circle" post).
      for (const d of leaderboardInputs) {
        const winnerBlob = await renderShareCard({
          template: "winner",
          roundName: data.round_name,
          leagueName,
          leaders: d.leaders,
          acePool: 0,
          pool: (payoutInputs.find((p) => p.divisionLabel === d.divisionLabel)?.poolTotal) || 0,
          divisionLabel: d.divisionLabel,
        });
        if (!winnerBlob) continue;
        const safeD = d.divisionLabel.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
        zip.file(`${safeD}/winner.png`, winnerBlob);
        fileCount += 1;
      }

      // Payout PNG per division (only when the division has a real pool).
      const payoutCards = await renderDivisionPayoutCards({
        roundName: data.round_name, leagueName, divisions: payoutInputs, curve: activeCurve,
      });
      for (const { divisionLabel, blob } of payoutCards) {
        if (!blob) continue;
        const safeD = divisionLabel.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
        zip.file(`${safeD}/payouts.png`, blob);
        fileCount += 1;
      }

      const zipBlob = await zip.generateAsync({ type: "blob" });
      downloadBlob(zipBlob, `ace-chasers-${safeR}-bundle.zip`);
      toast.success(`Post bundle ready · ${fileCount} card${fileCount === 1 ? "" : "s"} zipped`);
    } catch {
      toast.error("Bundle build failed");
    } finally {
      setBundling(false);
    }
  };

  if (!data) return null;

  const divisionsWithPool = Object.values(data.divisions || {}).filter(
    (block) => (block.players || []).length > 0 && (block.pool || 0) > 0
  );
  const canSharePayouts = divisionsWithPool.length > 0;
  const canBundle = Object.values(data.divisions || {}).some(
    (block) => (block.players || []).length > 0
  );

  return (
    <div className="fixed inset-0 z-40 bg-black/80 backdrop-blur-sm flex items-start sm:items-center justify-center p-4 overflow-y-auto" onClick={onClose} data-testid="payout-distribution-modal">
      <div className="card-surface max-w-3xl w-full p-6 my-6" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 mb-1">PAYOUT DISTRIBUTION</div>
            <div className="font-display text-2xl flex items-center gap-2">
              <MoneyWavy weight="fill" className="text-[#F5C542]" size={22} /> {data.round_name}
            </div>
          </div>
          <button data-testid="payout-close-btn" onClick={onClose} className="text-zinc-500 hover:text-white text-2xl leading-none">×</button>
        </div>

        <div className="mb-4 p-4 rounded-lg bg-[#2a5f3d] border border-white/6 flex items-center justify-between">
          <div>
            <div className="font-mono-data text-[10px] text-zinc-500">POOL AVAILABLE</div>
            <div className="font-mega text-3xl text-emerald-400">${data.pool_available.toFixed(2)}</div>
          </div>
          <div className="text-right text-xs text-zinc-500 font-mono-data">
            SPLIT · POOL {(data.payout_split.pool * 100).toFixed(0)}% ·<br />
            ACE {(data.payout_split.ace * 100).toFixed(0)}% · CLUB {(data.payout_split.club * 100).toFixed(0)}%
          </div>
        </div>

        {/* Payout curve preset selector — director-only, saves at league level */}
        {isDirector && leagueId && (
          <div
            className="mb-6 p-4 rounded-xl bg-slate-50 border border-slate-200"
            data-testid="payout-curve-panel"
          >
            <div className="flex items-center gap-2 mb-2">
              <SlidersHorizontal size={16} weight="duotone" className="text-emerald-600" />
              <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500">
                Payout curve
              </div>
              <div className="font-mono-data text-xs text-slate-800 ml-auto">
                Active · {formatCurve(activeCurve)}
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {Object.keys(CURVE_PRESETS).map((key) => {
                const isActive = activeCurveKey === key;
                return (
                  <button
                    key={key}
                    type="button"
                    disabled={savingCurve || isActive}
                    onClick={() => onPresetChange(key)}
                    data-testid={`payout-curve-preset-${key.replace(/\//g, "-")}`}
                    className={`px-3 py-2 rounded-full text-xs font-semibold border-2 transition-colors ${
                      isActive
                        ? "bg-emerald-600 border-emerald-600 text-white"
                        : "bg-white border-emerald-600 text-emerald-600 hover:bg-emerald-50"
                    } disabled:opacity-40`}
                  >
                    {key}
                  </button>
                );
              })}
              <button
                type="button"
                disabled={savingCurve}
                onClick={() => onPresetChange("custom")}
                data-testid="payout-curve-preset-custom"
                className={`px-3 py-2 rounded-full text-xs font-semibold border-2 transition-colors inline-flex items-center gap-1.5 ${
                  activeCurveKey === "custom" && !showCustomInput
                    ? "bg-emerald-600 border-emerald-600 text-white"
                    : "bg-white border-emerald-600 text-emerald-600 hover:bg-emerald-50"
                } disabled:opacity-40`}
              >
                <PencilSimple size={12} weight="duotone" />
                Custom
              </button>
            </div>
            {showCustomInput && (
              <div className="mt-3 flex flex-wrap gap-2 items-center">
                <input
                  data-testid="payout-curve-custom-input"
                  value={customCurveInput}
                  onChange={(e) => setCustomCurveInput(e.target.value)}
                  placeholder="e.g. 70/20/10"
                  className="flex-1 min-w-[180px] rounded-lg bg-white border border-slate-200 px-3 py-2 text-sm text-slate-800 focus:outline-none focus:ring-2 focus:ring-emerald-500/10 focus:border-emerald-500 font-mono-data"
                />
                <button
                  type="button"
                  disabled={savingCurve || !customCurveInput.trim()}
                  onClick={applyCustomCurve}
                  data-testid="payout-curve-custom-apply"
                  className="px-4 py-2 rounded-full text-xs font-semibold bg-emerald-600 hover:bg-emerald-700 text-white disabled:opacity-40 shadow-sm"
                >
                  {savingCurve ? "Saving…" : "Apply"}
                </button>
                <button
                  type="button"
                  onClick={() => { setShowCustomInput(false); setCustomCurveInput(""); }}
                  className="px-3 py-2 rounded-full text-xs font-semibold text-slate-500 hover:text-slate-800"
                >
                  Cancel
                </button>
              </div>
            )}
            <p className="mt-2 text-[11px] text-slate-500">
              Curve is applied to every completed round in this league. Shares
              must sum to 100% (±2%). Percent (60/25/15) or decimals (.6/.25/.15) both work.
            </p>
          </div>
        )}

        {Object.keys(data.divisions).length === 0 ? (
          <div className="text-zinc-500 text-sm">No completed scorecards yet.</div>
        ) : (
          Object.entries(data.divisions).map(([div, block]) => (
            <div key={div} className="mb-5" data-testid={`payout-division-${div}`}>
              <div className="flex items-center justify-between mb-2">
                <div className="font-display text-lg">{div} Division</div>
                <div className="font-mono-data text-xs text-zinc-500">POOL ${block.pool.toFixed(2)}</div>
              </div>
              <div className="overflow-x-auto">
                <table className="ledger-grid">
                  <thead>
                    <tr>
                      <th style={{ width: "60px" }}>Place</th>
                      <th>Player</th>
                      <th style={{ textAlign: "right" }}>Total</th>
                      <th style={{ textAlign: "right" }}>Net</th>
                      <th style={{ textAlign: "right" }}>Payout</th>
                      <th style={{ width: "80px" }}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {block.players.map((p, i) => (
                      <tr key={p.member_id} data-testid={`payout-row-${div}-${i}`}>
                        <td>
                          <span className={`font-mega text-xl ${i === 0 ? "text-[#F5C542]" : "text-zinc-500"}`}>{p.place}</span>
                        </td>
                        <td>
                          <div className="flex items-center gap-2">
                            {p.picture ? <img src={p.picture} alt="" className="w-6 h-6 rounded-full" /> : <div className="w-6 h-6 rounded-full bg-zinc-800 text-[10px] flex items-center justify-center">{p.name?.charAt(0)}</div>}
                            <span className="font-sans normal-case tracking-normal text-zinc-100">{p.name}</span>
                            {i === 0 && <Trophy weight="fill" className="text-[#F5C542]" size={14} />}
                          </div>
                        </td>
                        <td style={{ textAlign: "right" }}>{p.total}</td>
                        <td style={{ textAlign: "right" }} className="text-zinc-400">{p.net.toFixed(1)}</td>
                        <td style={{ textAlign: "right" }} className={p.payout > 0 ? "text-emerald-400" : "text-zinc-600"}>
                          ${p.payout.toFixed(2)}
                        </td>
                        <td>
                          {i === 0 && (
                            <button
                              data-testid={`victory-card-btn-${div}`}
                              onClick={() => setVictoryFor({
                                name: p.name, division: div, total: p.total,
                                plus_minus: p.plus_minus,
                              })}
                              className="chip-orange px-2 py-1 rounded-md text-[10px] font-mono-data hover:brightness-125 flex items-center gap-1"
                            >
                              <Sparkle weight="fill" size={10} /> CARD
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))
        )}

        {((isDirector && data.pool_available > 0) || canSharePayouts || (isDirector && canBundle)) && (
          <div className="flex flex-wrap justify-end gap-2 pt-2">
            {isDirector && canBundle && (
              <button
                type="button"
                onClick={downloadPostBundle}
                disabled={bundling}
                data-testid="payout-bundle-btn"
                title="Winner + Leaderboard + Payout cards for every division, zipped"
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-600 bg-white border-2 border-emerald-600 hover:bg-emerald-50 rounded-full px-3 py-2 disabled:opacity-40 shadow-sm"
              >
                <Package size={14} weight="duotone" />
                {bundling ? "Zipping…" : "Post bundle · zip"}
              </button>
            )}
            {canSharePayouts && (
              <button
                type="button"
                onClick={downloadPayoutCards}
                disabled={sharing}
                data-testid="payout-share-cards-btn"
                title={`One projected-payouts PNG per division · ${divisionsWithPool.length} to share`}
                className="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-full px-3 py-2 disabled:opacity-40 shadow-sm"
              >
                <ShareNetwork size={14} weight="duotone" />
                {sharing ? "…" : `Payout cards · ${divisionsWithPool.length}`}
              </button>
            )}
            {isDirector && data.pool_available > 0 && (
              <button data-testid="payout-finalize-btn" onClick={finalize} disabled={finalizing} className="btn-primary flex items-center gap-2">
                <Coins size={14} weight="fill" /> {finalizing ? "Finalizing…" : "Finalize Payouts"}
              </button>
            )}
          </div>
        )}
      </div>

      {victoryFor && (
        <VictoryCard
          winnerName={victoryFor.name}
          division={victoryFor.division}
          finalScore={victoryFor.total}
          plusMinus={victoryFor.plus_minus}
          roundName={data.round_name}
          leagueName={leagueName}
          onClose={() => setVictoryFor(null)}
        />
      )}
    </div>
  );
}
