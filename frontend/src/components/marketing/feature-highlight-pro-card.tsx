"use client";

import { motion } from "framer-motion";
import { BadgeCheck, CheckCircle2, Check, Crown, Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";

interface CheckoutView {
  plan: string;
  paymentId: string;
  qrImage: string;
  amount: number;
}

const PRO_FEATURES = [
  "150 analyses per month",
  "All four agents, one decision",
  "Live XAUUSD + BTCUSD data",
  "Order-flow & HMM regime analysis",
  "Episodic memory + LLM review",
];

/**
 * Pro upgrade card following the 21st.dev "Feature Highlight Pro Card" design:
 * a floating, premium card with ultra-rounded corners, a soft glow background
 * and a smoothly floating highlight image (the KHQR), with fade-and-rise
 * entrance animation.
 */
export function FeatureHighlightProCard({
  checkout,
  checking,
  paid,
  onCheck,
  onCancel,
}: {
  checkout: CheckoutView;
  checking: boolean;
  paid: boolean;
  onCheck: () => void;
  onCancel: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="mx-auto w-full max-w-md"
    >
      <div className="relative overflow-hidden rounded-[2.5rem] border border-white/10 bg-gradient-to-b from-card to-card/60 p-8 shadow-2xl">
        {/* Soft glow background */}
        <div
          aria-hidden
          className="pointer-events-none absolute -top-24 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full bg-[#003AF9]/30 blur-3xl"
        />
        <div
          aria-hidden
          className="pointer-events-none absolute -bottom-24 right-0 h-56 w-56 rounded-full bg-[#003AF9]/20 blur-3xl"
        />

        <div className="relative">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div>
              <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
                Pkay TDAI
              </p>
              <h1 className="mt-1 text-2xl font-bold tracking-tight text-foreground">Pro plan</h1>
            </div>
            <span className="flex items-center gap-1.5 rounded-full bg-[#003AF9]/15 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-[#003AF9]">
              <Crown className="size-3.5" />
              Pro
            </span>
          </div>

          <div className="mt-3 flex items-baseline gap-1">
            <span className="font-serif text-5xl font-medium tracking-tight text-foreground">
              ${checkout.amount.toFixed(2)}
            </span>
            <span className="text-sm text-muted-foreground">/ 30 days</span>
          </div>

          {/* Feature checklist */}
          <ul className="mt-6 space-y-2.5">
            {PRO_FEATURES.map((feature) => (
              <li key={feature} className="flex items-start gap-2.5 text-sm text-foreground">
                <span className="mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full bg-[#003AF9]/10 text-[#003AF9]">
                  <Check className="size-3.5" />
                </span>
                {feature}
              </li>
            ))}
          </ul>

          {/* Floating highlight image (KHQR) */}
          <div className="mt-8 flex justify-center">
            <motion.div
              animate={{ y: [0, -12, 0] }}
              transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
              className="relative"
            >
              <div
                aria-hidden
                className="absolute -inset-4 rounded-[2rem] bg-[#003AF9]/20 blur-2xl"
              />
              <motion.div
                animate={paid ? { opacity: 0.4 } : { opacity: 1 }}
                className="relative rounded-[1.75rem] border border-white/10 bg-white p-5 shadow-xl"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={checkout.qrImage}
                  alt="KHQR payment code"
                  className="size-52 object-contain"
                />
              </motion.div>
            </motion.div>
          </div>

          <div className="mt-6 text-center">
            {paid ? (
              <div className="flex items-center justify-center gap-2 text-bull">
                <CheckCircle2 className="size-5" />
                <span className="text-sm font-medium">Payment confirmed — Pro is active</span>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                Scan with your banking app to pay. Your Pro plan activates automatically once
                confirmed.
              </p>
            )}
          </div>

          {/* Actions */}
          <div className="mt-6 grid grid-cols-2 gap-3">
            <Button className="gap-2" disabled={checking || paid} onClick={onCheck}>
              {checking ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <BadgeCheck className="size-4" />
              )}
              I&apos;ve paid
            </Button>
            <Button variant="outline" className="gap-2" onClick={onCancel} disabled={paid}>
              <X className="size-4" />
              Cancel
            </Button>
          </div>
          <p className="mt-4 text-center font-mono text-xs text-muted-foreground">
            Reference: {checkout.paymentId}
          </p>
        </div>
      </div>
    </motion.div>
  );
}