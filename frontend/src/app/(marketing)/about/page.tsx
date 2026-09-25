import Link from "next/link";

import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";

export const metadata = { title: "About — Pkay TDAI" };

export default function AboutPage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="font-serif text-4xl font-medium tracking-tight">About Pkay TDAI</h1>
        <div className="mt-8 space-y-6 text-sm leading-relaxed text-muted-foreground">
          <p>
            Pkay TDAI is a multi-agent AI trading system for gold (XAUUSD) and bitcoin (BTCUSD).
            Four specialised agents — a Technical Analyst, a News Monitor, a Risk Manager and a
            Decision Maker — analyse the same market in parallel and vote on a single, risk-aware
            trade decision.
          </p>
          <p>
            Every agent output is validated, cross-checked against the others and passed through a
            circuit breaker, so a failing component degrades gracefully instead of producing bad
            signals. Regime detection, order-flow analysis and episodic memory tune the decisions
            to the market conditions at hand.
          </p>
          <p>
            Pkay TDAI is built for research and education. It runs on paper trading by default, and
            the full source is engineered with strict typing and an extensive test suite.
          </p>
        </div>

        <div className="mt-10 rounded-2xl border border-border bg-card/60 p-6">
          <h2 className="font-medium text-foreground">The four agents</h2>
          <ul className="mt-4 space-y-3 text-sm text-muted-foreground">
            <li>
              <span className="font-medium text-foreground">Technical Analyst</span> — indicators,
              multi-timeframe confirmation and order-flow absorption.
            </li>
            <li>
              <span className="font-medium text-foreground">News Monitor</span> — economic calendar
              and sentiment with impact alerts.
            </li>
            <li>
              <span className="font-medium text-foreground">Risk Manager</span> — VaR, position
              sizing and veto power.
            </li>
            <li>
              <span className="font-medium text-foreground">Decision Maker</span> — regime-aware
              voting, consistency checks and an optional LLM review.
            </li>
          </ul>
        </div>

        <p className="mt-10 text-xs text-muted-foreground">
          See how it works on the{" "}
          <Link href="/how-it-works" className="text-foreground underline-offset-4 hover:underline">
            How it works
          </Link>{" "}
          page.
        </p>
      </main>

      <FooterSection />
    </div>
  );
}