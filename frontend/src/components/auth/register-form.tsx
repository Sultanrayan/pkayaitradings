"use client";

import { useCallback, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { HoneypotField, ReCaptcha } from "@/components/auth/recaptcha";
import { writeTokenCookie } from "@/lib/auth";

const RECAPTCHA_SITE_KEY = process.env.NEXT_PUBLIC_RECAPTCHA_SITE_KEY ?? "";

export function RegisterForm() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Anti-bot signals, all verified server-side.
  const [token, setToken] = useState<string | null>(null);
  const [honeypot, setHoneypot] = useState("");
  const [recaptchaKey, setRecaptchaKey] = useState(0);
  const [formStartedAt] = useState(() => Date.now() / 1000);

  const handleToken = useCallback((next: string | null) => setToken(next), []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      setLoading(false);
      return;
    }

    try {
      const response = await fetch("/api/v1/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name,
          email,
          password,
          recaptcha_token: token ?? "",
          form_started_at: formStartedAt,
          website: honeypot,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        setError(data.detail || "Registration failed");
        setLoading(false);
        // The token is single-use and short-lived; take a fresh challenge.
        setToken(null);
        setRecaptchaKey((key) => key + 1);
        return;
      }

      // Store token in cookie
      writeTokenCookie(data.token);

      // Redirect to dashboard
      router.push("/dashboard");
      router.refresh();
    } catch {
      setError("An error occurred. Please try again.");
      setLoading(false);
      setToken(null);
      setRecaptchaKey((key) => key + 1);
    }
  };

  const needsVerification = Boolean(RECAPTCHA_SITE_KEY) && !token;

  return (
    <form onSubmit={handleSubmit} className="relative space-y-4">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <HoneypotField value={honeypot} onChange={setHoneypot} />

      <div className="space-y-2">
        <Label htmlFor="name">Full Name</Label>
        <Input
          id="name"
          type="text"
          placeholder="John Doe"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          disabled={loading}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={loading}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          type="password"
          placeholder="Enter your password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          disabled={loading}
        />
        <p className="text-xs text-muted-foreground">Must be at least 8 characters</p>
      </div>

      <ReCaptcha
        siteKey={RECAPTCHA_SITE_KEY}
        onTokenChange={handleToken}
        resetKey={recaptchaKey}
      />

      <Button type="submit" className="w-full" disabled={loading || needsVerification}>
        {loading ? "Creating account..." : "Create account"}
      </Button>
    </form>
  );
}