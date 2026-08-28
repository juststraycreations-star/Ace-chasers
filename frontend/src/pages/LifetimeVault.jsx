import { useEffect, useMemo, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Archive, CaretDown, CaretUp, Share, Trophy } from "@phosphor-icons/react";

/**
 * LifetimeVault — free, unlimited scorecard history. Reads from the
 * new `/api/vault/summary` endpoint which derives everything from the
 * existing scorecards + rounds collections (no schema change).
 *
 * Primary view: the user's last 5 finalized rounds up top for at-a-
 * glance scanning. Below, a responsive collapsible accordion groups
 * every round they've ever played by Year → Month.
 */
export default function LifetimeVault() {
  const [data, setData] = useState({ recent: [], by_month: {}, total_rounds: 0 });
  const [openMonths, setOpenMonths] = useState({}); // { "2026-02": true }
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const { data } = await api.get("/vault/summary", { params: { recent_limit: 5 } });
        setData(data);
      } catch (e) {
        toast.error(e?.response?.data?.detail || "Failed to load Vault");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  // Group months by year for the accordion.
  const byYear = useMemo(() => {
    const map = new Map();
    for (const [ym, rows] of Object.entries(data.by_month || {})) {
      const [year, month] = ym.split("-");
      if (!map.has(year)) map.set(year, []);
      map.get(year).push({ ym, year, month, rows });
    }
    return Array.from(map.entries())
      .sort((a, b) => (a[0] < b[0] ? 1 : -1))       // newest year first
      .map(([year, months]) => ({
        year,
        months: months.sort((a, b) => (a.ym < b.ym ? 1 : -1)),
      }));
  }, [data.by_month]);

  const monthLabel = (mm) => {
    const n = Number(mm);
    if (!n) return mm;
    return new Date(2000, n - 1, 1).toLocaleString(undefined, { month: "long" });
  };

  const shareRound = async (s) => {
    const summary =
      `${s.round_name || "Round"} · ${s.course || ""}\n` +
      `${s.total} (${s.plus_minus >= 0 ? "+" : ""}${s.plus_minus}) · ${s.holes} holes · ${s.date || ""}`;
    if (navigator.share) {
      try { await navigator.share({ title: "Ace Chasers · Round", text: summary }); return; }
      catch { /* user cancelled */ }
    }
    try {
      await navigator.clipboard.writeText(summary);
      toast.success("Round summary copied to clipboard");
    } catch { toast.error("Share not supported on this device"); }
  };

  const renderRow = (s) => (
    <li
      key={s.scorecard_id}
      data-testid={`vault-row-${s.scorecard_id}`}
      className="flex items-center justify-between gap-3 flex-wrap px-4 py-3 border-b border-slate-100 last:border-b-0"
    >
      <div className="min-w-0">
        <div className="font-display text-sm text-slate-900 truncate">
          {s.round_name || "Round"}
        </div>
        <div className="text-[11px] text-slate-500 font-mono-data uppercase tracking-wider">
          {s.date || "—"} · {s.course || "—"} · {s.holes} holes
        </div>
      </div>
      <div className="flex items-center gap-3">
        <div className="text-right">
          <div className="font-mono-data text-lg text-emerald-700 font-bold">{s.total}</div>
          <div className="font-mono-data text-[10px] text-slate-500 uppercase tracking-wider">
            {s.plus_minus > 0 ? `+${s.plus_minus}` : s.plus_minus} vs par
          </div>
        </div>
        <button
          type="button"
          onClick={() => shareRound(s)}
          data-testid={`vault-share-${s.scorecard_id}`}
          title="Share this round"
          className="inline-flex items-center justify-center w-10 h-10 rounded-full bg-white text-slate-800 border border-slate-300 hover:border-emerald-500 hover:text-emerald-600 transition-colors"
        >
          <Share size={16} weight="duotone" />
        </button>
      </div>
    </li>
  );

  return (
    <div className="min-h-screen bg-slate-50 py-8" data-testid="lifetime-vault-page">
      <div className="max-w-3xl mx-auto px-4">
        <div className="flex items-center gap-2 mb-1">
          <Archive size={22} weight="duotone" className="text-emerald-600" />
          <h1 className="font-display text-3xl text-slate-900">Lifetime Vault</h1>
        </div>
        <p className="text-sm text-slate-600 mb-6">
          Every scorecard, forever. Free.
          {" "}<span className="inline-flex items-center gap-1 font-mono-data text-emerald-700">
            <Trophy size={12} weight="fill" />
            {data.total_rounds} total rounds
          </span>
        </p>

        {loading ? (
          <div className="text-sm text-slate-500">Loading your Vault…</div>
        ) : (
          <>
            {/* Primary view — last 5 */}
            <h2 className="font-display text-sm uppercase tracking-widest text-slate-700 mb-2">
              Recent rounds
            </h2>
            {data.recent.length === 0 ? (
              <div
                data-testid="vault-empty"
                className="rounded-xl border border-dashed border-slate-300 bg-white p-6 text-center text-sm text-slate-500 mb-6"
              >
                No rounds yet. Play one and it&apos;ll live here forever.
              </div>
            ) : (
              <ul
                className="rounded-2xl border border-slate-200 bg-white overflow-hidden shadow-sm mb-8"
                data-testid="vault-recent-list"
              >
                {data.recent.map(renderRow)}
              </ul>
            )}

            {/* Lifetime accordion */}
            {byYear.length > 0 && (
              <>
                <h2 className="font-display text-sm uppercase tracking-widest text-slate-700 mb-2">
                  Lifetime archive
                </h2>
                <div className="space-y-3" data-testid="vault-lifetime-archive">
                  {byYear.map(({ year, months }) => (
                    <div key={year} data-testid={`vault-year-${year}`}>
                      <div className="font-display text-2xl text-emerald-700 mb-1">{year}</div>
                      {months.map(({ ym, month, rows }) => {
                        const open = !!openMonths[ym];
                        return (
                          <div key={ym} className="rounded-xl border border-slate-200 bg-white overflow-hidden mb-2">
                            <button
                              type="button"
                              onClick={() => setOpenMonths((prev) => ({ ...prev, [ym]: !prev[ym] }))}
                              data-testid={`vault-month-toggle-${ym}`}
                              aria-expanded={open}
                              className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-50 transition-colors"
                            >
                              <div className="font-display text-base text-slate-900">
                                {monthLabel(month)}
                                <span className="ml-2 font-mono-data text-xs text-slate-400">
                                  · {rows.length} round{rows.length === 1 ? "" : "s"}
                                </span>
                              </div>
                              <span className="text-slate-500">
                                {open ? <CaretUp size={16} /> : <CaretDown size={16} />}
                              </span>
                            </button>
                            {open && (
                              <ul data-testid={`vault-month-list-${ym}`}>
                                {rows.map(renderRow)}
                              </ul>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ))}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  );
}
