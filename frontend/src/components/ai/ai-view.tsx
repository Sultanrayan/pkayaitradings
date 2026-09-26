"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { History, Plus, Sparkles, SquarePen, Trash2 } from "lucide-react";
import { cn } from "cn";

import { PromptInput, type PromptMeta } from "@/components/ui/ai-chat-input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
  }, []);

  const deleteChat = useCallback((id: string) => {
    setChats((previous) => previous.filter((chat) => chat.id !== id));
    setActiveId((current) => (current === id ? null : current));
  }, []);

  const submit = useCallback(
    async (prompt: string, meta: PromptMeta) => {
      const trimmed = prompt.trim();
      if (!trimmed || busy) return;
      const sessionId = activeId ?? nextId("chat");
      if (!activeId) {
        const session: ChatSession = { id: sessionId, title: "New chat", createdAt: Date.now(), messages: [] };
        setChats((previous) => [session, ...previous].slice(0, MAX_SESSIONS));
        setActiveId(sessionId);
      }
      const userMessage: ChatMessage = { id: nextId("msg"), role: "user", text: trimmed, model: meta.model };
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
          model: meta.model,
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
    [activeId, busy, symbol, timeframe],
  );

  const messages = active?.messages ?? [];

  return (
    <div className="flex h-full flex-col pt-14">
      {/* Slim top bar */}
      <header className="flex items-center gap-2 border-b border-border px-4 py-2.5 md:px-6">
        <div className="flex items-center gap-2">
          <Plus className="size-4 text-foreground" />
          <span className="text-sm font-medium tracking-tight">AI Assistant</span>
        </div>

        <span className="ml-2 hidden items-center gap-1.5 rounded-full border border-border bg-muted/40 px-2 py-0.5 text-[11px] text-muted-foreground sm:flex">
          <Sparkles className="size-3 text-gold" />
          {symbol} · {timeframe}
        </span>

        <div className="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" className="gap-1.5" onClick={newChat}>
            <SquarePen className="size-3.5" />
            <span className="hidden sm:inline">New chat</span>
          </Button>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-1.5">
                <History className="size-3.5" />
                <span className="hidden sm:inline">History</span>
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel>Conversations</DropdownMenuLabel>
              <DropdownMenuSeparator />
              {chats.length === 0 ? (
                <div className="px-3 py-6 text-center text-xs text-muted-foreground">
                  No conversations yet.
                </div>
              ) : (
                chats.map((chat) => {
                  const isActive = chat.id === activeId;
                  return (
                    <div key={chat.id} className="group flex items-center">
                      <DropdownMenuItem
                        onSelect={() => setActiveId(chat.id)}
                        className={cn("min-w-0 flex-1", isActive && "bg-accent")}
                      >
                        <span className="truncate">{chat.title}</span>
                      </DropdownMenuItem>
                      <button
                        type="button"
                        aria-label="Delete chat"
                        onClick={() => deleteChat(chat.id)}
                        className="mr-1 rounded p-1 text-muted-foreground opacity-0 transition-opacity hover:bg-accent hover:text-destructive group-hover:opacity-100 focus-visible:opacity-100"
                      >
                        <Trash2 className="size-3.5" />
                      </button>
                    </div>
                  );
                })
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </header>

      {/* Conversation thread */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex h-full max-w-3xl flex-col gap-6 px-4 py-8 md:px-6">
          {messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
              <span className="flex size-11 items-center justify-center rounded-2xl bg-accent">
                <Sparkles className="size-5 text-gold" />
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
                  "flex flex-col gap-1.5",
                  message.role === "user" ? "items-end" : "items-start",
                )}
              >
                {message.role === "assistant" ? (
                  <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-muted-foreground">
                    <Sparkles className="size-3 text-gold" />
                    Pkay AI · {message.model}
                  </span>
                ) : null}
                <div
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap break-words text-[15px] leading-relaxed",
                    message.role === "user"
                      ? "rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-primary-foreground"
                      : "w-full pb-1 text-foreground",
                  )}
                >
                  {message.text}
                </div>
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

      {/* Composer */}
      <div className="flex justify-center px-4 pb-4 md:px-6">
        <div className="w-full max-w-3xl">
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
  );
}