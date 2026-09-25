"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { useAuth } from "@/components/auth-provider";
import { FeatureHighlightProCard } from "@/components/marketing/feature-highlight-pro-card";
import { FooterSection } from "@/components/marketing/footer-section";
import { PaymentCard } from "@/components/marketing/payment-card";
import { SiteHeader } from "@/components/marketing/site-header";
import { api, type CheckoutResult } from "@/lib/api";

const POLL_INTERVAL_MS = 4000;
const POLL_ATTEMPTS = 30;

export default function CheckoutPage() {
  const router = useRouter();
  const { user, loading } = useAuth();
  const [checkout, setCheckout] = useState<CheckoutResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [paid, setPaid] = useState(false);

  useEffect(() => {
    if (loading || user) return;
    const next = encodeURIComponent(`/pricing/checkout${window.location.search}`);
    router.replace(`/login?next=${next}`);
  }, [user, loading, router]);

  const verify = useCallback(async (paymentId: string): Promise<boolean> => {
    setChecking(true);
    try {
      const result = await api.billingVerify(paymentId);
      if (result.paid) {
        setPaid(true);
        toast.success("Payment received — your plan is active.");
        return true;
      }
    } catch {
      // keep polling
    } finally {
      setChecking(false);
    }
    return false;
  }, []);

  useEffect(() => {
    if (!user) return;
    let active = true;
    void (async () => {
      const param = new URLSearchParams(window.location.search).get("plan");
      const targetPlan: "pro" | "ultra" = param === "ultra" ? "ultra" : "pro";
      try {
        const result = await api.billingCheckout(targetPlan);
        if (!active) return;
        setCheckout(result);
        void (async () => {
          for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt += 1) {
            await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
            if (await verify(result.payment_id)) return;
          }
        })();
      } catch (cause) {
        if (active) setError(cause instanceof Error ? cause.message : "Checkout failed");
      }
    })();
    return () => {
      active = false;
    };
  }, [user, verify]);

  const next = encodeURIComponent("/pricing/checkout?plan=pro");

  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="px-6 py-14">
        <div className="mx-auto max-w-md">
          <div className="mb-6 text-center">
            <p className="text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
              Secure payment
            </p>
            <h1 className="mt-2 font-serif text-3xl font-medium tracking-tight">
              Complete your upgrade
            </h1>
          </div>

          {!user ? (
            <div className="rounded-2xl border border-border bg-card/60 p-8 text-center text-sm text-muted-foreground">
              <p>You need to sign in before upgrading.</p>
              <div className="mt-4">
                <Link
                  href={`/login?next=${next}`}
                  className="text-foreground underline-offset-4 hover:underline"
                >
                  Sign in to continue
                </Link>
              </div>
            </div>
          ) : checkout ? (
            checkout.plan === "pro" ? (
              <FeatureHighlightProCard
                checkout={{
                  plan: checkout.plan,
                  paymentId: checkout.payment_id,
                  qrImage: checkout.qr_image,
                  amount: checkout.amount,
                }}
                checking={checking}
                paid={paid}
                onCheck={() => void verify(checkout.payment_id)}
                onCancel={() => router.push("/pricing")}
              />
            ) : (
              <PaymentCard
                checkout={{
                  plan: checkout.plan,
                  paymentId: checkout.payment_id,
                  qrImage: checkout.qr_image,
                  amount: checkout.amount,
                }}
                checking={checking}
                paid={paid}
                onCheck={() => void verify(checkout.payment_id)}
                onCancel={() => router.push("/pricing")}
              />
            )
          ) : error ? (
            <div className="rounded-2xl border border-bear/30 bg-bear/5 p-8 text-center">
              <p className="text-sm text-bear">{error}</p>
              <p className="mt-4">
                <Link
                  href="/pricing"
                  className="text-sm text-foreground underline-offset-4 hover:underline"
                >
                  Back to pricing
                </Link>
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-border bg-card/60 p-10 text-center">
              <Loader2 className="size-6 animate-spin text-muted-foreground" />
              <p className="text-sm text-muted-foreground">Creating your KHQR payment…</p>
            </div>
          )}
        </div>
      </main>

      <FooterSection />
    </div>
  );
}