"use client";

import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api, googleLoginUrl } from "@/lib/api";

function GoogleMark() {
  return (
    <svg viewBox="0 0 24 24" className="size-4" aria-hidden>
      <path
        fill="#4285F4"
        d="M23.49 12.27c0-.79-.07-1.54-.2-2.27H12v4.51h6.44a5.51 5.51 0 0 1-2.39 3.62v3h3.86c2.26-2.09 3.58-5.17 3.58-8.86z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.86-3c-1.08.72-2.45 1.15-4.07 1.15-3.13 0-5.78-2.11-6.73-4.96H1.29v3.09A12 12 0 0 0 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.27 14.28a7.2 7.2 0 0 1 0-4.56V6.63H1.29a12 12 0 0 0 0 10.74l3.98-3.09z"
      />
      <path
        fill="#EA4335"
        d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0A12 12 0 0 0 1.29 6.63l3.98 3.09C6.22 6.86 8.87 4.75 12 4.75z"
      />
    </svg>
  );
}

/** "Continue with Google" button that starts the backend OAuth flow. */
export function GoogleSignIn({
  label = "Continue with Google",
  turnstileToken,
  disabled = false,
}: {
  label?: string;
  turnstileToken?: string;
  disabled?: boolean;
}) {
  const [configured, setConfigured] = useState<boolean | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      await Promise.resolve();
      try {
        const config = await api.authConfig();
        if (active) setConfigured(config.google);
      } catch {
        if (active) setConfigured(false);
      }
    })();
    return () => {
      active = false;
    };
  }, []);

  const start = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    const params = new URLSearchParams(window.location.search);
    const next = params.get("next") ?? undefined;
    window.location.assign(googleLoginUrl(turnstileToken, next));
  };

  if (configured === null) {
    return (
      <Button disabled className="w-full gap-2">
        <Loader2 className="size-4 animate-spin" />
        Checking sign-in…
      </Button>
    );
  }

  if (!configured) {
    return (
      <div className="rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
        Google sign-in is not configured yet. Set <code>GOOGLE_CLIENT_ID</code> and{" "}
        <code>GOOGLE_CLIENT_SECRET</code> on the backend to enable it.
      </div>
    );
  }

  if (disabled) {
    return (
      <Button disabled className="w-full gap-2">
        <GoogleMark />
        {label}
      </Button>
    );
  }

  return (
    <Button className="w-full gap-2" onClick={start}>
      <GoogleMark />
      {label}
    </Button>
  );
}
