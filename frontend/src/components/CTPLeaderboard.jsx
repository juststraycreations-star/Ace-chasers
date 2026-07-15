import { useEffect, useState, useCallback } from "react";
import api from "@/lib/api";
import { Target, Ruler, Plus, Trash } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function CTPLeaderboard({ roundId, currentHole, currentMemberId, isDirector, refresh }) {
  const [data, setData] = useState({ entries: [], leaderboard: {}, ctp_holes: [] });
  const [form, setForm] = useState({ feet: "", inches: "" });

  const load = useCallback(async () => {
    try {
      const { data } = await api.get(`/rounds/${roundId}/ctp`);
      setData(data);
    } catch {}
  }, [roundId]);

  useEffect(() => { load(); }, [load, refresh]);

  const submit = async () => {
    const feet = parseInt(form.feet || "0", 10);
    const inches = parseFloat(form.inches || "0");
    if ((feet === 0 && inches === 0) || feet < 0 || inches < 0 || inches >= 12) {
      toast.error("Enter valid feet + inches");
      return;
    }
    try {
      await api.post(`/rounds/${roundId}/ctp`, { hole: currentHole, feet, inches });
      setForm({ feet: "", inches: "" });
      toast.success(`CTP entry logged · Hole ${currentHole}`);
      await load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };

  const removeEntry = async (id) => {
    try {
      await api.delete(`/ctp/${id}`);
      await load();
    } catch { toast.error("Failed to remove"); }
  };

  const isCtpHole = data.ctp_holes?.includes(currentHole);
  const holeEntries = (data.leaderboard[currentHole] || []).slice();

  return (
    <div className="card-surface p-5" data-testid="ctp-leaderboard">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Target size={20} weight="duotone" className="text-[#F5C542]" />
          <div>
            <div className="font-mono-data text-[10px] text-zinc-500">CLOSEST TO PIN</div>
            <div className="font-display text-lg">Hole {currentHole}{isCtpHole && <span className="ml-2 chip-orange px-2 py-0.5 rounded text-[10px] font-mono-data">CTP HOLE</span>}</div>
          </div>
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <div className="flex-1 flex gap-2">
          <div className="flex-1">
            <div className="text-[10px] font-mono-data text-zinc-500 mb-1">FT</div>
            <input
              data-testid="ctp-feet-input"
              type="number"
              min={0}
              value={form.feet}
              onChange={(e) => setForm({ ...form, feet: e.target.value })}
              placeholder="0"
              className="w-full h-10 bg-[#2a5f3d] border border-white/10 rounded-md px-3 font-mono-data"
            />
          </div>
          <div className="flex-1">
            <div className="text-[10px] font-mono-data text-zinc-500 mb-1">IN</div>
            <input
              data-testid="ctp-inches-input"
              type="number"
              min={0}
              max={11.99}
              step={0.25}
              value={form.inches}
              onChange={(e) => setForm({ ...form, inches: e.target.value })}
              placeholder="0"
              className="w-full h-10 bg-[#2a5f3d] border border-white/10 rounded-md px-3 font-mono-data"
            />
          </div>
        </div>
        <button data-testid="ctp-submit-btn" onClick={submit} className="btn-primary text-xs self-end flex items-center gap-1"><Plus size={12} weight="bold" />Log</button>
      </div>

      {holeEntries.length === 0 ? (
        <div className="text-zinc-500 text-xs text-center py-2 font-mono-data">NO CTP ENTRIES YET FOR HOLE {currentHole}</div>
      ) : (
        <div className="space-y-1.5" data-testid="ctp-hole-list">
          {holeEntries.map((e, i) => (
            <div key={e.id} className={`flex items-center justify-between p-2 rounded border ${i === 0 ? "bg-[#F5C542]/8 border-[#F5C542]/30" : "bg-[#2a5f3d] border-white/6"}`} data-testid={`ctp-entry-${e.id}`}>
              <div className="flex items-center gap-2 min-w-0">
                <span className={`font-mega text-lg ${i === 0 ? "text-[#F5C542]" : "text-zinc-500"}`}>{i + 1}</span>
                <div className="truncate text-sm">{e.member_name}</div>
              </div>
              <div className="flex items-center gap-3">
                <div className="font-mono-data text-xs flex items-center gap-1"><Ruler size={11} /> {e.feet}'{e.inches ? ` ${e.inches}"` : ''}</div>
                {(isDirector || e.member_id === currentMemberId) && (
                  <button data-testid={`ctp-remove-${e.id}`} onClick={() => removeEntry(e.id)} className="text-zinc-500 hover:text-red-400">
                    <Trash size={12} />
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
