"use client";

import Link from "next/link";
import { motion, type Variants } from "framer-motion";
import { cn } from "cn";

/**
 * Full-screen hero: radial brand gradient, a bordered nav, a large two-line
 * headline, two CTAs, and a wide media panel with a bottom fade.
 *
 * Rebuilt from the 21st.dev component
 * `@solaceui/components/hero-section-6`. Its source could not be pulled through the
 * API (free tier exhausted, `403 retrieval_limit_reached`), but the compiled
 * component was recovered verbatim from the public CDN bundle, so the structure,
 * class names and animation timings below are the original's.
 *
 * Notable details carried over from the compiled original:
 *
 * * The root is `h-screen overflow-hidden`, so the media panel is deliberately cut
 *   off at the viewport edge — it reads as continuing below the fold rather than
 *   ending. The preview shows the same hard crop.
 * * `--color-primary:#003AF9` is a custom property set on the root, and the
 *   gradient and both primary buttons reference it, so the whole section is
 *   re-themed by changing that one value.
 * * The gradient, headline and CTAs all carry `dark:` variants. The dark one is the
 *   one that shows here: this app sets `class="dark"` on `<html>` unconditionally.
 * * The headline container sets `initial="hidden" animate="visible"` with a
 *   `staggerChildren: 0.1` container variant; each child then uses the same blur-in
 *   item variant. In the original this came from 21st's `TextAnim` magic component.
 * * The panel animates in on a delay of 0.4s.
 *
 * One structural element of the original is deliberately absent. It places a second,
 * much narrower panel over the middle of the media panel — a PNG screenshot of a
 * phone, arriving on a 0.7s delay, positioned at `-translate-y-[55%]` and scaled
 * through `w-[150px] sm:w-[220px] md:w-[260px] lg:w-[320px] xl:w-[380px]` with the
 * matching heights `h-[240px] md:h-[420px] lg:h-[480px] xl:h-[540px]`. The homepage
 * does not want a box there, so the slot and its `overlay` prop were removed outright
 * rather than left as an unused prop that callers could never exercise. Reinstating it
 * means restoring that wrapper inside the panel and the prop on this interface.
 */

export interface HeroNavLink {
  label: string;
  href: string;
}

export interface HeroCta {
  label: string;
  href?: string;
  onClick?: () => void;
}

/** The design carries two auth buttons on the right of the nav: outline, then filled. */
export interface HeroAuth {
  primary: HeroCta;
  secondary?: HeroCta;
}

export interface HeroSectionProps {
  brand: React.ReactNode;
  navLinks?: HeroNavLink[];
  auth: HeroAuth;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  primaryCta?: HeroCta;
  secondaryCta?: HeroCta;
  /**
   * Fills the wide media panel. The original renders an `<Image>` here at
   * `h-auto w-full object-cover object-left`; this is a node instead so the panel can
   * hold arbitrary content without the frame, border, shadow, animation and bottom
   * fade around it having to be rebuilt per caller.
   */
  panel: React.ReactNode;
  className?: string;
}

/** Blur-in used by every headline child. The original passes `y: 20` (downward). */
const itemVariants: Variants = {
  hidden: { opacity: 0, filter: "blur(10px)", y: 20 },
  visible: {
    opacity: 1,
    filter: "blur(0px)",
    y: 0,
    transition: { type: "spring", bounce: 0.2, duration: 1 },
  },
};

/** Only `visible` is defined in the original, so the container itself never animates. */
const containerVariants: Variants = {
  visible: { transition: { staggerChildren: 0.1 } },
};

/**
 * The original styles its nav buttons and its hero CTAs differently, and the
 * difference is visible: the hero pair is `text-lg` with a brand-coloured shadow
 * and responsive padding, while the nav pair is `text-sm` and square. Kept apart
 * so neither inherits the other's sizing.
 */
