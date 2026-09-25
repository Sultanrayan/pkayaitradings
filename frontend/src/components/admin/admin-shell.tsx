"use client";

import Image from "next/image";
import Link from "next/link";
import { LogOut, ShieldCheck } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { ADMIN_PATH } from "@/lib/admin";

/** Chrome for the (secret) admin console. */
export function AdminShell({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-dvh bg-background">
      <header className="sticky top-0 z-30 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3">
          <Link href={ADMIN_PATH} className="flex items-center gap-3">
            <span className="relative size-8 shrink-0 overflow-hidden rounded-lg ring-1 ring-border">
              <Image src="/logo-pkay.jpg" alt="Pkay TDAI" fill sizes="32px" className="object-cover" />
            </span>
            <span className="flex items-center gap-2 text-sm font-semibold tracking-tight">
              <ShieldCheck className="size-4 text-gold" />
              Pkay TDAI · Admin
            </span>
          </Link>

          <div className="flex items-center gap-3">
            <span className="hidden text-xs text-muted-foreground sm:inline">{user?.email}</span>
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={logout}>
              <LogOut className="size-4" />
              Sign out
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}
