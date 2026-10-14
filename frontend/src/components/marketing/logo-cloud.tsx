import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { cn } from "cn";

import {
  BinanceIcon,
  BybitIcon,
  ChatGptIcon,
  ClaudeIcon,
  DeepSeekIcon,
  OkxIcon,
  QdrantIcon,
} from "@/components/marketing/brand-icons";
import { Button } from "@/components/ui/button";

/**
 * Logo cloud: a text card spanning three rows beside a grid of provider tiles.
 *
 * Rebuilt from the 21st.dev component
 * `@shadcnui-blocks/components/logo-cloud-14`. Its source could not be pulled
 * through the API (free tier exhausted, `403 retrieval_limit_reached`), but the
 * compiled component was recovered verbatim from the public CDN bundle, so the
 * structure and class names below are the original's.
 *
 * The original ships full-colour brand logo *artwork* as image files. This renders
 * each brand's real mark in the brand's own colour instead, from the CC0 vector
 * paths already vendored in `brand-icons.tsx`, so the page still makes no
 * third-party requests.
 *
 * The compiled original:
 *
 * * root `px-6 py-12`, grid `mx-auto mt-10 grid max-w-5xl grid-cols-2 gap-4
 *   sm:grid-cols-3 md:grid-cols-4`
 * * text card `flex flex-col rounded-xl bg-muted p-5 max-sm:col-span-full
 *   sm:row-span-3`, so it holds the first column for three rows on `sm` and above
 *   and goes full width below that
 * * headline `mb-8 max-w-[20ch] text-balance font-medium text-2xl tracking-tight
 *   sm:text-xl lg:text-2xl`
 * * button is `size="lg"` with `mt-auto max-sm:me-auto`, which pins it to the
 *   bottom of the card and pulls it left on small screens
 * * each tile is `flex w-full items-center justify-center rounded-xl bg-muted
 *   px-3 py-7` wrapping a single icon at `h-7 sm:h-8`
 *
 * The original ships nine tiles, which is exactly what fills a 4-column grid once
 * the text card has taken three cells, so this keeps nine.
 *
 * Two content notes. The headline is "Data From" rather than the original's
 * "Trusted by teams and companies around the world", which is a customer claim
 * this project cannot make. The logos are the providers this codebase is actually
 * configured against — see `PROVIDERS` below for where each one comes from.
 */

interface Provider {
  id: string;
  /** Rendered as a real brand mark when one exists in the repo. */
  Mark?: (props: { className?: string }) => React.ReactNode;
  /** Otherwise rendered as a wordmark, at a comparable optical weight. */
  wordmark?: string;
  /**
   * Brand colour. Every vendored mark is `fill="currentColor"`, so setting this on a
   * wrapper tints the glyph without touching the generated `brand-icons.tsx`.
   */
  color?: string;
}

/**
 * Six of these are the brand marks already displayed in the Capabilities section
 * (`integration-card.tsx`), so the page is consistent about which providers it
 * names. The other three have no SVG in the repo and are wordmarked instead of
 * inventing one.
 *
 * Read off `shared/config.py`: `biquote_base_url` is the candle and price feed,
 * `qdrant_api_key` is the vector store, and `broker` accepts `"mt5"`.
 *
 * The hexes are the brands' own, taken from simple-icons' published dataset (CC0,
 * the same source the vendored paths come from) rather than eyeballed. Two of them
 * cannot be used as published: simple-icons gives OKX `#000000` and Anthropic
 * `#191919`, both of which are invisible against this dark hero. OKX's identity is
 * genuinely white-on-dark, so it is set to white; ChatGPT and DeepSeek are shown in
 * their product colours (`#10A37F`, `#4D6BFE`), which is what the Capabilities
 * section already uses. The two remaining wordmarks have no verifiable brand hex, so
 * they inherit the foreground colour rather than being given an invented one.
 *
 * Three providers have no logo here: Bybit has no CC0 mark and is a text span,
 * while Biquote and MetaTrader 5 have no vector in any source this project uses.
 * Those three render as wordmarks. Anything beyond that would mean either inventing
 * a logo or shipping third-party image files at runtime, so it is left visible rather
 * than papered over.
 */
const PROVIDERS: Provider[] = [
  { id: "binance", Mark: BinanceIcon, color: "#F0B90B" },
  { id: "bybit", Mark: BybitIcon, color: "#F7A600" },
  { id: "okx", Mark: OkxIcon, color: "#FFFFFF" },
  { id: "chatgpt", Mark: ChatGptIcon, color: "#10A37F" },
  { id: "claude", Mark: ClaudeIcon, color: "#D97757" },
  { id: "deepseek", Mark: DeepSeekIcon, color: "#4D6BFE" },
  { id: "biquote", wordmark: "Biquote" },
  { id: "qdrant", Mark: QdrantIcon, color: "#DC244C" },
  { id: "metatrader", wordmark: "MetaTrader 5" },
];

export interface LogoCloudProps {
  headline: string;
  actionLabel: string;
  actionHref: string;
  /**
   * The original's root carries `px-6 py-12` because it sits directly on the page.
   * When it is embedded in the hero's media panel instead, that padding is dropped
   * by the caller.
   */
  className?: string;
}

export function LogoCloud({
  headline,
  actionLabel,
  actionHref,
  className,
}: LogoCloudProps) {
  return (
    <div className={cn("px-6 py-12", className)}>
      <div className="mx-auto mt-10 grid max-w-5xl grid-cols-2 gap-4 sm:grid-cols-3 md:grid-cols-4">
        <div className="flex flex-col rounded-xl bg-muted p-5 max-sm:col-span-full sm:row-span-3">
          <p className="mb-8 max-w-[20ch] text-balance font-medium text-2xl tracking-tight sm:text-xl lg:text-2xl">
            {headline}
          </p>
          <Button asChild size="lg" className="mt-auto max-sm:me-auto">
            <Link href={actionHref}>
              {actionLabel}
              <ArrowUpRight />
            </Link>
          </Button>
        </div>

        {PROVIDERS.map((provider) => (
          <div
            key={provider.id}
            className="flex w-full items-center justify-center rounded-xl bg-muted px-3 py-7"
          >
            {provider.Mark ? (
              /* currentColor on the vendored path resolves against this wrapper. */
              <span style={provider.color ? { color: provider.color } : undefined}>
                {provider.Mark({ className: "h-7 sm:h-8" })}
              </span>
            ) : (
              <span
                className="text-center text-base font-semibold tracking-tight text-foreground sm:text-lg"
                title={provider.wordmark}
              >
                {provider.wordmark}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}