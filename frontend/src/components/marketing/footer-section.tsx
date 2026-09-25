"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { motion, type Variants } from "framer-motion";
import { toast } from "sonner";
import { cn } from "cn";

/**
 * Page footer: a branded blue card next to a links/newsletter card. Socials are
 * limited to the official Telegram and TikTok channels.
 */

const CURRENT_YEAR = new Date().getFullYear();
const BRAND_TITLE = "Multi-agent analysis for gold and bitcoin.";

const TELEGRAM_URL = "https://t.me/pkaytradingaiofficial";
const TIKTOK_URL = "https://www.tiktok.com/@userbrbthaerrorhx";

interface FooterLink {
  label: string;
  href: string;
}

interface FooterColumn {
  title: string;
  links: FooterLink[];
}

const FOOTER_COLUMNS: FooterColumn[] = [
  {
    title: "Product",
    links: [
      { label: "Pricing", href: "/pricing" },
      { label: "Dashboard", href: "/dashboard" },
      { label: "Charts", href: "/charts" },
      { label: "Signals", href: "/signals" },
      { label: "Agents", href: "/agents" },
      { label: "Risk", href: "/risk" },
    ],
  },
  {
    title: "Resources",
    links: [
      { label: "How it works", href: "/how-it-works" },
      { label: "API Reference", href: "/api-reference" },
      { label: "Status", href: "/status" },
      { label: "Change log", href: "/changelog" },
    ],
  },
  {
    title: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Contact", href: "/contact" },
      { label: "Privacy", href: "/privacy" },
      { label: "Terms", href: "/terms" },
    ],
  },
];

const SOCIAL_LINKS = [
  { label: "Telegram", href: TELEGRAM_URL },
  { label: "TikTok", href: TIKTOK_URL },
];

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.2, delayChildren: 0.1 } },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 30 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.6, ease: "easeOut" } },
};

export function FooterSection({ className }: { className?: string }) {
  const [email, setEmail] = useState("");

  const onSubmit = (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!email.trim()) return;
    toast.success("Thanks. We'll be in touch.");
    setEmail("");
  };

  return (
    <footer className={cn("px-4 py-12", className)}>
      <motion.div
        className="mx-auto max-w-7xl"
        initial="hidden"
        whileInView="visible"
        viewport={{ once: true, margin: "-100px" }}
        variants={containerVariants}
      >
        <div className="flex h-full flex-col gap-4 md:flex-row">
          {/* Brand card */}
          <motion.div
            variants={itemVariants}
            className="relative flex min-h-[300px] w-full flex-col justify-between overflow-hidden rounded-2xl bg-[#003AF9] p-8 md:min-h-[600px] md:w-1/3 md:p-10"
          >
            <svg
              aria-hidden
              className="pointer-events-none absolute inset-0 z-0 h-full w-full opacity-90 mix-blend-multiply"
              xmlns="http://www.w3.org/2000/svg"
            >
              <filter id="footer-noise">
                <feTurbulence
                  type="fractalNoise"
                  baseFrequency="0.65"
                  numOctaves="4"
                  stitchTiles="stitch"
                />
              </filter>
              <rect width="100%" height="100%" filter="url(#footer-noise)" />
            </svg>

            <div className="relative z-10 flex items-center gap-3">
              <span className="relative size-8 shrink-0 overflow-hidden rounded-lg ring-1 ring-white/25">
                <Image src="/logo-pkay.jpg" alt="Pkay TDAI" fill sizes="32px" className="object-cover" />
              </span>
              <span className="text-xl font-bold tracking-tight text-white">Pkay TDAI</span>
            </div>

            <div className="relative z-10 space-y-6">
              <h3 className="text-lg font-bold text-white">{BRAND_TITLE}</h3>
              <div className="flex flex-wrap items-center gap-3">
                {SOCIAL_LINKS.map((social) => (
                  <a
                    key={social.label}
                    href={social.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-label={social.label}
                    className="rounded-full bg-white/10 px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-white/20"
                  >
                    {social.label}
                  </a>
                ))}
              </div>
              <p className="text-xs text-white/60">
                &copy; {CURRENT_YEAR} Pkay TDAI. All rights reserved.
              </p>
            </div>
          </motion.div>

          {/* Links + newsletter card */}
          <motion.div
            variants={itemVariants}
            className="flex min-h-[500px] w-full flex-col justify-between rounded-2xl border border-border bg-card p-8 md:min-h-[600px] md:w-2/3 md:p-12"
          >
            <div className="grid grid-cols-2 gap-8 md:grid-cols-4 md:gap-10">
              {FOOTER_COLUMNS.map((column) => (
                <div key={column.title} className="flex flex-col space-y-6">
                  <h4 className="text-lg font-bold text-foreground">{column.title}</h4>
                  <ul className="flex flex-col space-y-3 text-sm font-medium text-muted-foreground">
                    {column.links.map((link) => (
                      <li key={link.label}>
                        <Link
                          href={link.href}
                          className="transition-colors hover:text-foreground"
                        >
                          {link.label}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>

            <div className="mt-12 space-y-4 md:mt-0">
              <h4 className="text-lg font-bold text-foreground">Newsletter</h4>
              <form onSubmit={onSubmit} className="flex w-full max-w-md flex-col gap-4 sm:flex-row">
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="Enter your email"
                  className="flex-1 rounded-md border border-border bg-transparent px-4 py-3 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-foreground"
                />
                <button
                  type="submit"
                  className="rounded-md bg-foreground px-8 py-3 text-sm font-medium text-background transition-opacity hover:opacity-90"
                >
                  Subscribe
                </button>
              </form>
              <p className="max-w-md text-xs text-muted-foreground">
                &copy; {CURRENT_YEAR} Pkay TDAI. All rights reserved. Copying or reproducing any
                part of this user interface is prohibited.
              </p>
            </div>
          </motion.div>
        </div>
      </motion.div>
    </footer>
  );
}