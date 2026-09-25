"use client";

import Link from "next/link";

import { GoogleSignIn } from "@/components/auth/google-sign-in";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function RegisterPage() {
  return (
    <Card className="bg-card/80 backdrop-blur ring-border">
      <CardHeader>
        <CardTitle className="text-lg">Create your account</CardTitle>
        <CardDescription>Sign up with Google to get started.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <GoogleSignIn label="Sign up with Google" />
        <p className="text-center text-xs text-muted-foreground">
          Already registered?{" "}
          <Link href="/login" className="text-foreground underline-offset-4 hover:underline">
            Sign in
          </Link>
        </p>
      </CardContent>
    </Card>
  );
}