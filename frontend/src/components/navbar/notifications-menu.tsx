"use client";

import { Bell } from "lucide-react";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useSocial } from "@/hooks/use-social";
import { useAlerts } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/format";

const TYPE_LABEL: Record<string, string> = {
  like: "Liked",
  comment: "Comment",
  reply: "Reply",
  repost: "Repost",
  follow: "New follower",
  mention: "Mention",
};

function NotificationRow({
  type,
  text,
  createdAt,
  read,
}: {
  type: string;
  text: string;
  createdAt: string;
  read: boolean;
}) {
  return (
    <div className={`border-b border-border px-3 py-2.5 last:border-0 ${read ? "" : "bg-accent/40"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
          {TYPE_LABEL[type] ?? type}
        </span>
        <span className="text-[10px] text-muted-foreground">{formatDateTime(createdAt)}</span>
      </div>
      <div className="mt-0.5 text-xs font-medium">{text}</div>
    </div>
  );
}

/**
 * Global notification bell combining system alerts with community
 * notifications (likes, comments, replies, reposts, follows, mentions).
 */
export function NotificationsMenu() {
  const {
    notifications,
    markAllNotificationsRead,
  } = useSocial();
  const alerts = useAlerts(8);

  const communityNew = notifications.filter((notification) => !notification.read).length;
  const hasUnread = communityNew > 0 || alerts.data.length > 0;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Notifications"
          className="relative rounded-full p-2 text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Bell className="size-4" />
          {hasUnread ? (
            <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-gold ring-2 ring-background" />
          ) : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          Notifications
          <button
            type="button"
            onClick={markAllNotificationsRead}
            className="text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            Mark all read
          </button>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <ScrollArea className="h-auto max-h-96">
          {notifications.length === 0 && alerts.data.length === 0 ? (
            <div className="px-3 py-8 text-center text-xs text-muted-foreground">
              No notifications yet.
            </div>
          ) : (
            <>
              {notifications.map((notification) => (
                <NotificationRow
                  key={notification.id}
                  type={notification.type}
                  text={notification.text}
                  createdAt={notification.createdAt}
                  read={notification.read}
                />
              ))}
              {alerts.data.length > 0 ? (
                <div className="px-3 py-2">
                  <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                    System alerts · {alerts.data.length}
                  </div>
                  {alerts.data.map((alert) => (
                    <div key={alert.id} className="py-1.5 text-xs text-muted-foreground">
                      {alert.title}
                    </div>
                  ))}
                </div>
              ) : null}
            </>
          )}
        </ScrollArea>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}