"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bot,
  ChevronRight,
  CreditCard,
  LogOut,
  Settings,
  Shield,
  UserRound,
  Users,
} from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useProfile } from "@/hooks/use-profile";
import { profileInitials } from "@/lib/profile";

const MENU = [
  { href: "/subscriptions", label: "Subscriptions", icon: CreditCard },
  { href: "/community", label: "Community", icon: Users },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/ai", label: "AI", icon: Bot },
];

export function ProfileMenu() {
  const { user, logout } = useAuth();
  const profile = useProfile();
  const router = useRouter();

  const name = user?.name ?? profile.name;
  const plan = user?.plan ?? "Free";
  const initials = profileInitials(name);

  const handleLogout = () => {
    logout();
    router.push("/login");
  };

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Account menu"
          className="rounded-full outline-none ring-ring transition-opacity hover:opacity-90 focus-visible:ring-2"
        >
          <Avatar className="size-8">
            {profile.avatarUrl ? <AvatarImage src={profile.avatarUrl} alt={name} /> : null}
            <AvatarFallback className="bg-accent text-xs font-medium">{initials}</AvatarFallback>
          </Avatar>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel className="flex items-center gap-3 p-3">
          <Avatar className="size-10">
            {profile.avatarUrl ? <AvatarImage src={profile.avatarUrl} alt={name} /> : null}
            <AvatarFallback className="bg-accent text-sm">{initials}</AvatarFallback>
          </Avatar>
          <div className="min-w-0">
            <div className="truncate text-sm font-medium">{name}</div>
            <div className="flex items-center gap-1 truncate text-[11px] text-muted-foreground">
              <Shield className="size-3 shrink-0" />
              <span className="truncate">{plan}</span>
            </div>
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          {MENU.map((item) => {
            const Icon = item.icon;
            return (
              <DropdownMenuItem key={item.href} asChild>
                <Link href={item.href} className="flex w-full items-center justify-between">
                  <span className="flex items-center gap-2">
                    <Icon className="size-4" />
                    {item.label}
                  </span>
                  <ChevronRight className="size-3.5 text-muted-foreground" />
                </Link>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onClick={handleLogout} className="justify-between">
          <span className="flex items-center gap-2">
            <LogOut className="size-4" />
            Logout
          </span>
          <UserRound className="size-3.5 opacity-50" />
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}