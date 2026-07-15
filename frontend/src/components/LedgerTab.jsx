import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { Coins, ArrowUpRight, ArrowDownRight, Plus } from "@phosphor-icons/react";
import { Input } from "@/components/ui/input";

const CATEGORIES = ["Ace Pool", "CTP Cash", "Club Payout", "Entry Fee", "Other"];

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
        {CATEGORIES.slice(0, 4).map((cat) => {
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

      <div className="card-surface p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 mb-1">FINANCIAL LEDGER</div>
            <h3 className="font-display text-2xl flex items-center gap-2"><Coins weight="fill" className="text-[#FF9E00]" /> Debit / Credit</h3>
          </div>
          <div className="text-right">
            <div className="font-mono-data text-[10px] text-zinc-500">NET BALANCE</div>
            <div className={`font-mega text-2xl ${balance >= 0 ? "text-emerald-400" : "text-red-400"}`}>${balance.toFixed(2)}</div>
          </div>
        </div>

        {isDirector && (
          <form onSubmit={submit} className="grid grid-cols-1 sm:grid-cols-5 gap-2 mb-6 p-4 rounded-lg bg-[#111114] border border-white/5" data-testid="ledger-form">
            <select
              data-testid="ledger-kind"
              value={form.kind}
              onChange={(e) => setForm({ ...form, kind: e.target.value })}
              className="h-11 bg-[#131316] border border-white/10 rounded-md px-3 text-sm"
            >
              <option value="credit">Credit (in)</option>
              <option value="debit">Debit (out)</option>
            </select>
            <select
              data-testid="ledger-category"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="h-11 bg-[#131316] border border-white/10 rounded-md px-3 text-sm"
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
              className="h-11 bg-[#131316] border-white/10"
            />
            <Input
              data-testid="ledger-note"
              placeholder="Note (optional)"
              value={form.note}
              onChange={(e) => setForm({ ...form, note: e.target.value })}
              className="h-11 bg-[#131316] border-white/10"
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
