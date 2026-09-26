"use client";

import * as React from "react";
import { ArrowUp, Mic } from "lucide-react";
import { cn } from "cn";

/**
 * AI chat composer: one unified horizontal input.
 *
 * The textarea grows to fill the available width and expands vertically as
 * the user types, while the microphone and send buttons live inside the same
 * container on the right, vertically aligned with the input. No page-level
 * positioning — everything is a single flex bar.
 */

export interface PromptMeta {
  model: string;
  effort: string;
  attachments: File[];
}

export interface PromptInputProps {
  onSubmit?: (message: string, meta?: PromptMeta) => void;
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  className?: string;
  minHeight?: number;
  maxHeight?: number;
}

export function PromptInput({
  onSubmit,
  placeholder = "Ask anything about the market…",
  value,
  onChange,
  disabled = false,
  className,
  minHeight = 24,
  maxHeight = 160,
}: PromptInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const controlled = value !== undefined;
  const [internal, setInternal] = React.useState("");
  const text = controlled ? (value ?? "") : internal;

  const adjustHeight = React.useCallback(
    (reset = false) => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = "0px";
      if (reset) {
        el.style.height = "auto";
        return;
      }
      const next = Math.max(minHeight, Math.min(el.scrollHeight, maxHeight));
      el.style.height = `${next}px`;
    },
    [minHeight, maxHeight],
  );

  React.useEffect(() => {
    adjustHeight();
    const onResize = () => adjustHeight();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [adjustHeight]);

  const setText = React.useCallback(
    (next: string) => {
      if (controlled) onChange?.(next);
      else setInternal(next);
    },
    [controlled, onChange],
  );

  const submit = React.useCallback(() => {
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSubmit?.(trimmed);
    setText("");
    requestAnimationFrame(() => adjustHeight(true));
  }, [text, disabled, onSubmit, setText, adjustHeight]);

  const canSubmit = text.trim().length > 0;

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit();
    }
  };

  return (
    <div
      className={cn(
        "group flex w-full items-end gap-2 rounded-2xl border border-border bg-card p-2 pl-3.5 shadow-sm transition-colors",
        "focus-within:border-ring/60 focus-within:ring-2 focus-within:ring-ring/20 hover:border-border/80",
        disabled && "opacity-60",
        className,
      )}
    >
      <textarea
        id="ai-input"
        ref={textareaRef}
        placeholder={placeholder}
        disabled={disabled}
        value={text}
        rows={1}
        onChange={(event) => {
          setText(event.target.value);
          requestAnimationFrame(() => adjustHeight());
        }}
        onKeyDown={handleKeyDown}
        style={{ minHeight, maxHeight }}
        className={cn(
          "min-w-0 flex-1 resize-none overflow-y-auto bg-transparent px-1 py-2.5 text-[15px] leading-6 text-foreground outline-none",
          "placeholder:text-muted-foreground/70",
          "[&::-webkit-resizer]:hidden",
        )}
      />

      {/* Action buttons – inside the same container, right-aligned and
          vertically centred; never leaves the composer bar. */}
      <div className="flex shrink-0 items-center gap-1.5 self-center">
        <button
          type="button"
          disabled={disabled}
          aria-label="Use voice input"
          title="Voice input"
          className="flex size-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50"
        >
          <Mic className="size-4.5" />
        </button>

        <button
          type="button"
          onClick={submit}
          disabled={disabled || !canSubmit}
          aria-label="Send prompt"
          title="Send"
          className={cn(
            "flex size-9 items-center justify-center rounded-full bg-primary text-primary-foreground transition-all duration-200 hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ring",
            !canSubmit && "bg-muted text-muted-foreground hover:bg-muted hover:opacity-100",
            !canSubmit && "opacity-60",
          )}
        >
          <ArrowUp className="size-4.5" />
        </button>
      </div>
    </div>
  );
}