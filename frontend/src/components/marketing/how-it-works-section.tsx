"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { cn } from "cn";

/**
 * Homepage "How it works" section, headlined "Your Journey Starts Here".
 *
 * Source: the 21st.dev shadcn registry document for
 * `https://21st.dev/@ayushmxxn/components/feature-section`, fetched from the
 * registry API at `/r/ayushmxxn/feature-section` (4229 chars,
 * `/components/blocks/feature-section.tsx`, `type: registry:block`).
 *
 * Note for anyone re-fetching this: `21st get 5541` serves a *different* component
 * that shares the name — 4537 chars, `src/components/ui/feature-section.tsx`,
 * `type: registry:component`, published under the `ruixen.ui` namespace. That one is
 * a two-column layout with an infinite scrolling card. It is not this design.
 *
 * Kept from the source: the centred title, the two-column order flip (image first on
 * mobile), the numbered/checkmarked circles that mark completed steps, the dimming of
 * inactive rows, the timed auto-advance, the `AnimatePresence mode="wait"` image
 * cross-fade with its upward rotateX entry and downward exit, and the bottom
 * gradient over the image.
 *
 * Four deliberate departures, each necessary or corrective:
 *
 * 1. `cn` is imported from the `cn` package. The source imports `@/lib/utils`, which
 *    does not exist in this project.
 * 2. `imageHeight` is actually applied. Upstream destructures the prop and then
 *    ignores it, hardcoding the height ladder instead, so the knob does nothing.
 *    The default reproduces upstream's rendered classes exactly.
 * 3. The auto-advance timer is created once rather than torn down and rebuilt every
 *    100ms. Upstream lists `progress` in its dependency array, so each tick
 *    re-creates the interval; timing is unchanged but it cannot drift.
 * 4. Transitions are dropped under `prefers-reduced-motion`. The rotation itself is
 *    kept, because freezing it would hide two of the three panels from anyone who
 *    cannot tolerate the animation.
 */

interface Feature {
  /** Short label for the step. Also used for the fallback heading. */
  step: string;
  title?: string;
  content: string;
  image: string;
}

interface FeatureStepsProps {
  features: Feature[];
  className?: string;
  title?: string;
  /** Milliseconds each feature is held before advancing. */
  autoPlayInterval?: number;
  imageHeight?: string;
  /** Anchor target. Upstream has no id support, and the homepage nav needs one. */
  id?: string;
}

const TICK_MS = 100;

export function FeatureSteps({
  features,
  className,
  title = "How to get Started",
  autoPlayInterval = 3000,
  imageHeight = "h-[200px] md:h-[300px] lg:h-[400px]",
  id,
}: FeatureStepsProps) {
  const [state, setState] = useState({ feature: 0, progress: 0 });
  const reducedMotion = useReducedMotion();

  const total = features.length;

  useEffect(() => {
    if (total === 0) return;
    // Upstream advances by `100 / (autoPlayInterval / 100)` per 100ms tick, which
    // fills the bar in autoPlayInterval ms. Same arithmetic, one interval.
    const perTick = 100 / (autoPlayInterval / TICK_MS);
    const id = window.setInterval(() => {
      setState((previous) => {
        const next = previous.progress + perTick;
        return next < 100
          ? { ...previous, progress: next }
          : { feature: (previous.feature + 1) % total, progress: 0 };
      });
    }, TICK_MS);
    return () => window.clearInterval(id);
  }, [autoPlayInterval, total]);

  const currentFeature = state.feature;

  return (
    <div id={id} className={cn("p-8 md:p-12", className)}>
      <div className="mx-auto w-full max-w-7xl">
        <h2 className="mb-10 text-center text-3xl font-bold md:text-4xl lg:text-5xl">
          {title}
        </h2>

        <div className="flex flex-col gap-6 md:grid md:grid-cols-2 md:gap-10">
          <div className="order-2 space-y-8 md:order-1">
            {features.map((feature, index) => (
              <motion.div
                key={feature.step}
                className="flex items-center gap-6 md:gap-8"
                initial={{ opacity: 0.3 }}
                animate={{ opacity: index === currentFeature ? 1 : 0.3 }}
                transition={reducedMotion ? { duration: 0 } : { duration: 0.5 }}
              >
                <motion.div
                  className={cn(
                    "flex size-8 items-center justify-center rounded-full border-2 md:size-10",
                    index === currentFeature
                      ? "scale-110 border-primary bg-primary text-primary-foreground"
                      : "border-muted-foreground bg-muted",
                  )}
                >
                  {index <= currentFeature ? (
                    <span className="text-lg font-bold">✓</span>
                  ) : (
                    <span className="text-lg font-semibold">{index + 1}</span>
                  )}
                </motion.div>

                <div className="flex-1">
                  <h3 className="text-xl font-semibold md:text-2xl">
                    {feature.title || feature.step}
                  </h3>
                  <p className="text-sm text-muted-foreground md:text-lg">
                    {feature.content}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>

          <div
            className={cn(
              "relative order-1 overflow-hidden rounded-lg md:order-2",
              imageHeight,
            )}
          >
            <AnimatePresence mode="wait">
              {features.map(
                (feature, index) =>
                  index === currentFeature && (
                    <motion.div
                      key={feature.step}
                      className="absolute inset-0 overflow-hidden rounded-lg"
                      initial={reducedMotion ? false : { y: 100, opacity: 0, rotateX: -20 }}
                      animate={{ y: 0, opacity: 1, rotateX: 0 }}
                      exit={reducedMotion ? undefined : { y: -100, opacity: 0, rotateX: 20 }}
                      transition={
                        reducedMotion
                          ? { duration: 0 }
                          : { duration: 0.5, ease: "easeInOut" }
                      }
                    >
                      <Image
                        src={feature.image}
                        // Decorative: the step's title and content sit directly
                        // beside this panel, so describing the image would either
                        // duplicate them or invent a product claim.
                        alt=""
                        className="h-full w-full object-cover"
                        width={1000}
                        height={500}
                        sizes="(min-width: 768px) 50vw, 100vw"
                        priority={index === 0}
                      />
                      <div className="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-background via-background/50 to-transparent" />
                    </motion.div>
                  ),
              )}
            </AnimatePresence>
          </div>
        </div>
      </div>
    </div>
  );
}

/**
 * The three pipeline stages, one per supplied image.
 *
 * The pipeline runs four agents; stages 3 and 4 share a row here because only three
 * images were supplied. Both agents are still named in that row's copy.
 */
const FEATURES: Feature[] = [
  {
    step: "Step 1",
    title: "Read the market",
    content:
      "Live prices stream in from biquote. Candles, the economic calendar and news headlines are collected into one feed.",
    image: "/pic-1.png",
  },
  {
    step: "Step 2",
    title: "Agents analyse",
    content:
      "The Technical Analyst studies price and indicators. The News Monitor scores events and sentiment.",
    image: "/pic-2.png",
  },
  {
    step: "Step 3",
    title: "Risk checks, then decides",
    content:
      "The Risk Manager sets position size and stop loss. The Decision Maker combines the signals into one call.",
    image: "/pic-3.png",
  },
];

export function HowItWorksSection() {
  return (
    // The section is the landmark; the anchor sits on FeatureSteps' own root so the
    // scroll target and the component's outermost element cannot drift apart.
    <section className="bg-background text-foreground">
      <FeatureSteps
        id="how-it-works"
        features={FEATURES}
        title="Your Journey Starts Here"
      />
    </section>
  );
}
