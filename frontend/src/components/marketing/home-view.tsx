"use client";

import Image from "next/image";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Database,
  LogOut,
  ShieldCheck,
  Zap,
} from "lucide-react";

import { FooterSection } from "@/components/marketing/footer-section";
import { FeaturesSection } from "@/components/marketing/features-section";
import { ResponsiveHeroBanner } from "@/components/marketing/responsive-hero-banner";
import { PipelineStepper, type StepperStep } from "@/components/marketing/stepper";
import { useAuth } from "@/components/auth-provider";
import { Button } from "@/components/ui/button";
import { AGENTS } from "@/lib/constants";

const STEPS = [
  {
    icon: Database,
    title: "1. Read the market",
    body: "Live prices stream in from biquote. Candles, the economic calendar, and news headlines are collected into one feed.",
  },
  {
    icon: Bot,
    title: "2. Agents analyse",
    body: "The Technical Analyst studies price and indicators. The News Monitor scores events and sentiment.",
  },
  {
    icon: ShieldCheck,
    title: "3. Risk checks the trade",
    body: "The Risk Manager sets the position size and stop loss. It can block a trade that breaks the limits.",
  },
  {
    icon: Zap,
    title: "4. Decide and execute",
    body: "The Decision Maker combines the signals. If the score is high enough, the trade is placed.",
  },
];

const HIGHLIGHTS = [
  {
    title: "Four agents, one decision",
    body: "The Technical Analyst, News Monitor, Risk Manager, and Decision Maker all vote. The Risk Manager can veto.",
  },
  {
    title: "Live market data",
    body: "Prices come from biquote over a live connection. Candles, the calendar, and headlines are included.",
  },
  {
    title: "Risk comes first",
    body: "Position size, stop loss, drawdown limits, and VaR are checked before any trade is made.",
  },
];

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
      <ResponsiveHeroBanner
        brand={
          <Link href="/" className="flex items-center gap-3">
            <span className="relative size-8 shrink-0 overflow-hidden rounded-lg ring-1 ring-white/15">
              <Image src="/logo-pkay.jpg" alt="Pkay TDAI" fill sizes="32px" className="object-cover" />
            </span>
            <span className="text-sm font-semibold tracking-tight">Pkay TDAI</span>
          </Link>
        }
        navLinks={[
          { label: "How it works", href: "/how-it-works" },
          { label: "Capabilities", href: "#capabilities" },
          { label: "Agents", href: "#agents" },
          { label: "Pricing", href: "/pricing" },
        ]}
        navAction={
          signedIn ? (
            <div className="flex items-center gap-2">
              <Button asChild size="sm" className="gap-1.5">
                <Link href="/dashboard">
                  Open console <ArrowRight className="size-3.5" />
                </Link>
              </Button>
              <Button variant="ghost" size="sm" className="gap-1.5" onClick={logout}>
                <LogOut className="size-3.5" />
                <span className="hidden sm:inline">Sign out</span>
              </Button>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" asChild>
                <Link href="/login">Sign in</Link>
              </Button>
              <Button size="sm" asChild>
                <Link href="/register">Get started</Link>
              </Button>
            </div>
          )
        }
        title="Gold and Bitcoin analysis from four AI agents"
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
      />

      {/* How it works */}
      <section id="how-it-works" className="mx-auto max-w-6xl px-6 py-24">
        <div className="mx-auto max-w-2xl text-center">
          <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
            How it works
          </p>
          <h2 className="mt-3 font-serif text-3xl font-medium tracking-tight sm:text-4xl">
            What happens in one analysis cycle
          </h2>
          <p className="mt-4 text-sm text-muted-foreground">
            Each cycle runs the four agents in order and records why it made its decision.
          </p>
        </div>

        <div className="mt-14 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((step, index) => {
            const Icon = step.icon;
            return (
              <div key={step.title} className="relative rounded-2xl border border-border bg-card p-6">
                <span className="mb-5 flex size-10 items-center justify-center rounded-xl bg-accent">
                  <Icon className="size-5" />
                </span>
                <h3 className="text-sm font-medium">{step.title}</h3>
                <p className="mt-2 text-sm text-muted-foreground">{step.body}</p>
                {index < STEPS.length - 1 ? (
                  <ArrowRight className="absolute -right-3 top-1/2 hidden size-5 -translate-y-1/2 text-muted-foreground/40 lg:block" />
                ) : null}
              </div>
            );
          })}
        </div>
      </section>

      {/* Features (below How it works) */}
      <FeaturesSection />

      {/* Capabilities */}
      <section id="capabilities" className="border-y border-border bg-card/40">
        <div className="mx-auto max-w-6xl px-6 py-24">
          <div className="grid gap-6 md:grid-cols-3">
            {HIGHLIGHTS.map((item) => (
              <div key={item.title} className="rounded-2xl border border-border bg-card p-6">
                <h2 className="text-base font-medium">{item.title}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{item.body}</p>
              </div>
            ))}
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
