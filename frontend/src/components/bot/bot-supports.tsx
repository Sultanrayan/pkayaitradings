"use client";

import { Send } from "lucide-react";
import { motion } from "framer-motion";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

const TELEGRAM_URL = "https://t.me/pkaytradingaiofficial";

/**
 * Floating Telegram launcher, bottom-left of every page. Opens the official
 * community channel in a new tab.
 */
export function BotSupports() {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <motion.a
          href={TELEGRAM_URL}
          target="_blank"
          rel="noopener noreferrer"
          aria-label="Open the Pkay Telegram community"
          initial={{ scale: 0.8, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 18 }}
          className="fixed bottom-5 left-5 z-50 flex size-12 items-center justify-center rounded-full bg-[#229ED9] text-white shadow-lg shadow-black/40 ring-1 ring-black/20 transition-transform hover:scale-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Send className="size-5" />
        </motion.a>
      </TooltipTrigger>
      <TooltipContent side="top" sideOffset={10}>
        Telegram community
      </TooltipContent>
    </Tooltip>
  );
}
