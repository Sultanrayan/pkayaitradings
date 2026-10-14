import Image from "next/image";
import Link from "next/link";
import { ArrowUpRight, Star } from "lucide-react";

/**
 * Homepage features section.
 *
 * Rebuilt from the 21st.dev preview render of
 * `@prebuiltui/components/feature-sections/features-section-with-team`
 * (fetched 2026-10-05). The component's *source* was not retrievable — the free
 * tier was exhausted at 0/2 and the registry API answered
 * `403 retrieval_limit_reached` — so this is a reconstruction from the rendered
 * preview image plus the utility class names recovered from the public
 * `bundle.html`. It is not the component's original code, and is marked as such.
 *
 * Layout reproduced from the preview: a blurred indigo glow bleeding in from the
 * top-left, a lead paragraph, then a three-column grid where a two-column photo
 * carries a frosted stat block and an indigo avatar pill, and the side column
 * carries a gradient widget card, a headline, a paragraph and a Learn more link.
 * Class names recovered from the bundle are kept where they are theme-neutral
 * (`max-w-5xl`, `md:grid-cols-3`, `md:col-span-2`, `md:col-span-1`, `gap-10`,
 * `blur-3xl`, `aspect-square`, `bg-indigo-500/30`, `hover:-translate-y-0.5`).
 *
 * Two deliberate departures:
 *
 * 1. Palette. The preview is a light design (`text-slate-800`, white widget). This
 *    app is dark-only — `:root` and `.dark` are identical — so the type and surface
 *    colours map onto this project's tokens. Copying the slate values verbatim would
 *    put near-black text on a black background. The indigo accent and the white
 *    widget inset are kept, since that contrast is the design's signature.
 * 2. Claims. The preview ships "10X", "Used by 1,000+ developers" and "$180.00".
 *    None of those can be substantiated for this product, so each is replaced with
 *    something verifiable: the agent count from `AGENTS`, and the Ultra price from
 *    the site's own terms page. The bar chart and the star row are decorative and
 *    hidden from assistive tech rather than presented as data.
 */

/** Bar heights for the decorative chart, as proportions of the widget height. */
const BARS = [34, 52, 41, 68, 47, 78, 58, 88, 64, 72];
const HIGHLIGHTED_BAR = 7;

export function FeaturesSection() {
  return (
    <section id="features" className="relative overflow-hidden border-y border-border">
      {/* Decorative backdrop glow. */}
      <div
        aria-hidden
        className="pointer-events-none absolute -left-20 -top-10 aspect-square size-[400px] rounded-full bg-indigo-500/30 blur-3xl"
      />

      <div className="relative mx-auto max-w-5xl px-4 py-24">
        <p className="max-w-3xl text-left text-lg text-muted-foreground">
          Every signal is produced by four specialised agents reading the same market
          independently, then reconciled under hard risk limits — so a position is only
          taken when the analysis and the guardrails agree.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-10 md:grid-cols-3">
          {/* Lead image with the stat block and social pill overlaid. */}
          <div className="md:col-span-2">
            <div className="relative aspect-[16/10] overflow-hidden rounded-xl">
              <Image
                src="/trader.png"
                alt="Two traders reviewing charts on a laptop"
                fill
                sizes="(min-width: 768px) 66vw, 100vw"
                className="object-cover"
              />

              {/* Frosted stat panel. */}
              <div className="absolute right-5 top-1/2 -translate-y-1/2 rounded-lg bg-white/15 px-5 py-4 backdrop-blur-md">
                <p className="text-3xl font-semibold text-white">4</p>
                <p className="mt-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-white/80">
                  Agents on every signal
                </p>
              </div>

              {/* Avatar pill. */}
              <div className="absolute inset-x-5 bottom-5 flex items-center gap-4 rounded-xl bg-indigo-600/95 px-4 py-3">
                <div className="flex -space-x-3">
                  {["/people1.png", "/people2.png", "/people3.png"].map((src) => (
                    <Image
                      key={src}
                      src={src}
                      alt=""
                      width={36}
                      height={36}
                      sizes="36px"
                      className="size-9 rounded-full border-2 border-white object-cover"
                    />
                  ))}
                </div>
                <div>
                  <div className="flex gap-0.5" aria-hidden>
                    {Array.from({ length: 5 }, (_, index) => (
                      <Star key={index} className="size-3 fill-white text-white" />
                    ))}
                  </div>
                  <p className="mt-0.5 text-[11px] text-white/85">
                    Built for traders and analysts
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Widget card, copy and link. */}
          <div className="md:col-span-1">
            <div className="rounded-xl bg-gradient-to-br from-indigo-600 to-violet-600 p-4 transition-transform duration-300 hover:-translate-y-0.5">
              <div className="rounded-lg bg-white p-4">
                <p className="text-xs text-slate-500">Ultra plan</p>
                <p className="mt-1 text-2xl font-semibold text-slate-900">USD 65</p>
                <p className="text-[11px] text-slate-500">per 30-day period</p>
                {/* Decorative: not a data series. */}
                <div className="mt-4 flex h-14 items-end gap-1.5" aria-hidden>
                  {BARS.map((height, index) => (
                    <span
                      key={index}
                      className={
                        index === HIGHLIGHTED_BAR
                          ? "flex-1 rounded-sm bg-indigo-600"
                          : "flex-1 rounded-sm bg-indigo-200"
                      }
                      style={{ height: `${height}%` }}
                    />
                  ))}
                </div>
              </div>
            </div>

            <h3 className="mt-6 text-2xl font-medium leading-snug text-foreground">
              Analysis you can trace back to the bars
            </h3>
            <p className="mt-2 text-sm text-muted-foreground">
              Each cycle records why it reached its decision, so any signal can be
              audited against the prices and headlines behind it.
            </p>
            <Link
              href="/learn-more"
              className="group mt-4 inline-flex items-center gap-2 text-indigo-400 transition-colors hover:text-indigo-300"
            >
              Learn more
              <ArrowUpRight className="size-5 transition-transform duration-300 group-hover:translate-x-0.5" />
            </Link>
          </div>
        </div>
      </div>
    </section>
  );
}
