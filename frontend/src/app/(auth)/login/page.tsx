"use client";

import Link from "next/link";

import { GoogleSignIn } from "@/components/auth/google-sign-in";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  return (
    <Card className="bg-card/80 backdrop-blur ring-border">
      <CardHeader>
        <CardTitle className="text-lg">Sign in</CardTitle>
        <CardDescription>Continue with Google to open the console.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <GoogleSignIn label="Continue with Google" />
        <p className="text-center text-xs text-muted-foreground">
          New here?{" "}
          <Link href="/register" className="text-foreground underline-offset-4 hover:underline">
            Create an account
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}