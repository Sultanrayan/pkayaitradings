"use client";

/**
 * Draggable widget grid.
 *
 * Widgets can be reordered by dragging one onto another; the order is kept in
 * `localStorage` so it survives reloads. Implemented with pointer events and
 * FLIP-free CSS transforms — no external drag dependency.
 *
 * Adapted from the layout of 21st.dev/@carolinaraulino/components/draggable-widget-grid.
 */

import {
  useCallback,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { cn } from "cn";

/* ------------------------------------------------------------------ *
 * Persisted order store
 *
 * Kept at module scope so `useSyncExternalStore` can supply a stable server
 * snapshot (`null`) and adopt the stored order on the client afterwards.
 * ------------------------------------------------------------------ */

const cache = new Map<string, string[]>();
const listeners = new Set<() => void>();

function subscribeOrder(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function readOrder(key: string): string[] | null {
  const cached = cache.get(key);
  if (cached) return cached;
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as string[];
    if (!Array.isArray(parsed)) return null;
    cache.set(key, parsed);
    return parsed;
  } catch {
    return null;
  }
}

function writeOrder(key: string, order: string[]): void {
  cache.set(key, order);
  try {
    window.localStorage.setItem(key, JSON.stringify(order));
  } catch {
    /* storage is best-effort */
  }
  for (const listener of listeners) listener();
}

export interface WidgetSpec {
  id: string;
  /** Tailwind grid span, e.g. "lg:col-span-2". */
  span?: string;
  children: ReactNode;
}

export interface WidgetGridProps {
  widgets: WidgetSpec[];
  /** Storage key for the saved order. Pass `null` to disable persistence. */
  storageKey?: string | null;
  onReorder?: (order: string[]) => void;
  hint?: string;
  className?: string;
}

export function WidgetGrid({
  widgets,
  storageKey = "pkay.admin.widgets",
  onReorder,
  hint,
  className,
}: WidgetGridProps) {
  const defaultOrder = useMemo(() => widgets.map((w) => w.id), [widgets]);

  /**
   * The saved order is read through an external store rather than an effect:
   * the server snapshot is `null`, so the first client render matches SSR and
   * the persisted order is adopted on the following one.
   */
  const saved = useSyncExternalStore(
    subscribeOrder,
    () => (storageKey ? readOrder(storageKey) : null),
    () => null,
  );

  const order = useMemo(() => {
    if (!saved) return defaultOrder;
    const known = new Set(defaultOrder);
    const filtered = saved.filter((id) => known.has(id));
    // Append any widget added since the order was saved.
    const missing = defaultOrder.filter((id) => !filtered.includes(id));
    return [...filtered, ...missing];
  }, [saved, defaultOrder]);

  const [dragId, setDragId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  const persist = useCallback(
    (next: string[]) => {
      onReorder?.(next);
      if (storageKey) writeOrder(storageKey, next);
    },
    [onReorder, storageKey],
  );

  const move = useCallback(
    (fromId: string, toId: string) => {
      if (fromId === toId) return;
      const next = [...order];
      const from = next.indexOf(fromId);
      const to = next.indexOf(toId);
      if (from < 0 || to < 0) return;
      next.splice(to, 0, next.splice(from, 1)[0]);
      persist(next);
    },
    [order, persist],
  );

  const byId = useMemo(() => new Map(widgets.map((w) => [w.id, w])), [widgets]);
  const ordered = useMemo(
    () => order.map((id) => byId.get(id)).filter((w): w is WidgetSpec => Boolean(w)),
    [order, byId],
  );

  const reset = () => persist(widgets.map((w) => w.id));

  return (
    <div className={cn("space-y-2", className)}>
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {ordered.map((widget) => {
          const dragging = dragId === widget.id;
          const targeted = overId === widget.id && dragId !== widget.id;
          return (
            <div
              key={widget.id}
              draggable
              onDragStart={(event) => {
                setDragId(widget.id);
                event.dataTransfer.effectAllowed = "move";
                // Firefox requires data to be set for the drag to begin.
                event.dataTransfer.setData("text/plain", widget.id);
              }}
              onDragOver={(event) => {
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                if (overId !== widget.id) setOverId(widget.id);
              }}
              onDragLeave={() => setOverId((id) => (id === widget.id ? null : id))}
              onDrop={(event) => {
                event.preventDefault();
                const fromId = event.dataTransfer.getData("text/plain") || dragId;
                if (fromId) move(fromId, widget.id);
                setDragId(null);
                setOverId(null);
              }}
              onDragEnd={() => {
                setDragId(null);
                setOverId(null);
              }}
              className={cn(
                "cursor-grab rounded-lg border border-border bg-card/60 p-4 transition-[transform,opacity,border-color] active:cursor-grabbing",
                widget.span,
                dragging && "scale-[1.02] opacity-70 shadow-lg",
                targeted && "border-foreground/40",
              )}
            >
              {widget.children}
            </div>
          );
        })}
      </div>

      {storageKey ? (
        <button
          type="button"
          onClick={reset}
          className="rounded px-1.5 py-1 text-[11px] text-muted-foreground underline-offset-2 transition-colors hover:text-foreground hover:underline"
        >
          Reset layout
        </button>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ *
 * Widget primitives
 * ------------------------------------------------------------------ */

export function Widget({
  title,
  meta,
  value,
  unit,
  delta,
  children,
  className,
}: {
  title: string;
  meta?: ReactNode;
  /** Optional headline figure. Detail widgets supply only `children`. */
  value?: ReactNode;
  unit?: ReactNode;
  delta?: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex h-full flex-col", className)}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[10px] font-medium uppercase tracking-widest text-muted-foreground">
          {title}
        </span>
        {meta ? <span className="text-[10px] text-muted-foreground">{meta}</span> : null}
      </div>

      {value !== undefined ? (
        <div className="mt-2 flex items-baseline gap-2">
          <span className="tabular text-2xl font-semibold leading-none">{value}</span>
          {unit ? <span className="text-[11px] text-muted-foreground">{unit}</span> : null}
          {delta ? <span className="text-[11px]">{delta}</span> : null}
        </div>
      ) : null}

      {children ? <div className="mt-3 flex-1">{children}</div> : null}
    </div>
  );
}

/** Small status line with a coloured dot. */
export function WidgetStatus({
  tone,
  children,
}: {
  tone: "bull" | "bear" | "flat";
  children: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
      <span
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          tone === "bull" ? "bg-bull" : tone === "bear" ? "bg-bear" : "bg-flat",
        )}
      />
      <span className="truncate">{children}</span>
    </div>
  );
}

/** Compact horizontal meter used at the bottom of several widgets. */
export function WidgetMeter({
  segments,
  className,
}: {
  segments: Array<{ value: number; tone?: "bull" | "bear" | "flat" }>;
  className?: string;
}) {
  return (
    <div className={cn("flex h-4 items-end gap-0.5", className)} aria-hidden>
      {segments.map((segment, index) => (
        <span
          key={index}
          className={cn(
            "flex-1 rounded-[1px]",
            segment.tone === "bull"
              ? "bg-bull"
              : segment.tone === "bear"
                ? "bg-bear"
                : "bg-muted-foreground/35",
          )}
          style={{ height: `${Math.max(12, Math.min(100, segment.value * 100))}%` }}
        />
      ))}
    </div>
  );
}

/** Labelled progress row used inside detail widgets. */
export function WidgetRow({
  label,
  value,
  progress,
  className,
}: {
  label: string;
  value: ReactNode;
  /** 0..1 */
  progress?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-1 py-1", className)}>
      <div className="flex items-center justify-between gap-2 text-[11px]">
        <span className="truncate text-muted-foreground">{label}</span>
        <span className="tabular text-foreground">{value}</span>
      </div>
      {progress !== undefined ? (
        <div className="h-1 overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-foreground/70"
            style={{ width: `${Math.round(Math.min(Math.max(progress, 0), 1) * 100)}%` }}
          />
        </div>
      ) : null}
    </div>
  );
}
