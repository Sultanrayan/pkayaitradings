"use client";

import { useEffect, useRef } from "react";

declare global {
  interface Window {
    grecaptcha?: {
      render: (container: HTMLElement, options: Record<string, unknown>) => number;
      reset: (widgetId: number) => void;
      remove: (widgetId: number) => void;
      ready: (callback: () => void) => void;
    };
  }
}

const RECAPTCHA_SCRIPT_URL = "https://www.google.com/recaptcha/api.js?render=explicit";
const RECAPTCHA_SCRIPT_ID = "google-recaptcha-api";

export interface ReCaptchaProps {
  siteKey: string;
  onTokenChange: (token: string | null) => void;
  /**
   * Bump to force a fresh widget. reCAPTCHA v2 tokens expire after roughly two
   * minutes, so a form left open long enough needs a new challenge; incrementing
   * this is how the parent asks for one.
   */
  resetKey?: number;
  className?: string;
}

/**
 * Google reCAPTCHA v2 checkbox, rendered explicitly rather than via the
 * `g-recaptcha` auto-attribute class.
 *
 * Explicit rendering is what lets the token be reported as state and lets the widget
 * be reset; the auto class gives neither. The script is loaded lazily and only once,
 * and an absent site key renders nothing so local development is unaffected.
 *
 * This is the client half only. The token is worth nothing on its own — the server
 * verifies it against the secret in `orchestrator/recaptcha.py`.
 */
export function ReCaptcha({ siteKey, onTokenChange, resetKey = 0, className }: ReCaptchaProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<number | null>(null);

  useEffect(() => {
    if (!siteKey) return;

    let disposed = false;

    const render = () => {
      if (disposed || !containerRef.current || !window.grecaptcha) return;
      // A stale id would be removed by the cleanup below; never render twice into
      // the same node, which reCAPTCHA treats as an error.
      if (widgetIdRef.current !== null) return;
      widgetIdRef.current = window.grecaptcha.render(containerRef.current, {
        sitekey: siteKey,
        theme: "dark",
        callback: (token: string) => onTokenChange(token),
        "expired-callback": () => onTokenChange(null),
        "error-callback": () => onTokenChange(null),
      });
    };

    const existing = document.getElementById(RECAPTCHA_SCRIPT_ID);
    if (existing) {
      if (window.grecaptcha) render();
      else existing.addEventListener("load", render);
    } else {
      const script = document.createElement("script");
      script.src = RECAPTCHA_SCRIPT_URL;
      script.async = true;
      script.defer = true;
      script.id = RECAPTCHA_SCRIPT_ID;
      script.addEventListener("load", render);
      document.body.appendChild(script);
    }

    return () => {
      disposed = true;
      if (widgetIdRef.current !== null && window.grecaptcha) {
        window.grecaptcha.remove(widgetIdRef.current);
        widgetIdRef.current = null;
      }
    };
  }, [siteKey, onTokenChange, resetKey]);

  if (!siteKey) return null;

  return (
    <div
      ref={containerRef}
      className={className ?? "flex min-h-16 items-center justify-center"}
    />
  );
}

/**
 * Honeypot field.
 *
 * Hidden from people and from assistive tech, but not from a script that reads the
 * DOM and fills every input it finds. Submitted with the form so the server can
 * reject on a non-empty value. `tabIndex={-1}` and `autoComplete="off"` keep it out
 * of keyboard navigation and out of autofill, which would otherwise trip it for a
 * real person.
 */
export function HoneypotField({
  value,
  onChange,
  name = "website",
}: {
  value: string;
  onChange: (value: string) => void;
  name?: string;
}) {
  return (
    <div aria-hidden className="absolute left-[-9999px] top-[-9999px] h-0 w-0 overflow-hidden">
      <label htmlFor="hp-website">Leave this field empty</label>
      <input
        id="hp-website"
        name={name}
        type="text"
        tabIndex={-1}
        autoComplete="off"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}