"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Bot, Loader2, Send, X } from "lucide-react";

import { useMarketContext } from "@/components/symbol-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { api } from "@/lib/api";
import type { ChartTimeframe } from "@/lib/types";

interface Message {
  id: string;
  role: "user" | "bot";
  text: string;
}

const QUICK_ACTIONS = [
  "Analyze this chart",
  "Explain this market",
  "Explain this signal",
  "Summarize market news",
  "Help me understand the chart",
];

function contextPrompt(symbol: string, timeframe: ChartTimeframe, text: string): string {
  return (
    `[Context] The user is viewing ${symbol} on the ${timeframe} timeframe in the Pkay trading app. ` +
    `Answer as a helpful market-analysis assistant. The user says: "${text}"`
  );
}

/** Chat body shared by the floating Bot Supports panel and the dedicated AI page. */
export function BotPanel({ onClose }: { onClose?: () => void }) {
  const { symbol, timeframe } = useMarketContext();
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const serial = useRef(0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const submit = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || busy) return;
      setMessages((previous) => [
        ...previous,
        { id: `u${serial.current++}`, role: "user", text },
      ]);
      setInput("");
      setBusy(true);
      try {
        const response = await api.raggrapQuery(contextPrompt(symbol, timeframe, text));
        setMessages((previous) => [
          ...previous,
          { id: `b${serial.current++}`, role: "bot", text: response.answer },
        ]);
      } catch {
        setMessages((previous) => [
          ...previous,
          {
            id: `b${serial.current++}`,
            role: "bot",
            text: "I couldn't reach the analysis engine right now. Please try again in a moment.",
          },
        ]);
      } finally {
        setBusy(false);
        inputRef.current?.focus();
      }
    },
    [busy, symbol, timeframe],
  );

  const quickAction = (label: string) => () => void submit(label);

  return (
    <div className="flex h-[28rem] max-h-[70vh] flex-col overflow-hidden rounded-2xl border border-border bg-card shadow-xl shadow-black/30">
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="relative flex size-8 items-center justify-center rounded-full bg-foreground text-background">
            <Bot className="size-4" />
          </span>
          <div>
            <div className="text-sm font-medium">Bot Supports</div>
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <span className="size-1.5 rounded-full bg-bull" />
              Online · {symbol} {timeframe}
            </div>
          </div>
        </div>
        {onClose ? (
          <Button variant="ghost" size="icon-sm" aria-label="Close bot" onClick={onClose}>
            <X className="size-4" />
          </Button>
        ) : null}
      </div>

      {messages.length === 0 ? (
        <div className="flex-1 space-y-2 overflow-y-auto px-4 py-4">
          <p className="text-xs text-muted-foreground">
            Hi! I&apos;m the Pkay market assistant. Ask me anything about the market — I have context
            on the chart you&apos;re currently viewing.
          </p>
          <div className="grid grid-cols-1 gap-2 pt-1">
            {QUICK_ACTIONS.map((action) => (
              <button
                key={action}
                type="button"
                onClick={quickAction(action)}
                className="rounded-lg border border-border px-3 py-2 text-left text-xs transition-colors hover:bg-accent hover:text-foreground"
              >
                {action}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <ScrollArea className="flex-1">
          <div className="space-y-3 px-4 py-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={
                  message.role === "user"
                    ? "ml-auto max-w-[85%] rounded-xl rounded-br-sm bg-foreground px-3 py-2 text-[13px] text-background"
                    : "mr-auto max-w-[90%] rounded-xl rounded-bl-sm border border-border bg-muted px-3 py-2 text-[13px]"
                }
              >
                {message.text}
              </div>
            ))}
            {busy ? (
              <div className="mr-auto flex w-fit items-center gap-2 rounded-xl border border-border bg-muted px-3 py-2 text-[13px] text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Thinking…
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>
        </ScrollArea>
      )}

      <div className="border-t border-border p-3">
        <form
          className="flex items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void submit(input);
          }}
        >
          <Input
            ref={inputRef}
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="Ask about the market…"
            autoComplete="off"
          />
          <Button type="submit" size="icon" disabled={busy || !input.trim()} aria-label="Send message">
            <Send className="size-4" />
          </Button>
        </form>
      </div>
    </div>
  );
}