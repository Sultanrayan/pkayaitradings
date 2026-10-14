import Link from "next/link";

import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";
import { AGENTS } from "@/lib/constants";

export const metadata = {
  title: "Learn more - Pkay TDAI",
  description:
    "How Pkay TDAI turns live market data into a risk-gated decision, and what each of the four agents contributes.",
};

/**
 * Destination for the Features section's "Learn more" link.
 *
 * Content is architecture, not performance: what each stage of the pipeline does and
 * where the limits sit. No accuracy figures, latency claims or win rates appear here,
 * because none are established anywhere in the codebase.
 */
const STAGES = [
  {
    title: "1. Read the market",
    body: "Live XAU/USD and BTC/USD ticks, M5 candles, the economic calendar and news headlines are collected into a single feed. Every later stage reads from that one snapshot, so the agents cannot disagree about what the market looked like.",
  },
  {
    title: "2. Four agents analyse it independently",
    body: "The Technical Analyst studies price and indicators. The News Monitor scores events and sentiment. Neither sees the other's output, which is what makes their agreement meaningful rather than circular.",
  },
  {
    title: "3. Risk checks the position",
    body: "The Risk Manager sizes the position, derives the stop, applies VaR and drawdown limits, and holds a veto. It can block a trade outright — that veto is not advisory, and a drawdown breach is the one condition that stops the cycle on its own.",
  },
  {
    title: "4. The decision is recorded",
    body: "The Decision Maker reconciles the signals into one call, and the reasoning is stored alongside the bars and headlines that produced it. Any signal can be traced back to its inputs after the fact.",
  },
];

export default function LearnMorePage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-6 py-16">
        <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          Learn more
        </p>
        <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight">
          How a decision is made
        </h1>
        <p className="mt-4 text-sm leading-relaxed text-muted-foreground">
          Pkay TDAI runs one pipeline per symbol. The stages below run in order, and
          each one can refuse to hand work to the next.
        </p>

        <ol className="mt-12 space-y-8">
          {STAGES.map((stage) => (
            <li key={stage.title} className="border-l border-border pl-5">
              <h2 className="text-base font-medium">{stage.title}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                {stage.body}
              </p>
            </li>
          ))}
        </ol>

        <h2 className="mt-16 font-serif text-2xl font-medium tracking-tight">
          The four agents
        </h2>
        <ul className="mt-5 space-y-3">
          {AGENTS.map((agent) => (
            <li
              key={agent.id}
              className="rounded-xl border border-border bg-card px-4 py-3"
            >
              <p className="text-sm font-medium">{agent.name}</p>
              <p className="mt-1 text-sm text-muted-foreground">{agent.description}</p>
            </li>
          ))}
        </ul>

        <h2 className="mt-16 font-serif text-2xl font-medium tracking-tight">
          Where the limits sit
        </h2>
        <ul className="mt-5 space-y-3 text-sm leading-relaxed text-muted-foreground">
          <li>
            <strong className="font-medium text-foreground">Risk can veto.</strong> The
            Risk Manager blocks a trade that breaches its limits regardless of how
            strong the analysis was.
          </li>
          <li>
            <strong className="font-medium text-foreground">Drawdown stops the
            cycle.</strong> Past the configured limit, no new position is opened.
          </li>
          <li>
            <strong className="font-medium text-foreground">Reasons are kept.</strong>{" "}
            The decision and its inputs are stored, so a past call can be audited
            rather than taken on trust.
          </li>
        </ul>

        <div className="mt-14 flex flex-wrap gap-3">
          <Link
            href="/how-it-works"
            className="rounded-lg bg-foreground px-4 py-2 text-sm font-medium text-background transition-opacity hover:opacity-90"
          >
            See how it works
          </Link>
          <Link
            href="/pricing"
            className="rounded-lg border border-border px-4 py-2 text-sm font-medium transition-colors hover:bg-accent"
          >
            View pricing
          </Link>
        </div>
      </main>

      <FooterSection />
    </div>
  );
}
