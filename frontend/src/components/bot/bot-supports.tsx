"use client";

import { useEffect, useRef, useState } from "react";
import { Bot, X } from "lucide-react";
import { motion } from "framer-motion";

import { BotPanel } from "@/components/bot/bot-panel";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

/**
 * Floating circular "Bot Supports" launcher, visible across the app. Opens a
 * context-aware AI support panel that learns the selected asset & timeframe.
 */
export function BotSupports() {
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <>
      <Tooltip>
        <TooltipTrigger asChild>
          <motion.button
            type="button"
            aria-label="Bot Supports"
            onClick={() => setOpen((value) => !value)}
            initial={{ scale: 0.8, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ type: "spring", stiffness: 260, damping: 18 }}
            className="fixed bottom-5 right-5 z-50 flex size-12 items-center justify-center rounded-full bg-foreground text-background shadow-lg shadow-black/40 ring-1 ring-border transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {open ? <X className="size-5" /> : <Bot className="size-5" />}
          </motion.button>
        </TooltipTrigger>
        <TooltipContent side="top" sideOffset={10}>
          Bot Supports
        </TooltipContent>
      </Tooltip>

      {open ? (
        <div ref={panelRef} className="fixed bottom-20 right-4 z-50 w-[calc(100vw-2rem)] max-w-sm sm:right-6">
          <BotPanel onClose={() => setOpen(false)} />
        </div>
      ) : null}
    </>
  );
}