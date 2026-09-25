"use client";

import { motion } from "framer-motion";
import {
  BadgeCheck,
  CheckCircle2,
  Copy,
  Loader2,
  RefreshCw,
  ShieldCheck,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";

interface CheckoutView {
  plan: string;
  paymentId: string;
  qrImage: string;
  amount: number;
}

/**
 * Payment card inspired by the 21st.dev "Insurance Card": a modern, animated
 * card that displays the plan being purchased, the scannable KHQR code and
 * quick actions.
 */
export function PaymentCard({
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
  const copyReference = async () => {
    try {
      await navigator.clipboard.writeText(checkout.paymentId);
    } catch {
      // clipboard unavailable — ignore
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 24 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: "easeOut" }}
      className="mx-auto w-full max-w-md overflow-hidden rounded-3xl border border-border bg-card shadow-xl"
    >
      {/* Header */}
      <div className="bg-gradient-to-br from-[#003AF9] to-[#001e80] p-6 text-white">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-[11px] uppercase tracking-[0.2em] text-white/60">Pkay TDAI</p>
            <h1 className="mt-1 text-2xl font-bold tracking-tight capitalize">
              {checkout.plan} plan
            </h1>
          </div>
          <ShieldCheck className="size-8 text-white/80" />
        </div>
        <div className="mt-4 flex items-baseline gap-1">
          <span className="font-serif text-4xl font-medium">${checkout.amount.toFixed(2)}</span>
          <span className="text-sm text-white/70">/ 30 days</span>
        </div>
      </div>

      {/* QR code */}
      <div className="px-6 py-6">
        <div className="flex flex-col items-center gap-4">
          <motion.div
            animate={paid ? { opacity: 0.4 } : { opacity: 1 }}
            className="rounded-2xl border border-border bg-white p-4 shadow-sm"
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={checkout.qrImage} alt="KHQR payment code" className="size-52 object-contain" />
          </motion.div>

          <div className="text-center">
            {paid ? (
              <div className="flex items-center gap-2 text-bull">
                <CheckCircle2 className="size-5" />
                <span className="text-sm font-medium">Payment confirmed — plan active</span>
              </div>
            ) : (
              <>
                <p className="text-sm font-medium text-foreground">Scan with your banking app</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  The plan activates automatically once the payment is confirmed.
                </p>
              </>
            )}
          </div>
        </div>

        {/* Details */}
        <div className="mt-6 space-y-3 rounded-2xl border border-border bg-muted/30 p-4">
          <DetailRow icon={<BadgeCheck className="size-4 text-bull" />} label="Plan" value={checkout.plan} />
          <DetailRow icon={<RefreshCw className="size-4 text-bull" />} label="Billing" value="30-day period" />
          <DetailRow
            icon={<Copy className="size-4 text-bull" />}
            label="Reference"
            value={checkout.paymentId}
            copyable
            onCopy={copyReference}
          />
        </div>

        {/* Quick actions */}
        <div className="mt-6 grid grid-cols-2 gap-3">
          <Button className="gap-2" disabled={checking || paid} onClick={onCheck}>
            {checking ? <Loader2 className="size-4 animate-spin" /> : <BadgeCheck className="size-4" />}
            I&apos;ve paid
          </Button>
          <Button variant="outline" className="gap-2" onClick={onCancel} disabled={paid}>
            <X className="size-4" />
            Cancel
          </Button>
        </div>
      </div>
    </motion.div>
  );
}

function DetailRow({
  icon,
  label,
  value,
  copyable,
  onCopy,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  copyable?: boolean;
  onCopy?: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 text-sm">
      <span className="flex items-center gap-2 text-muted-foreground">
        {icon}
        {label}
      </span>
      <span className="flex items-center gap-2">
        <span className="font-mono text-xs text-foreground">{value}</span>
        {copyable && onCopy ? (
          <button
            type="button"
            onClick={onCopy}
            aria-label="Copy payment reference"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <Copy className="size-3.5" />
          </button>
        ) : null}
      </span>
    </div>
  );
}