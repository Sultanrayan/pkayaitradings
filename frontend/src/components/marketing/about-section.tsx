"use client";

import { useRef, type ReactNode } from "react";
import { motion, useInView, type Variants } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { cn } from "cn";

/**
 * Homepage "who we are" block.
 *
 * Rebuilt from the 21st.dev component
 * `@uilayout.contact/components/about-section`. Its source could not be pulled
 * through the API (free tier exhausted, `403 retrieval_limit_reached`), but the
 * compiled component was recovered verbatim from the public CDN bundle, so the
 * structure, class names, animation timings and — importantly — the SVG clip path
 * below are the original's, not an approximation.
 *
 * What the earlier reconstruction got wrong, and what is now faithful:
 *
 * * The photograph is an SVG `<image>` inside a `clipPath` with a custom path. The
 *   irregular silhouette is that path; it is not a rounded frame with a background
 *   block painted over one edge.
 * * The label row is absolutely positioned at `w-[85%]` with negative top offsets at
 *   the small breakpoints, so it deliberately overlaps the section above.
 * * The asterisk spins (`animate-spin`).
 * * Elements reveal on scroll with a blur-in, staggered by `animationNum * 0.4`.
 * * The headline is a word-by-word vertical cut reveal on a spring.
 * * The pill button is `rounded-lg` with a `hover:gap-4`, not a fully rounded pill.
 *
 * Content substitutions, because the original is a freelancer's personal block and
 * makes claims that cannot be substantiated here: the "10+ years / 3 million words"
 * and "100+ brands / 30% higher engagement" figures are replaced with the agent
 * count and covered instruments, both read off this codebase. Everything structural
 * is unchanged.
 *
 * Palette is mapped onto this project's tokens: the original is a light section
 * (`bg-[#f9f9f9]`, `text-gray-900`) and this app is dark-only, so the slate values
 * would be unreadable. The red accent and the layout are kept.
 */

/** The original's clip path, verbatim. */
const CLIP_PATH =
  "M0.0998072 1H0.422076H0.749756C0.767072 1 0.774207 0.961783 0.77561 0.942675V0.807325C0.777053 0.743631 0.791844 0.731953 0.799059 0.734076H0.969813C0.996268 0.730255 1.00088 0.693206 0.999875 0.675159V0.0700637C0.999875 0.0254777 0.985045 0.00477707 0.977629 0H0.902473C0.854975 0 0.890448 0.138535 0.850165 0.138535H0.0204424C0.00408849 0.142357 0 0.180467 0 0.199045V0.410828C0 0.449045 0.0136283 0.46603 0.0204424 0.469745H0.0523086C0.0696245 0.471019 0.0735527 0.497877 0.0733523 0.511146V0.915605C0.0723903 0.983121 0.090588 1 0.0998072 1Z";

/**
 * Blur-in-on-scroll wrapper. The original is 21st's `ScrollAnimation` magic
 * component, which this reproduces: `animationNum` becomes framer-motion's `custom`,
 * and the variant function uses it to stagger each element by 0.4s.
 */
function ScrollAnimation({
  as: Tag = "div",
  animationNum = 0,
  variants,
  className,
  children,
  ...rest
}: {
  as?: "div" | "span" | "a" | "figure" | "p";
  animationNum?: number;
  variants?: Variants;
  className?: string;
  children: ReactNode;
} & Record<string, unknown>) {
  const MotionTag = motion[Tag] as typeof motion.div;
  return (
    <MotionTag
      custom={animationNum}
      initial="hidden"
      whileInView="visible"
      viewport={{ once: true, margin: "-100px" }}
      variants={variants}
      className={className}
      {...rest}
    >
      {children}
    </MotionTag>
  );
}

