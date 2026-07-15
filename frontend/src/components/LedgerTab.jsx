import { useEffect, useState } from "react";
import api, { API } from "../lib/api";
import { toast } from "sonner";
import { Coins, ArrowUpRight, ArrowDownRight, Plus, DownloadSimple, UsersFour } from "@phosphor-icons/react";
import { Input } from "@/components/ui/input";

function EntryFeeEscrowCard({ leagueId, onCollected }) {
  const [members, setMembers] = useState([]);
  const [selected, setSelected] = useState(new Set());
  const [rounds, setRounds] = useState([]);
  const [roundId, setRoundId] = useState("");
  const [league, setLeague] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        const [m, r, l] = await Promise.all([
          api.get(`/leagues/${leagueId}/members`),
          api.get(`/leagues/${leagueId}/rounds`),
          api.get(`/leagues/${leagueId}`),
        ]);
        setMembers(m.data);
        setRounds(r.data);
        setLeague(l.data);
        const active = r.data.find((x) => x.status === "active") || r.data[0];
        if (active) setRoundId(active.id);
      } catch {}
    })();
  }, [leagueId]);

  const toggle = (id) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id); else next.add(id);
    setSelected(next);
  };
  const selectAll = () => setSelected(new Set(members.map((m) => m.id)));
  const clearAll = () => setSelected(new Set());

  const collect = async () => {
    if (selected.size === 0) { toast.error("Select at least one player"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/leagues/${leagueId}/entry-fees/collect`, {
        member_ids: [...selected],
        round_id: roundId || null,
      });
      toast.success(`Collected $${data.total.toFixed(2)} → split into 3 pools`);
      setSelected(new Set());
      onCollected?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Collection failed");
    } finally { setBusy(false); }
  };

  const perPlayer = league?.entry_fee || 0;
  const total = perPlayer * selected.size;

  return (
    <div className="card-surface p-6" data-testid="entry-fee-escrow">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
        <div>
          <div className="font-mono-data text-xs text-zinc-500 mb-1">ENTRY FEE ESCROW</div>
          <h3 className="font-display text-xl flex items-center gap-2">
            <UsersFour weight="fill" className="text-[#F5C542]" /> Collect + Auto-Split
          </h3>
        </div>
        <div className="text-right">
          <div className="font-mono-data text-[10px] text-zinc-500">FEE / PLAYER</div>
          <div className="font-mega text-2xl text-[#F5C542]">${perPlayer.toFixed(2)}</div>
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
        <select
          data-testid="escrow-round-select"
          value={roundId}
          onChange={(e) => setRoundId(e.target.value)}
          className="h-10 bg-[#2a5f3d] border border-white/10 rounded-md px-3 text-sm"
        >
          <option value="">No round association</option>
          {rounds.map((r) => (
            <option key={r.id} value={r.id}>{r.name} ({r.status})</option>
          ))}
        </select>
        <div className="flex gap-2">
          <button data-testid="escrow-select-all" onClick={selectAll} className="text-xs px-3 py-2 rounded-md border border-white/10 hover:bg-white/5">Select All</button>
          <button data-testid="escrow-clear" onClick={clearAll} className="text-xs px-3 py-2 rounded-md border border-white/10 hover:bg-white/5">Clear</button>
        </div>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 max-h-48 overflow-y-auto mb-4">
        {members.map((m) => {
          const on = selected.has(m.id);
          return (
            <button
              key={m.id}
              data-testid={`escrow-member-${m.id}`}
              onClick={() => toggle(m.id)}
              className={`p-2 rounded-lg border text-left text-xs ${on ? "border-[#F5C542] bg-[#F5C542]/10" : "border-white/10 bg-[#2a5f3d]"}`}
            >
              <div className="font-mono-data text-[10px] text-zinc-500">#{m.bag_tag} · {m.division}</div>
              <div className="font-medium truncate">{m.name}</div>
            </button>
          );
        })}
      </div>

      {selected.size > 0 && (
        <div className="terminal mb-4">
          <div className="ts">// COLLECTING FROM {selected.size} PLAYER(S)</div>
          <div><span className="ts">[TOTAL]</span> → <span className="val">${total.toFixed(2)}</span></div>
          <div><span className="ts">[WEEKLY PAYOUT 70%]</span> → <span className="val">${(total * 0.7).toFixed(2)}</span></div>
          <div><span className="ts">[ACE POOL 20%]</span> → <span className="val">${(total * 0.2).toFixed(2)}</span></div>
          <div><span className="ts">[CLUB FUND 10%]</span> → <span className="val">${(total * 0.1).toFixed(2)}</span></div>
        </div>
      )}
      <div className="flex justify-end">
        <button data-testid="escrow-collect-btn" onClick={collect} disabled={busy || selected.size === 0 || perPlayer <= 0} className="btn-primary text-xs flex items-center gap-2 disabled:opacity-40">
          <Coins size={13} weight="fill" /> {busy ? "Collecting…" : `Collect $${total.toFixed(2)}`}
        </button>
      </div>
    </div>
  );
}

const CATEGORIES = ["Ace Pool", "CTP Cash", "Club Payout", "Entry Fee", "Weekly Payout", "Club Fund", "Other"];

export default function LedgerTab({ leagueId, isDirector }) {
  const [entries, setEntries] = useState([]);
  const [totals, setTotals] = useState({});
  const [balance, setBalance] = useState(0);
  const [form, setForm] = useState({ kind: "credit", category: "Ace Pool", amount: "", note: "" });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    const { data } = await api.get(`/leagues/${leagueId}/ledger`);
    setEntries(data.entries);
    setTotals(data.totals);
    setBalance(data.balance);
  };
  useEffect(() => { load(); }, [leagueId]);

  const submit = async (e) => {
    e.preventDefault();
    if (!form.amount) return;
    setBusy(true);
    try {
      await api.post(`/leagues/${leagueId}/ledger`, {
        kind: form.kind, category: form.category, amount: Number(form.amount), note: form.note,
      });
      setForm({ kind: "credit", category: "Ace Pool", amount: "", note: "" });
      toast.success("Entry recorded");
      await load();
    } catch {
      toast.error("Failed to save entry");
    } finally { setBusy(false); }
  };

  return (
    <div className="space-y-6" data-testid="ledger-tab">
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        {["Weekly Payout", "Ace Pool", "Club Fund", "CTP Cash"].map((cat) => {
          const t = totals[cat] || { credit: 0, debit: 0 };
          const bal = t.credit - t.debit;
          return (
            <div key={cat} className="card-surface p-5" data-testid={`ledger-total-${cat.replace(/\s+/g, '-').toLowerCase()}`}>
              <div className="font-mono-data text-[10px] text-zinc-500 mb-2">{cat}</div>
              <div className={`font-mega text-3xl ${bal >= 0 ? "text-emerald-400" : "text-red-400"}`}>${Math.abs(bal).toFixed(0)}</div>
              <div className="text-[10px] text-zinc-600 mt-1 font-mono-data">
                +${t.credit.toFixed(0)} · −${t.debit.toFixed(0)}
              </div>
            </div>
          );
        })}
      </div>

      {isDirector && <EntryFeeEscrowCard leagueId={leagueId} onCollected={load} />}

      <div className="card-surface p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 mb-1">FINANCIAL LEDGER</div>
            <h3 className="font-display text-2xl flex items-center gap-2"><Coins weight="fill" className="text-[#F5C542]" /> Debit / Credit</h3>
          </div>
          <div className="text-right">
            <div className="font-mono-data text-[10px] text-zinc-500">NET BALANCE</div>
            <div className={`font-mega text-2xl ${balance >= 0 ? "text-emerald-400" : "text-red-400"}`}>${balance.toFixed(2)}</div>
            <button
              data-testid="ledger-export-btn"
              onClick={() => {
                const token = localStorage.getItem("session_token");
                window.open(`${API}/leagues/${leagueId}/ledger.csv?auth=${encodeURIComponent(token)}`, "_blank");
              }}
              className="mt-2 text-[10px] px-2 py-1 rounded-full border border-white/15 text-zinc-400 hover:bg-white/5 flex items-center gap-1 ml-auto"
            >
              <DownloadSimple size={11} weight="bold" /> CSV
            </button>
          </div>
        </div>

        {isDirector && (
          <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-5 gap-2 mb-6 p-4 rounded-lg bg-[#111114] border border-white/5" data-testid="ledger-form">
            <select
              data-testid="ledger-kind"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
              className="h-11 bg-[#2a5f3d] border border-white/10 rounded-md px-3 text-sm"
            >
              <option value="credit">Credit (in)</option>
              <option value="debit">Debit (out)</option>
            </select>
            <select
              data-testid="ledger-category"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="h-11 bg-[#2a5f3d] border border-white/10 rounded-md px-3 text-sm"
            >
              {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <Input
              data-testid="ledger-amount"
              placeholder="Amount"
              type="number"
              step="0.01"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
              className="h-11 bg-[#2a5f3d] border-white/10"
            />
            <Input
              data-testid="ledger-note"
              placeholder="Note (optional)"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              className="h-11 bg-[#2a5f3d] border-white/10"
            />
            <button data-testid="ledger-submit" disabled={busy} className="btn-primary text-sm flex items-center justify-center gap-1">
              <Plus size={14} weight="bold" /> Record
            </button>
          </form>
        )}

        <div className="overflow-x-auto">
          <table className="ledger-grid">
            <thead>
              <tr>
                <th>Date</th>
                <th>Category</th>
                <th>Note</th>
                <th style={{ textAlign: "right" }}>Amount</th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 && (
                <tr><td colSpan="4" className="text-center text-zinc-500 py-6">No entries yet</td></tr>
              )}
              {entries.map((e) => (
                <tr key={e.id} data-testid={`ledger-entry-${e.id}`}>
                  <td className="text-zinc-500">{new Date(e.created_at).toLocaleDateString()}</td>
                  <td>{e.category}</td>
                  <td className="font-sans normal-case tracking-normal text-zinc-300">{e.note || <span className="text-zinc-600">—</span>}</td>
                  <td style={{ textAlign: "right" }}>
                    <div className={`inline-flex items-center gap-1 ${e.kind === "credit" ? "text-emerald-400" : "text-red-400"}`}>
                      {e.kind === "credit" ? <ArrowUpRight size={14} /> : <ArrowDownRight size={14} />}
                      ${e.amount.toFixed(2)}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
