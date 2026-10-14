"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowRight } from "lucide-react";

import { AboutSection } from "@/components/marketing/about-section";
import { FooterSection } from "@/components/marketing/footer-section";
import { FeaturesSection } from "@/components/marketing/features-section";
import { HeroSection } from "@/components/marketing/hero-section";
import { HowItWorksSection } from "@/components/marketing/how-it-works-section";
import { IntegrationCard } from "@/components/marketing/integration-card";
import { LogoCloud } from "@/components/marketing/logo-cloud";
import { PipelineStepper, type StepperStep } from "@/components/marketing/stepper";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { AGENTS } from "@/lib/constants";

const PIPELINE_STEPS: StepperStep[] = [
  {
    title: "Market data",
    description: "Live ticks, candles, calendar, and news.",
  },
  {
    title: "Analysis",
    description: "Technical and news signals are produced.",
  },
  {
    title: "Risk review",
    description: "Size and stops are set, or the trade is blocked.",
  },
  {
    title: "Decision",
    description: "Signals are combined and the trade is placed.",
  },
];

export function HomeView() {
  const { user, logout } = useAuth();
  const signedIn = Boolean(user);

  return (
    <div className="min-h-dvh">
      <HeroSection
        brand={
          <Link href="/" className="flex items-center gap-3">
            <span className="relative size-8 shrink-0 overflow-hidden rounded-lg ring-1 ring-white/15">
              <Image src="/logo-pkay.jpg" alt="Pkay TDAI" fill sizes="32px" className="object-cover" />
            </span>
            <span className="text-md font-bold tracking-tight">Pkay TDAI</span>
          </Link>
        }
        navLinks={[
          { label: "How it works", href: "/how-it-works" },
          { label: "Capabilities", href: "#capabilities" },
          { label: "Agents", href: "#agents" },
          { label: "Pricing", href: "/pricing" },
        ]}
        auth={
          signedIn
            ? {
                secondary: { label: "Sign out", onClick: logout },
                primary: { label: "Open console", href: "/dashboard" },
              }
            : {
                secondary: { label: "Sign in", href: "/login" },
                primary: { label: "Get started", href: "/register" },
              }
        }
        /* Two lines with a hard break, as in the original. */
        title={
          <>
            Gold and Bitcoin Analysis
            <br />
            From Four AI Agents
          </>
        }
        subtitle="Pkay TDAI combines technical analysis, news sentiment, and strict risk limits. Each agent gives a signal, and the system only trades when they agree."
        primaryCta={
          signedIn
            ? { label: "Open console", href: "/dashboard" }
            : { label: "Get started", href: "/register" }
        }
        secondaryCta={
          signedIn
            ? { label: "View charts", href: "/charts" }
            : { label: "See how it works", href: "#how-it-works" }
        }
        /* The image area. The logo cloud sits in the hero's media panel, in place of
            the price-chart image it used to hold. */
        panel={
          <LogoCloud
            className="px-4 py-6"
            headline="Data From"
            actionLabel="View integrations"
            actionHref="#capabilities"
          />
        }
      />

      {/* Who we are — 21st.dev `about-section` (@uilayout.contact). Its label row is
          absolutely positioned with negative top offsets at the small breakpoints, so
          it is designed to overlap the block above it. */}
      <AboutSection />

      {/* How it works - 21st.dev `Feature Section` (ayushmxxn, id 5541), adapted to
          this project's tokens and real pipeline copy. It replaced a four-card grid
          that was the only consumer of the old STEPS array. */}
      <HowItWorksSection />

      {/* Features (below How it works) */}
      <FeaturesSection />

      {/* Capabilities — component style on the left, text on the right */}
      <section id="capabilities" className="border-y border-border bg-card/40">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <IntegrationCard />
            <div className="space-y-6">
              <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                Capabilities
              </p>
              <h2 className="font-serif text-3xl font-medium tracking-tight sm:text-4xl">
                Everything connected to one decision engine
              </h2>
              <p className="max-w-xl text-sm leading-relaxed text-muted-foreground">
                Live markets, four specialised agents, and an LLM review all feed into a single
                pipeline. Each part updates the others, and the whole system only acts when the
                pieces agree and the risk limits hold.
              </p>
              <div className="grid gap-x-8 gap-y-4 sm:grid-cols-2">
                <div>
                  <h3 className="text-base font-medium">Four agents, one decision</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    The Technical Analyst, News Monitor, Risk Manager and Decision Maker all vote;
                    the Risk Manager can veto.
                  </p>
                </div>
                <div>
                  <h3 className="text-base font-medium">Live market data</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Prices stream over a live connection, with candles, the calendar and headlines
                    included.
                  </p>
                </div>
                <div>
                  <h3 className="text-base font-medium">Risk comes first</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Position size, stop loss, drawdown limits and VaR are checked before any trade.
                  </p>
                </div>
                <div>
                  <h3 className="text-base font-medium">Reasoned by an LLM</h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    Every signal gets a readable narrative that explains why the agents voted the
                    way they did.
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Agent fleet */}
      <section id="agents" className="mx-auto max-w-6xl px-6 py-24">
        <div className="mb-10 flex items-end justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
              The agent fleet
            </p>
            <h2 className="mt-3 font-serif text-3xl font-medium tracking-tight">
              Meet the agents
            </h2>
          </div>
          <Link
            href={signedIn ? "/agents" : "/login"}
            className="hidden items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground sm:flex"
          >
            Inspect agents <ArrowRight className="size-4" />
          </Link>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {AGENTS.map((agent) => (
            <div
              key={agent.id}
              className="rounded-2xl border border-border bg-card p-5 transition-colors hover:border-foreground/25"
            >
              <span className="relative mb-4 block size-12 overflow-hidden rounded-xl ring-1 ring-border">
                <Image src={agent.logo} alt={agent.name} fill sizes="48px" className="object-cover" />
              </span>
              <h3 className="text-sm font-medium">{agent.name}</h3>
              <p className="mt-1 text-xs text-muted-foreground">{agent.description}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Step progress */}
      <section id="step-progress" className="mx-auto max-w-6xl px-6 pb-24">
        <div className="rounded-2xl border border-border bg-card p-8 sm:p-10">
          <div className="mx-auto mb-12 max-w-2xl text-center">
            <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
              Step progress
            </p>
            <h2 className="mt-3 font-serif text-2xl font-medium tracking-tight sm:text-3xl">
              How a cycle moves through the agents
            </h2>
            <p className="mt-3 text-sm text-muted-foreground">
              The active step advances on its own. Click a step to jump to it.
            </p>
          </div>
          <PipelineStepper steps={PIPELINE_STEPS} />
        </div>
      </section>

      {/* Final CTA */}
      <section className="border-t border-border">
        <div className="mx-auto max-w-4xl px-6 py-24 text-center">
          <h2 className="font-serif text-3xl font-medium tracking-tight sm:text-4xl">
            {signedIn ? "Your console is ready" : "Sign in with Google to open the console"}
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-sm text-muted-foreground">
            The dashboard, charts, signal feed, and risk panels are available to registered users.
            Access is limited to signed-in accounts.
          </p>
          <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
            {signedIn ? (
              <Button asChild size="lg" className="gap-2">
                <Link href="/dashboard">
                  Open console <ArrowRight className="size-4" />
                </Link>
              </Button>
            ) : (
              <>
                <Button asChild size="lg">
                  <Link href="/register">Continue with Google</Link>
                </Button>
                <Button asChild variant="outline" size="lg">
                  <Link href="/login">Sign in</Link>
                </Button>
              </>
            )}
          </div>
        </div>
      </section>

      <FooterSection />
    </div>
  );
}
