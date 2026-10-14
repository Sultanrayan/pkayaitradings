"use client";

import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Menu, Plus, X } from "lucide-react";
import { cn } from "cn";

import { AITextLoading } from "@/components/ui/ai-text-loading";
import { Button } from "@/components/ui/button";
import { ApiError, api, type ZenmuxAnalysis, type ZenmuxModelId, type ZenmuxTimeframe } from "@/lib/api";

import { AnalysisCard } from "./analysis-card";
import { Composer } from "./composer";
import { ConversationList } from "./conversation-list";
import {
  DEFAULT_ZENMUX_MODEL,
  DEFAULT_ZENMUX_TIMEFRAME,
  ZENMUX_SYMBOL_LABEL,
  titleFrom,
} from "./constants";

interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  /** Present on assistant turns that produced a card. */
  analysis?: ZenmuxAnalysis;
}

interface ChatSession {
  id: string;
  title: string;
  createdAt: number;
  messages: ChatMessage[];
}

/**
 * Deliberately a different storage key from `/ai` (`pkay.ai.chats`).
 *
 * The two surfaces look alike and must stay independent: sharing a key would let
 * a Zenmux probability land in the assistant's history and be replayed as a prior
 * turn, which is meaningless to both.
 */
const STORAGE_KEY = "pkay.zenmux.chats";
const MAX_SESSIONS = 30;

function readChats(): ChatSession[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(
        (item): item is ChatSession =>
          Boolean(item && typeof item.id === "string" && Array.isArray(item.messages)),
      )
      .slice(0, MAX_SESSIONS);
  } catch {
    return [];
  }
}

/**
 * Surface the real reason for a failure.
 *
 * The server's own wording matters: a 503 explains an unconfigured key, an
 * unreachable upstream or an unsupported symbol, and those need different fixes. A
 * generic apology sends the user to retry a request that will fail identically.
 *
 * Two shapes have to be handled, and conflating them is what hid the cause here:
 *
 * * an HTTP failure arrives as `ApiError`, whose ``message`` already holds the
 *   server's ``detail`` string. Reading ``error.detail`` — which does not exist —
 *   silently discarded every real reason and always fell through to the generic text.
 * * a transport failure (nothing listening, blocked by CORS, offline) throws a plain
 *   ``TypeError`` from ``fetch`` before any response exists. There is no status and
 *   no server wording, so it needs its own message rather than being reported as an
 *   application error.
 */
function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const detail = error.message?.trim();
    if (detail) return detail;
    return `The analysis service returned an error (${error.status}).`;
  }

  // No HTTP response was received at all: the request never reached the server.
  if (error instanceof TypeError) {
    return (
      "Could not reach the analysis service. Check that the API is running and " +
      "reachable, then try again."
    );
  }

  const detail = (error as { detail?: unknown; message?: unknown } | null)?.detail;
  if (typeof detail === "string" && detail.trim()) return detail;
  const message = (error as { message?: unknown } | null)?.message;
  if (typeof message === "string" && message.trim()) return message;
  return "Zenmux could not analyse that right now. Please try again in a moment.";
}

let serial = 0;
function nextId(prefix: string): string {
  serial += 1;
  return `${prefix}-${Date.now().toString(36)}-${serial}`;
}

