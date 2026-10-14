"use client";

import { useRef, useState } from "react";
import { cn } from "cn";

const COMPLETE_THRESHOLD = 0.85;
const THUMB_SIZE = 28;

/**
 * Swipe-to-confirm trigger for signal generation.
 *
 * Drag the thumb forward (mouse or touch): a color bar pinned to the bottom
 * of the track fills gold → green with the swipe. Releasing before the
 * threshold snaps the thumb back; swiping past it flashes full and confirms.
 * Keyboard: focus + Enter/Space confirms.
 */
export function SwipeGenerateButton({
  onConfirm,
  disabled,
  label = "Generate Signal",
  fluid = false,
}: {
  onConfirm: () => void;
  disabled?: boolean;
  label?: string;
  /** Full-width track (e.g. inside dialogs) instead of the fixed toolbar size. */
  fluid?: boolean;
}) {
  const trackRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ startX: number; max: number } | null>(null);
  const progressRef = useRef(0);
  const [x, setX] = useState(0);
  const [progress, setProgress] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [flash, setFlash] = useState(false);

  const maxTravel = () => {
    const track = trackRef.current;
    if (!track) return 160;
    return Math.max(80, track.clientWidth - THUMB_SIZE - 4);
  };

  const confirm = () => {
    setFlash(true);
    setX(maxTravel());
    setProgress(1);
    window.setTimeout(() => {
      setFlash(false);
      setX(0);
      setProgress(0);
      progressRef.current = 0;
      onConfirm();
    }, 240);
  };

  const onPointerDown = (event: React.PointerEvent<HTMLDivElement>) => {
    if (disabled || flash) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    dragRef.current = { startX: event.clientX, max: maxTravel() };
    progressRef.current = 0;
    setDragging(true);
  };

  const onPointerMove = (event: React.PointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const dx = Math.min(Math.max(event.clientX - drag.startX, 0), drag.max);
    const next = drag.max === 0 ? 0 : dx / drag.max;
    progressRef.current = next;
    setX(dx);
    setProgress(next);
  };

  const endDrag = () => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setDragging(false);
    if (progressRef.current >= COMPLETE_THRESHOLD) {
      confirm();
    } else {
      progressRef.current = 0;
      setX(0);
      setProgress(0);
    }
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (disabled || flash) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      confirm();
    }
  };

  return (
    <div
      ref={trackRef}
      role="button"
      tabIndex={disabled ? -1 : 0}
      aria-label={`${label} — swipe forward or press Enter to confirm`}
      aria-disabled={disabled}
      onKeyDown={onKeyDown}
      className={cn(
        "relative h-9 select-none overflow-hidden rounded-lg border border-border bg-card outline-none transition-opacity focus-visible:ring-2 focus-visible:ring-ring",
        fluid ? "w-full" : "w-44 sm:w-48",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-ew-resize",
      )}
    >
      {/* Label fades as the swipe advances */}
      <span
        className="pointer-events-none absolute inset-0 flex items-center justify-center pl-6 text-xs font-medium"
        style={{ opacity: 1 - progress * 0.9 }}
      >
        {label}
      </span>

      {/* Thumb */}
      <div
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
        className={cn(
          "absolute left-0.5 top-1/2 h-7 w-7 rounded-md border border-border bg-accent touch-none",
          flash ? "bg-bull/30" : undefined,
        )}
        style={{
          width: THUMB_SIZE,
          transform: `translate(${x}px, -50%)`,
          transition: dragging || flash ? "none" : "transform 200ms ease-out, background-color 200ms",
          boxShadow: progress > 0 ? `0 0 ${Math.round(4 + progress * 10)}px rgba(34, 197, 94, ${0.25 + progress * 0.45})` : undefined,
        }}
      >
        {/* Grip ridges (texture, not an icon) */}
        <span className="absolute inset-0 flex items-center justify-center gap-[3px]">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-3 w-px rounded bg-muted-foreground/50" />
          ))}
        </span>
      </div>

      {/* Bottom color animation: fills + shifts gold → green with the swipe */}
      <div className="pointer-events-none absolute inset-x-2 bottom-1 h-[3px] overflow-hidden rounded-full bg-muted/60">
        <div
          className="h-full rounded-full"
          style={{
            width: flash ? "100%" : `${progress * 100}%`,
            background: "linear-gradient(90deg, var(--gold) 0%, var(--bull) 100%)",
            boxShadow: progress > 0 || flash ? "0 0 8px rgba(34, 197, 94, 0.8)" : undefined,
            transition: dragging ? "none" : "width 200ms ease-out",
            opacity: flash ? 1 : 0.35 + progress * 0.65,
          }}
        />
      </div>
    </div>
  );
}
