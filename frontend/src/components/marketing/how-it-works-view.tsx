import { FooterSection } from "@/components/marketing/footer-section";
import { PipelineStepper, type StepperStep } from "@/components/marketing/stepper";
import { SiteHeader } from "@/components/marketing/site-header";
import { AGENTS } from "@/lib/constants";

const PIPELINE_STEPS: StepperStep[] = [
  { title: "Market data", description: "Live ticks, candles, calendar, and news." },
  { title: "Analysis", description: "Technical and news signals are produced." },
  { title: "Risk review", description: "Size and stops are set, or the trade is blocked." },
  { title: "Decision", description: "Signals are combined into one decision." },
];

const AGENT_DETAILS = [
  {
    id: "technical_analyst",
    heading: "Technical Analyst",
    input: "OHLCV candles",
    output: "Direction, confidence, key levels, indicators",
    body: "Scores EMA trend, MACD momentum, RSI, Bollinger position, and short-term momentum, then damps confidence when ADX shows a weak trend.",
  },
  {
    id: "news_monitor",
    heading: "News Monitor",
    input: "Headlines or a sentiment value",
    output: "Sentiment, impact, alert level",
    body: "Scores headlines with a transparent lexicon, or accepts a sentiment you computed yourself. It flags events that should change position size.",
  },
  {
    id: "risk_manager",
    heading: "Risk Manager",
    input: "A trade proposal and account context",
    output: "Position size, stops, VaR, approval or veto",
    body: "Uses fractional Kelly sizing, ATR stops, drawdown limits, correlation and volatility guards. It holds veto power.",
  },
  {
    id: "decision_maker",
    heading: "Decision Maker",
    input: "The three signals above",
    output: "BUY, SELL, WAIT or SKIP with a score",
    body: "Combines the signals with fixed weights (technical 0.45, news 0.25, risk 0.30). A risk veto always forces SKIP.",
  },
];

export function HowItWorksView() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-6xl px-6 py-20">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">How it works</p>
          <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight">
            Four agents, one decision
          </h1>
          <p className="mt-4 text-sm text-muted-foreground">
            Each cycle runs the four agents in order. Every step is a rule you can read, so the
            result can be explained rather than guessed.
          </p>
        </div>

        <div className="mt-16 rounded-2xl border border-border bg-card p-8 sm:p-10">
          <PipelineStepper steps={PIPELINE_STEPS} />
        </div>

        <section className="mt-20 space-y-4">
          {AGENT_DETAILS.map((agent) => {
            const meta = AGENTS.find((item) => item.id === agent.id);
            return (
              <div
                key={agent.id}
                className="grid gap-4 rounded-2xl border border-border bg-card p-6 md:grid-cols-[2fr_1fr_1fr] md:items-start"
              >
                <div>
                  <h2 className="text-base font-medium">{agent.heading}</h2>
                  <p className="mt-2 text-sm text-muted-foreground">{agent.body}</p>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    Input
                  </div>
                  <div className="mt-1 text-sm">{agent.input}</div>
                </div>
                <div>
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground">
                    Output
                  </div>
                  <div className="mt-1 text-sm">{agent.output}</div>
                </div>
                {meta ? <span className="sr-only">{meta.name}</span> : null}
              </div>
            );
          })}
        </section>
      </main>

      <FooterSection />
    </div>
  );
}
