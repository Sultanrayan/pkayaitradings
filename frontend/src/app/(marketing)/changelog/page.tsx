import { Rocket } from "lucide-react";

import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";

export const metadata = { title: "Change log — Pkay TDAI" };

interface Change {
  version: string;
  date: string;
  tag: "release" | "feature" | "fix";
  summary: string;
  items: string[];
}

const CHANGES: Change[] = [
  {
    version: "v2.1",
    date: "2026-09-21",
    tag: "feature",
    summary: "Plans, payments and the intelligence layer.",
    items: [
      "Added plan verification and KHQR payments via Khpay (Free / Pro / Ultra).",
      "Added About, Change log, Status, Contact, Privacy and Terms pages.",
      "Added order-flow analysis, episodic memory and a Gaussian HMM regime detector.",
      "Added an LLM chain-of-thought review layer with a bounded confidence adjustment.",
      "Automated plan deactivation at the end of the billing period.",
    ],
  },
  {
    version: "v2.0",
    date: "2026-09-20",
    tag: "release",
    summary: "A resilient, self-adaptive decision core.",
    items: [
      "Added Pydantic output validation and per-agent circuit breakers.",
      "Added cross-agent consistency checks and non-linear (geometric) aggregation.",
      "Multi-timeframe confirmation now requires 3/4 alignment for a strong signal.",
      "Google-only sign-in and a robust server-side session cookie.",
    ],
  },
  {
    version: "v1.0",
    date: "2026-09-19",
    tag: "release",
    summary: "The first public release.",
    items: [
      "Initial multi-agent analysis pipeline (Technical, News, Risk, Decision).",
      "Live XAUUSD and BTCUSD feed with WebSocket streaming.",
      "Console with charts, signals, agents, risk and performance views.",
    ],
  },
];

const TAG_STYLES: Record<Change["tag"], string> = {
  release: "bg-bull/15 text-bull",
  feature: "bg-[#003AF9]/15 text-[#003AF9]",
  fix: "bg-amber-500/15 text-amber-500",
};

export default function ChangelogPage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-6 py-16">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          <Rocket className="size-3.5" />
          Change log
        </div>
        <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight">What&apos;s new</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Every release and notable change in Pkay TDAI, newest first.
        </p>

        <div className="mt-12 space-y-0">
          {CHANGES.map((change) => (
            <div key={change.version} className="relative flex gap-5 pb-10 last:pb-0">
              {/* Timeline rail */}
              <div className="flex flex-col items-center">
                <span
                  className={`rounded-full px-2.5 py-1 font-mono text-[11px] font-semibold ${TAG_STYLES[change.tag]}`}
                >
                  {change.version}
                </span>
                {change !== CHANGES[CHANGES.length - 1] ? (
                  <span className="mt-2 w-px flex-1 bg-border" />
                ) : null}
              </div>

              {/* Entry body */}
              <div className="-mt-1 flex-1 rounded-2xl border border-border bg-card/60 p-5">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">{change.date}</span>
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                    {change.tag}
                  </span>
                </div>
                <p className="mt-2 text-sm font-medium text-foreground">{change.summary}</p>
                <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm text-muted-foreground">
                  {change.items.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          ))}
        </div>
      </main>

      <FooterSection />
    </div>
  );
}