import { Activity, Bot, BrainCircuit, ShieldCheck, TrendingUp, Waves } from "lucide-react";

interface Feature {
  icon: typeof Bot;
  title: string;
  body: string;
}

const FEATURES: Feature[] = [
  {
    icon: Bot,
    title: "Multi-agent decisioning",
    body: "Four agents analyse the same market in parallel and vote. The Risk Manager holds veto power over every trade.",
  },
  {
    icon: Activity,
    title: "Live market feed",
    body: "Real-time XAUUSD and BTCUSD ticks, candles, the economic calendar and headlines stream into one analysis pipeline.",
  },
  {
    icon: ShieldCheck,
    title: "Risk-first execution",
    body: "Position sizing, VaR, drawdown limits and stop-loss checks run before any trade is placed.",
  },
  {
    icon: Waves,
    title: "Order-flow absorption",
    body: "Cumulative delta, divergence and wick exhaustion reveal institutional accumulation behind the price.",
  },
  {
    icon: TrendingUp,
    title: "Regime-aware analysis",
    body: "An HMM regime detector reads the market state and adapts decision weights to trending or ranging conditions.",
  },
  {
    icon: BrainCircuit,
    title: "Self-improving memory",
    body: "Every decision is recalled with its outcome, so confidence is adjusted by what actually worked before.",
  },
];

/** Homepage features grid (21st.dev "features-8" style). */
export function FeaturesSection() {
  return (
    <section id="features" className="border-y border-border bg-card/40">
      <div className="mx-auto max-w-6xl px-6 py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">Features</p>
          <h2 className="mt-3 font-serif text-3xl font-medium tracking-tight sm:text-4xl">
            Built for traders, engineered for safety
          </h2>
          <p className="mt-4 text-sm text-muted-foreground">
            Pkay TDAI pairs deep market analysis with institutional-grade guardrails.
          </p>
        </div>

        <div className="mt-14 grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map((feature) => {
            const Icon = feature.icon;
            return (
              <div
                key={feature.title}
                className="group rounded-2xl border border-border bg-card p-6 transition-colors hover:border-foreground/25"
              >
                <span className="mb-5 flex size-11 items-center justify-center rounded-xl bg-accent text-foreground transition-colors group-hover:bg-[#003AF9] group-hover:text-white">
                  <Icon className="size-5" />
                </span>
                <h3 className="text-base font-medium text-foreground">{feature.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{feature.body}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}