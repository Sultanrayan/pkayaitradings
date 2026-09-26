"use client";

import { useEffect, useRef, useState } from "react";
import {
  BarChart3Icon,
  ImageIcon,
  LinkIcon,
  LineChartIcon,
  SendIcon,
  TrendingUpIcon,
  XIcon,
} from "lucide-react";
import { cn } from "cn";

import { useMarketContext } from "@/components/symbol-provider";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { UserAvatar } from "@/components/community/shared";
import {
  ChartAttachment,
  MarketAttachment,
  SignalAttachment,
} from "@/components/community/attachments";
import type { SocialUser, PostAttachment } from "@/hooks/use-social";

const EMOJI = ["🚀", "📈", "📉", "💎", "🔥", "🪙", "🎯", "🧠", "🛡️", "💬", "✅", "⚠️"];

export function PostComposer({
  me,
  symbols,
  onPost,
}: {
  me: SocialUser | null;
  symbols: string[];
  onPost: (payload: { text: string; attachments: PostAttachment[]; hashtags: string[] }) => void;
}) {
  const { setSymbol } = useMarketContext();
  const [expanded, setExpanded] = useState(false);
  const [text, setText] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const [importUrl, setImportUrl] = useState("");
  const [attachMarket, setAttachMarket] = useState<string | null>(null);
  const [attachChart, setAttachChart] = useState<{ symbol: string; timeframe: string } | null>(null);
  const [attachSignal, setAttachSignal] = useState<{
    symbol: string;
    side: "BUY" | "SELL";
    timeframe: string;
    entry: number;
    target: number;
    stop: number;
  } | null>(null);
  const [showEmoji, setShowEmoji] = useState(false);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const textRef = useRef<HTMLTextAreaElement | null>(null);
  const [symbolPick, setSymbolPick] = useState(symbols[0] ?? "XAUUSD");

  // Listen for "quote post" events from the PostCard quote action.
  useEffect(() => {
    const handler = (event: Event) => {
      const detail = (event as CustomEvent<{ text?: string }>).detail;
      setExpanded(true);
      const quoted = detail?.text;
      if (quoted) {
        setText((previous) => (previous ? previous : `Quoting: "${quoted.slice(0, 120)}"`));
      }
    };
    window.addEventListener("pkay:quote", handler);
    return () => window.removeEventListener("pkay:quote", handler);
  }, []);

  const defaultSymbol = (): string => (symbols.includes(symbolPick) ? symbolPick : symbols[0] ?? "XAUUSD");

  const reset = () => {
    setText("");
    setImage(null);
    setImportUrl("");
    setAttachMarket(null);
    setAttachChart(null);
    setAttachSignal(null);
    setShowEmoji(false);
    setExpanded(false);
  };

  const insertText = (addition: string) => {
    setText((previous) => (previous ? `${previous} ${addition}` : addition));
    setShowEmoji(false);
    requestAnimationFrame(() => textRef.current?.focus());
  };

  const attachEmoji = (emoji: string) => {
    insertText(emoji);
    setShowEmoji(false);
  };

  const handleFile = (file: File | undefined) => {
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 4 * 1024 * 1024) return;
    const reader = new FileReader();
    reader.onload = () => setImage(String(reader.result ?? null));
    reader.readAsDataURL(file);
  };

  const handleImport = () => {
    const url = importUrl.trim();
    if (/^https?:\/\/.+/.test(url)) {
      setImage(url);
      setImportUrl("");
    }
  };

  const handleSignalAdd = () => {
    const symbol = defaultSymbol();
    const base = symbol.startsWith("BTC") ? 96400 : symbol.startsWith("XAU") ? 4270 : 6120;
    const side: "BUY" | "SELL" = attachSignal?.side ?? "BUY";
    const entry = base;
    const range = base * (side === "BUY" ? 0.004 : 0.004);
    setAttachSignal({
      symbol,
      side,
      timeframe: "H1",
      entry,
      target: side === "BUY" ? entry + range * 2 : entry - range * 2,
      stop: side === "BUY" ? entry - range : entry + range,
    });
  };

  const canPost = text.trim().length > 0 || image !== null || attachMarket !== null || attachChart !== null || attachSignal !== null;

  const handlePost = () => {
    if (!canPost) return;
    const hashtags = Array.from(
      new Set(
        text
          .split(/\s+/)
          .filter((token) => token.startsWith("#"))
          .map((token) => token.slice(1)),
      ),
    );
    const attachments: PostAttachment[] = [];
    if (image) attachments.push({ type: "image", id: `img-${Date.now()}`, url: image });
    if (attachMarket) attachments.push({ type: "market", id: `mkt-${Date.now()}`, symbol: attachMarket });
    if (attachChart)
      attachments.push({
        type: "chart",
        id: `chart-${Date.now()}`,
        symbol: attachChart.symbol,
        timeframe: attachChart.timeframe,
      });
    if (attachSignal)
      attachments.push({
        type: "signal",
        id: `sig-${Date.now()}`,
        ...attachSignal,
        createdAt: new Date().toISOString(),
      });
    onPost({ text, attachments, hashtags });
    reset();
  };

  return (
    <Card className="gap-0 p-3 ring-border">
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => handleFile(event.target.files?.[0] ?? undefined)}
      />

      {/* Collapsed row */}
      <div className="flex items-center gap-3">
        <UserAvatar user={me ?? { name: "Guest", avatar: null }} />
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="min-w-0 flex-1 rounded-full border border-border bg-muted/40 px-4 py-2 text-left text-sm text-muted-foreground transition-colors hover:bg-muted/70"
        >
          What&apos;s happening in the market?
        </button>
        <Button className="hidden shrink-0 sm:inline-flex" onClick={() => setExpanded(true)}>
          Create Post
        </Button>
      </div>

      {expanded ? (
        <div className="mt-3 space-y-3">
          <textarea
            ref={textRef}
            value={text}
            onChange={(event) => {
              setText(event.target.value);
              event.target.style.height = "auto";
              event.target.style.height = `${event.target.scrollHeight}px`;
            }}
            placeholder="Share an idea, a level, a chart…"
            rows={3}
            className="w-full resize-none rounded-lg border border-input bg-transparent px-2.5 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
          />

          {/* Pending attachments preview */}
          <div className="space-y-2">
            {image ? (
              <div className="relative overflow-hidden rounded-lg border border-border">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={image} alt="Attachment" className="max-h-48 w-full object-cover" />
                <button
                  type="button"
                  onClick={() => setImage(null)}
                  className="absolute right-2 top-2 rounded-full bg-black/60 p-1 text-white"
                  aria-label="Remove image"
                >
                  <XIcon className="size-3.5" />
                </button>
              </div>
            ) : null}
            {attachMarket ? (
              <MarketAttachment
                symbol={attachMarket}
                onClick={() => setSymbol(attachMarket)}
              />
            ) : null}
            {attachChart ? (
              <ChartAttachment
                symbol={attachChart.symbol}
                timeframe={attachChart.timeframe}
                onClick={() => setSymbol(attachChart.symbol)}
              />
            ) : null}
            {attachSignal ? (
              <SignalAttachment
                symbol={attachSignal.symbol}
                side={attachSignal.side}
                timeframe={attachSignal.timeframe}
                entry={attachSignal.entry}
                target={attachSignal.target}
                stop={attachSignal.stop}
                createdAt={new Date().toISOString()}
                onClick={() => setSymbol(attachSignal.symbol)}
              />
            ) : null}
          </div>

          {/* Attach market picker */}
          {attachMarket === null ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <label className="text-[11px] text-muted-foreground">Attach market:</label>
              <select
                value={symbolPick}
                onChange={(event) => setSymbolPick(event.target.value)}
                className="h-7 rounded-md border border-border bg-background px-1.5 text-xs outline-none"
              >
                {symbols.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1 text-muted-foreground"
                onClick={() => setAttachMarket(defaultSymbol())}
              >
                <TrendingUpIcon className="size-3.5" /> Market
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1 text-muted-foreground"
                onClick={() => setAttachChart({ symbol: defaultSymbol(), timeframe: "H1" })}
              >
                <LineChartIcon className="size-3.5" /> Chart
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1 text-muted-foreground"
                onClick={handleSignalAdd}
              >
                <BarChart3Icon className="size-3.5" /> Signal
              </Button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2 rounded-lg border border-border px-3 py-2">
              <span className="flex items-center gap-2 text-xs">
                <TrendingUpIcon className="size-3.5 text-muted-foreground" />
                Market attached: <span className="font-semibold">{attachMarket}</span>
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setAttachMarket(null)}
                className="text-muted-foreground"
              >
                <XIcon className="size-3.5" /> Remove
              </Button>
            </div>
          )}

          {/* Attach signal controls */}
          {attachSignal === null ? null : (
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border px-3 py-2">
              <span className="flex items-center gap-1.5 text-xs">
                <BarChart3Icon className="size-3.5 text-muted-foreground" /> Signal
              </span>
              <select
                value={attachSignal.side}
                onChange={(event) =>
                  setAttachSignal({ ...attachSignal, side: event.target.value as "BUY" | "SELL" })
                }
                className="h-7 rounded-md border border-border bg-background px-1.5 text-xs outline-none"
                aria-label="Signal direction"
              >
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
              <span className="text-[11px] text-muted-foreground">
                Entry {attachSignal.entry.toLocaleString()} · Target {attachSignal.target.toLocaleString()} · SL {attachSignal.stop.toLocaleString()}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setAttachSignal(null)}
                className="ml-auto text-muted-foreground"
              >
                <XIcon className="size-3.5" /> Remove
              </Button>
            </div>
          )}

          {/* Image tools */}
          {attachMarket !== null ? null : (
            <div className="flex flex-wrap items-center gap-1.5">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1 text-muted-foreground"
                onClick={() => fileRef.current?.click()}
              >
                <ImageIcon className="size-3.5" /> Add image
              </Button>
              <div className="flex min-w-0 flex-1 items-center gap-1.5">
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
                  className="h-7 text-xs"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  onClick={handleImport}
                  aria-label="Import image from URL"
                >
                  <LinkIcon className="size-3.5" />
                </Button>
              </div>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className={cn("gap-1 text-muted-foreground", showEmoji && "bg-accent")}
                onClick={() => setShowEmoji((value) => !value)}
              >
                😀 Emoji
              </Button>
            </div>
          )}

          {/* Emoji picker */}
          {showEmoji ? (
            <div className="flex flex-wrap gap-1.5 rounded-lg border border-border bg-muted/30 p-2">
              {EMOJI.map((emoji) => (
                <button
                  key={emoji}
                  type="button"
                  onClick={() => attachEmoji(emoji)}
                  className="rounded-md p-1 text-lg transition-colors hover:bg-accent"
                >
                  {emoji}
                </button>
              ))}
            </div>
          ) : null}

          <div className="flex items-center justify-end gap-2">
            <Button variant="outline" onClick={reset}>
              Cancel
            </Button>
            <Button onClick={handlePost} disabled={!canPost} className="gap-1.5">
              <SendIcon className="size-3.5" /> Post
            </Button>
          </div>
        </div>
      ) : null}
    </Card>
  );
}