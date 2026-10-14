"use client";

import * as React from "react";
import { ChevronDown, CornerDownLeft, Lightbulb } from "lucide-react";
import { cn } from "cn";

import {
  COMPOSER_HINT,
  SPEAKABLE_PHRASES,
  ZENMUX_MODELS,
  ZENMUX_SYMBOL_LABEL,
  ZENMUX_TIMEFRAMES,
} from "./constants";
import type { ZenmuxModelId, ZenmuxModelOption, ZenmuxTimeframe } from "@/lib/api";

export interface ComposerProps {
  /** Called only when the user taps Enter. Never automatically. */
  onSubmit: (text: string) => void;
  model: ZenmuxModelId;
  onModelChange: (model: ZenmuxModelId) => void;
  timeframe: ZenmuxTimeframe;
  onTimeframeChange: (timeframe: ZenmuxTimeframe) => void;
  /** True while a reply is in flight. */
  busy?: boolean;
  models?: ZenmuxModelOption[];
}

/**
 * Characters revealed per tick, and the ceiling on the total reveal time.
 *
 * The delay is derived from the phrase length so a long phrase does not crawl: a
 * 40-character phrase reveals in ~800ms, a 120-character one in ~1.1s. Fixed
 * per-character timing made the long ones feel broken.
 */
const REVEAL_BUDGET_MS = 1100;
const REVEAL_MIN_DELAY_MS = 8;
const REVEAL_MAX_DELAY_MS = 20;

function subscribeToNothing(): () => void {
  return () => {};
}

/** Honour a reduced-motion preference rather than animating regardless. */
function useReducedMotion(): boolean {
  return React.useSyncExternalStore(
    subscribeToNothing,
    () =>
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    () => false,
  );
}

function revealDelay(length: number): number {
  if (length <= 0) return REVEAL_MAX_DELAY_MS;
  const perChar = Math.round(REVEAL_BUDGET_MS / length);
  return Math.min(REVEAL_MAX_DELAY_MS, Math.max(REVEAL_MIN_DELAY_MS, perChar));
}

/** A staged phrase plus how much of it has been revealed so far. */
interface StagedText {
  text: string;
  revealed: number;
}

/**
 * The Zenmux composer: a phrase is chosen, revealed, then sent.
 *
 * There is no text field and no microphone. The text comes from the phrase library —
 * tapping a phrase stages it whole, or, if a word inside it is selected first, stages
 * just that word — and the reveal types it out so it is readable before it is sent.
 *
 * Nothing is sent automatically. Staging a phrase is not consent to send it, and a
 * composer that fires on selection would submit half-read questions the moment the
 * phrase box closed. The Enter button is the only send path.
 *
 * Not the shared `PromptInput`, which belongs to `/ai`. The two screens must stay
 * independent.
 */
