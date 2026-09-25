import { Activity } from "lucide-react";

import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";
import SystemStatusBlock from "@/components/ui/system-status-block";

export const metadata = { title: "Status — Pkay TDAI" };

export default function StatusPage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-4xl px-6 py-16">
        <div className="flex items-center gap-2 text-[11px] uppercase tracking-[0.2em] text-muted-foreground">
          <Activity className="size-3.5" />
          System status
        </div>
        <h1 className="mt-3 font-serif text-4xl font-medium tracking-tight">System Status</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          Real-time status of the Pkay TDAI services, with 30-day uptime and incident history.
        </p>

        <div className="mt-10">
          <SystemStatusBlock />
        </div>

        <p className="mt-12 text-center text-xs text-muted-foreground">
          For incidents or questions, see the{" "}
          <a
            href="https://t.me/pkaytradingaiofficial"
            target="_blank"
            rel="noopener noreferrer"
            className="text-foreground underline-offset-4 hover:underline"
          >
            Telegram
          </a>{" "}
          channel.
        </p>
      </main>

      <FooterSection />
    </div>
  );
}