import { useEffect, useState } from "react";
import api from "@/lib/api";
import { toast } from "sonner";
import { PaperPlaneTilt, MegaphoneSimple, ChatCircle, X } from "@phosphor-icons/react";

/**
 * ManagerDMPanel — director-only compose surface for direct messages
 * and league-wide broadcasts. Uses the existing DM `/api/messages/*`
 * router for 1:1 sends and the new `/api/leagues/{id}/broadcast`
 * endpoint for group blasts.
 *
 * Design: a compact card that expands into a modal on demand so it
 * doesn't overwhelm the league dashboard.
 */
export default function ManagerDMPanel({ leagueId, isDirector }) {
  const [members, setMembers] = useState([]);
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("broadcast"); // broadcast | dm
  const [recipient, setRecipient] = useState(null); // { user_id, name }
  const [body, setBody] = useState("");
  const [title, setTitle] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!leagueId || !isDirector) return;
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/members`);
        setMembers(data || []);
      } catch {
        // silent — dashboard also loads members elsewhere.
      }
    })();
  }, [leagueId, isDirector]);

  const reset = () => {
    setBody("");
    setTitle("");
    setRecipient(null);
    setMode("broadcast");
  };

  const send = async () => {
    const text = body.trim();
    if (!text) {
      toast.error("Message can't be empty");
      return;
    }
    setSending(true);
    try {
      if (mode === "broadcast") {
        const { data } = await api.post(`/leagues/${leagueId}/broadcast`, {
          body: text,
          title: title.trim() || null,
        });
        toast.success(`Broadcast sent to ${data.delivered} player${data.delivered === 1 ? "" : "s"}`);
      } else {
        if (!recipient?.user_id) {
          toast.error("Pick a recipient");
          setSending(false);
          return;
        }
        await api.post(`/messages/${recipient.user_id}`, { body: text });
        toast.success(`Sent to ${recipient.name}`);
      }
      reset();
      setOpen(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Send failed");
    } finally {
      setSending(false);
    }
  };

  if (!isDirector) return null;

  return (
    <>
      <div
        className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm"
        data-testid="manager-dm-panel"
      >
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-slate-100 text-slate-800 flex items-center justify-center">
            <MegaphoneSimple size={18} weight="duotone" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500">
              Manager comms
            </div>
            <div className="font-semibold text-sm text-slate-900">
              Direct message or broadcast
            </div>
            <p className="text-xs text-slate-600 mt-0.5">
              Send round updates, weather calls, or a nudge to a specific player.
            </p>
          </div>
          <button
            type="button"
            onClick={() => { setMode("broadcast"); setOpen(true); }}
            data-testid="manager-dm-open-broadcast"
            className="text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 px-4 py-2 rounded-full shadow-sm transition-colors"
          >
            Broadcast
          </button>
          <button
            type="button"
            onClick={() => { setMode("dm"); setOpen(true); }}
            data-testid="manager-dm-open-dm"
            className="text-xs font-semibold text-slate-700 border border-slate-300 hover:border-slate-500 bg-white px-4 py-2 rounded-full transition-colors"
          >
            DM
          </button>
        </div>
      </div>

      {open && (
        <div
          className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => !sending && setOpen(false)}
          data-testid="manager-dm-modal"
        >
          <div
            className="bg-white rounded-2xl border border-slate-200 max-w-lg w-full p-6 shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start justify-between mb-4">
              <div>
                <div className="font-mono-data text-[10px] uppercase tracking-widest text-slate-500">
                  {mode === "broadcast" ? "League broadcast" : "Direct message"}
                </div>
                <div className="font-display text-xl text-slate-900">
                  {mode === "broadcast" ? "Message every member" : "Message a player"}
                </div>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                data-testid="manager-dm-close"
                className="text-slate-400 hover:text-slate-800"
              >
                <X size={20} />
              </button>
            </div>

            <div className="flex gap-2 mb-4">
              <button
                type="button"
                onClick={() => setMode("broadcast")}
                data-testid="manager-dm-mode-broadcast"
                className={`text-xs px-3 py-1.5 rounded-full border ${
                  mode === "broadcast"
                    ? "bg-slate-800 text-white border-slate-800"
                    : "text-slate-700 border-slate-200"
                }`}
              >
                <MegaphoneSimple size={12} weight="duotone" className="inline mr-1" /> Broadcast
              </button>
              <button
                type="button"
                onClick={() => setMode("dm")}
                data-testid="manager-dm-mode-dm"
                className={`text-xs px-3 py-1.5 rounded-full border ${
                  mode === "dm"
                    ? "bg-slate-800 text-white border-slate-800"
                    : "text-slate-700 border-slate-200"
                }`}
              >
                <ChatCircle size={12} weight="duotone" className="inline mr-1" /> Direct message
              </button>
            </div>

            {mode === "dm" && (
              <div className="mb-3">
                <label className="text-xs font-mono-data text-slate-500 mb-1 block">
                  Recipient
                </label>
                <select
                  data-testid="manager-dm-recipient"
                  value={recipient?.user_id || ""}
                  onChange={(e) => {
                    const m = members.find((x) => x.user_id === e.target.value);
                    setRecipient(m ? { user_id: m.user_id, name: m.name } : null);
                  }}
                  className="w-full h-10 border border-slate-200 rounded-md px-3 text-sm bg-white"
                >
                  <option value="">— pick a player —</option>
                  {members
                    .filter((m) => m.user_id)
                    .map((m) => (
                      <option key={m.id} value={m.user_id}>
                        #{m.bag_tag} · {m.name}
                      </option>
                    ))}
                </select>
              </div>
            )}

            {mode === "broadcast" && (
              <div className="mb-3">
                <label className="text-xs font-mono-data text-slate-500 mb-1 block">
                  Title <span className="text-slate-400">(optional)</span>
                </label>
                <input
                  data-testid="manager-dm-title"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Weather delay"
                  className="w-full h-10 border border-slate-200 rounded-md px-3 text-sm"
                />
              </div>
            )}

            <label className="text-xs font-mono-data text-slate-500 mb-1 block">
              Message
            </label>
            <textarea
              data-testid="manager-dm-body"
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={4}
              maxLength={2000}
              placeholder={
                mode === "broadcast"
                  ? "Hey team — tee times pushed back 30 minutes due to lightning."
                  : "Nice round today — you're up two tags for next week."
              }
              className="w-full border border-slate-200 rounded-md px-3 py-2 text-sm resize-none"
            />

            <div className="flex justify-end gap-2 mt-4">
              <button
                type="button"
                onClick={() => setOpen(false)}
                disabled={sending}
                className="text-xs px-4 py-2 rounded-lg text-slate-600 hover:text-slate-900 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={send}
                disabled={sending || !body.trim() || (mode === "dm" && !recipient)}
                data-testid="manager-dm-send"
                className="text-sm px-4 py-2 rounded-lg bg-slate-800 text-white font-semibold hover:bg-slate-900 disabled:opacity-40 disabled:cursor-not-allowed inline-flex items-center gap-1.5"
              >
                <PaperPlaneTilt size={14} weight="duotone" />
                {sending ? "Sending…" : mode === "broadcast" ? "Send broadcast" : "Send DM"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
