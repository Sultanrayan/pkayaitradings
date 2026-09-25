"use client";

import { AppShell } from "@/components/app-shell";
import { SymbolProvider } from "@/components/symbol-provider";

/** Protected application shell: market context + sidebar layout. */
export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <SymbolProvider>
      <AppShell>{children}</AppShell>
    </SymbolProvider>
  );
}
