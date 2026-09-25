"use client";

import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import { cn } from "cn";

export interface StepperStep {
  title: string;
  description?: string;
}

type StepState = "complete" | "current" | "upcoming";

function StepDot({ index, state }: { index: number; state: StepState }) {
  return (
    <span
      className={cn(
        "relative z-10 flex size-8 items-center justify-center rounded-full border text-xs font-medium transition-colors",
        state === "complete" && "border-foreground bg-foreground text-background",
        state === "current" && "border-foreground bg-background text-foreground",
        state === "upcoming" && "border-border bg-background text-muted-foreground",
      )}
      aria-current={state === "current" ? "step" : undefined}
    >
      {state === "complete" ? <Check className="size-4" /> : index + 1}
    </span>
  );
}

/** Horizontal step-progress indicator. */
export function Stepper({
  steps,
  active,
  onSelect,
  className,
}: {
  steps: StepperStep[];
  active: number;
  onSelect?: (index: number) => void;
  className?: string;
}) {
  return (
    <ol className={cn("flex w-full", className)}>
      {steps.map((step, index) => {
        const state: StepState =
          index < active ? "complete" : index === active ? "current" : "upcoming";
        return (
          <li key={step.title} className="relative flex flex-1 flex-col items-center text-center">
            {index < steps.length - 1 ? (
              <span
                aria-hidden
                className={cn(
                  "absolute left-1/2 top-4 h-px w-full",
                  index < active ? "bg-foreground" : "bg-border",
                )}
              />
            ) : null}
            <StepDot index={index} state={state} />
            <button
              type="button"
              onClick={() => onSelect?.(index)}
              className="mt-3 w-full max-w-[12rem] space-y-1 focus-visible:outline-none"
            >
              <div
                className={cn(
                  "text-sm font-medium",
                  state === "upcoming" && "text-muted-foreground",
                )}
              >
                {step.title}
              </div>
              {step.description ? (
                <p className="text-xs text-muted-foreground">{step.description}</p>
              ) : null}
            </button>
          </li>
        );
      })}
    </ol>
  );
}

/** Stepper that advances through the steps on a timer; click to jump. */
export function PipelineStepper({ steps }: { steps: StepperStep[] }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setActive((value) => (value + 1) % steps.length), 2600);
    return () => clearInterval(timer);
  }, [steps.length]);

  return <Stepper steps={steps} active={active} onSelect={setActive} />;
}
