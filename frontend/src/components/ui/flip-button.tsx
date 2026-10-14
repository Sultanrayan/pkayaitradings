"use client";

/**
 * Flip Button
 *
 * Adapted from 21st.dev/@ln-dev7/components/flip-button (MIT).
 * Original hardcodes a blue/light palette and renders an inert label swap; this
 * version keeps the spring `rotateX` flip but drives colour from the project
 * design tokens, supports a real `onClick`, disabled/size states and keyboard +
 * screen-reader semantics.
 *
 * Use for two-state confirm actions ("Save Preferences" → "Saved").
 */

import { useState, type ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { cn } from "cn";

export interface FlipButtonProps {
  /** Label shown after the flip (the confirmed state). */
  text1: ReactNode;
  /** Label shown at rest. */
  text2: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  /** Controlled flipped state; omit for uncontrolled. */
  flipped?: boolean;
  defaultFlipped?: boolean;
  onFlippedChange?: (flipped: boolean) => void;
  size?: "sm" | "default";
  /** `solid` is the filled call-to-action look; `toggle` is a quieter switch-like pill. */
  variant?: "solid" | "toggle";
  className?: string;
  type?: "button" | "submit";
  title?: string;
  ariaLabel?: string;
}

/**
 * Palette lifted from the original component so the flip reads identically:
 * at rest a blue face with white text, flipped a near-white face with dark text.
 * The `toggle` variant keeps a quiet neutral "off" face, since a blue "off"
 * state would read as actionable.
 */
const PALETTE = {
  solid: {
    rest: { background: "#3b82f6", foreground: "#ffffff", border: "#3b82f6" },
    flipped: { background: "#f4f4f5", foreground: "#18181b", border: "#f4f4f5" },
  },
  toggle: {
    rest: { background: "#1a1a1a", foreground: "#8b8b8b", border: "#262626" },
    flipped: { background: "#f4f4f5", foreground: "#18181b", border: "#f4f4f5" },
  },
} as const;

export function FlipButton({
  text1,
  text2,
  onClick,
  disabled = false,
  flipped,
  defaultFlipped = false,
  onFlippedChange,
  size = "default",
  variant = "solid",
  className,
  type = "button",
  title,
  ariaLabel,
}: FlipButtonProps) {
  const reduceMotion = useReducedMotion();
  const [internal, setInternal] = useState(defaultFlipped);
  const isFlipped = flipped ?? internal;

  const setFlipped = (next: boolean) => {
    if (flipped === undefined) setInternal(next);
    onFlippedChange?.(next);
  };

  const handleClick = () => {
    if (disabled) return;
    setFlipped(!isFlipped);
    onClick?.();
  };

  const duration = reduceMotion ? 0 : 0.6;
  const face = (variant === "toggle" ? PALETTE.toggle : PALETTE.solid)[
    isFlipped ? "flipped" : "rest"
  ];

  return (
    <motion.button
      type={type}
      onClick={handleClick}
      disabled={disabled}
      title={title}
      aria-label={ariaLabel}
      aria-pressed={isFlipped}
      whileTap={reduceMotion || disabled ? undefined : { scale: 0.96 }}
      whileHover={reduceMotion || disabled ? undefined : { scale: 1.02 }}
      animate={{
        backgroundColor: face.background,
        color: face.foreground,
        borderColor: face.border,
      }}
      transition={{ duration, type: "spring" }}
      className={cn(
        "inline-flex w-full items-center justify-center overflow-hidden rounded-full border font-medium outline-none transition-[filter] duration-200 hover:brightness-110 focus-visible:ring-2 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
        size === "sm" ? "h-7 px-3 text-[11px]" : "h-10 px-6 text-sm",
        className,
      )}
      style={{ perspective: 800 }}
    >
      {/*
        The label is counter-rotated against the button's `rotateX`.

        A single `rotateX: 180` on the label leaves the text permanently upside down
        once the flip settles, which is what made the "ON" state read as reversed.
        Rotating the inner span by the opposite angle brings the net rotation back to
        0 at rest, so the label stays upright in both states while still reading as a
        physical flip mid-transition.
      */}
      <motion.span
        className="block w-full text-center"
        animate={{ rotateX: isFlipped ? 180 : 0 }}
        transition={{ duration, type: "spring" }}
      >
        <motion.span
          className="block w-full"
          animate={{ rotateX: isFlipped ? 180 : 0 }}
          transition={{ duration, type: "spring" }}
        >
          {isFlipped ? text1 : text2}
        </motion.span>
      </motion.span>
    </motion.button>
  );
}

export interface FlipToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  onLabel?: string;
  offLabel?: string;
  size?: "sm" | "default";
  className?: string;
  disabled?: boolean;
  ariaLabel?: string;
}

/**
 * Two-state toggle built on FlipButton.
 *
 * The state is spelled out in text rather than implied by a switch position,
 * so the current value is readable at a glance.
 */
export function FlipToggle({
  checked,
  onCheckedChange,
  onLabel = "ON",
  offLabel = "OFF",
  size = "sm",
  className,
  disabled,
  ariaLabel,
}: FlipToggleProps) {
  return (
    <FlipButton
      variant="toggle"
      size={size}
      flipped={checked}
      text1={onLabel}
      text2={offLabel}
      disabled={disabled}
      onClick={() => onCheckedChange(!checked)}
      ariaLabel={ariaLabel}
      className={cn("w-16 shrink-0", className)}
    />
  );
}

export default FlipButton;
