"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Menu, Plus, Sparkles, Trash2, X } from "lucide-react";
import { cn } from "cn";

import { PromptInput, type PromptMeta } from "@/components/ui/ai-chat-input";
import { Button } from "@/components/ui/button";
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

function sessionTitle(messages: ChatMessage[]): string {
  const first = messages.find((message) => message.role === "user");
  if (!first) return "New chat";
  const trimmed = first.text.trim();
  return trimmed.length > 42 ? `${trimmed.slice(0, 42)}…` : trimmed;
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
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

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
    const id = nextId("chat");
    const session: ChatSession = {
      id,
      title: "New chat",
      createdAt: Date.now(),
      messages: [],
    };
    setChats((previous) => [session, ...previous].slice(0, MAX_SESSIONS));
    setActiveId(id);
    setSidebarOpen(false);
  }, []);

  const deleteChat = useCallback((id: string) => {
    setChats((previous) => previous.filter((chat) => chat.id !== id));
    setActiveId((current) => (current === id ? null : current));
  }, []);

  const submit = useCallback(
    async (prompt: string, meta?: PromptMeta) => {
      const trimmed = prompt.trim();
      if (!trimmed || busy) return;
      const model = meta?.model ?? "Pkay AI";
      const sessionId = activeId ?? nextId("chat");
      if (!activeId) {
        const session: ChatSession = { id: sessionId, title: "New chat", createdAt: Date.now(), messages: [] };
        setChats((previous) => [session, ...previous].slice(0, MAX_SESSIONS));
        setActiveId(sessionId);
      }
      const userMessage: ChatMessage = { id: nextId("msg"), role: "user", text: trimmed, model };
      setChats((previous) =>
        previous.map((chat) =>
          chat.id === sessionId
            ? { ...chat, messages: [...chat.messages, userMessage], title: chat.title === "New chat" ? sessionTitle([userMessage]) : chat.title }
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
          model,
        };
        setChats((previous) =>
          previous.map((chat) =>
            chat.id === sessionId
              ? { ...chat, messages: [...chat.messages, assistantMessage] }
              : chat,
          ),
        );
      } catch {
        const fallback: ChatMessage = {
          id: nextId("msg"),
          role: "assistant",
          text: "I couldn't reach the analysis engine right now. Please try again in a moment.",
          model,
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
    [activeId, busy, symbol, timeframe],
  );

  const messages = active?.messages ?? [];

  const conversationList = chats.map((chat) => {
    const isActive = chat.id === activeId;
    return (
      <div key={chat.id} className="group flex items-center">
        <button
          type="button"
          onClick={() => {
            setActiveId(chat.id);
            setSidebarOpen(false);
          }}
          className={cn(
            "flex min-w-0 flex-1 items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors",
            isActive ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          <Sparkles className={cn("size-3.5 shrink-0", isActive ? "text-gold" : "text-muted-foreground")} />
          <span className="truncate">{chat.title}</span>
        </button>
        <button
          type="button"
          aria-label="Delete chat"
          onClick={() => deleteChat(chat.id)}
          className="rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
    );
  });

  const sidebar = (
    <div className="flex h-full flex-col gap-2 p-3">
      <Button className="w-full justify-start gap-2" onClick={newChat}>
        <Plus className="size-4" />
        New Chat
      </Button>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="space-y-0.5">
          {chats.length === 0 ? (
            <div className="px-3 py-6 text-center text-xs text-muted-foreground">No conversations yet.</div>
          ) : (
            conversationList
          )}
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-full flex-col pt-14">
      <div className="flex min-h-0 flex-1">
        {/* Desktop sidebar */}
        <aside className="hidden w-64 shrink-0 border-r border-border bg-card/40 md:block">{sidebar}</aside>

        {/* Mobile sidebar drawer */}
        {sidebarOpen ? (
          <div className="fixed inset-0 z-50 md:hidden">
            <div className="absolute inset-0 bg-black/50" onClick={() => setSidebarOpen(false)} />
            <div className="absolute left-0 top-0 h-full w-72 border-r border-border bg-card p-2 shadow-xl">
              <button
                type="button"
                aria-label="Close sidebar"
                onClick={() => setSidebarOpen(false)}
                className="mb-1 ml-auto flex size-8 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <X className="size-4" />
              </button>
              {sidebar}
            </div>
          </div>
        ) : null}

        {/* Chat column */}
        <div className="flex min-w-0 flex-1 flex-col">
          {/* Mobile menu toggle */}
          <div className="flex items-center border-b border-border px-2 py-1.5 md:hidden">
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => setSidebarOpen(true)}>
              <Menu className="size-4" />
              History
            </Button>
          </div>

          {/* Conversation thread */}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex h-full max-w-3xl flex-col gap-5 px-4 py-6 md:py-8">
              {messages.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
                  <span className="relative size-11 overflow-hidden rounded-2xl ring-1 ring-border">
                    <Image
                      src="/logo-pkay.jpg"
                      alt="Pkay"
                      fill
                      sizes="44px"
                      priority
                      className="object-cover"
                    />
                  </span>
                  <div>
                    <div className="text-base font-medium">Start a conversation</div>
                    <div className="mt-1 text-xs text-muted-foreground">
                      Ask about {symbol}, its timeframes, or the market in general.
                    </div>
                  </div>
                </div>
              ) : (
                messages.map((message) => (
                  <div
                    key={message.id}
                    className={cn(
                      "flex w-full flex-col gap-1.5",
                      message.role === "user" ? "items-end" : "items-start",
                    )}
                  >
                    {message.role === "assistant" ? (
                      <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                        <Sparkles className="size-3 text-gold" />
                        Pkay AI · {message.model}
                      </span>
                    ) : null}
                    {message.role === "assistant" ? (
                      <div className="w-full whitespace-pre-wrap break-words pb-1 text-[15px] leading-relaxed text-foreground">
                        {message.text}
                      </div>
                    ) : (
                      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-sky-600 px-4 py-2.5 text-[15px] leading-relaxed text-white shadow-sm">
                        {message.text}
                      </div>
                    )}
                  </div>
                ))
              )}

              {busy ? (
                <div className="flex items-start gap-1.5">
                  <span className="mt-0.5 flex gap-1">
                    <span className="size-1.5 animate-bounce rounded-full bg-foreground/60 [animation-delay:-0.3s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-foreground/60 [animation-delay:-0.15s]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-foreground/60" />
                  </span>
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Centered composer (nudged slightly left for optical centering) */}
          <div className="flex justify-center px-3 pb-3 md:px-6 md:pb-5">
            <div className="w-full max-w-3xl md:-mr-3">
              <PromptInput
                key={activeId ?? "new"}
                onSubmit={submit}
                placeholder={
                  messages.length > 0 ? "Ask a follow-up…" : "Ask anything about the market…"
                }
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}