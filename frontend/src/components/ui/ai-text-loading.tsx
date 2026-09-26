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
    <div className="flex items-center justify-center p-6">
      <motion.div
        animate={{ opacity: 1 }}
        initial={{ opacity: 0 }}
        transition={{ duration: 0.4 }}
        className="relative w-full px-4 py-2"
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={texts[index]}
            animate={{ opacity: 1, y: 0, backgroundPosition: ["200% center", "-200% center"] }}
            initial={{ opacity: 0, y: 20 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{
              opacity: { duration: 0.3 },
              y: { duration: 0.3 },
              backgroundPosition: { duration: 2.5, ease: "linear", repeat: Number.POSITIVE_INFINITY },
            }}
            className={cn(
              "flex min-w-max justify-center whitespace-nowrap bg-[length:200%_100%] bg-gradient-to-r from-neutral-950 via-neutral-400 to-neutral-950 bg-clip-text text-3xl font-bold text-transparent dark:from-white dark:via-neutral-600 dark:to-white",
              className,
            )}
          >
            {texts[index]}
          </motion.div>
        </AnimatePresence>
      </motion.div>
    </div>
  );
}