import { useNavigate } from "@tanstack/react-router";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, type NotificationItem } from "@/lib/api";
import { formatDate } from "@/lib/format";

const SEV_DOT: Record<string, string> = {
  critical: "bg-red-600",
  high: "bg-orange-500",
  medium: "bg-amber-500",
  low: "bg-slate-400",
};

function linkToPath(n: NotificationItem): { to: string; search?: Record<string, string> } {
  const layer = n.link?.layer;
  const docId = n.link?.document_id;
  if (docId) return { to: "/owner/raw-data", search: { document_id: docId } };
  if (layer === "analytics") return { to: "/owner/analytics" };
  if (layer === "performance") return { to: "/owner/performance" };
  if (layer === "departments") return { to: "/owner/departments" };
  return { to: "/owner" };
}

export function NotificationBell() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.notifications();
      setItems(data.items);
      setUnread(data.unread_count);
    } catch {
      /* ignore (e.g. backend unreachable) */
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => void load(), 60 * 1000); // poll every minute
    return () => clearInterval(id);
  }, [load]);

  // Close on outside click.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function onItemClick(n: NotificationItem) {
    if (!n.is_read) {
      try {
        await api.markNotificationRead(n.id);
      } catch {
        /* ignore */
      }
    }
    setOpen(false);
    await load();
    const target = linkToPath(n);
    void navigate(target);
  }

  async function markAll() {
    try {
      await api.markAllNotificationsRead();
      await load();
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-md border border-input bg-background px-3 py-1.5 text-sm hover:bg-accent"
        title="التنبيهات"
        aria-label="التنبيهات"
      >
        🔔
        {unread > 0 && (
          <span className="absolute -left-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
            {unread > 99 ? "99+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute left-0 z-50 mt-2 w-80 overflow-hidden rounded-xl border border-border bg-card shadow-lg" dir="rtl">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-sm font-semibold text-foreground">التنبيهات</span>
            {unread > 0 && (
              <button onClick={() => void markAll()} className="text-xs text-blue-600 hover:underline">
                تعليم الكل كمقروء
              </button>
            )}
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-3 py-6 text-center text-sm text-muted-foreground">لا توجد تنبيهات</p>
            ) : (
              items.map((n) => (
                <button
                  key={n.id}
                  onClick={() => void onItemClick(n)}
                  className={`flex w-full items-start gap-2 border-b border-border/50 px-3 py-2 text-right last:border-0 hover:bg-accent/40 ${
                    n.is_read ? "opacity-60" : ""
                  }`}
                >
                  <span className={`mt-1 h-2 w-2 shrink-0 rounded-full ${SEV_DOT[n.severity] ?? "bg-slate-400"}`} />
                  <span className="flex-1">
                    <span className="block text-sm font-medium text-foreground">{n.title}</span>
                    <span className="block text-xs text-muted-foreground line-clamp-2">{n.body}</span>
                    <span className="mt-1 block text-[10px] text-muted-foreground" dir="ltr">
                      {formatDate(n.created_at)}
                    </span>
                  </span>
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
