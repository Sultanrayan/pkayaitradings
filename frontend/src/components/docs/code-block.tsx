"use client";

import { useState } from "react";

import { CopyButton } from "@/components/docs/copy-button";
import { cn } from "cn";

export interface CodeBlockProps {
  /** Single snippet. Ignored when `tabs` is supplied. */
  code?: string;
  /** Language badge shown when there is only one snippet. */
  language?: string;
  /** Language label to snippet. Renders a tab bar instead of a single snippet. */
  tabs?: Record<string, string>;
  className?: string;
}

/**
 * A copyable snippet, optionally with one tab per language.
 *
 * The preformatted area scrolls horizontally rather than wrapping, because wrapped
 * code is harder to read than scrolled code — long URLs and shell lines stay intact
 * at any viewport width. Tabs are real buttons in a `role="tablist"` so arrow-key
 * navigation works.
 */
export function CodeBlock({ code, language, tabs, className }: CodeBlockProps) {
  const languages = tabs ? Object.keys(tabs) : [];
  const [active, setActive] = useState(languages[0] ?? "");
  const snippet = tabs ? tabs[active] : (code ?? "");

  return (
    <figure
      className={cn(
        "overflow-hidden rounded-lg border border-border bg-muted/40",
        className,
      )}
    >
      {tabs ? (
        <div
          role="tablist"
          aria-label="Language"
          className="flex items-center gap-1 border-b border-border px-2 py-1.5"
        >
          {languages.map((name) => {
            const selected = name === active;
            return (
              <button
                key={name}
                role="tab"
                type="button"
                aria-selected={selected}
                onClick={() => setActive(name)}
                className={cn(
                  "rounded-md px-2 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                  selected
                    ? "bg-muted text-foreground"
                    : "text-muted-foreground hover:text-foreground",
                )}
              >
                {name}
              </button>
            );
          })}
          <CopyButton value={snippet} className="ml-auto" />
        </div>
      ) : language ? (
        <div className="flex items-center justify-between gap-2 border-b border-border px-2 py-1.5">
          <span className="px-1 text-xs font-medium text-muted-foreground">{language}</span>
          <CopyButton value={snippet} />
        </div>
      ) : null}

      <pre className="overflow-x-auto px-4 py-3 text-[13px] leading-6">
        <code className="font-mono text-foreground">{snippet}</code>
      </pre>
    </figure>
  );
}