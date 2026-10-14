import type { ReactNode } from "react";

import { cn } from "cn";

export interface ArticleSectionProps {
  id: string;
  /** Label used by the page-contents navigation; defaults to the heading. */
  title: string;
  children: ReactNode;
  /** Renders a hairline above the section. */
  divided?: boolean;
  className?: string;
}

/**
 * A titled block within the article.
 *
 * `scroll-mt-24` keeps the heading clear of the sticky navbar when a page-contents
 * link jumps to it, which is why the offset lives here rather than on each link.
 */
export function ArticleSection({
  id,
  title,
  children,
  divided = false,
  className,
}: ArticleSectionProps) {
  return (
    <section
      id={id}
      aria-labelledby={`${id}-heading`}
      className={cn("scroll-mt-24", divided && "mt-10 border-t border-border pt-10", className)}
    >
      <h2
        id={`${id}-heading`}
        className="scroll-mt-24 text-xl font-semibold tracking-tight sm:text-2xl"
      >
        {title}
      </h2>
      <div className="mt-4 space-y-4 text-[15px] leading-7 text-muted-foreground">
        {children}
      </div>
    </section>
  );
}