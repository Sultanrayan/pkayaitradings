"use client";

import { cn } from "cn";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { toneBgClass, toneTextClass, type Tone } from "@/lib/format";

export function Panel({
  title,
  description,
  action,
  children,
  className,
  contentClassName,
}: {
  title: React.ReactNode;
  description?: React.ReactNode;
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <Card className={cn("bg-card ring-border", className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div className="space-y-1">
          <CardTitle className="text-sm font-medium tracking-wide">{title}</CardTitle>
          {description ? <CardDescription className="text-xs">{description}</CardDescription> : null}
        </div>
        {action}
      </CardHeader>
      <CardContent className={contentClassName}>{children}</CardContent>
    </Card>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: React.ReactNode;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone,
  className,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <Card className={cn("bg-card ring-border", className)}>
      <CardContent className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</span>
          {icon ? <span className="text-muted-foreground">{icon}</span> : null}
        </div>
        <div
          className={cn(
            "tabular text-2xl font-semibold leading-none",
            tone ? toneTextClass[tone] : "text-foreground",
          )}
        >
          {value}
        </div>
        {hint ? <div className="text-xs text-muted-foreground">{hint}</div> : null}
      </CardContent>
    </Card>
  );
}

export function Metric({
  label,
  value,
  sub,
  tone,
  className,
}: {
  label: string;
  value: React.ReactNode;
  sub?: React.ReactNode;
  tone?: Tone;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1", className)}>
      <div className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</div>
      <div className={cn("tabular text-sm font-medium", tone ? toneTextClass[tone] : "text-foreground")}>
        {value}
      </div>
      {sub ? <div className="text-xs text-muted-foreground">{sub}</div> : null}
    </div>
  );
}

export function TonePill({
  label,
  tone,
  className,
}: {
  label: string;
  tone: Tone;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1",
        toneBgClass[tone],
        className,
      )}
    >
      {label}
    </span>
  );
}

export function ConfidenceBar({
  value,
  tone = "flat",
  className,
}: {
  value: number;
  tone?: Tone;
  className?: string;
}) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className={cn("space-y-1", className)}>
      <Progress
        value={pct}
        className="h-1.5 bg-muted"
        indicatorClassName={tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : "bg-foreground"}
      />
      <div className="tabular text-right text-[11px] text-muted-foreground">{pct}%</div>
    </div>
  );
}

export function StatusDot({ tone, pulse = false }: { tone: Tone; pulse?: boolean }) {
  const color = tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : "bg-flat";
  return (
    <span className="relative inline-flex size-2">
      {pulse ? (
        <span className={cn("absolute inline-flex size-full animate-ping rounded-full opacity-60", color)} />
      ) : null}
      <span className={cn("relative inline-flex size-2 rounded-full", color)} />
    </span>
  );
}

export function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-24 items-center justify-center rounded-lg border border-dashed border-border px-4 py-6 text-center text-xs text-muted-foreground">
      {children}
    </div>
  );
}

export function LoadingRows({ rows = 4, className }: { rows?: number; className?: string }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }).map((_, index) => (
        <Skeleton key={index} className="h-10 w-full bg-muted" />
      ))}
    </div>
  );
}

export function ErrorNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-bear/30 bg-bear/5 px-4 py-3 text-sm text-bear">
      {children}
    </div>
  );
}

export function LegendBadge({
  label,
  variant,
}: {
  label: string;
  variant?: "outline" | "secondary" | "default";
}) {
  return (
    <Badge variant={variant ?? "outline"} className="tabular font-normal">
      {label}
    </Badge>
  );
}
