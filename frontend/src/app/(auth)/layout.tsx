import Image from "next/image";
import Link from "next/link";

export default function AuthLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="relative flex min-h-dvh items-center justify-center px-4 py-12">
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,rgba(234,179,8,0.16),transparent_55%),radial-gradient(ellipse_at_bottom,rgba(34,197,94,0.12),transparent_50%)]" />
        <div className="grid-noise absolute inset-0 opacity-40" />
        <div className="absolute inset-0 bg-gradient-to-b from-transparent to-background" />
      </div>

      <div className="w-full max-w-md">
        <Link href="/" className="mb-8 flex items-center justify-center gap-3">
          <span className="relative size-9 shrink-0 overflow-hidden rounded-lg ring-1 ring-border">
            <Image src="/logo-pkay.jpg" alt="Pkay TDAI" fill sizes="36px" className="object-cover" />
          </span>
          <span className="text-base font-semibold tracking-tight">Pkay TDAI</span>
        </Link>
        {children}
      </div>
    </div>
  );
}
