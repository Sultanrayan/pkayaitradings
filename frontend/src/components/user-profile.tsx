"use client";

import { useState } from "react";
import { Settings } from "lucide-react";
import { cn } from "cn";

import { SettingsDialog } from "@/components/settings/settings-dialog";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { useProfile } from "@/hooks/use-profile";
import { profileInitials } from "@/lib/profile";

/**
 * User profile trigger. Clicking it opens the centered settings dialog.
 *
 * `sidebar` shows the avatar plus name/email; `compact` shows only the avatar
 * (used in the header).
 */
export function UserProfile({ variant = "sidebar" }: { variant?: "sidebar" | "compact" }) {
  const profile = useProfile();
  const [open, setOpen] = useState(false);
  const initials = profileInitials(profile.name);

  const avatar = (
    <Avatar className={variant === "sidebar" ? "size-9" : "size-8"}>
      {profile.avatarUrl ? <AvatarImage src={profile.avatarUrl} alt={profile.name} /> : null}
      <AvatarFallback className="bg-accent text-xs font-medium">{initials}</AvatarFallback>
    </Avatar>
  );

  return (
    <>
      {variant === "sidebar" ? (
        <button
          type="button"
          onClick={() => setOpen(true)}
          className="flex w-full items-center gap-3 rounded-lg p-2 text-left transition-colors hover:bg-accent/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-label="Open profile settings"
        >
          {avatar}
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium">{profile.name}</div>
            <div className="truncate text-[11px] text-muted-foreground">{profile.email}</div>
          </div>
          <Settings className="size-4 shrink-0 text-muted-foreground" />
        </button>
      ) : (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open profile settings"
          className={cn(
            "rounded-full outline-none transition-opacity hover:opacity-90",
            "focus-visible:ring-2 focus-visible:ring-ring",
          )}
        >
          {avatar}
        </button>
      )}

      <SettingsDialog open={open} onOpenChange={setOpen} />
    </>
  );
}
