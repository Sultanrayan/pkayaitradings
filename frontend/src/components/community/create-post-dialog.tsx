"use client";

import { useRef, useState } from "react";
import { HashIcon, ImageIcon, LinkIcon, UploadIcon, XIcon } from "lucide-react";
import { cn } from "cn";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { parseHashtags } from "@/hooks/use-community";

const MAX_IMAGE_BYTES = 4 * 1024 * 1024; // 4 MB data-URL upload cap

/**
 * "Create post" form: caption + optional title, an image that can be uploaded
 * from disk or imported from a URL, and hashtags. Submits via `onSubmit` with
 * a readonly preview image + parsed hashtags.
 */
export function CreatePostDialog({
  open,
  onOpenChange,
  onSubmit,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSubmit: (payload: {
    title: string;
    caption: string;
    hashtags: string[];
    image: string | null;
  }) => void;
}) {
  const fileRef = useRef<HTMLInputElement | null>(null);
  const [title, setTitle] = useState("");
  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [importUrl, setImportUrl] = useState("");
  const [imageError, setImageError] = useState<string | null>(null);

  const handleFile = (file: File | undefined) => {
    setImageError(null);
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setImageError("Please choose an image file.");
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError("Image is too large — keep it under 4 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setImage(String(reader.result ?? null));
    reader.onerror = () => setImageError("Could not read the selected file.");
    reader.readAsDataURL(file);
  };

  const handleImport = () => {
    const url = importUrl.trim();
    if (!url) return;
    setImageError(null);
    if (!/^https?:\/\/.+/.test(url)) {
      setImageError("Enter a valid http(s) image URL.");
      return;
    }
    setImage(url);
    setImportUrl("");
  };

  const reset = () => {
    setTitle("");
    setCaption("");
    setHashtags("");
    setImage(null);
    setImportUrl("");
    setImageError(null);
  };

  const canPost = caption.trim().length > 0 || image !== null || title.trim().length > 0;

  const handleSubmit = () => {
    if (!canPost) return;
    onSubmit({
      title: title.trim(),
      caption: caption.trim(),
      hashtags: parseHashtags(hashtags),
      image,
    });
    reset();
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg bg-card sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="text-base">Create post</DialogTitle>
          <DialogDescription>
            Share an idea with the community — add a caption, an image and hashtags.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Caption */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">Caption</label>
            <textarea
              value={caption}
              onChange={(event) => setCaption(event.target.value)}
              placeholder="What's on your mind?"
              rows={4}
              className="w-full resize-none rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
          </div>

          {/* Optional title */}
          <div className="space-y-1.5">
            <label className="text-xs font-medium text-muted-foreground">
              Title <span className="text-muted-foreground/50">(optional)</span>
            </label>
            <Input
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="A headline for your post"
            />
          </div>

          {/* Image upload / import */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-muted-foreground">Image</label>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(event) => handleFile(event.target.files?.[0] ?? undefined)}
            />

            {image ? (
              <div className="overflow-hidden rounded-lg border border-border bg-muted/40">
                {/* data-URL or remote image, so a plain img is used */}
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={image}
                  alt="Post preview"
                  className="max-h-56 w-full object-cover"
                />
                <div className="flex items-center justify-between border-t border-border px-3 py-2">
                  <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                    <ImageIcon className="size-3.5" /> Image attached
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setImage(null)}
                    className="text-muted-foreground"
                  >
                    <XIcon className="size-3.5" /> Remove
                  </Button>
                </div>
              </div>
            ) : (
              <div className="flex flex-col gap-2 sm:flex-row">
                <Button
                  type="button"
                  variant="outline"
                  className="flex-1 justify-center gap-1.5"
                  onClick={() => fileRef.current?.click()}
                >
                  <UploadIcon className="size-4" /> Upload image
                </Button>
                <div className="flex flex-1 items-center gap-1.5">
                  <Input
                    value={importUrl}
                    onChange={(event) => setImportUrl(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        handleImport();
                      }
                    }}
                    placeholder="…or paste an image URL"
                    className="min-w-0"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={handleImport}
                    aria-label="Import image from URL"
                  >
                    <LinkIcon className="size-4" />
                  </Button>
                </div>
              </div>
            )}
            {imageError ? (
              <p className="text-xs text-bear">{imageError}</p>
            ) : null}
          </div>

          {/* Hashtags */}
          <div className="space-y-1.5">
            <label className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
              <HashIcon className="size-3.5" /> Hashtags
            </label>
            <Input
              value={hashtags}
              onChange={(event) => setHashtags(event.target.value)}
              placeholder="gold, xauusd, setup"
            />
            {hashtags.trim() ? (
              <div className="flex flex-wrap gap-1.5">
                {parseHashtags(hashtags).map((tag) => (
                  <span
                    key={tag}
                    className="rounded-full bg-muted px-2 py-0.5 text-[11px] text-blue-500"
                  >
                    #{tag}
                  </span>
                ))}
              </div>
            ) : null}
          </div>
        </div>

        <DialogFooter className={cn("-mx-4 -mb-4")}>
          <Button
            variant="outline"
            onClick={() => {
              reset();
              onOpenChange(false);
            }}
          >
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={!canPost}>
            Post
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}