import type { ReactNode } from "react";

import { cn } from "cn";

export interface Step {
  title: string;
  children?: ReactNode;
  /** One-line supporting detail rendered under the title, e.g. the endpoint called. */
  meta?: ReactNode;
}

export interface StepListProps {
  steps: Step[];
  /** `pad` renders 01, 02, 03 instead of a circular marker. */
  variant?: "dot" | "pad";
  className?: string;
}

/**
 * Numbered procedure.
 *
 * Rendered as an ordered list so the numbering is conveyed semantically, with the
 * markers drawn in CSS rather than as literal text. The gap between the marker and
 * the body is done with a padding on the list item, so a long step's paragraph stays
 * aligned under its title instead of under the number.
 */
export function StepList({ steps, variant = "dot", className }: StepListProps) {
  return (
    <ol className={cn(variant === "pad" ? "space-y-6" : "space-y-5", className)}>
      {steps.map((step, index) => (
        <li key={step.title} className="relative pl-9">
          {variant === "pad" ? (
            <span
              aria-hidden
              className="absolute left-0 top-0 font-mono text-xs tabular-nums text-muted-foreground/70"
            >
              {String(index + 1).padStart(2, "0")}
            </span>
          ) : (
            <span
              aria-hidden
              className="absolute left-0 top-0.5 grid size-5 place-items-center rounded-full border border-border bg-muted text-[11px] font-medium tabular-nums text-foreground"
            >
              {index + 1}
            </span>
          )}

          <p className={cn("font-medium text-foreground", variant === "pad" && "text-[15px]")}>
            {step.title}
          </p>

          {step.meta ? (
            <p className="mt-1 font-mono text-[13px] text-muted-foreground">{step.meta}</p>
          ) : null}

          {step.children ? (
            <div
              className={cn(
                "text-[15px] leading-7 text-muted-foreground",
                step.meta ? "mt-1.5" : "mt-1.5",
              )}
            >
              {step.children}
            </div>
          ) : null}
        </li>
      ))}
    </ol>
  );
}