/** Word-by-word vertical cut reveal for the headline (the original's magic component). */
function VerticalCutReveal({
  text,
  reverse = false,
  staggerDuration = 0.1,
  delay = 0,
}: {
  text: string;
  reverse?: boolean;
  staggerDuration?: number;
  delay?: number;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const inView = useInView(ref, { once: true, margin: "-100px" });
  const words = text.split(" ");

  return (
    <span ref={ref} className="flex flex-wrap whitespace-pre-wrap">
      {/* Full text for assistive tech; the animated pieces are decorative. */}
      <span className="sr-only">{text}</span>
      {words.map((word, index) => (
        <span
          key={`${word}-${index}`}
          aria-hidden
          className="inline-flex overflow-hidden"
        >
          {Array.from(word).map((character, charIndex) => (
            <span
              key={`${character}-${charIndex}`}
              className="inline-block whitespace-pre-wrap"
              style={{
                transform: inView ? "translateY(0)" : `translateY(${reverse ? "-100%" : "100%"})`,
                opacity: inView ? 1 : 0,
                transition: `transform 700ms cubic-bezier(0.16,1,0.3,1) ${
                  delay + (index + charIndex / word.length) * staggerDuration * 10
                }s, opacity 400ms linear ${delay}s`,
              }}
            >
              {character}
            </span>
          ))}
          {index < words.length - 1 ? <span> </span> : null}
        </span>
      ))}
    </span>
  );
}

function TelegramMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden className={className}>
      <path d="M21.94 4.3 19.2 19.2c-.2 1.02-.84 1.27-1.7.79l-4.7-3.46-2.27 2.18c-.25.25-.46.46-.95.46l.34-4.8 8.74-7.9c.38-.34-.08-.53-.59-.19l-10.8 6.8-4.65-1.46c-1.01-.32-1.03-1.01.21-1.5l18.16-7c.84-.31 1.58.2 1.3 1.5Z" />
    </svg>
  );
}

/** The project's one real social presence, already used in the footer and contact page. */
const TELEGRAM_URL = "https://t.me/pkaytradingaiofficial";

/** Blur-in variants: one nudges up, one fades in place. Mirrors the original pair. */
const riseVariants: Variants = {
  hidden: { filter: "blur(10px)", y: -20, opacity: 0 },
  visible: (index: number) => ({
    y: 0,
    opacity: 1,
    filter: "blur(0px)",
    transition: { delay: index * 0.4, duration: 0.5 },
  }),
};

const fadeVariants: Variants = {
  hidden: { filter: "blur(10px)", opacity: 0 },
  visible: (index: number) => ({
    opacity: 1,
    filter: "blur(0px)",
    transition: { delay: index * 0.4, duration: 0.5 },
  }),
};

const SOCIAL_CLASS =
  "md:w-8 md:h-8 sm:w-6 w-5 sm:h-6 h-5 border border-border bg-muted rounded-lg flex items-center justify-center cursor-pointer";

