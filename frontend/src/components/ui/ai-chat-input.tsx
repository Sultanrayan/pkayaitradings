"use client";

import * as React from "react";
import { ArrowUp, Mic } from "lucide-react";
import { cn } from "cn";

/**
 * AI input, adapted from the 21st.dev `@kokonutd/components/ai-input`.
 * A single auto-resizing textarea with a mic chip and an animated submit
 * button that fades in when there is text. Enter submits; Shift+Enter inserts
 * a new line.
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
  placeholder = "Type your message…",
  value,
  onChange,
  disabled = false,
  className,
  minHeight = 52,
  maxHeight = 200,
}: PromptInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const controlled = value !== undefined;
  const [internal, setInternal] = React.useState("");
  const text = controlled ? (value ?? "") : internal;

  const adjustHeight = React.useCallback(
    (reset = false) => {
      const el = textareaRef.current;
      if (!el) return;
      el.style.height = `${minHeight}px`;
      if (reset) return;
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

  return (
    <div className={cn("w-full py-2", className)}>
      <div className="relative mx-auto w-full max-w-xl">
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
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              submit();
            }
          }}
          style={{ minHeight, maxHeight }}
          className={cn(
            "max-w-xl resize-none overflow-y-auto rounded-3xl border-none bg-black/5 py-[16px] pl-6 pr-16 text-wrap text-black shadow-[inset_0_0_0_1px] shadow-black/20 transition-[height] duration-100 ease-out outline-none focus-visible:ring-0 focus-visible:ring-offset-0 placeholder:text-black/50 dark:bg-white/5 dark:text-white dark:shadow-white/20 dark:placeholder:text-white/50 [&::-webkit-resizer]:hidden",
          )}
        />

        {/* Mic chip – visible while empty */}
        <div
          className={cn(
            "absolute top-1/2 -translate-y-1/2 rounded-xl bg-black/5 py-1 px-1 transition-all duration-200 dark:bg-white/5",
            canSubmit ? "right-10 opacity-0" : "right-3",
          )}
        >
          <Mic className="h-4 w-4 text-black/70 dark:text-white/70" />
        </div>

        {/* Submit button – fades in with text */}
        <button
          type="button"
          onClick={submit}
          disabled={disabled || !canSubmit}
          aria-label="Send prompt"
          className={cn(
            "absolute right-3 top-1/2 -translate-y-1/2 rounded-xl bg-black/5 py-1 px-1 text-black/70 transition-all duration-200 hover:bg-black/10 disabled:pointer-events-none dark:bg-white/5 dark:text-white/70 dark:hover:bg-white/10 dark:disabled:pointer-events-none",
            canSubmit ? "scale-100 opacity-100" : "pointer-events-none scale-95 opacity-0",
          )}
        >
          <ArrowUp className="h-4 w-4" />
        </button>
      </div>
    </div>
  );
}