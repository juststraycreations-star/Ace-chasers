import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../lib/api";
import { useAuthStore } from "../store/authStore";
import { toast } from "sonner";
import { DownloadSimple, Trash, Envelope } from "@phosphor-icons/react";

/**
 * Admin-only view of closed-beta signups. Backend gates on
 * BETA_ADMIN_EMAILS so only whitelisted uids can list/export/delete.
 */
export default function BetaTestersAdmin() {
  const profile = useAuthStore((s) => s.profile);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);
  const [inviting, setInviting] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get(`/beta-testers`);
      setRows(data.testers || []);
    } catch (e) {
      if (e?.response?.status === 403) setForbidden(true);
      else toast.error("Failed to load beta testers");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, []);

  const remove = async (id, email) => {
    if (!window.confirm(`Remove ${email} from the beta list?`)) return;
    try {
      await api.delete(`/beta-testers/${id}`);
      setRows((prev) => prev.filter((r) => r.id !== id));
      toast.success("Removed");
    } catch { toast.error("Failed"); }
  };

  const downloadCsv = async () => {
    // Streaming CSV — trigger via <a> with a temp blob after fetch
    try {
      const res = await api.get(`/beta-testers/export.csv`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url; a.download = "ace-chasers-beta-testers.csv"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch { toast.error("Export failed"); }
  };

  const downloadUsersCsv = async () => {
    try {
      const res = await api.get(`/admin/users/export.csv`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url; a.download = "ace-chasers-users.csv"; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 100);
    } catch { toast.error("User export failed"); }
  };

  const inviteAllUsers = async () => {
    if (!window.confirm("Email every registered user the beta install link? Users already invited will be skipped.")) return;
    setInviting(true);
    try {
      const { data } = await api.post(`/admin/users/beta-invite-all`);
      toast.success(`Sent ${data.sent} · Failed ${data.failed} · Skipped ${data.skipped_already_invited}`);
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Bulk invite failed");
    } finally {
      setInviting(false);
    }
  };

  if (forbidden) {
    return (
      <div className="min-h-screen bg-white flex items-center justify-center p-6" data-testid="beta-admin-forbidden">
        <div className="text-center">
          <div className="font-mono-data text-xs text-zinc-500 tracking-wider">ADMIN ONLY</div>
          <h1 className="font-display text-3xl mt-2">Nope, not you.</h1>
          <p className="text-sm text-gray-600 mt-2">
            {profile?.email
              ? `Signed in as ${profile.email}, which isn't on the admin whitelist.`
              : "Please sign in with an admin account."}
          </p>
          <Link to="/feed" className="mt-4 inline-block text-sm text-[#1f4d2e] underline">← Back to feed</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white" data-testid="beta-admin-page">
      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-end justify-between mb-6">
          <div>
            <div className="font-mono-data text-xs text-zinc-500 tracking-wider">ADMIN · CLOSED BETA</div>
            <h1 className="font-display text-4xl tracking-tighter mt-1">Beta Testers ({rows.length})</h1>
            <p className="text-sm text-gray-600 mt-1">
              Export CSV → paste emails into <b>Play Console → Testing → Closed testing → Testers</b>.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={downloadUsersCsv}
              data-testid="beta-admin-users-export-btn"
              className="text-xs px-3 py-2 rounded-lg border border-gray-200 text-zinc-700 hover:border-gray-300 flex items-center gap-1 font-mono-data uppercase tracking-wider"
              title="Export all registered user emails (paste into Google Groups)"
            >
              <DownloadSimple size={14} weight="bold" /> Users CSV
            </button>
            <button
              onClick={inviteAllUsers}
              disabled={inviting}
              data-testid="beta-admin-invite-all-btn"
              className="text-xs px-3 py-2 rounded-lg bg-[#1f4d2e] text-white hover:bg-[#1a3f26] disabled:opacity-50 flex items-center gap-1 font-mono-data uppercase tracking-wider"
              title="Email every registered Ace Chasers user the Play beta install link"
            >
              <Envelope size={14} weight="bold" /> {inviting ? "Sending…" : "Invite all users"}
            </button>
            <button
              onClick={downloadCsv}
              data-testid="beta-admin-export-btn"
              className="btn-primary flex items-center gap-2"
            >
              <DownloadSimple size={16} weight="bold" /> Testers CSV
            </button>
          </div>
        </div>

        {loading && <div className="text-zinc-500 font-mono-data text-xs">LOADING…</div>}

        {!loading && rows.length === 0 && (
          <div className="rounded-xl border border-gray-200 p-8 text-center">
            <div className="font-mono-data text-xs text-zinc-500">EMPTY</div>
            <p className="text-sm text-gray-600 mt-2">No signups yet. Share <Link to="/beta" className="underline">/beta</Link> to start collecting.</p>
          </div>
        )}

        {!loading && rows.length > 0 && (
          <div className="overflow-x-auto border border-gray-200 rounded-xl">
            <table className="w-full text-sm" data-testid="beta-admin-table">
              <thead className="bg-gray-50 text-xs font-mono-data uppercase tracking-wider text-zinc-500">
                <tr>
                  <th className="px-3 py-2 text-left">Email</th>
                  <th className="px-3 py-2 text-left">Name</th>
                  <th className="px-3 py-2 text-left">Phone</th>
                  <th className="px-3 py-2 text-left">Source</th>
                  <th className="px-3 py-2 text-left">Signed up</th>
                  <th className="px-3 py-2 text-left">Email delivered</th>
                  <th className="px-3 py-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {rows.map((r) => (
                  <tr key={r.id} data-testid={`beta-admin-row-${r.id}`}>
                    <td className="px-3 py-2 font-mono-data">{r.email}</td>
                    <td className="px-3 py-2">{r.name}</td>
                    <td className="px-3 py-2 text-zinc-500">{r.phone || "—"}</td>
                    <td className="px-3 py-2 text-zinc-500">{r.referral_source || "—"}</td>
                    <td className="px-3 py-2 text-zinc-500 whitespace-nowrap">{new Date(r.created_at).toLocaleString()}</td>
                    <td className="px-3 py-2">
                      {r.notification_status === "sent" ? (
                        <span className="text-emerald-600 font-mono-data text-[10px] uppercase">Sent</span>
                      ) : (
                        <span className="text-yellow-600 font-mono-data text-[10px] uppercase" title={r.notification_status}>{r.notification_status}</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <button
                        onClick={() => remove(r.id, r.email)}
                        className="text-zinc-400 hover:text-red-600 p-1"
                        data-testid={`beta-admin-remove-${r.id}`}
                        title="Remove"
                      >
                        <Trash size={14} weight="duotone" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
