"use client";

import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { cn } from "cn";

export interface CopyButtonProps {
  value: string;
  className?: string;
  label?: string;
}

/**
 * Copies `value` to the clipboard and confirms it briefly.
 *
 * `navigator.clipboard` is unavailable on insecure origins, so the legacy path is kept
 * as a fallback rather than leaving the button inert in those contexts.
 */
export function CopyButton({ value, className, label = "Copy" }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(value);
      } else {
        const field = document.createElement("textarea");
        field.value = value;
        field.setAttribute("readonly", "");
        field.style.position = "fixed";
        field.style.opacity = "0";
        document.body.appendChild(field);
        field.select();
        document.execCommand("copy");
        document.body.removeChild(field);
      }
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard permission can be refused; leave the button unconfirmed rather than
      // claiming a copy that did not happen.
    }
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={copied ? "Copied" : label}
      className={cn(
        "inline-flex h-7 shrink-0 items-center gap-1.5 rounded-md border border-border bg-background px-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        copied && "text-foreground",
        className,
      )}
    >
      {copied ? <Check aria-hidden className="size-3.5" /> : <Copy aria-hidden className="size-3.5" />}
      {copied ? "Copied" : label}
    </button>
  );
}