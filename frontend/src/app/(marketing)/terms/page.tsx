import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";

export const metadata = { title: "Terms of service — Pkay TDAI" };

export default function TermsPage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="font-serif text-4xl font-medium tracking-tight">Terms of service</h1>
        <p className="mt-3 text-xs text-muted-foreground">Last updated: 2026-09-21</p>

        <div className="mt-8 space-y-6 text-sm leading-relaxed text-muted-foreground">
          <section>
            <h2 className="font-medium text-foreground">1. Service</h2>
            <p className="mt-2">
              Pkay TDAI provides a multi-agent AI analysis tool for educational and research
              purposes. The output is not financial advice and no guarantee is made about its
              accuracy or profitability.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">2. Plans and billing</h2>
            <p className="mt-2">
              The service offers Free (20 analyses per month), Pro (150 analyses per month, USD 15)
              and Ultra (unlimited analyses, USD 65) plans. Paid plans are billed per 30-day period
              via Khpay. If a payment is not made by the end of the billing period, the plan is
              automatically deactivated and the account reverts to Free.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">3. Acceptable use</h2>
            <p className="mt-2">
              You agree not to abuse the platform, circumvent usage limits, or copy or reproduce
              any part of the user interface without permission. You are responsible for keeping
              your account credentials secure.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">4. Risk disclosure</h2>
            <p className="mt-2">
              Trading financial instruments carries significant risk. Past performance does not
              guarantee future results. The operators are not responsible for any financial losses
              incurred using this software.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">5. Changes</h2>
            <p className="mt-2">
              We may update these terms. Continued use after changes constitutes acceptance.
            </p>
          </section>
        </div>
      </main>

      <FooterSection />
    </div>
  );
}