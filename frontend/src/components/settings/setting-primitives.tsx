"use client";

/**
 * Reusable settings primitives.
 *
 * Every settings block shares the same shape: an icon, a title, a short
 * description and a control grid. Rows are label-left / control-right on wide
 * screens and collapse to a single column on small screens.
 */

import type React from "react";
import { cn } from "cn";

import { Label } from "@/components/ui/label";
import { FlipToggle } from "@/components/ui/flip-button";

export function SettingsSection({
  icon,
  title,
  description,
  children,
  className,
  bodyClassName,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-border bg-card/40", className)}>
      <header className="flex items-start gap-2.5 border-b border-border px-3 py-2.5">
        {icon ? <span className="mt-0.5 text-muted-foreground">{icon}</span> : null}
        <div className="min-w-0 space-y-0.5">
          <h2 className="text-[10px] font-medium uppercase tracking-widest text-foreground">
            {title}
          </h2>
          {description ? (
            <p className="text-[11px] leading-relaxed text-muted-foreground">{description}</p>
          ) : null}
        </div>
      </header>
      <div className={cn("space-y-3 px-3 py-3", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Label on the left, control on the right; stacks on narrow screens. */
export function SettingRow({
  label,
  description,
  children,
  className,
  htmlFor,
}: {
  label: string;
  description?: string;
  children: React.ReactNode;
  className?: string;
  htmlFor?: string;
}) {
  return (
    <div
      className={cn(
        "flex flex-col gap-1.5 border-b border-border/60 pb-3 last:border-b-0 last:pb-0 sm:flex-row sm:items-center sm:justify-between sm:gap-4",
        className,
      )}
    >
      <div className="min-w-0 sm:py-0.5">
        <Label htmlFor={htmlFor} className="text-xs font-normal text-foreground">
          {label}
        </Label>
        {description ? (
          <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">
            {description}
          </p>
        ) : null}
      </div>
      <div className="flex shrink-0 items-center gap-2 sm:w-auto sm:justify-end">
        {children}
      </div>
    </div>
  );
}

/**
 * Toggle-only row. The control is a FlipToggle so the current state is spelled
 * out ("ON" / "OFF") instead of only being implied by a switch position.
 */
export function ToggleRow({
  label,
  description,
  checked,
  onCheckedChange,
  disabled,
  id,
}: {
  label: string;
  description?: string;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  disabled?: boolean;
  id?: string;
}) {
  return (
    <SettingRow label={label} description={description} htmlFor={id}>
      <FlipToggle
        checked={checked}
        onCheckedChange={onCheckedChange}
        disabled={disabled}
        ariaLabel={label}
      />
    </SettingRow>
  );
}

/** Two-column grid for paired selects / inputs. */
export function FieldGrid({ children }: { children: React.ReactNode }) {
  return <div className="grid gap-3 sm:grid-cols-2">{children}</div>;
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-[11px] text-muted-foreground">{label}</Label>
      {children}
    </div>
  );
}
