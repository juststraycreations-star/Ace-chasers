import { useEffect, useState } from "react";
import { Megaphone, PencilSimple, Check, X } from "@phosphor-icons/react";
import api from "@/lib/api";
import { toast } from "sonner";

export default function DirectorNotesBanner({ round, isDirector, onUpdated }) {
  const [editing, setEditing] = useState(false);
  const [notes, setNotes] = useState(round?.director_notes || "");

  useEffect(() => { setNotes(round?.director_notes || ""); }, [round?.director_notes]);

  const save = async () => {
    try {
      await api.patch(`/rounds/${round.id}/director-notes`, { director_notes: notes });
      setEditing(false);
      toast.success("Broadcast sent to all players");
      onUpdated?.();
    } catch { toast.error("Failed to update"); }
  };

  const empty = !round?.director_notes?.trim();
  if (empty && !isDirector) return null;

  return (
    <div className="sticky top-[100px] z-20 mb-4" data-testid="director-notes-banner">
      <div className={`rounded-lg p-3 border ${empty ? "bg-zinc-900/70 border-white/8" : "bg-[#FF5C00]/12 border-[#FF5C00]/40"} backdrop-blur-lg`}>
        <div className="flex items-start gap-3">
          <div className={`p-2 rounded-md ${empty ? "bg-white/5 text-zinc-400" : "bg-[#FF5C00]/20 text-[#FF9E00]"}`}>
            <Megaphone size={16} weight="fill" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-mono-data text-[10px] text-zinc-500 mb-1">LEAGUE DIRECTOR BROADCAST</div>
            {editing ? (
              <textarea
                data-testid="director-notes-input"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                placeholder="Hole 7 OB rope moved to left tree line. Play from previous lie."
                className="w-full bg-black/40 border border-white/15 rounded-md px-2 py-1.5 text-sm"
              />
            ) : (
              <div className={`text-sm ${empty ? "text-zinc-500 italic" : "text-white font-medium"}`}>
                {round?.director_notes || "No active broadcasts. Course conditions & rulings will appear here."}
              </div>
            )}
          </div>
          {isDirector && (
            editing ? (
              <div className="flex gap-1">
                <button data-testid="director-notes-save" onClick={save} className="p-2 rounded-md bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30"><Check size={14} weight="bold" /></button>
                <button data-testid="director-notes-cancel" onClick={() => { setNotes(round?.director_notes || ""); setEditing(false); }} className="p-2 rounded-md bg-white/5 text-zinc-400 hover:bg-white/10"><X size={14} /></button>
              </div>
            ) : (
              <button data-testid="director-notes-edit" onClick={() => setEditing(true)} className="p-2 rounded-md bg-white/5 text-zinc-400 hover:text-white hover:bg-white/10">
                <PencilSimple size={14} weight="duotone" />
              </button>
            )
          )}
        </div>
      </div>
    </div>
  );
}
