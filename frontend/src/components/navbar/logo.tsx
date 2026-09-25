import Image from "next/image";
import Link from "next/link";

/** Brand logo tied to the dashboard landing page. */
export function Logo() {
  return (
    <Link href="/dashboard" className="flex shrink-0 items-center gap-2.5" aria-label="Pkay dashboard">
      <span className="relative size-8 shrink-0 overflow-hidden rounded-lg ring-1 ring-border">
        <Image src="/logo-pkay.jpg" alt="Pkay" fill sizes="32px" priority className="object-cover" />
      </span>
      <span className="hidden text-sm font-semibold tracking-tight sm:inline">Pkay</span>
    </Link>
  );
}