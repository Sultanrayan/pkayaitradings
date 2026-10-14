"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { cn } from "cn";

/**
 * AI text loading indicator, adapted from the 21st.dev
 * `@kokonutd/components/ai-text-loading`.
 *
 * Cycles through status phrases while sweeping a shimmering gradient across
 * the clipped text. Use while the AI is thinking/generating.
 */

export interface AITextLoadingProps {
  texts?: string[];
  intervalMs?: number;
  className?: string;
}

export function AITextLoading({
  texts = ["Thinking...", "Processing...", "Analyzing...", "Computing...", "Almost..."],
  intervalMs = 1500,
  className,
}: AITextLoadingProps) {
  const [index, setIndex] = React.useState(0);

  React.useEffect(() => {
    const timer = window.setInterval(() => setIndex((value) => (value + 1) % texts.length), intervalMs);
    return () => window.clearInterval(timer);
  }, [texts.length, intervalMs]);

  return (
    // Sized and aligned like an assistant message bubble. This previously
    // rendered as `text-3xl font-bold` inside a centred flex, which filled the
    // viewport as one oversized heading while a query was in flight.
    <div className="flex w-full justify-start">
      <motion.div
        animate={{ opacity: 1 }}
        initial={{ opacity: 0 }}
        transition={{ duration: 0.25 }}
        className="inline-flex max-w-[85%] items-center rounded-xl rounded-bl-sm border border-border bg-muted px-3 py-2"
      >
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={texts[index]}
            animate={{ opacity: 1, y: 0 }}
            initial={{ opacity: 0, y: 6 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
            className={cn(
              "whitespace-nowrap text-[13px] font-normal text-muted-foreground",
              className,
            )}
          >
            {texts[index]}
          </motion.span>
        </AnimatePresence>
      </motion.div>
    </div>
  );
}