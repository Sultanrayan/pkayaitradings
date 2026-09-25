import Link from "next/link";
import { ArrowLeft } from "lucide-react";

import { ApplyForm } from "@/components/marketing/apply-form";
import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";

export const metadata = { title: "Apply for API access — Pkay TDAI" };

export default function ApplyPage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="px-4 py-12">
        <div className="mx-auto max-w-2xl">
          <Link
            href="/api-reference"
            className="mb-8 inline-flex items-center gap-1.5 text-xs text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
          >
            <ArrowLeft className="size-3.5" />
            Back to API reference
          </Link>

          <div className="mb-8 space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight">Apply for API access</h1>
            <p className="text-sm leading-relaxed text-muted-foreground">
              The agent endpoints require a bearer token. Tell us what you plan to build and we
              will review your request — approved developers receive their token by email.
            </p>
          </div>

          <div className="rounded-2xl border border-border bg-card/60 p-6 sm:p-8">
            <ApplyForm />
          </div>
        </div>
      </main>

      <FooterSection />
    </div>
  );
}
