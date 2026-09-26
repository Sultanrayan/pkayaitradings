"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageSquare, Plus, Sparkles, Trash2 } from "lucide-react";
import { cn } from "cn";

import { PromptInput, type PromptMeta } from "@/components/ui/ai-chat-input";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useMarketContext } from "@/components/symbol-provider";
import { api } from "@/lib/api";
import type { ChartTimeframe } from "@/lib/types";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  model: string;
}

interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  messages: ChatMessage[];
}

const STORAGE_KEY = "pkay.ai.chats";
const MAX_SESSIONS = 20;

function readChats(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((item): item is ChatSession => Boolean(item && typeof item.id === "string"))
      .slice(0, MAX_SESSIONS);
  } catch {
    return [];
  }
}

function walletTitle(messages: ChatMessage[]): string {
  const first = messages.find((message) => message.role === "user");
  if (!first) return "New chat";
  const trimmed = first.text.trim();
  return trimmed.length > 40 ? `${trimmed.slice(0, 40)}…` : trimmed;
}

function buildContext(symbol: string, timeframe: ChartTimeframe, prompt: string): string {
  return (
    `[Context] The user is viewing ${symbol} on the ${timeframe} timeframe in the Pkay trading app. ` +
    `Answer as a helpful market-analysis assistant. The user says: "${prompt}"`
  );
}

let serial = 0;
function nextId(prefix: string): string {
  serial += 1;
  return `${prefix}-${Date.now().toString(36)}-${serial}`;
}

