import { FooterSection } from "@/components/marketing/footer-section";
import { SiteHeader } from "@/components/marketing/site-header";

export const metadata = { title: "Privacy — Pkay TDAI" };

export default function PrivacyPage() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main className="mx-auto max-w-3xl px-6 py-16">
        <h1 className="font-serif text-4xl font-medium tracking-tight">Privacy policy</h1>
        <p className="mt-3 text-xs text-muted-foreground">Last updated: 2026-09-21</p>

        <div className="mt-8 space-y-6 text-sm leading-relaxed text-muted-foreground">
          <section>
            <h2 className="font-medium text-foreground">1. What we collect</h2>
            <p className="mt-2">
              When you create an account we store the name and email you provide (or receive from
              Google). If you purchase a paid plan, the Khpay payment reference and your plan
              status are recorded. We do not store payment card details — payments are processed by
              Khpay.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">2. How we use it</h2>
            <p className="mt-2">
              Your account is used to authenticate you, enforce plan limits and support you.
              Analytics of your usage (such as analysis counts) are used only to operate the
              service.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">3. Sharing</h2>
            <p className="mt-2">
              We do not sell your data. Payment processing is handled by Khpay under its own terms.
              We may share data with service providers necessary to run the platform (hosting,
              email), and where required by law.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">4. Cookies</h2>
            <p className="mt-2">
              We use a session cookie to keep you signed in. Cloudflare may set security cookies
              to verify visitors.
            </p>
          </section>

          <section>
            <h2 className="font-medium text-foreground">5. Your rights</h2>
            <p className="mt-2">
              You may request access to or deletion of your account data by contacting us. Deleting
              your account removes your profile and usage history.
            </p>
          </section>
        </div>
      </main>

      <FooterSection />
    </div>
  );
}