function HeroButton({
  cta,
  variant,
  size,
}: {
  cta: HeroCta;
  variant: "outline" | "filled";
  size: "nav" | "hero";
}) {
  const className = cn(
    "cursor-pointer rounded-sm",
    size === "nav"
      ? cn(
          "px-3 py-1 text-sm font-medium transition-colors",
          variant === "filled"
            ? "bg-(--color-primary) text-white hover:bg-black/90"
            : "border border-neutral-200 text-black hover:bg-neutral-200 dark:border-white/20 dark:text-white dark:hover:bg-white/10",
        )
      : cn(
          "w-full px-1 py-1 text-lg sm:w-auto md:px-4 md:py-2",
          variant === "filled"
            ? "bg-(--color-primary) text-white shadow-lg shadow-(--color-primary)/20 transition-all hover:bg-(--color-primary)/90 hover:shadow-(--color-primary)/40"
            : "border border-neutral-300 transition-colors hover:bg-neutral-300 dark:border-neutral-700 dark:hover:bg-neutral-800",
        ),
  );

  if (cta.href) {
    return (
      <Link href={cta.href} className={className}>
        {cta.label}
      </Link>
    );
  }
  return (
    <button type="button" className={className} onClick={cta.onClick}>
      {cta.label}
    </button>
  );
}

export function HeroSection({
  brand,
  navLinks = [],
  auth,
  title,
  subtitle,
  primaryCta,
  secondaryCta,
  panel,
  className,
}: HeroSectionProps) {
  return (
    <div
      className={cn(
        "relative h-screen w-full overflow-hidden [--color-primary:#003AF9]",
        className,
      )}
    >
      <div className="absolute inset-0 z-0 bg-[radial-gradient(125%_125%_at_50%_10%,#fff_40%,var(--color-primary)_100%)] dark:bg-[radial-gradient(125%_125%_at_50%_10%,#000_40%,var(--color-primary)_100%)]" />

      <nav className="relative z-10 flex w-full items-center justify-between border-b border-black/10 px-4 py-4 sm:px-6 dark:border-white/20">
        <div className="text-md font-bold tracking-tight">{brand}</div>
        <div className="hidden items-center gap-4 md:flex">
          {navLinks.map((link) => (
            <Link key={link.href} href={link.href}>
              <span className="text-sm text-neutral-400 transition-colors hover:text-black md:text-[1rem] dark:text-white/70 dark:hover:text-white">
                {link.label}
              </span>
            </Link>
          ))}
        </div>
        <div className="flex items-center gap-4">
          {auth.secondary ? (
            <HeroButton cta={auth.secondary} variant="outline" size="nav" />
          ) : null}
          <HeroButton cta={auth.primary} variant="filled" size="nav" />
        </div>
      </nav>

      <div className="relative z-10 mx-auto flex max-w-7xl flex-col items-center justify-start rounded-none px-4 pb-0 pt-20 text-center md:pt-10">
        <motion.div
          initial="hidden"
          animate="visible"
          variants={containerVariants}
          className="mx-auto flex max-w-4xl flex-col items-center text-center"
        >
          <motion.h1
            variants={itemVariants}
            className="mb-5 px-6 text-3xl font-bold leading-[1.1] tracking-tight text-gray-900 md:px-0 md:text-4xl lg:text-6xl dark:text-white"
          >
            {title}
          </motion.h1>
          {subtitle ? (
            <motion.p
              variants={itemVariants}
              className="mx-auto mb-6 max-w-[350px] text-sm text-neutral-600 sm:text-sm md:mb-5 md:max-w-lg md:text-lg lg:text-xl dark:text-neutral-300"
            >
              {subtitle}
            </motion.p>
          ) : null}
          {primaryCta || secondaryCta ? (
            <motion.div
              variants={itemVariants}
              className="mx-auto mb-16 flex w-[300px] flex-row items-center justify-center gap-4 sm:flex-row md:w-full"
            >
              {primaryCta ? (
                <HeroButton cta={primaryCta} variant="filled" size="hero" />
              ) : null}
              {secondaryCta ? (
                <HeroButton cta={secondaryCta} variant="outline" size="hero" />
              ) : null}
            </motion.div>
          ) : null}
        </motion.div>

        <div className="relative z-20 mx-auto w-full">
          <div className="relative">
            <motion.div
              initial={{ opacity: 0, y: 30, scale: 0.98 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
              className="relative w-full overflow-hidden rounded-md border border-gray-200 shadow-xl dark:border-gray-800 dark:bg-gray-900"
            >
              {panel}
            </motion.div>
          </div>

          {/* Fades the panel into the section below, which is why the hero can be
              clipped at the viewport edge without a hard cut. */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.8, delay: 0.4, ease: "easeOut" }}
            className="pointer-events-none absolute -bottom-2 left-0 right-0 z-30 h-50 rounded-md bg-gradient-to-t from-white via-white/80 to-transparent md:h-60 lg:h-80 dark:from-black dark:via-black/80"
          />
        </div>
      </div>
    </div>
  );
}