"use client";

import { useState } from "react";
import { Play } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "cn";

export interface WatchVideoButtonProps {
  label?: string;
  className?: string;
}

/**
 * Opens the walkthrough in a modal.
 *
 * The frame is a styled placeholder rather than an embedded player: there is no
 * video asset to point at, and shipping an empty `<iframe>` would look like a
 * broken embed. Swap the placeholder body for a real player when one exists.
 */
export function WatchVideoButton({
  label = "Watch Video",
  className,
}: WatchVideoButtonProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className={cn(
          "inline-flex items-center gap-2 rounded-md border border-border bg-background px-4 py-2 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          className,
        )}
      >
        <Play className="size-4" />
        {label}
      </button>

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>
              A short walkthrough of creating and managing table views.
            </DialogDescription>
          </DialogHeader>

          <div className="grid aspect-video w-full place-items-center rounded-md border border-border bg-muted">
            <div className="flex flex-col items-center gap-2 text-muted-foreground">
              <Play className="size-8" />
              <p className="text-sm">Video placeholder</p>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}