import { cn } from "cn";

export interface DocumentationImageProps {
  src: string;
  alt: string;
  /** Optional caption rendered under the frame. */
  caption?: string;
  className?: string;
}

/**
 * Framed screenshot slot.
 *
 * A documentation image is illustrative, so `alt` describes what the reader is being
 * shown rather than repeating the caption.
 */
export function DocumentationImage({
  src,
  alt,
  caption,
  className,
}: DocumentationImageProps) {
  return (
    <figure className={cn("mt-6", className)}>
      <div className="overflow-hidden rounded-lg border border-border bg-muted">
        {/* Documentation screenshots are UI captures read at their authored size.
            next/image would re-encode them and soften the very text they exist to
            show, and it requires knowing the intrinsic dimensions up front, which a
            docs asset does not guarantee. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={src} alt={alt} loading="lazy" className="block w-full" />
      </div>
      {caption ? (
        <figcaption className="mt-2 text-xs text-muted-foreground">{caption}</figcaption>
      ) : null}
    </figure>
  );
}