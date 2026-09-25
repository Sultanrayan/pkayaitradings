import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";

export const metadata = { title: "Contact — Pkay TDAI" };

export default function ContactPage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="font-serif text-4xl font-medium tracking-tight">Contact</h1>
        <p className="mt-3 text-sm text-muted-foreground">
          The fastest way to reach us is our Telegram channel.
        </p>

        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          <a
            href="https://t.me/pkaytradingaiofficial"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-2xl border border-border bg-card/60 p-6 transition-colors hover:border-foreground/40"
          >
            <h2 className="font-medium text-foreground">Telegram</h2>
            <p className="mt-2 text-sm text-muted-foreground">
              Join the community and get support.
            </p>
            <p className="mt-4 text-xs text-foreground">t.me/pkaytradingaiofficial</p>
          </a>

          <a
            href="https://www.tiktok.com/@userbrbthaerrorhx"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-2xl border border-border bg-card/60 p-6 transition-colors hover:border-foreground/40"
          >
            <h2 className="font-medium text-foreground">TikTok</h2>
            <p className="mt-2 text-sm text-muted-foreground">Updates, tips and analysis.</p>
            <p className="mt-4 text-xs text-foreground">@userbrbthaerrorhx</p>
          </a>
        </div>

        <div className="mt-6 rounded-2xl border border-border bg-card/60 p-6">
          <h2 className="font-medium text-foreground">Billing support</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            For payment or plan questions, message the Telegram channel with your account email and
            we will help as soon as possible.
          </p>
        </div>
      </main>

      <FooterSection />
    </div>
  );
}