export function ZenmuxView() {
  const [chats, setChats] = useState<ChatSession[]>(() => readChats());
  const [activeId, setActiveId] = useState<string | null>(() => {
    const stored = readChats();
    return stored.length > 0 ? stored[0].id : null;
  });
  const [model, setModel] = useState<ZenmuxModelId>(DEFAULT_ZENMUX_MODEL);
  const [timeframe, setTimeframe] = useState<ZenmuxTimeframe>(DEFAULT_ZENMUX_TIMEFRAME);
  const [busy, setBusy] = useState(false);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(chats));
    } catch {
      /* storage unavailable or full; the thread still works in-session */
    }
  }, [chats]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chats, busy]);

  const active = useMemo(
    () => chats.find((chat) => chat.id === activeId) ?? chats[0] ?? null,
    [chats, activeId],
  );
  const messages = active?.messages ?? [];

  const newChat = useCallback(() => {
    const id = nextId("zenmux");
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

  const renameChat = useCallback((id: string, title: string) => {
    setChats((previous) =>
      previous.map((chat) => (chat.id === id ? { ...chat, title } : chat)),
    );
  }, []);

  const submit = useCallback(
    async (prompt: string) => {
      const trimmed = prompt.trim();
      if (!trimmed || busy) return;

      const sessionId = activeId ?? nextId("zenmux");
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
      };
      setChats((previous) =>
        previous.map((chat) =>
          chat.id === sessionId
            ? {
                ...chat,
                messages: [...chat.messages, userMessage],
                title: chat.title === "New chat" ? titleFrom(trimmed) : chat.title,
              }
            : chat,
        ),
      );

      setBusy(true);
      try {
        const priorTurns = (active?.messages ?? [])
          .slice(-8)
          .map((entry) => ({ role: entry.role, content: entry.text }));
        const result = await api.zenmux({
          question: trimmed,
          model,
          timeframe,
          history: priorTurns,
        });
        const assistantMessage: ChatMessage = {
          id: nextId("msg"),
          role: "assistant",
          text: result.summary,
          analysis: result,
        };
        setChats((previous) =>
          previous.map((chat) =>
            chat.id === sessionId
              ? { ...chat, messages: [...chat.messages, assistantMessage] }
              : chat,
          ),
        );
      } catch (error) {
        const fallback: ChatMessage = {
          id: nextId("msg"),
          role: "assistant",
          text: errorMessage(error),
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
    [active, activeId, busy, model, timeframe],
  );

  const sidebar = (
    <div className="flex h-full flex-col gap-1 p-3">
      <Button
        variant="outline"
        className="w-full justify-start gap-2"
        onClick={() => {
          newChat();
        }}
      >
        <Plus className="size-4" />
        New Chat
      </Button>
      <div className="min-h-0 flex-1 overflow-y-auto pt-1">
        {chats.length === 0 ? (
          <p className="px-2 py-6 text-center text-xs text-muted-foreground">
            No conversations yet.
          </p>
        ) : (
          <ConversationList
            conversations={chats}
            activeId={activeId}
            onSelect={(id) => {
              setActiveId(id);
              setSidebarOpen(false);
            }}
            onRename={renameChat}
            onDelete={deleteChat}
          />
        )}
      </div>
    </div>
  );

  return (
    <div className="flex h-full flex-col pt-14">
      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-64 shrink-0 border-r border-border bg-card/40 md:block">
          {sidebar}
        </aside>

        {sidebarOpen ? (
          <div className="fixed inset-0 z-50 md:hidden">
            <div
              className="absolute inset-0 bg-black/50"
              onClick={() => setSidebarOpen(false)}
            />
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

        <div className="flex min-w-0 flex-1 flex-col">
          <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-2 md:hidden">
            <Button variant="ghost" size="sm" className="gap-1.5" onClick={() => setSidebarOpen(true)}>
              <Menu className="size-4" />
              History
            </Button>
            <span className="text-[11px] text-muted-foreground">{ZENMUX_SYMBOL_LABEL}</span>
          </div>

          {/* Thread */}
          <div className="min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto flex min-h-full max-w-3xl flex-col gap-6 px-4 py-6 md:py-8">
              {messages.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
                  <span className="relative size-12 overflow-hidden rounded-2xl ring-1 ring-border">
                    <Image
                      src="/logo-pkay.jpg"
                      alt="Pkay"
                      fill
                      sizes="48px"
                      priority
                      className="object-cover"
                    />
                  </span>
                  <div>
                    <h2 className="text-[17px] font-medium">Ask Zenmux about XAU/USD</h2>
                    <p className="mt-1 text-[13px] text-muted-foreground">
                      AI-powered market analysis for Gold.
                    </p>
                  </div>
                  {/* The suggested-prompt cards that used to sit here were removed:
                      the composer stages a phrase and waits for Enter, so these live
                      in its phrase box instead of duplicating a list the user has to
                      reach for anyway. */}
                </div>
              ) : (
                messages.map((message) => (
                  <div
                    key={message.id}
                    className={cn(
                      "flex w-full flex-col gap-3",
                      message.role === "user" ? "items-end" : "items-start",
                    )}
                  >
                    {message.role === "user" ? (
                      <div className="max-w-[85%] whitespace-pre-wrap break-words rounded-2xl rounded-br-md bg-sky-600 px-4 py-2.5 text-[15px] leading-relaxed text-white shadow-sm">
                        {message.text}
                      </div>
                    ) : (
                      <div className="flex w-full flex-col items-start gap-3">
                        <p className="text-[14.5px] leading-relaxed text-foreground/90">
                          {message.text}
                        </p>
                        {message.analysis ? <AnalysisCard analysis={message.analysis} /> : null}
                      </div>
                    )}
                  </div>
                ))
              )}

              {busy ? (
                <div className="flex w-full justify-center py-2">
                  <AITextLoading />
                </div>
              ) : null}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Composer, quick actions and suggestion row. */}
          <div className="border-t border-border bg-background/60 px-3 pb-3 pt-2.5 backdrop-blur md:px-6 md:pb-5">
            <div className="mx-auto w-full max-w-3xl">
              {/* The quick-action pill row that used to sit here was removed: the
                  phrase box is the single prompt library, and two overlapping lists
                  in the same spot is clutter. */}
              <Composer
                model={model}
                onModelChange={setModel}
                timeframe={timeframe}
                onTimeframeChange={setTimeframe}
                onSubmit={(text) => void submit(text)}
                busy={busy}
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
