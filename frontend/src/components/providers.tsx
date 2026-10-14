"use client";

import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

/**
 * Client-side providers: tooltips and toasts.
 *
 * Theme handling lives on the document itself — `globals.css` defines `:root`
 * and `.dark` with identical (dark-only) tokens, `<html>` hardcodes the `dark`
 * class and `html { color-scheme: dark }` sets the form/scrollbar scheme. A
 * client theme provider is therefore unnecessary, and `next-themes` was
 * removed because it injects a pre-hydration detection `<script>` that React 19
 * refuses to execute when rendered inside a component.
 */
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <TooltipProvider delayDuration={200}>
      {children}
      <Toaster position="bottom-right" closeButton />
    </TooltipProvider>
  );
}
