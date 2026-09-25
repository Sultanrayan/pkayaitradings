"use client";

import { useEffect, useRef } from "react";

declare global {
  interface Window {
    turnstile?: {
      render: (container: HTMLElement, options: Record<string, unknown>) => string;
      reset: (widgetId: string) => void;
      remove: (widgetId: string) => void;
    };
  }
}

interface TurnstileProps {
  siteKey: string;
  onTokenChange: (token: string | null) => void;
}

const TURNSTILE_SCRIPT_URL =
  "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
const TURNSTILE_SCRIPT_ID = "cf-turnstile-api";

/**
 * Renders a Cloudflare Turnstile widget and reports the verification token
 * (or null when it expires / fails) back to the caller.
 *
 * Loads the Turnstile script lazily; a no-op when no site key is configured.
 */
export function Turnstile({ siteKey, onTokenChange }: TurnstileProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string | null>(null);

  useEffect(() => {
    if (!siteKey) return;

    let disposed = false;

    const render = () => {
      if (disposed || !containerRef.current || !window.turnstile) return;
      widgetIdRef.current = window.turnstile.render(containerRef.current, {
        sitekey: siteKey,
        callback: (token: string) => onTokenChange(token),
        "expired-callback": () => onTokenChange(null),
        "error-callback": () => onTokenChange(null),
      });
    };

    const existing = document.getElementById(TURNSTILE_SCRIPT_ID);
    if (existing) {
      if (window.turnstile) render();
      else existing.addEventListener("load", render);
    } else {
      const script = document.createElement("script");
      script.src = TURNSTILE_SCRIPT_URL;
      script.async = true;
      script.defer = true;
      script.id = TURNSTILE_SCRIPT_ID;
      script.addEventListener("load", render);
      document.body.appendChild(script);
    }

    return () => {
      disposed = true;
      if (widgetIdRef.current && window.turnstile) {
        window.turnstile.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [siteKey, onTokenChange]);

  if (!siteKey) return null;
  return <div ref={containerRef} className="flex min-h-16 items-center justify-center" />;
}