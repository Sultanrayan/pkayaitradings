"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2, ShieldAlert } from "lucide-react";

import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";
import { ADMIN_LOGIN_PATH } from "@/lib/admin";

type Status = "checking" | "authorized" | "denied";

/**
 * Gate the admin console: require a signed-in account whose email is on the
 * backend allowlist. The allowlist itself is never hard-coded here — the backend
 * is the single source of truth and answers `/api/v1/admin/session`.
 */
export function AdminGuard({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    if (loading) return;

    if (!user) {
      router.replace(ADMIN_LOGIN_PATH);
      return;
    }

    let active = true;
    void (async () => {
      try {
        await api.adminSession();
        if (active) setStatus("authorized");
      } catch {
        if (active) setStatus("denied");
      }
    })();
    return () => {
      active = false;
    };
  }, [loading, user, router]);

  if (loading || status === "checking") {
    return (
      <div className="flex min-h-dvh items-center justify-center">
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" />
          Verifying access…
        </div>
      </div>
    );
  }

  if (status === "denied") {
    return (
      <div className="flex min-h-dvh items-center justify-center px-4">
        <Card className="w-full max-w-md bg-card/80 ring-border">
          <CardHeader className="text-center">
            <div className="mx-auto mb-3 flex size-11 items-center justify-center rounded-xl bg-bear/10">
              <ShieldAlert className="size-5 text-bear" />
            </div>
            <CardTitle className="text-lg">Access denied</CardTitle>
            <CardDescription>
              {user?.email ?? "This account"} is not authorized for the admin area.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-center text-xs text-muted-foreground">
              Admin access is limited to allow-listed, verified accounts.
            </p>
            <Button asChild variant="outline" className="w-full">
              <Link href="/">Back to home</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  return <>{children}</>;
}
