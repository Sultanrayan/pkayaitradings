"use client";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import type { SocialUser } from "@/hooks/use-social";

export function UserAvatar({
  user,
  size = "default",
  className,
}: {
  user: Pick<SocialUser, "name" | "avatar">;
  size?: "default" | "sm" | "lg" | "xs";
  className?: string;
}) {
  const initials = user.name
    .split(/\s+/)
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
  const sizeClass =
    size === "xs"
      ? "size-7"
      : size === "sm"
        ? "size-8"
        : size === "lg"
          ? "size-12"
          : "size-10";
  return (
    <Avatar size={size === "sm" ? "sm" : size === "lg" ? "lg" : "default"} className={className}>
      {user.avatar ? <AvatarImage src={user.avatar} alt={user.name} /> : null}
      <AvatarFallback className={sizeClass}>{initials || "U"}</AvatarFallback>
    </Avatar>
  );
}

/** Compact relative time: "5m", "3h", "2d". */
export function relativeTime(iso: string): string {
  const delta = Date.now() - new Date(iso).getTime();
  if (delta < 60_000) return "now";
  if (delta < 3_600_000) return `${Math.floor(delta / 60_000)}m`;
  if (delta < 86_400_000) return `${Math.floor(delta / 3_600_000)}h`;
  return `${Math.floor(delta / 86_400_000)}d`;
}

/** Verified badge shown next to a display name. */
export function VerifiedBadge() {
  return (
    <svg
      viewBox="0 0 24 24"
      className="size-4 shrink-0 fill-sky-500 text-background"
      aria-label="Verified"
    >
      <path d="M12 1.6 14.8 4l3.6-.6 1 3.4 3.2 1.8-1 3.4 1 3.4-3.2 1.8-1 3.4L14.8 20 12 22.4 9.2 20l-3.6.6-1-3.4L1.4 15.4l1-3.4-1-3.4 3.2-1.8 1-3.4L9.2 4z" />
      <path
        d="M10.6 14.9 8 12.3l-1.1 1.1 3.7 3.7 6-6-1.1-1.1z"
        className="fill-background"
      />
    </svg>
  );
}