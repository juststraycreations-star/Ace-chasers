import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { toast } from "sonner";
import {
  CheckCircle,
  Warning,
  Handshake,
  Users,
  CaretRight,
  ChatCircleDots,
} from "@phosphor-icons/react";

/**
 * ComplianceTab — director-only, one-glance snapshot of who has agreed
 * to the Clubhouse Fair Play terms and which players still need to
 * certify their scorecards, per round. Solves the "sweep-finalize
 * stalls silently" problem: directors can now see EXACTLY who is
 * blocking the round from closing.
 */
export default function ComplianceTab({ leagueId, isDirector }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/leagues/${leagueId}/compliance`);
      setData(data);
    } catch (e) {
      toast.error(
        e?.response?.status === 403
          ? "Compliance dashboard is director-only"
          : "Failed to load compliance"
      );
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  // Deep-link into Messages with the target user pre-selected.
  // Falls back to a toast when the member has no linked user account
  // (e.g. a director-added "manual" player).
  const dmMember = ({ user_id, name }) => {
    if (!user_id) {
      toast.error("This player doesn't have a linked account yet — can't DM.");
      return;
    }
    navigate("/messages", { state: { withUid: user_id, withName: name } });
  };

  useEffect(() => { load(); }, [leagueId]);

  if (!isDirector) {
    return (
      <div
        className="card-surface p-8 text-center text-sm text-zinc-500"
        data-testid="compliance-nondirector"
      >
        Compliance dashboard is available to league directors only.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="text-zinc-500 font-mono-data text-xs py-8" data-testid="compliance-loading">
        LOADING…
      </div>
    );
  }

  if (!data) return null;

  const { clubhouse_terms: terms, rounds } = data;
  const totalMembers = data.league?.member_count || 0;
  const agreedPct = totalMembers ? Math.round((terms.agreed_count / totalMembers) * 100) : 0;

  return (
    <div className="space-y-6" data-testid="compliance-tab">
      {/* ===== Clubhouse Fair Play rollup ===== */}
      <div className="card-surface p-5 sm:p-6" data-testid="compliance-clubhouse-card">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-[#F5C542]/12 text-[#F5C542]">
              <Handshake size={20} weight="duotone" />
            </div>
            <div>
              <div className="font-mono-data text-[10px] tracking-widest text-zinc-500 uppercase">
                Clubhouse Fair Play Terms
              </div>
              <div className="font-display text-lg">
                {terms.agreed_count}/{totalMembers} members agreed
              </div>
            </div>
          </div>
          <div className="text-right">
            <div className="font-mega text-2xl leading-none text-[#F5C542]" data-testid="compliance-agreed-pct">
              {agreedPct}%
            </div>
          </div>
        </div>
        {/* Progress bar */}
        <div className="h-2 w-full rounded-full bg-white/5 overflow-hidden mb-4">
          <div
            className="h-full bg-[#F5C542] transition-all duration-500"
            style={{ width: `${agreedPct}%` }}
          />
        </div>

        {terms.outstanding_count === 0 ? (
          <div
            className="flex items-center gap-2 text-sm text-green-500"
            data-testid="compliance-clubhouse-clear"
          >
            <CheckCircle size={16} weight="fill" />
            Every member has agreed. You&apos;re clear.
          </div>
        ) : (
          <div data-testid="compliance-clubhouse-outstanding">
            <div className="text-xs text-zinc-500 mb-2 font-mono-data uppercase tracking-wider">
              Not yet agreed ({terms.outstanding_count})
            </div>
            <div className="flex flex-wrap gap-2">
              {terms.outstanding_members.map((mm) => (
                <button
                  key={mm.id}
                  type="button"
                  onClick={() => dmMember(mm)}
                  disabled={!mm.user_id}
                  data-testid={`compliance-outstanding-${mm.id}`}
                  title={mm.user_id ? `DM ${mm.name} to nudge them` : "No linked account"}
                  className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/8 px-3 py-1.5 text-xs hover:bg-amber-500/15 hover:border-amber-500/60 disabled:opacity-50 disabled:cursor-not-allowed transition-colors group"
                >
                  <span className="font-mono-data text-amber-300/80">#{mm.bag_tag}</span>
                  <span>{mm.name}</span>
                  {mm.user_id && (
                    <ChatCircleDots
                      size={12}
                      weight="duotone"
                      className="text-amber-400 opacity-70 group-hover:opacity-100"
                    />
                  )}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* ===== Rounds scorecard certification ===== */}
      <div>
        <div className="flex items-center gap-2 mb-3">
          <Users size={14} weight="duotone" className="text-zinc-500" />
          <div className="font-mono-data text-[10px] tracking-widest text-zinc-500 uppercase">
            Scorecard Certification · Latest Rounds
          </div>
        </div>

        {rounds.length === 0 && (
          <div className="text-sm text-zinc-500 italic" data-testid="compliance-rounds-empty">
            No rounds yet.
          </div>
        )}

        <div className="space-y-3">
          {rounds.map((r) => {
            const canSweep = r.can_sweep_finalize;
            const pctCert = r.scorecard_total
              ? Math.round((r.certified_count / r.scorecard_total) * 100)
              : 0;
            return (
              <div
                key={r.round_id}
                className="card-surface p-4 sm:p-5"
                data-testid={`compliance-round-${r.round_id}`}
              >
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-display text-base sm:text-lg">{r.name}</span>
                      <span className={`text-[10px] font-mono-data px-2 py-0.5 rounded-md ${
                        r.status === "completed" ? "chip-green" :
                        r.status === "active" ? "chip-orange" :
                        "bg-zinc-800/60 text-zinc-400 border border-white/10"
                      }`}>
                        {String(r.status || "scheduled").toUpperCase()}
                      </span>
                    </div>
                    <div className="text-xs text-zinc-500">
                      {r.date ? new Date(r.date).toLocaleDateString() : "No date"}
                      {" · "}
                      {r.certified_count}/{r.scorecard_total} scorecards certified
                      {r.finalized_count > 0 && ` · ${r.finalized_count} finalized`}
                    </div>
                  </div>
                  <div className="flex items-center gap-3 shrink-0">
                    <div className="text-right">
                      <div className={`font-mega text-2xl leading-none ${canSweep ? "text-green-500" : "text-amber-400"}`}>
                        {pctCert}%
                      </div>
                      <div className="text-[9px] font-mono-data tracking-wider text-zinc-500 uppercase">
                        Certified
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => navigate(`/rounds/${r.round_id}`)}
                      data-testid={`compliance-round-open-${r.round_id}`}
                      className="text-xs px-3 py-2 rounded-full border border-white/15 hover:bg-white/5 flex items-center gap-1 whitespace-nowrap"
                    >
                      Open Round <CaretRight size={12} weight="bold" />
                    </button>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="h-1.5 w-full rounded-full bg-white/5 overflow-hidden mb-3">
                  <div
                    className={`h-full transition-all duration-500 ${canSweep ? "bg-green-500" : "bg-amber-400"}`}
                    style={{ width: `${pctCert}%` }}
                  />
                </div>

                {r.scorecard_total === 0 && (
                  <div className="text-xs text-zinc-500 italic">
                    No scorecards on this round yet.
                  </div>
                )}

                {r.pending_certification.length > 0 && (
                  <div>
                    <div className="text-[10px] font-mono-data uppercase tracking-wider text-amber-400/80 mb-2 flex items-center gap-1">
                      <Warning size={12} weight="fill" />
                      Blocking sweep-finalize ({r.pending_certification.length})
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {r.pending_certification.map((p) => (
                        <button
                          key={p.scorecard_id}
                          type="button"
                          onClick={() => dmMember({ user_id: p.user_id, name: p.member_name })}
                          disabled={!p.user_id}
                          data-testid={`compliance-pending-${p.scorecard_id}`}
                          title={
                            p.finalized ? "Scorecard finalized but not marked certified"
                            : p.player_certified ? "Player certified · director sign-off pending"
                            : p.user_id ? `DM ${p.member_name} to nudge them to certify`
                            : "Awaiting player self-certification · no linked account to DM"
                          }
                          className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/8 px-3 py-1.5 text-xs hover:bg-amber-500/15 hover:border-amber-500/60 disabled:opacity-50 disabled:cursor-not-allowed transition-colors group"
                        >
                          <span className="font-mono-data text-amber-300/80">#{p.bag_tag ?? "?"}</span>
                          <span>{p.member_name}</span>
                          <span className="text-[10px] text-zinc-500 font-mono-data">
                            {p.finalized ? "FINAL"
                              : p.player_certified ? "PLAYER OK"
                              : "NO CERT"}
                          </span>
                          {p.user_id && (
                            <ChatCircleDots
                              size={12}
                              weight="duotone"
                              className="text-amber-400 opacity-70 group-hover:opacity-100"
                            />
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {canSweep && r.scorecard_total > 0 && (
                  <div
                    className="mt-2 flex items-center gap-2 text-xs text-green-500"
                    data-testid={`compliance-round-clear-${r.round_id}`}
                  >
                    <CheckCircle size={14} weight="fill" />
                    Ready to sweep-finalize.
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
