import { useState, useMemo, useEffect } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { ArrowUp, ArrowDown, Lock, LockOpen, Shuffle, PlayCircle, X, ChartBar } from "@phosphor-icons/react";

/**
 * SeedManagementPanel — director-only UI to reorder / lock member seeds
 * BEFORE generating a Match-Play bracket.
 *
 * Design:
 *   - Each member row shows seed #, name, ↑/↓ reorder, lock toggle
 *   - "Shuffle unlocked" randomizes ONLY unlocked members (locked seeds
 *     stay pinned at their current index)
 *   - "Generate bracket" POSTs the final ordered `member_ids` list to
 *     /api/leagues/{id}/bracket/seed
 *
 * We deliberately use up/down arrow buttons instead of HTML5 drag-and-drop
 * so the panel works on touch devices and doesn't need a heavy DnD lib.
 */
export default function SeedManagementPanel({ leagueId, members, onSeeded, onCancel }) {
  // rows: { id, name, locked }
  const [rows, setRows] = useState(() =>
    (members || []).map((m) => ({ id: m.id, name: m.name, locked: false }))
  );
  const [seeding, setSeeding] = useState(false);
  // handicapMap: { [memberId]: { handicap: number, played: number } | null }
  // `null` chip → unrated (no computed data yet), rendered as an em-dash.
  const [handicapMap, setHandicapMap] = useState({});

  // Fetch rolling handicaps on open so the chips next to each name give
  // the director confidence in the ordering (especially before auto-seed).
  useEffect(() => {
    if (!leagueId) return;
    let dead = false;
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/handicaps`);
        if (dead) return;
        const map = {};
        for (const row of data || []) {
          map[row.member_id] = {
            handicap: row.handicap,
            played: row.rounds_played || 0,
          };
        }
        setHandicapMap(map);
      } catch { /* silent — chip just shows em-dash */ }
    })();
    return () => { dead = true; };
  }, [leagueId]);

  const canSeed = rows.length >= 2 && !seeding;

  const move = (idx, delta) => {
    setRows((prev) => {
      const target = idx + delta;
      if (target < 0 || target >= prev.length) return prev;
      if (prev[idx].locked || prev[target].locked) {
        toast.error("Unlock both rows to swap");
        return prev;
      }
      const next = [...prev];
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    });
  };

  const toggleLock = (idx) => {
    setRows((prev) => prev.map((r, i) => (i === idx ? { ...r, locked: !r.locked } : r)));
  };

  const shuffleUnlocked = () => {
    setRows((prev) => {
      const lockedByIdx = new Map();
      const pool = [];
      prev.forEach((r, i) => {
        if (r.locked) lockedByIdx.set(i, r);
        else pool.push(r);
      });
      // Fisher-Yates shuffle the unlocked pool
      for (let i = pool.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [pool[i], pool[j]] = [pool[j], pool[i]];
      }
      const next = [];
      let poolIdx = 0;
      for (let i = 0; i < prev.length; i++) {
        if (lockedByIdx.has(i)) next.push(lockedByIdx.get(i));
        else next.push(pool[poolIdx++]);
      }
      return next;
    });
  };

  const seed = async () => {
    if (!canSeed) return;
    if (!window.confirm(`Seed bracket with ${rows.length} players in this order?`)) return;
    setSeeding(true);
    try {
      await api.post(`/leagues/${leagueId}/bracket/seed`, {
        member_ids: rows.map((r) => r.id),
      });
      toast.success("Bracket seeded");
      onSeeded?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Seed failed");
    } finally {
      setSeeding(false);
    }
  };

  const autoSeed = async () => {
    if (seeding) return;
    if (!window.confirm(
      `Auto-seed by rolling handicap? Lowest handicap becomes seed #1. Any manual reorder or lock will be replaced.`
    )) return;
    setSeeding(true);
    try {
      const { data } = await api.post(`/leagues/${leagueId}/bracket/auto-seed`);
      const order = data?.seed_order || [];
      if (order.length) {
        setRows(order.map((s) => ({ id: s.member_id, name: s.name, locked: false })));
        // Merge any handicap/played info from the auto-seed response so
        // chips stay accurate even if the initial fetch was stale.
        setHandicapMap((prev) => {
          const next = { ...prev };
          for (const s of order) {
            next[s.member_id] = { handicap: s.handicap, played: s.played };
          }
          return next;
        });
      }
      toast.success("Bracket auto-seeded by handicap");
      onSeeded?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Auto-seed failed");
    } finally {
      setSeeding(false);
    }
  };

  const lockedCount = useMemo(() => rows.filter((r) => r.locked).length, [rows]);

  return (
    <section
      className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm"
      data-testid="seed-management-panel"
    >
      <div className="flex items-center gap-2 mb-4">
        <div className="w-8 h-8 rounded-lg bg-amber-100 text-amber-700 flex items-center justify-center">
          <PlayCircle size={18} weight="duotone" />
        </div>
        <div>
          <div className="font-mono-data text-[10px] uppercase tracking-widest text-amber-700">
            Seed override
          </div>
          <div className="font-display text-lg text-slate-900">
            Order players before bracket generation
          </div>
        </div>
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            data-testid="seed-panel-close"
            className="ml-auto text-slate-400 hover:text-slate-800"
          >
            <X size={18} />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2 mb-3 text-xs font-mono-data text-slate-500 justify-between">
        <span>
          {rows.length} player{rows.length === 1 ? "" : "s"} · {lockedCount} locked
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={autoSeed}
            disabled={seeding || rows.length < 2}
            data-testid="seed-auto-rating-btn"
            title="Order players by rolling handicap · lowest = seed #1"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 disabled:opacity-40 rounded-full px-3 py-1.5"
          >
            <ChartBar size={12} weight="duotone" /> Auto-seed by rating
          </button>
          <button
            type="button"
            onClick={shuffleUnlocked}
            data-testid="seed-shuffle-btn"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-700 border border-slate-200 hover:border-slate-400 rounded-full px-3 py-1.5"
          >
            <Shuffle size={12} weight="duotone" /> Shuffle unlocked
          </button>
        </div>
      </div>

      <ol
        className="max-h-[420px] overflow-y-auto pr-1 space-y-1 border border-slate-100 rounded-lg divide-y divide-slate-100"
        data-testid="seed-list"
      >
        {rows.map((row, i) => (
          <li
            key={row.id}
            className={`flex items-center gap-2 p-2 ${row.locked ? "bg-amber-50" : "bg-white"}`}
            data-testid={`seed-row-${i + 1}`}
          >
            <span className="w-8 h-8 shrink-0 rounded-md bg-slate-100 text-slate-800 font-mono text-xs flex items-center justify-center">
              {i + 1}
            </span>
            <div className="flex-1 min-w-0 flex items-center gap-2">
              <div className="text-sm text-slate-900 truncate">
                {row.name}
              </div>
              {(() => {
                const h = handicapMap[row.id];
                const played = h?.played ?? 0;
                const rated = h && played > 0;
                const value = rated ? h.handicap : null;
                const label = rated
                  ? (value > 0 ? `+${value}` : `${value}`)
                  : "—";
                return (
                  <span
                    data-testid={`seed-handicap-chip-${i + 1}`}
                    title={
                      rated
                        ? `Rolling handicap · ${played} round${played === 1 ? "" : "s"} played`
                        : "No completed rounds yet"
                    }
                    className={`shrink-0 font-mono-data text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                      rated
                        ? "bg-emerald-50 border-emerald-200 text-emerald-800"
                        : "bg-slate-100 border-slate-200 text-slate-500"
                    }`}
                  >
                    HCP {label}
                  </span>
                );
              })()}
            </div>
            <button
              type="button"
              onClick={() => move(i, -1)}
              disabled={i === 0 || row.locked}
              data-testid={`seed-up-${i + 1}`}
              title="Move up"
              className="p-1.5 text-slate-500 hover:text-slate-900 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ArrowUp size={14} weight="bold" />
            </button>
            <button
              type="button"
              onClick={() => move(i, 1)}
              disabled={i === rows.length - 1 || row.locked}
              data-testid={`seed-down-${i + 1}`}
              title="Move down"
              className="p-1.5 text-slate-500 hover:text-slate-900 disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <ArrowDown size={14} weight="bold" />
            </button>
            <button
              type="button"
              onClick={() => toggleLock(i)}
              data-testid={`seed-lock-${i + 1}`}
              title={row.locked ? "Unlock this seed" : "Lock this seed"}
              className={`p-1.5 rounded-md ${row.locked ? "text-amber-700 bg-amber-100" : "text-slate-400 hover:text-slate-800"}`}
            >
              {row.locked ? <Lock size={14} weight="fill" /> : <LockOpen size={14} weight="duotone" />}
            </button>
          </li>
        ))}
      </ol>

      <div className="mt-4 flex justify-end gap-2">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            className="text-xs px-4 py-2 rounded-lg text-slate-600 hover:text-slate-900"
          >
            Cancel
          </button>
        )}
        <button
          type="button"
          onClick={seed}
          disabled={!canSeed}
          data-testid="seed-generate-btn"
          className="text-sm px-4 py-2 rounded-lg bg-amber-600 text-white font-semibold hover:bg-amber-700 disabled:opacity-40 inline-flex items-center gap-1.5"
        >
          {seeding ? "Seeding…" : "Generate bracket"}
        </button>
      </div>
    </section>
  );
}
