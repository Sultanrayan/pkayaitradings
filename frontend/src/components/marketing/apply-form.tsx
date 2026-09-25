"use client";

import { useCallback, useState } from "react";
import { CheckCircle2, Loader2, Send } from "lucide-react";

import { Turnstile } from "@/components/auth/turnstile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

const TURNSTILE_SITE_KEY = process.env.NEXT_PUBLIC_TURNSTILE_SITE_KEY ?? "";

/**
 * Form that collects a developer's application for API access.
 *
 * On submit the request appears on the admin page for review; the developer is
 * told to allow 24–48 hours.
 */
export function ApplyForm() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [useCase, setUseCase] = useState("");
  const [website, setWebsite] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);

  const handleToken = useCallback((token: string | null) => {
    setTurnstileToken(token);
    setError(null);
  }, []);

  const submit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (submitting) return;
    if (!turnstileToken && TURNSTILE_SITE_KEY) {
      setError("Complete the security check to continue.");
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await api.applyForAccess({
        name,
        email,
        use_case: useCase,
        website,
        turnstile_token: turnstileToken ?? undefined,
      });
      setSubmitted(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Submission failed");
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="flex flex-col items-center rounded-2xl border border-bull/30 bg-bull/5 px-6 py-12 text-center">
        <div className="mb-4 flex size-14 items-center justify-center rounded-full bg-bull/10">
          <CheckCircle2 className="size-7 text-bull" />
        </div>
        <h2 className="text-xl font-semibold tracking-tight text-foreground">
          Thank You for Submit!
        </h2>
        <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground">
          Your information is currently under review. Please allow{" "}
          <span className="text-foreground">24 to 48 hours</span> for approval. Once approved,
          your API access token will be emailed to{" "}
          <span className="text-foreground">{email}</span>.
        </p>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-5">
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="space-y-1.5">
          <Label htmlFor="apply-name">Name</Label>
          <Input
            id="apply-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Ada Lovelace"
            autoComplete="name"
            required
            maxLength={80}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="apply-email">Email</Label>
          <Input
            id="apply-email"
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            required
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="apply-use-case">Intended use case</Label>
        <textarea
          id="apply-use-case"
          value={useCase}
          onChange={(event) => setUseCase(event.target.value)}
          placeholder="Tell us what you plan to build with the agent endpoints…"
          required
          minLength={5}
          maxLength={2000}
          rows={5}
          className="w-full resize-y rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
        />
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="apply-website">Website link</Label>
        <Input
          id="apply-website"
          type="url"
          value={website}
          onChange={(event) => setWebsite(event.target.value)}
          placeholder="https://your-project.com"
          autoComplete="url"
          maxLength={300}
        />
      </div>

      {error ? (
        <p className="rounded-lg border border-bear/30 bg-bear/5 px-3 py-2 text-xs text-bear">
          {error}
        </p>
      ) : null}

      <Turnstile siteKey={TURNSTILE_SITE_KEY} onTokenChange={handleToken} />

      <Button type="submit" disabled={submitting} className="gap-2">
        {submitting ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        Submit application
      </Button>
    </form>
  );
}
