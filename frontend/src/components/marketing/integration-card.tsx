"use client";

import Image from "next/image";
import Link from "next/link";
import { useId } from "react";
import {
  ArrowRight,
  BrainCircuit,
  CandlestickChart,
  Database,
  Newspaper,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "cn";

/**
 * Integration network card.
 *
 * Visual style adapted from 21st.dev's shadcnspace "integration-card": an SVG
 * grid of floating tool chips connected by pulsing gradient lines to a central
 * brand mark. Text/copy here is Pkay-specific.
 */

type Node = {
  id: string;
  icon: LucideIcon;
  x: number;
  y: number;
  path: string;
  delay: number;
};

const NODES: Node[] = [
  { id: "data", icon: Database, x: 110, y: 90, path: "M 270 205 V 105 Q 270 90 255 90 H 110", delay: 0.1 },
  { id: "technical", icon: CandlestickChart, x: 360, y: 70, path: "M 294 205 V 85 Q 294 70 309 70 H 360", delay: 0.2 },
  { id: "news", icon: Newspaper, x: 160, y: 205, path: "M 250 205 H 160", delay: 0.3 },
  { id: "risk", icon: ShieldCheck, x: 480, y: 205, path: "M 314 205 H 480", delay: 0.4 },
  { id: "decision", icon: BrainCircuit, x: 282, y: 360, path: "M 282 205 V 360", delay: 0.6 },
  { id: "llm", icon: Sparkles, x: 460, y: 340, path: "M 314 215 V 325 Q 314 340 329 340 H 460", delay: 0.7 },
];

function ConnectorLine({ d, id }: { d: string; id: string }) {
  // Stable pseudo-random delay from the node id (avoid impure Math.random in render).
  const seed = id.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  const delay = (seed % 200) / 100;
  return (
    <>
      <path d={d} stroke="currentColor" strokeWidth={1} fill="none" className="text-border" />
      <motion.path
        d={d}
        stroke={`url(#${id})`}
        strokeWidth={2}
        fill="none"
        strokeDasharray="40 160"
        initial={{ strokeDashoffset: 200 }}
        animate={{ strokeDashoffset: -200 }}
        transition={{ duration: 4, repeat: Infinity, ease: "linear", delay }}
      />
      <defs>
        <linearGradient id={id} gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="transparent" />
          <stop offset="50%" stopColor="var(--color-primary)" stopOpacity={0.5} />
          <stop offset="100%" stopColor="transparent" />
        </linearGradient>
      </defs>
    </>
  );
}

export function IntegrationNetwork() {
  const uid = useId().replace(/[:]/g, "");
  return (
    <div className="relative h-full w-full">
      <svg
        className="pointer-events-none absolute inset-0 h-full w-full"
        viewBox="0 0 564 410"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        {NODES.map((node) => (
          <ConnectorLine key={node.id} d={node.path} id={`${uid}-${node.id}`} />
        ))}
      </svg>

      {/* Central brand mark */}
      <div className="absolute left-1/2 top-1/2 z-20 flex -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-lg border border-border bg-background p-0.5 shadow-md sm:rounded-2xl sm:p-2 sm:shadow-xl">
        <div className="rounded-lg border p-1 sm:rounded-xl sm:p-2.5">
          <Image
            src="/logo-pkay.jpg"
            alt="Pkay"
            width={35}
            height={35}
            className="size-6 rounded object-cover sm:size-10"
          />
        </div>
        <motion.div
          className="absolute inset-0 rounded-lg border-2 border-primary/10 sm:rounded-2xl"
          animate={{ scale: [1, 1.15, 1], opacity: [0.3, 0, 0.3] }}
          transition={{ duration: 3, repeat: Infinity }}
        />
      </div>

      {/* Floating tool chips */}
      {NODES.map((node) => {
        const Icon = node.icon;
        return (
          <motion.div
            key={node.id}
            initial={{ opacity: 0, scale: 0.8 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true }}
            transition={{ delay: node.delay }}
            style={{ left: `${(node.x / 564) * 100}%`, top: `${(node.y / 410) * 100}%` }}
            className="absolute z-10 flex h-9 w-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-lg border border-border bg-background text-foreground shadow-sm sm:h-12 sm:w-12 sm:rounded-xl"
          >
            <Icon className="size-4 text-foreground sm:size-6" strokeWidth={1.5} />
          </motion.div>
        );
      })}
    </div>
  );
}

export function VisualContainer({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        "relative flex aspect-[564/460] w-full items-center justify-center overflow-hidden rounded-none bg-muted p-8 sm:aspect-[564/410] dark:bg-muted/50",
        className,
      )}
    >
      <div
        className="absolute inset-0 opacity-20"
        style={{
          backgroundImage: "radial-gradient(circle, var(--color-foreground) 1px, transparent 1px)",
          backgroundSize: "32px 32px",
        }}
      />
      <div className="pointer-events-none absolute inset-0 bg-linear-to-b from-background/60 from-10% via-transparent to-90% to-background/60" />
      <div className="relative z-10 flex h-full w-full items-center justify-center">{children}</div>
    </div>
  );
}

const INTEGRATIONS = [
  { label: "Live market feed", detail: "Candles, quotes and calendar data." },
  { label: "Technical Analyst", detail: "Indicators and trend detection." },
  { label: "News Monitor", detail: "Headlines and event sentiment." },
  { label: "Risk Manager", detail: "Sizing, stops and veto checks." },
  { label: "Decision Maker", detail: "Final, risk-checked call." },
  { label: "LLM review", detail: "Reasoned narrative over every signal." },
];

export function IntegrationCard() {
  return (
    <div className="flex flex-col overflow-hidden rounded-2xl border border-border bg-card ring-0">
      <VisualContainer>
        <IntegrationNetwork />
      </VisualContainer>
      <div className="flex flex-col gap-6 p-6 sm:gap-8 sm:p-8">
        <div className="flex flex-col gap-2">
          <h3 className="text-xl font-medium tracking-tight sm:text-2xl">
            One pipeline, six connected parts
          </h3>
          <p className="text-base leading-relaxed text-muted-foreground">
            Every market signal flows through the same connected pipeline, from live data to a
            final, risk-checked decision.
          </p>
        </div>
        <div className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
          {INTEGRATIONS.map((item) => (
            <div key={item.label} className="flex items-start gap-2 text-sm">
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />
              <div>
                <div className="font-medium">{item.label}</div>
                <div className="text-xs text-muted-foreground">{item.detail}</div>
              </div>
            </div>
          ))}
        </div>
        <Link
          href="/dashboard"
          className="group inline-flex h-10 w-fit items-center gap-2 rounded-full bg-primary px-5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/80"
        >
          Open the console
          <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
        </Link>
      </div>
    </div>
  );
}