export function AiView() {
  const { symbol, timeframe } = useMarketContext();
  const [chats, setChats] = useState<ChatSession[]>(() => readChats());
  const [activeId, setActiveId] = useState<string | null>(() => {
    const stored = readChats();
    return stored.length > 0 ? stored[0].id : null;
  });
  const [busy, setBusy] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Persist on change.
  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
    } catch {
      /* storage unavailable */
    }
  }, [chats]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chats, busy]);

  const active = useMemo(
    () => chats.find((chat) => chat.id === activeId) ?? chats[0] ?? null,
    [chats, activeId],
  );

  const newChat = useCallback(() => {
    if (serial < 0) serial = 0;
    const id = nextId("chat");
    const session: ChatSession = {
      id,
      title: "New chat",
      createdAt: Date.now(),
      messages: [],
    };
    setChats((previous) => {
      const next = [session, ...previous].slice(0, MAX_SESSIONS);
      return next;
    });
    setActiveId(id);
  }, []);

  const deleteChat = useCallback((id: string) => {
    setChats((previous) => previous.filter((chat) => chat.id !== id));
    setActiveId((current) => {
      if (current !== id) return current;
      return null;
    });
  }, []);

  const activeSession = active ?? undefined;

  const submit = useCallback(
    async (prompt: string, meta: PromptMeta) => {
      const trimmed = prompt.trim();
      if (!trimmed) return;
      const sessionId = activeId ?? nextId("chat");
      if (!activeId) {
        const session: ChatSession = {
          id: sessionId,
          title: "New chat",
          createdAt: Date.now(),
          messages: [],
        };
        setChats((previous) => [session, ...previous].slice(0, MAX_SESSIONS));
        setActiveId(sessionId);
      }
      const userMessage: ChatMessage = {
        id: nextId("msg"),
        role: "user",
        text: trimmed,
        model: meta.model,
      };
      setChats((previous) =>
        previous.map((chat) =>
          chat.id === sessionId
            ? { ...chat, messages: [...chat.messages, userMessage], title: chat.title === "New chat" ? walletTitle([userMessage]) : chat.title }
            : chat,
        ),
      );
      setBusy(true);
      try {
        const response = await api.raggrapQuery(buildContext(symbol, timeframe, trimmed));
        const assistantMessage: ChatMessage = {
          id: nextId("msg"),
          role: "assistant",
          text: response.answer,
          model: meta.model,
        };
        setChats((previous) =>
          previous.map((chat) =>
            chat.id === sessionId
              ? {
                  ...chat,
                  messages: [...chat.messages, assistantMessage],
                  title:
                    chat.messages.length > 0
                      ? chat.title
                      : walletTitle([userMessage, assistantMessage]),
                }
              : chat,
          ),
        );
      } catch {
        const fallback: ChatMessage = {
          id: nextId("msg"),
          role: "assistant",
          text: "I couldn't reach the analysis engine right now. Please try again in a moment.",
          model: meta.model,
        };
        setChats((previous) =>
          previous.map((chat) =>
            chat.id === sessionId ? { ...chat, messages: [...chat.messages, fallback] } : chat,
          ),
        );
      } finally {
        setBusy(false);
      }
    },
    [activeId, symbol, timeframe],
  );

  return (
    <div className="mx-auto flex h-full max-w-6xl flex-col gap-4 px-4 pb-3 pt-14 lg:flex-row md:px-6">
      {/* Chat history sidebar */}
      <aside className="flex w-full flex-col gap-2 lg:w-64 lg:shrink-0">
        <Button className="gap-2" onClick={newChat}>
          <Plus className="size-4" />
          New Chat
        </Button>
        <ScrollArea className="flex-1 rounded-xl border border-border bg-card">
          <div className="space-y-1 p-2">
            {chats.length === 0 ? (
              <div className="px-3 py-8 text-center text-xs text-muted-foreground">
                No conversations yet. Start a new chat to begin.
              </div>
            ) : (
              chats.map((chat) => {
                const isActive = chat.id === activeId;
                return (
                  <div
                    key={chat.id}
                    className={cn(
                      "group flex items-center gap-2 rounded-lg px-2.5 py-2 transition-colors",
                      isActive ? "bg-accent" : "hover:bg-accent/50",
                    )}
                  >
                    <button
                      type="button"
                      onClick={() => setActiveId(chat.id)}
                      className="flex min-w-0 flex-1 items-center gap-2 text-left"
                    >
                      <MessageSquare className="size-3.5 shrink-0 text-muted-foreground" />
                      <span className="truncate text-xs font-medium">{chat.title}</span>
                    </button>
                    <button
                      type="button"
                      aria-label="Delete chat"
                      onClick={() => deleteChat(chat.id)}
                      className="rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-background hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
                    >
                      <Trash2 className="size-3.5" />
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </ScrollArea>
      </aside>

      {/* Chat panel */}
      <section className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex items-center gap-2 rounded-xl border border-border bg-muted/40 px-4 py-2.5 text-xs text-muted-foreground">
          <Sparkles className="size-3.5 text-gold" />
          Viewing {symbol} on {timeframe} — the assistant has context on this market.
        </div>

        <div className="min-h-0 flex-1 rounded-xl border border-border bg-card">
          <ScrollArea className="h-full">
            <div className="space-y-4 p-4">
              {!activeSession || activeSession.messages.length === 0 ? (
                <div className="flex h-full min-h-[12rem] flex-col items-center justify-center gap-3 text-center">
                  <span className="flex size-12 items-center justify-center rounded-2xl bg-accent">
                    <Sparkles className="size-5 text-gold" />
                  </span>
                  <div>
                    <div className="text-sm font-medium">Start a conversation</div>
                    <div className="text-xs text-muted-foreground">
                      Ask about {symbol}, its timeframes, or any market you like.
                    </div>
                  </div>
                </div>
              ) : (
                activeSession.messages.map((message) => (
                  <div
                    key={message.id}
                    className={cn(
                      "flex max-w-[85%] flex-col gap-1",
                      message.role === "user" ? "ml-auto items-end" : "mr-auto items-start",
                    )}
                  >
                    {message.role === "assistant" ? (
                      <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                        <Sparkles className="size-3 text-gold" />
                        {message.model}
                      </span>
                    ) : null}
                    <div
                      className={cn(
                        "whitespace-pre-wrap break-words rounded-xl px-3.5 py-2.5 text-sm leading-relaxed",
                        message.role === "user"
                          ? "rounded-br-sm bg-primary text-primary-foreground"
                          : "rounded-bl-sm border border-border bg-muted/60 text-foreground",
                      )}
                    >
                      {message.text}
                    </div>
                  </div>
                ))
              )}
              {busy ? (
                <div className="mr-auto flex w-fit items-center gap-2 rounded-xl border border-border bg-muted/60 px-3.5 py-2.5 text-xs text-muted-foreground">
                  <span className="flex gap-1">
                    <span className="size-1 animate-bounce rounded-full bg-foreground/60 [animation-delay:-0.3s]" />
                    <span className="size-1 animate-bounce rounded-full bg-foreground/60 [animation-delay:-0.15s]" />
                    <span className="size-1 animate-bounce rounded-full bg-foreground/60" />
                  </span>
                  Thinking…
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>
          </ScrollArea>
        </div>

        <div className="flex justify-center px-2 pb-2">
          <PromptInput
            key={activeId ?? "new"}
            onSubmit={submit}
            placeholder={
              activeSession?.messages.length
                ? "Ask a follow-up…"
                : "Ask anything about the market…"
            }
          />
        </div>
      </section>
    </div>
  );
}