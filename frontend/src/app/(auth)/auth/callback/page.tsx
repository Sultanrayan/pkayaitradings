"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { writeTokenCookie } from "@/lib/auth";

/**
 * OAuth landing page.
 *
 * The backend redirects here with the issued token in the URL fragment
 * (`#token=...`), which is never sent to a server. We persist it, then send the
 * user directly to the dashboard.
 */
export default function AuthCallbackPage() {
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      await Promise.resolve();
      const hash = window.location.hash.replace(/^#/, "");
      const token = new URLSearchParams(hash).get("token");
      if (!token) {
        setError("Missing sign-in token. Please try again.");
        return;
      }
      writeTokenCookie(token);
      window.location.replace("/dashboard");
    })();
  }, []);

  return (
    <Card className="bg-card/80 backdrop-blur ring-border">
      <CardHeader>
        <CardTitle className="text-lg">Signing you in…</CardTitle>
        <CardDescription>Finishing Google authentication.</CardDescription>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="space-y-4">
            <p className="rounded-lg border border-bear/30 bg-bear/5 px-3 py-2 text-xs text-bear">
              {error}
            </p>
            <Button asChild className="w-full">
              <Link href="/login">Back to sign in</Link>
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Completing sign-in…
          </div>
        )}
      </CardContent>
    </Card>
  );
}
