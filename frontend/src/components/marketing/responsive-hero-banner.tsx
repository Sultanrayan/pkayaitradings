"use client";

import Image from "next/image";
import Link from "next/link";
import { motion, type Variants } from "framer-motion";
import { Sparkles } from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";

export interface HeroCta {
  label: string;
  href?: string;
  onClick?: () => void;
}

export interface HeroNavLink {
  label: string;
  href: string;
}

export interface ResponsiveHeroBannerProps {
  brand: React.ReactNode;
  navLinks?: HeroNavLink[];
  navAction?: React.ReactNode;
  badge?: string;
  title: React.ReactNode;
  subtitle?: string;
  primaryCta?: HeroCta;
  secondaryCta?: HeroCta;
  partners?: string[];
  className?: string;
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.12, delayChildren: 0.1 } },
};

const fadeSlideIn: Variants = {
  hidden: { opacity: 0, y: 26 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.65, ease: [0.22, 1, 0.36, 1] } },
};

function CtaButton({ cta, variant }: { cta: HeroCta; variant: "primary" | "secondary" }) {
  const className = cn(
    "h-11 rounded-full px-6 text-sm",
    variant === "primary"
      ? "bg-foreground text-background hover:bg-foreground/90"
      : "border-border bg-white/5 text-foreground backdrop-blur hover:bg-white/10",
  );
  if (cta.href) {
    return (
      <Button asChild variant={variant === "primary" ? "default" : "outline"} className={className}>
        <Link href={cta.href}>{cta.label}</Link>
      </Button>
    );
  }
  return (
    <Button
      variant={variant === "primary" ? "default" : "outline"}
      className={className}
      onClick={cta.onClick}
    >
      {cta.label}
    </Button>
  );
}

/**
 * Full-screen cinematic hero with a glassmorphic nav, animated badge, serif
 * headline, dual CTAs and a partner grid. Recreated to match the 21st.dev
 * "Responsive Hero Banner" spec.
 */
export function ResponsiveHeroBanner({
  brand,
  navLinks = [],
  navAction,
  badge,
  title,
  subtitle,
  primaryCta,
  secondaryCta,
  partners = [],
  className,
}: ResponsiveHeroBannerProps) {
  return (
    <section className={cn("relative isolate overflow-hidden", className)}>
      {/* Cinematic background */}
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(234,179,8,0.18),transparent_55%),radial-gradient(ellipse_at_bottom_right,rgba(34,197,94,0.14),transparent_50%)]" />
        <div className="grid-noise absolute inset-0 opacity-40" />
        <Image
          src="/logo-pkay.jpg"
          alt=""
          fill
          priority
          sizes="100vw"
          className="object-contain opacity-[0.05]"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-background/40 to-background" />
      </div>

      {/* Glassmorphic navigation */}
      <div className="absolute inset-x-0 top-0 z-20 px-4 pt-4">
        <nav className="mx-auto flex max-w-6xl items-center justify-between rounded-2xl border border-white/10 bg-white/5 px-4 py-3 backdrop-blur-xl">
          <div className="flex items-center gap-3">{brand}</div>
          <div className="hidden items-center gap-6 md:flex">
            {navLinks.map((link) => (
              <Link
                key={link.href}
                href={link.href}
                className="text-sm text-muted-foreground transition-colors hover:text-foreground"
              >
                {link.label}
              </Link>
            ))}
          </div>
          {navAction}
        </nav>
      </div>

      {/* Hero content */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="relative z-10 mx-auto flex min-h-dvh max-w-5xl flex-col items-center justify-center px-6 pt-32 pb-20 text-center"
      >
        {badge ? (
          <motion.span
            variants={fadeSlideIn}
            className="mb-6 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-1.5 text-xs font-medium text-muted-foreground backdrop-blur"
          >
            <Sparkles className="size-3.5 text-gold" />
            {badge}
          </motion.span>
        ) : null}

        <motion.h1
          variants={fadeSlideIn}
          className="font-serif text-4xl leading-[1.05] font-medium tracking-tight text-balance sm:text-6xl lg:text-7xl"
        >
          {title}
        </motion.h1>

        {subtitle ? (
          <motion.p
            variants={fadeSlideIn}
            className="mt-6 max-w-2xl text-base text-muted-foreground text-pretty sm:text-lg"
          >
            {subtitle}
          </motion.p>
        ) : null}

        {primaryCta || secondaryCta ? (
          <motion.div variants={fadeSlideIn} className="mt-9 flex flex-wrap items-center justify-center gap-3">
            {primaryCta ? <CtaButton cta={primaryCta} variant="primary" /> : null}
            {secondaryCta ? <CtaButton cta={secondaryCta} variant="secondary" /> : null}
          </motion.div>
        ) : null}

        {partners.length ? (
          <motion.div variants={fadeSlideIn} className="mt-16 w-full">
            <p className="mb-5 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
              Built with
            </p>
            <div className="grid grid-cols-2 items-center justify-items-center gap-4 sm:grid-cols-3 lg:grid-cols-6">
              {partners.map((partner) => (
                <span
                  key={partner}
                  className="text-sm font-medium text-muted-foreground/70 transition-colors hover:text-foreground"
                >
                  {partner}
                </span>
              ))}
            </div>
          </motion.div>
        ) : null}
      </motion.div>
    </section>
  );
}
