"use client";

import { Bell } from "lucide-react";
import { cn } from "cn";

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useAlerts } from "@/hooks/use-api";
import { formatDateTime } from "@/lib/format";
import type { Alert, AlertPriority } from "@/lib/types";

function priorityTone(priority: AlertPriority): string {
  if (priority === "critical" || priority === "high") return "text-bear";
  if (priority === "medium") return "text-gold";
  return "text-muted-foreground";
}

function AlertRow({ alert }: { alert: Alert }) {
  return (
    <div className="border-b border-border px-3 py-2.5 last:border-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] uppercase tracking-wider text-muted-foreground">{alert.type}</span>
        <span className={cn("text-[10px] uppercase tracking-wider", priorityTone(alert.priority))}>
          {alert.priority}
        </span>
      </div>
      <div className="mt-0.5 text-xs font-medium">{alert.title}</div>
      <div className="mt-0.5 line-clamp-2 text-[11px] text-muted-foreground">{alert.detail}</div>
      <div className="mt-1 text-[10px] text-muted-foreground">{formatDateTime(alert.created_at)}</div>
    </div>
  );
}

export function NotificationsMenu() {
  const alerts = useAlerts(12);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Notifications"
          className="relative rounded-full p-2 text-muted-foreground outline-none transition-colors hover:bg-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Bell className="size-4" />
          {alerts.data.length > 0 ? (
            <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-gold" />
          ) : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          Notifications
          <span className="tabular text-[11px] text-muted-foreground">
            {alerts.data.length} recent
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <ScrollArea className="h-auto max-h-96">
          {alerts.data.length === 0 ? (
            <div className="px-3 py-8 text-center text-xs text-muted-foreground">
              No notifications yet.
            </div>
          ) : (
            alerts.data.map((alert) => <AlertRow key={alert.id} alert={alert} />)
          )}
        </ScrollArea>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}