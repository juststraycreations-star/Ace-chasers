import { useEffect, useState } from "react";
import api from "@/lib/api";
import VictoryCard from "./VictoryCard";
import { Trophy, Coins, Sparkle, MoneyWavy, ShareNetwork } from "@phosphor-icons/react";
import { toast } from "sonner";
import { renderDivisionPayoutCards, downloadBlob } from "@/lib/shareCard";

export default function PayoutDistribution({ roundId, leagueName, isDirector, onClose }) {
  const [data, setData] = useState(null);
  const [victoryFor, setVictoryFor] = useState(null); // {name, division, total, plus_minus}
  const [finalizing, setFinalizing] = useState(false);
  const [sharing, setSharing] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get(`/rounds/${roundId}/payout`);
      setData(data);
    } catch { /* payout endpoint optional — panel just stays empty */ }
  };
  useEffect(() => { load(); }, [roundId]);

  const finalize = async () => {
    if (!window.confirm("Finalize payouts? This posts debit entries against the Weekly Payout pool.")) return;
    setFinalizing(true);
    try {
      await api.post(`/rounds/${roundId}/finalize-payout`);
      await load();
    } finally { setFinalizing(false); }
  };

  const downloadPayoutCards = async () => {
    if (sharing || !data) return;
    setSharing(true);
    try {
      // Curve mirrors the server-side 50/30/20 top-3 payout distribution
      // in leagues_rounds_router.get_payout.
      const curve = [0.5, 0.3, 0.2];
      const divisions = Object.entries(data.divisions || {})
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
        // Skip empty divisions and divisions with zero pool — the card
        // would be all $0.00 and nobody wants to post that.
        .filter((d) => d.players.length > 0 && d.poolTotal > 0);
      if (divisions.length === 0) {
        toast.error("No payouts to share yet");
        return;
      }
      const cards = await renderDivisionPayoutCards({
        roundName: data.round_name,
        leagueName,
        divisions,
        curve,
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

  if (!data) return null;

  const divisionsWithPool = Object.values(data.divisions || {}).filter(
    (block) => (block.players || []).length > 0 && (block.pool || 0) > 0
  );
  const canSharePayouts = divisionsWithPool.length > 0;

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

        <div className="mb-6 p-4 rounded-lg bg-[#2a5f3d] border border-white/6 flex items-center justify-between">
          <div>
            <div className="font-mono-data text-[10px] text-zinc-500">POOL AVAILABLE</div>
            <div className="font-mega text-3xl text-emerald-400">${data.pool_available.toFixed(2)}</div>
          </div>
          <div className="text-right text-xs text-zinc-500 font-mono-data">
            SPLIT · POOL {(data.payout_split.pool * 100).toFixed(0)}% ·<br />
            ACE {(data.payout_split.ace * 100).toFixed(0)}% · CLUB {(data.payout_split.club * 100).toFixed(0)}%
          </div>
        </div>

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

        {(isDirector && data.pool_available > 0) || canSharePayouts ? (
          <div className="flex flex-wrap justify-end gap-2 pt-2">
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
        ) : null}
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
