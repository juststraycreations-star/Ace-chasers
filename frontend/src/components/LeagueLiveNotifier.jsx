import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useWebSocket } from "@/lib/ws";
import { Bell, BellSlash } from "@phosphor-icons/react";
import { toast } from "sonner";

const seen = new Set();

export default function LeagueLiveNotifier({ leagueId, isDirector }) {
  const [permission, setPermission] = useState(typeof Notification !== "undefined" ? Notification.permission : "denied");

  useEffect(() => {
    // Prime the seen set with existing announcement ids so we don't re-notify old ones
    (async () => {
      try {
        const { data } = await api.get(`/leagues/${leagueId}/announcements`);
        data.forEach((a) => seen.add(a.id));
      } catch {}
    })();
  }, [leagueId]);

  useWebSocket(`/api/ws/leagues/${leagueId}`, (msg) => {
    if (msg.type === "announcement") {
      const a = msg.announcement;
      if (seen.has(a.id)) return;
      seen.add(a.id);
      const body = a.body?.slice(0, 140);
      // In-app toast
      toast(a.urgent ? `URGENT · ${a.title}` : a.title, { description: body });
      // Browser notification
      if (a.urgent && typeof Notification !== "undefined" && Notification.permission === "granted") {
        try {
          const n = new Notification(`⚠️ ${a.title}`, {
            body,
            tag: `ann-${a.id}`,
            silent: false,
          });
          n.onclick = () => window.focus();
        } catch {}
      }
    }
  });

  const requestPermission = async () => {
    if (typeof Notification === "undefined") {
      toast.error("Notifications not supported in this browser");
      return;
    }
    const res = await Notification.requestPermission();
    setPermission(res);
    if (res === "granted") toast.success("Notifications enabled — you'll be alerted on urgent updates.");
    else toast.error("Notifications blocked");
  };

  const enabled = permission === "granted";

  return (
    <button
      data-testid="notif-toggle-btn"
      onClick={enabled ? undefined : requestPermission}
      className={`text-xs px-3 py-1.5 rounded-full flex items-center gap-2 border transition-colors ${enabled ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10" : "border-white/15 text-zinc-300 hover:bg-white/5"}`}
      title={enabled ? "Push notifications on" : "Enable urgent-alert push notifications"}
    >
      {enabled ? <Bell size={13} weight="fill" /> : <BellSlash size={13} weight="duotone" />}
      {enabled ? "Alerts On" : "Enable Alerts"}
    </button>
  );
}
