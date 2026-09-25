import Link from "next/link";
import { ArrowRight, KeyRound } from "lucide-react";

import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";

interface Endpoint {
  method: "GET" | "POST";
  path: string;
  description: string;
  auth: boolean;
}

const ENDPOINTS: Endpoint[] = [
  {
    method: "POST",
    path: "/api/v1/agents/technical",
    description: "Score your own OHLC candles with the Technical Analyst strategy.",
    auth: true,
  },
  {
    method: "POST",
    path: "/api/v1/agents/news",
    description: "Score your headlines (or a supplied sentiment) with the News Monitor.",
    auth: true,
  },
  {
    method: "POST",
    path: "/api/v1/agents/risk",
    description: "Run position sizing, stops and risk-veto checks on a proposal.",
    auth: true,
  },
  {
    method: "POST",
    path: "/api/v1/agents/decide",
    description: "Combine the three agent outputs into the weighted final decision.",
    auth: true,
  },
  {
    method: "POST",
    path: "/api/v1/agents/analyze",
    description: "Run the full pipeline (technical, news, risk, decision) in one call.",
    auth: true,
  },
  {
    method: "GET",
    path: "/api/v1/agents/capabilities",
    description: "List the available agents, strategies and indicators.",
    auth: false,
  },
];

const METHOD_CLASS: Record<Endpoint["method"], string> = {
  GET: "bg-bull/10 text-bull ring-bull/30",
  POST: "bg-amber-500/10 text-amber-400 ring-amber-500/30",
};

export function ApiReferenceView() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="px-4 py-10">
        <div className="mx-auto max-w-4xl space-y-8">
          <div className="space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight">API Reference</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              The developer API runs the Pkay TDAI agent logic on your own data. Send your candles
              and headlines; receive the agent signals and decisions back.
            </p>
          </div>

          <section className="flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-border bg-card/60 px-6 py-5">
            <div className="flex items-start gap-3">
              <span className="mt-0.5 flex size-9 items-center justify-center rounded-lg bg-accent">
                <KeyRound className="size-4 text-gold" />
              </span>
              <div>
                <h2 className="text-sm font-semibold tracking-tight">
                  Every endpoint requires a token
                </h2>
                <p className="mt-1 max-w-xl text-xs leading-relaxed text-muted-foreground">
                  Send your token as{" "}
                  <code className="rounded bg-muted px-1 py-0.5 text-foreground/80">
                    Authorization: Bearer &lt;token&gt;
                  </code>
                  . Requests without a valid token fail. Apply for access — approved within 24–48
                  hours — and your token arrives by email.
                </p>
              </div>
            </div>
            <Link
              href="/apply"
              className="inline-flex items-center gap-1.5 rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Apply for access
              <ArrowRight className="size-4" />
            </Link>
          </section>

          <section className="overflow-hidden rounded-2xl border border-border bg-card">
            <div className="border-b border-border px-6 py-4">
              <h2 className="text-sm font-semibold tracking-tight">Agent endpoints</h2>
              <p className="mt-1 text-xs text-muted-foreground">
                Base URL: the origin you are viewing this page from.
              </p>
            </div>
            <ul className="divide-y divide-border">
              {ENDPOINTS.map((endpoint) => (
                <li key={endpoint.path} className="flex flex-wrap items-start gap-4 px-6 py-4">
                  <span
                    className={`inline-flex w-14 shrink-0 items-center justify-center rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ${METHOD_CLASS[endpoint.method]}`}
                  >
                    {endpoint.method}
                  </span>
                  <div className="min-w-0 flex-1">
                    <code className="font-mono text-sm text-foreground">{endpoint.path}</code>
                    <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                      {endpoint.description}
                    </p>
                  </div>
                  <span
                    className={
                      endpoint.auth
                        ? "inline-flex shrink-0 items-center rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground"
                        : "inline-flex shrink-0 items-center rounded-full bg-bull/10 px-2 py-0.5 text-[11px] text-bull"
                    }
                  >
                    {endpoint.auth ? "Token required" : "Public"}
                  </span>
                </li>
              ))}
            </ul>
          </section>

          <p className="text-xs leading-relaxed text-muted-foreground">
            Pkay TDAI provides agent logic and strategies only — not AI models, market data or
            sentiment data. You send the inputs and remain responsible for any decisions.
          </p>
        </div>
      </main>

      <FooterSection />
    </div>
  );
}