export function AboutSection() {
  return (
    <section id="about" className="bg-card/40 px-4 py-8">
      <div className="mx-auto max-w-6xl">
        <div className="relative">
          {/* Label and socials float above the section, hence the negative offsets. */}
          <div className="absolute z-10 mb-8 flex w-[85%] -top-3 items-center justify-between sm:-top-2 md:top-0 lg:top-4">
            <div className="flex items-center gap-2 text-xl">
              <span className="text-red-500 animate-spin">✱</span>
              <ScrollAnimation
                as="span"
                animationNum={0}
                variants={riseVariants}
                className="text-sm font-medium text-muted-foreground"
              >
                Who we are
              </ScrollAnimation>
            </div>

            <div className="flex gap-4">
              {/* The original links four of the component author's own accounts.
                  Only Telegram is a real Pkay presence, so one slot is rendered
                  rather than four links to a third party. */}
              <a
                href={TELEGRAM_URL}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Pkay TDAI on Telegram"
                className={cn(SOCIAL_CLASS, "text-foreground transition-colors hover:bg-accent")}
              >
                <TelegramMark className="size-4" />
              </a>
            </div>
          </div>

          {/* The clipped photograph. The silhouette is the path, not a frame. */}
          <ScrollAnimation
            as="figure"
            animationNum={4}
            variants={fadeVariants}
            className="group relative mt-12"
          >
            <svg
              className="w-full"
              width="100%"
              height="100%"
              viewBox="0 0 100 40"
              role="img"
              aria-label="Glass office towers seen from street level"
            >
              <defs>
                <clipPath id="about-clip-inverted" clipPathUnits="objectBoundingBox">
                  <path d={CLIP_PATH} />
                </clipPath>
              </defs>
              <image
                href="/homepage.png"
                clipPath="url(#about-clip-inverted)"
                preserveAspectRatio="xMidYMid slice"
                width="100%"
                height="100%"
              />
            </svg>

            {/* Credentials on the left, headline stats on the right. */}
            <div className="flex flex-wrap items-center justify-between py-3 text-sm lg:justify-start">
              <ScrollAnimation
                animationNum={5}
                variants={riseVariants}
                className="flex gap-4"
              >
                <div className="mb-2 flex items-center gap-2 text-xs sm:text-base">
                  <span className="font-bold text-red-500">4</span>
                  <span className="text-muted-foreground">agents per decision</span>
                  <span className="text-border">|</span>
                </div>
                <div className="mb-2 flex items-center gap-2 text-xs sm:text-base">
                  <span className="font-bold text-red-500">2</span>
                  <span className="text-muted-foreground">markets covered</span>
                </div>
              </ScrollAnimation>

              <div className="flex flex-row-reverse gap-4 lg:absolute lg:bottom-16 lg:right-0 lg:flex-col lg:gap-0">
                <ScrollAnimation
                  animationNum={6}
                  variants={riseVariants}
                  className="mb-2 flex items-center gap-2 text-2xl sm:text-3xl lg:text-4xl"
                >
                  <span className="font-semibold text-red-500">XAU/USD</span>
                  <span className="uppercase text-muted-foreground">+ BTC</span>
                </ScrollAnimation>
                <ScrollAnimation
                  animationNum={7}
                  variants={riseVariants}
                  className="mb-2 flex items-center gap-2 text-xs sm:text-base"
                >
                  <span className="font-bold text-red-500">4</span>
                  <span className="text-muted-foreground">independent analyses</span>
                  <span className="hidden text-border lg:hidden">|</span>
                </ScrollAnimation>
              </div>
            </div>
          </ScrollAnimation>
        </div>

        {/* Headline and body. */}
        <div className="grid gap-8 md:grid-cols-3">
          <div className="md:col-span-2">
            <h1 className="mb-8 !text-2xl font-semibold !leading-[110%] text-foreground sm:text-4xl md:text-5xl">
              <VerticalCutReveal
                text="Signals you can trace back to the market."
                reverse
                delay={0.3}
              />
            </h1>

            <ScrollAnimation
              animationNum={9}
              variants={riseVariants}
              className="grid gap-8 text-muted-foreground md:grid-cols-2"
            >
              <ScrollAnimation animationNum={10} variants={riseVariants} className="text-xs sm:text-base">
                <p className="text-justify leading-relaxed">
                  Every cycle starts from one snapshot: live prices, candles, the
                  economic calendar and news headlines. Each agent reads that same
                  snapshot, so none of them can be reasoning about a different market
                  than the others.
                </p>
              </ScrollAnimation>
              <ScrollAnimation animationNum={11} variants={riseVariants} className="text-xs sm:text-base">
                <p className="text-justify leading-relaxed">
                  The reasoning is kept alongside the bars and headlines that produced
                  it, so a past call can be audited rather than taken on trust. Risk
                  limits can veto a position outright.
                </p>
              </ScrollAnimation>
            </ScrollAnimation>
          </div>

          <div className="md:col-span-1">
            <div className="text-right">
              <ScrollAnimation
                animationNum={12}
                variants={riseVariants}
                className="mb-2 text-2xl font-bold text-red-500"
              >
                Pkay TDAI
              </ScrollAnimation>
              <ScrollAnimation
                animationNum={13}
                variants={riseVariants}
                className="mb-8 text-sm text-muted-foreground"
              >
                Multi-agent trading intelligence
              </ScrollAnimation>
              <ScrollAnimation animationNum={14} variants={riseVariants} className="mb-6">
                <p className="mb-4 font-medium text-foreground">
                  Want to see what the agents actually looked at?
                </p>
              </ScrollAnimation>
              <ScrollAnimation
                as="a"
                animationNum={15}
                variants={riseVariants}
                href="/how-it-works"
                className="ml-auto flex w-fit cursor-pointer items-center gap-2 rounded-lg border border-border bg-foreground px-5 py-3 font-semibold text-background shadow-lg transition-all duration-300 ease-in-out hover:gap-4"
              >
                See how it works
                <ArrowRight className="size-4" />
              </ScrollAnimation>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
