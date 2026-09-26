"use client";

import * as React from "react";
import {
  Bot,
  BrainCircuit,
  CornerDownLeft,
  Mic,
  Orbit,
  Paperclip,
  Sparkles,
  Square,
  Workflow,
  Zap,
  X,
  type LucideIcon,
} from "lucide-react";
import { cn } from "cn";

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface PromptMeta {
  model: string;
  effort: string;
  attachments: File[];
}

export interface AttachmentItem {
  id: string;
  file: File;
  url: string;
  name: string;
  width: number;
  height: number;
}

export interface PromptInputProps {
  onSubmit?: (message: string, meta: PromptMeta) => void;
  placeholder?: string;
  value?: string;
  onChange?: (value: string) => void;
  models?: string[];
  efforts?: string[];
  maxAttachments?: number;
  className?: string;
  disabled?: boolean;
}

const DEFAULT_MODELS = ["GPT 5.5", "Opus 4.8", "Gemini 3.5 Flash", "Composer 2.5", "GLM 5.2"];
const DEFAULT_EFFORTS = ["Low", "Medium", "Max Effort"];

const MODEL_ICON: Record<string, LucideIcon> = {
  "GPT 5.5": Sparkles,
  "Opus 4.8": Orbit,
  "Gemini 3.5 Flash": Workflow,
  "Composer 2.5": BrainCircuit,
  "GLM 5.2": Zap,
};

const EFFORT_BARS = {
  Low: 1,
  Medium: 2,
  "Max Effort": 3,
};

function EffortIcon({ level, className }: { level: number; className?: string }) {
  return (
    <span className={cn("flex items-end gap-[2px]", className)}>
      {[0, 1, 2].map((index) => (
        <span
          key={index}
          className={cn(
            "w-[2.5px] rounded-full bg-current transition-all duration-200",
            index < level ? "h-2 opacity-90" : "h-1 opacity-30",
          )}
        />
      ))}
    </span>
  );
}

function ModelIcon({ model, className }: { model: string; className?: string }) {
  const Icon = MODEL_ICON[model] ?? Bot;
  return <Icon className={className} />;
}

function EffortText({ effort }: { effort: string }) {
  if (effort === "Low") return "Low";
  if (effort === "Medium") return "Med";
  return "Max";
}

/* ------------------------------------------------------------------ */
/* Attachment preview sheet                                            */
/* ------------------------------------------------------------------ */