export function Composer({
  onSubmit,
  model,
  onModelChange,
  timeframe,
  onTimeframeChange,
  busy = false,
  models = ZENMUX_MODELS,
}: ComposerProps) {
  const [openMenu, setOpenMenu] = React.useState<"model" | "timeframe" | "phrases" | null>(null);
  /**
   * The staged phrase and how much of it is currently revealed.
   *
   * Held as one object so staging a phrase resets the reveal without a separate
   * ``setRevealed(0)`` inside an effect, which cascades an extra render on every
   * change.
   */
  const [staged, setStaged] = React.useState<StagedText | null>(null);

  const menuRef = React.useRef<HTMLDivElement | null>(null);
  const textRef = React.useRef<HTMLDivElement | null>(null);
  // A selection belongs to the phrase it was made in. Without recording which one, a
  // selection left over in phrase A would be applied to phrase B on the next tap.
  const selectionRef = React.useRef<{ phrase: string; text: string } | null>(null);

  const reducedMotion = useReducedMotion();

  React.useEffect(() => {
    if (!openMenu) return;
    const onPointerDown = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpenMenu(null);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpenMenu(null);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [openMenu]);

  // Typewriter reveal. Only the interval lives here — advancing the count is async,
  // so there is no synchronous setState in the effect body. A reduced-motion
  // preference is honoured at staging time instead.
  const stagedText = staged?.text;
  React.useEffect(() => {
    if (!stagedText || stagedText.length === 0) return;
    const id = window.setInterval(() => {
      setStaged((current) => {
        if (!current || current.revealed >= current.text.length) return current;
        return { ...current, revealed: current.revealed + 1 };
      });
    }, revealDelay(stagedText.length));
    return () => window.clearInterval(id);
  }, [stagedText]);

  // Keep the newest character in view as the line grows.
  const revealed = staged?.revealed ?? 0;
  React.useEffect(() => {
    const element = textRef.current;
    if (element) element.scrollLeft = element.scrollWidth;
  }, [revealed]);

  /** Stage a phrase, starting the reveal from the beginning. */
  const stage = React.useCallback(
    (text: string) => {
      setStaged({ text, revealed: reducedMotion ? text.length : 0 });
    },
    [reducedMotion],
  );

  /**
   * Capture a word selection as it completes. Mouse-up fires before click, so by the
   * time the click handler runs the selection is already known.
   */
  const handlePhraseMouseUp = (phrase: string) => {
    const selected = window.getSelection()?.toString().trim() ?? "";
    // Requiring the text to be contained in the phrase rejects a selection dragged
    // across two of them, which belongs to neither.
    selectionRef.current =
      selected && phrase.includes(selected) ? { phrase, text: selected } : null;
  };

  const handlePhraseClick = (phrase: string) => {
    const captured = selectionRef.current;
    selectionRef.current = null;
    stage(captured && captured.phrase === phrase ? captured.text : phrase);
    // Drop the browser selection so the next tap does not read this one.
    window.getSelection()?.removeAllRanges();
    setOpenMenu(null);
  };

  const canSend = Boolean(staged?.text.trim()) && !busy;

  const handleSend = React.useCallback(() => {
    const text = staged?.text.trim();
    if (!text || busy) return;
    onSubmit(text);
    setStaged(null);
  }, [staged, busy, onSubmit]);

  const triggerClass = cn(
    "flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-[11.5px] font-medium",
    "text-foreground transition-colors hover:bg-accent",
  );

  return (
    <div className="w-full rounded-2xl border border-border bg-card shadow-sm transition-colors focus-within:border-ring/60">
      {/* Context controls, with the phrase library beside the model selector. */}
      <div ref={menuRef} className="flex flex-wrap items-center gap-1 px-2.5 pb-2 pt-2.5">
        {/* Symbol is fixed for this screen — the service covers XAU/USD only. */}
        <span className="rounded-md bg-muted px-2 py-1 text-[11.5px] font-medium text-muted-foreground">
          {ZENMUX_SYMBOL_LABEL}
        </span>

        <div className="relative">
          <button
            type="button"
            aria-haspopup="listbox"
            aria-expanded={openMenu === "timeframe"}
            onClick={() =>
              setOpenMenu((current) => (current === "timeframe" ? null : "timeframe"))
            }
            className={triggerClass}
          >
            {timeframe}
            <ChevronDown className="size-3 opacity-70" aria-hidden />
          </button>
          {openMenu === "timeframe" ? (
            <div
              role="listbox"
              aria-label="Timeframe"
              className="absolute bottom-full left-0 z-30 mb-1.5 w-28 overflow-hidden rounded-xl border border-border bg-popover p-1 shadow-lg"
            >
              {ZENMUX_TIMEFRAMES.map((entry) => (
                <button
                  key={entry}
                  type="button"
                  role="option"
                  aria-selected={entry === timeframe}
                  onClick={() => {
                    onTimeframeChange(entry);
                    setOpenMenu(null);
                  }}
                  className={cn(
                    "flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-[12.5px] transition-colors",
                    entry === timeframe ? "bg-accent font-medium" : "hover:bg-accent/60",
                  )}
                >
                  {entry}
                  {entry === timeframe ? (
                    <span className="size-1.5 rounded-full bg-foreground" aria-hidden />
                  ) : null}
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="relative">
          <button
            type="button"
            aria-haspopup="listbox"
            aria-expanded={openMenu === "model"}
            onClick={() => setOpenMenu((current) => (current === "model" ? null : "model"))}
            className={triggerClass}
          >
            {modelName(models, model)}
            <ChevronDown className="size-3 opacity-70" aria-hidden />
          </button>
          {openMenu === "model" ? (
            <div
              role="listbox"
              aria-label="AI model"
              className="absolute bottom-full left-0 z-30 mb-1.5 w-60 overflow-hidden rounded-xl border border-border bg-popover p-1 shadow-lg"
            >
              {models.map((entry) => (
                <button
                  key={entry.id}
                  type="button"
                  role="option"
                  aria-selected={entry.id === model}
                  onClick={() => {
                    onModelChange(entry.id);
                    setOpenMenu(null);
                  }}
                  className={cn(
                    "flex w-full flex-col items-start gap-0.5 rounded-lg px-2.5 py-2 text-left transition-colors",
                    entry.id === model ? "bg-accent" : "hover:bg-accent/60",
                  )}
                >
                  <span className="text-[13px] font-medium text-foreground">{entry.name}</span>
                  <span className="text-[11.5px] text-muted-foreground">
                    {entry.description}
                  </span>
                </button>
              ))}
            </div>
          ) : null}
        </div>

        <div className="relative">
          <button
            type="button"
            aria-haspopup="dialog"
            aria-expanded={openMenu === "phrases"}
            onClick={() => setOpenMenu((current) => (current === "phrases" ? null : "phrases"))}
            className={triggerClass}
          >
            <Lightbulb className="size-3 opacity-70" aria-hidden />
            Phrases
          </button>
          {openMenu === "phrases" ? (
            <div
              role="dialog"
              aria-label="Phrases"
              className="absolute bottom-full left-0 z-30 mb-1.5 w-72 overflow-hidden rounded-xl border border-border bg-popover p-1 shadow-lg"
            >
              <p className="px-2.5 pb-1 pt-1.5 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground/70">
                Tap a phrase, or select a word inside one
              </p>
              <ul className="max-h-64 overflow-y-auto">
                {SPEAKABLE_PHRASES.map((phrase) => (
                  <li key={phrase}>
                    <button
                      type="button"
                      onMouseUp={() => handlePhraseMouseUp(phrase)}
                      onClick={() => handlePhraseClick(phrase)}
                      className="w-full select-text rounded-lg px-2.5 py-2 text-left text-[12.5px] leading-relaxed text-foreground transition-colors hover:bg-accent/60"
                    >
                      {phrase}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </div>

      {/* Staged text on the left, Enter on the right. */}
      <div className="flex items-center gap-3 border-t border-border px-3 py-2.5">
        <div
          ref={textRef}
          role="status"
          aria-live="polite"
          className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap text-[14.5px] leading-6 [&::-webkit-scrollbar]:hidden"
        >
          {staged === null ? (
            <span className="text-muted-foreground">{COMPOSER_HINT}</span>
          ) : (
            <span>
              {staged.text.slice(0, revealed)}
              {/* Caret while the reveal is still running. */}
              {revealed < staged.text.length ? (
                <span className="ml-px inline-block h-[1em] w-px translate-y-[2px] bg-foreground" />
              ) : null}
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={handleSend}
          disabled={!canSend}
          aria-label="Send"
          title={busy ? "Waiting for the current analysis" : "Send"}
          className={cn(
            "flex size-9 shrink-0 items-center justify-center rounded-full transition-all",
            "focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-card",
            canSend
              ? "bg-primary text-primary-foreground hover:opacity-90"
              : "cursor-not-allowed bg-muted text-muted-foreground",
          )}
        >
          <CornerDownLeft className="size-4" aria-hidden />
        </button>
      </div>
    </div>
  );
}

/** Display name for a model slug, falling back to a neutral label if unrecognised. */
function modelName(models: ZenmuxModelOption[], model: ZenmuxModelId): string {
  return models.find((entry) => entry.id === model)?.name ?? "Model";
}