function AttachmentPreview({
  item,
  onClose,
}: {
  item: AttachmentItem | null;
  onClose: () => void;
}) {
  return (
    <div
      className={cn(
        "fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm transition-opacity",
        item ? "opacity-100" : "pointer-events-none opacity-0",
      )}
    >
      <button
        type="button"
        aria-label="Enter attachment view"
        onClick={onClose}
        className="hidden"
      />
      <div className="relative max-h-full max-w-2xl overflow-hidden rounded-2xl border border-border bg-card shadow-xl">
        {item ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={item.url} alt={item.name} className="max-h-[70vh] w-auto object-contain" />
        ) : null}
        <button
          type="button"
          onClick={onClose}
          aria-label="Close preview"
          className="absolute right-3 top-3 flex size-8 items-center justify-center rounded-full bg-background/80 text-foreground shadow ring-1 ring-border transition-colors hover:bg-accent"
        >
          <X className="size-4" />
        </button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* PromptInput                                                         */
/* ------------------------------------------------------------------ */

const EASE = "cubic-bezier(0.175, 0.885, 0.32, 1.275)";

/**
 * AI chat input, adapted from the 21st.dev `ai-chat-input` component. A
 * collapsed pill expands into a full prompt card with model/effort selectors,
 * image attachments and optional voice input.
 */
export function PromptInput({
  onSubmit,
  placeholder = "Ask anything...",
  value,
  onChange,
  models = DEFAULT_MODELS,
  efforts = DEFAULT_EFFORTS,
  maxAttachments = 6,
  className,
  disabled = false,
}: PromptInputProps) {
  const textareaRef = React.useRef<HTMLTextAreaElement | null>(null);
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const fileRef = React.useRef<HTMLInputElement | null>(null);
  const topFadeRef = React.useRef<HTMLDivElement | null>(null);
  const bottomFadeRef = React.useRef<HTMLDivElement | null>(null);
  const modelMenuRef = React.useRef<HTMLDivElement | null>(null);

  const [focused, setFocused] = React.useState(false);
  const [internalValue, setInternalValue] = React.useState("");
  const [model, setModel] = React.useState(models[0]);
  const [effortIndex, setEffortIndex] = React.useState(1);
  const [attachments, setAttachments] = React.useState<AttachmentItem[]>([]);
  const [preview, setPreview] = React.useState<AttachmentItem | null>(null);
  const [modelOpen, setModelOpen] = React.useState(false);
  const [recording, setRecording] = React.useState(false);
  const [levels, setLevels] = React.useState<number[]>(new Array(5).fill(0));
  const [bubbleHeight, setBubbleHeight] = React.useState(68);
  const [scrollable, setScrollable] = React.useState(false);

  const controlled = value !== undefined;
  const text = controlled ? value : internalValue;
  const hasText = text.trim() !== "";
  const hasAttachments = attachments.length > 0;
  const canSubmit = hasText || hasAttachments;
  // Bubble height derived from the measured textarea height.
  const height = Math.max(116, bubbleHeight + 48);

  const timers = React.useRef<ReturnType<typeof setInterval>[]>([]);
  const streamTimer = React.useRef<ReturnType<typeof setInterval> | null>(null);

  const setText = React.useCallback(
    (next: string | ((previous: string) => string)) => {
      const resolved = typeof next === "function" ? next(controlled ? (value ?? "") : internalValue) : next;
      if (controlled) {
        onChange?.(resolved);
      } else {
        setInternalValue(resolved);
      }
    },
    [controlled, onChange, value, internalValue],
  );

  const stopRecording = React.useCallback(() => {
    setRecording(false);
    setLevels(new Array(5).fill(0));
    if (streamTimer.current) {
      clearInterval(streamTimer.current);
      streamTimer.current = null;
    }
  }, []);

  const simulateVoice = React.useCallback(() => {
    // Fallback for browsers without speech APIs: type out a demo sentence.
    const words = placeholder.split(" ").filter(Boolean);
    let index = 0;
    setText("");
    streamTimer.current = setInterval(() => {
      if (index < words.length) {
        setText((previous) => (previous ? `${previous} ${words[index]}` : words[index]));
        index += 1;
      } else {
        stopRecording();
      }
    }, 280);
  }, [placeholder, setText, stopRecording]);

  const startVoice = React.useCallback(() => {
    setRecording(true);
    // SpeechRecognition is not in the standard lib types; use a guarded cast.
    type SpeechRecognitionCtor = new () => {
      continuous: boolean;
      interimResults: boolean;
      start: () => void;
      stop: () => void;
      onresult: (event: { resultIndex: number; results: ArrayLike<{ isFinal: boolean; 0: { transcript: string } }> }) => void;
      onerror: (error: unknown) => void;
      onend: () => void;
    };
    const Ctor = (
      window as unknown as {
        SpeechRecognition?: SpeechRecognitionCtor;
        webkitSpeechRecognition?: SpeechRecognitionCtor;
      }
    ).SpeechRecognition;

    if (!Ctor) {
      simulateVoice();
      return;
    }
    const recognition = new Ctor();
    recognition.continuous = true;
    recognition.interimResults = true;
    let transcript = "";
    recognition.onresult = (event) => {
      let finalText = "";
      let interim = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        if (result.isFinal) finalText += result[0].transcript;
        else interim += result[0].transcript;
      }
      if (finalText) transcript += (transcript ? " " : "") + finalText;
      setText((transcript + (interim ? ` ${interim}` : "")).trim());
    };
    recognition.onerror = () => stopRecording();
    recognition.onend = () => stopRecording();
    recognition.start();
  }, [setText, simulateVoice, stopRecording]);

  const toggleVoice = React.useCallback(() => {
    if (recording) {
      stopRecording();
    } else {
      startVoice();
    }
  }, [recording, startVoice, stopRecording]);

  const handleSubmit = React.useCallback(() => {
    if (!canSubmit || recording) return;
    onSubmit?.(text.trim(), {
      model,
      effort: efforts[effortIndex],
      attachments: attachments.map((item) => item.file),
    });
    setText("");
    setAttachments((previous) => {
      previous.forEach((item) => URL.revokeObjectURL(item.url));
      return [];
    });
  }, [canSubmit, recording, text, model, effortIndex, efforts, attachments, onSubmit, setText]);

  const cycleEffort = React.useCallback(() => {
    setEffortIndex((index) => (index + 1) % efforts.length);
  }, [efforts.length]);

  const openFileChooser = React.useCallback(() => {
    fileRef.current?.click();
  }, []);

  const addFiles = React.useCallback((files: FileList | null) => {
    if (!files) return;
    const images = Array.from(files).filter((file) => file.type.startsWith("image/"));
    if (images.length === 0) return;
    setFocused(true);
    const room = Math.max(0, maxAttachments - attachments.length);
    setAttachments((previous) => {
      const remaining = previous.slice(0, maxAttachments);
      const next = [...remaining];
      for (const file of images.slice(0, room)) {
        const url = URL.createObjectURL(file);
        const id = `${file.name}-${file.lastModified}-${Math.random().toString(36).slice(2, 8)}`;
        next.push({ id, file, url, name: file.name, width: 800, height: 600 });
      }
      return next;
    });
  }, [maxAttachments, attachments.length]);

  const removeAttachment = React.useCallback((id: string) => {
    setAttachments((previous) => {
      const target = previous.find((item) => item.id === id);
      if (target) URL.revokeObjectURL(target.url);
      return previous.filter((item) => item.id !== id);
    });
  }, []);

  const updateTextareaHeight = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    const scrollHeight = el.scrollHeight;
    const nextHeight = Math.max(68, Math.min(scrollHeight, 160));
    el.style.height = `${nextHeight}px`;
    setBubbleHeight(nextHeight);
    setScrollable(scrollHeight > 160);
  }, []);

  // Adjust the surrounding bubble height to match the growing textarea.
  // The state update is scheduled via rAF so it is not synchronous in the effect.
  React.useEffect(() => {
    const frame = window.requestAnimationFrame(updateTextareaHeight);
    return () => window.cancelAnimationFrame(frame);
  }, [text, updateTextareaHeight]);

  const updateFades = React.useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    if (topFadeRef.current) {
      topFadeRef.current.style.opacity = String(Math.min(el.scrollTop / 20, 1));
    }
    if (bottomFadeRef.current) {
      const distance = el.scrollHeight - el.clientHeight - el.scrollTop;
      bottomFadeRef.current.style.opacity = String(Math.min(Math.max(distance - 16, 0) / 10, 1));
    }
  }, []);

  const collapse = React.useCallback(() => {
    setFocused(false);
    setModelOpen(false);
  }, []);

  const handleBlur = React.useCallback(
    (event: React.FocusEvent<HTMLDivElement>) => {
      if (modelMenuRef.current?.contains(event.relatedTarget as Node)) return;
      if (!hasText && !hasAttachments && !recording) collapse();
    },
    [hasText, hasAttachments, recording, collapse],
  );

  // Close the model menu on outside click.
  React.useEffect(() => {
    if (!modelOpen) return;
    const onDown = (event: MouseEvent) => {
      if (modelMenuRef.current && !modelMenuRef.current.contains(event.target as Node)) {
        setModelOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [modelOpen]);

  // Clean up timers + object URLs on unmount.
  React.useEffect(
    () => () => {
      timers.current.forEach(clearInterval);
      if (streamTimer.current) clearInterval(streamTimer.current);
    },
    [],
  );

  const actionLabel = recording
    ? "Stop recording"
    : canSubmit
      ? "Send prompt"
      : "Use voice input";

  return (
    <>
      <div
        ref={containerRef}
        onBlur={handleBlur}
        className={cn("relative flex w-full flex-col", className)}
        style={{
          maxWidth: focused ? 480 : 320,
          transition: focused
            ? "max-width 0.15s ease-out"
            : "max-width 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)",
        }}
      >
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          tabIndex={-1}
          onChange={(event) => {
            addFiles(event.target.files);
            event.target.value = "";
          }}
          className="hidden"
          aria-hidden="true"
        />

        {/* Attachment tray */}
        <div
          aria-hidden={!hasAttachments}
          style={{
            height: hasAttachments && focused ? 68 : 0,
            transition: focused
              ? "height 0.15s ease-out"
              : "height 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)",
          }}
          className="relative w-full overflow-hidden"
        >
          <div
            style={{
              position: "absolute",
              bottom: -8,
              left: 20,
              right: 20,
              height: 68,
              transform: hasAttachments && focused ? "translateY(0)" : "translateY(100%)",
              opacity: hasAttachments && focused ? 1 : 0,
              transition: focused
                ? "transform 0.15s ease-out, opacity 0.15s ease-out"
                : "transform 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275), opacity 0.3s ease-out",
            }}
            className="flex items-start gap-2 overflow-x-auto rounded-t-2xl border border-b-0 border-border bg-muted px-2 pb-1 pt-2"
          >
            {attachments.map((item) => (
              <div
                key={item.id}
                className="group relative size-12 shrink-0 overflow-hidden rounded-lg"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={item.url}
                  alt={item.name}
                  onClick={() => setPreview(item)}
                  className="h-full w-full cursor-zoom-in object-cover"
                />
                <button
                  type="button"
                  aria-label="Remove attachment"
                  onClick={() => removeAttachment(item.id)}
                  className="absolute right-0.5 top-0.5 flex size-4 items-center justify-center rounded-full bg-black/70 text-white opacity-0 transition-opacity hover:opacity-100 focus-visible:opacity-100"
                >
                  <X className="size-2.5" />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* The prompt bubble */}
        <div
          onMouseDown={(event) => {
            if (!focused && event.target === textareaRef.current) return;
            if (!focused) setFocused(true);
          }}
          style={{
            borderRadius: 24,
            height: focused ? height : 48,
            transition: focused
              ? undefined
              : `all 0.4s ${EASE}`,
            overflow: focused ? "visible" : "hidden",
          }}
          className={cn(
            "relative w-full border border-border bg-card shadow-sm focus-within:border-ring/40 focus-within:ring-1 focus-within:ring-ring/20 hover:border-border/80",
            focused ? "cursor-text" : "cursor-default",
          )}
        >
          {/* Growing textarea */}
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(event) => setText(event.target.value)}
            onScroll={updateFades}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                handleSubmit();
              }
              if (event.key === "Escape" && !hasText && !hasAttachments) collapse();
            }}
            placeholder={placeholder}
            aria-label="Prompt"
            disabled={disabled || recording}
            style={{
              transition: focused
                ? "height 0.15s ease-out"
                : "opacity 0.3s ease-out, transform 0.3s ease-out, height 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275)",
            }}
            className={cn(
              "absolute inset-x-0 top-0 z-[1] w-full resize-none bg-transparent py-3.5 pl-4 pr-12 text-sm leading-[22px] text-foreground outline-none placeholder:font-medium placeholder:text-muted-foreground/80",
              focused
                ? "translate-y-0 scale-100 opacity-100"
                : "pointer-events-none -translate-y-1 scale-95 opacity-0",
              scrollable ? "overflow-y-auto" : "overflow-y-hidden",
              (disabled || recording) && "pointer-events-none",
            )}
          />

          {/* Scroll fade gradients */}
          <div
            ref={topFadeRef}
            className="pointer-events-none absolute left-4 right-12 top-0 z-[2] h-8 bg-gradient-to-b from-card via-card/90 to-transparent"
          />
          <div
            ref={bottomFadeRef}
            style={{ opacity: 0, top: `${bubbleHeight - 32}px` }}
            className="pointer-events-none absolute left-4 right-12 z-[2] h-8 bg-gradient-to-t from-card via-card/90 to-transparent"
          />

          {/* Collapsed placeholder label */}
          <button
            type="button"
            onClick={() => setFocused(true)}
            style={{ transition: focused ? "none" : `all 0.4s ${EASE}` }}
            aria-label="Open prompt input"
            className={cn(
              "absolute inset-x-0 top-0 z-[1] cursor-text py-[15px] pl-4 pr-12 text-left text-sm font-medium leading-[17px] text-muted-foreground/80 outline-none",
              focused
                ? "pointer-events-none translate-y-1 scale-105 opacity-0"
                : "translate-y-0 scale-100 opacity-100",
            )}
          >
            {placeholder}
          </button>

          {/* Controls row */}
          <div
            className={cn(
              "absolute bottom-2 left-3 right-12 z-[10] flex items-center gap-0 transition-all duration-300 ease-[cubic-bezier(0.175,0.885,0.32,1.275)]",
              focused
                ? "pointer-events-auto translate-y-0 opacity-100 blur-0"
                : "pointer-events-none translate-y-2 opacity-0 blur-sm",
            )}
          >
            {/* Model selector */}
            <div className="relative">
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={(event) => {
                  event.stopPropagation();
                  setModelOpen((open) => !open);
                }}
                aria-label={`Select model. Current: ${model}`}
                className={cn(
                  "group flex items-center gap-1 rounded-full px-2 py-1 text-foreground/50 outline-none transition-all duration-200 hover:bg-accent/60 hover:text-foreground",
                  modelOpen && "bg-accent/60 text-foreground",
                )}
              >
                <ModelIcon model={model} className="size-3.5 opacity-70 transition-opacity group-hover:opacity-100" />
                <span className="select-none text-xs font-semibold">{model}</span>
              </button>

              <div
                ref={modelMenuRef}
                onMouseLeave={() => setModelOpen(false)}
                className={cn(
                  "absolute bottom-full left-0 z-50 mb-2.5 w-44 flex-col gap-0.5 rounded-2xl border border-border bg-card/95 p-1 shadow-xl backdrop-blur-md transition-all duration-200",
                  modelOpen
                    ? "pointer-events-auto flex translate-y-0 scale-100 opacity-100"
                    : "pointer-events-none hidden translate-y-3 scale-95 opacity-0",
                )}
              >
                {models.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onMouseDown={(event) => event.preventDefault()}
                    onClick={(event) => {
                      event.stopPropagation();
                      setModel(item);
                      setModelOpen(false);
                    }}
                    className={cn(
                      "flex h-8 w-full items-center justify-between rounded-xl px-2.5 py-1.5 text-left text-xs font-medium text-foreground/80 outline-none transition-colors active:scale-[0.98]",
                      model === item && "bg-accent",
                    )}
                  >
                    <span className="flex items-center gap-2">
                      <ModelIcon model={item} className="size-3.5 opacity-85" />
                      {item}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* Effort cycle */}
            <button
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={cycleEffort}
              className="group flex items-center gap-1 rounded-full px-2 py-1 text-foreground/50 outline-none transition-all duration-200 hover:bg-accent/60 hover:text-foreground"
            >
              <EffortIcon level={EFFORT_BARS[efforts[effortIndex] as keyof typeof EFFORT_BARS] ?? 1} className="size-3.5 opacity-70" />
              <span className="select-none text-xs font-semibold">
                <EffortText effort={efforts[effortIndex]} />
              </span>
            </button>

            {/* Attach */}
            <button
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={openFileChooser}
              disabled={attachments.length >= maxAttachments}
              aria-label="Attach image"
              className="ml-auto flex size-7 items-center justify-center rounded-full text-foreground/50 outline-none transition-all duration-200 hover:bg-accent/60 hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
            >
              <Paperclip className="size-3.5" />
            </button>
            {attachments.length > 0 ? (
              <span className="ml-1 tabular text-[10px] text-muted-foreground">
                {attachments.length}/{maxAttachments}
              </span>
            ) : null}
          </div>

          {/* Voice level bars */}
          <div
            className={cn(
              "absolute bottom-2 right-12 z-[10] flex h-8 items-center justify-end gap-[3px] transition-all duration-200",
              recording ? "w-16 translate-x-0 opacity-100" : "pointer-events-none w-0 translate-x-4 opacity-0",
            )}
          >
            {levels.map((level, index) => (
              <div
                key={index}
                className="w-1 rounded-full bg-primary transition-[height] duration-75"
                style={{ height: `${Math.max(4, level * 24)}px` }}
              />
            ))}
          </div>

          {/* Send / Stop / Mic */}
          <button
            type="button"
            aria-label={actionLabel}
            onClick={toggleVoice}
            onMouseDown={(event) => {
              event.preventDefault();
              event.stopPropagation();
            }}
            style={{ borderRadius: 9999 }}
            className="absolute bottom-2 right-2 z-[10] flex h-8 w-8 items-center justify-center bg-primary text-primary-foreground outline-none transition-all duration-300 hover:opacity-90 focus-visible:ring-2 focus-visible:ring-ring"
          >
            <span className="relative flex h-full w-full items-center justify-center">
              {canSubmit && !recording ? (
                <CornerDownLeft
                  className={cn(
                    "absolute inset-0 m-auto size-3.5 transition-all duration-300",
                    canSubmit && !recording
                      ? "rotate-0 scale-100 opacity-100 blur-none"
                      : "pointer-events-none rotate-45 scale-50 opacity-0 blur-[1px]",
                  )}
                />
              ) : recording ? (
                <Square
                  className={cn(
                    "absolute inset-0 m-auto size-3.5 transition-all duration-300",
                    recording ? "-rotate-45 scale-100 opacity-100 blur-none" : "pointer-events-none rotate-0 scale-50 opacity-0 blur-[1px]",
                  )}
                />
              ) : (
                <Mic
                  className={cn(
                    "absolute inset-0 m-auto size-3.5 transition-all duration-300",
                    !canSubmit && !recording
                      ? "rotate-0 scale-100 opacity-100 blur-none"
                      : "pointer-events-none rotate-45 scale-50 opacity-0 blur-[1px]",
                  )}
                />
              )}
            </span>
          </button>
        </div>
      </div>

      <AttachmentPreview item={preview} onClose={() => setPreview(null)} />
    </>
  );
}