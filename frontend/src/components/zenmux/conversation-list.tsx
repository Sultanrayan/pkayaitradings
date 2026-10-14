"use client";

import { useState } from "react";
import { Check, MessageSquare, Pencil, Trash2, X } from "lucide-react";
import { cn } from "cn";

import { GROUP_ORDER, groupFor, type ConversationGroup } from "./constants";

export interface ConversationEntry {
  id: string;
  title: string;
  createdAt: number;
}

export interface ConversationListProps {
  conversations: ConversationEntry[];
  activeId?: string | null;
  onSelect?: (id: string) => void;
  onRename?: (id: string, title: string) => void;
  onDelete?: (id: string) => void;
  className?: string;
}

/**
 * Date-grouped conversation history.
 *
 * Grouping, order and the hover-reveal interaction are adapted from the 21st
 * "Conversation List" component; the styling is moved onto this project's tokens so
 * it matches every other surface, and the pin affordance that component ships is
 * replaced with rename and delete, which is what this sidebar actually needs.
 *
 * Nothing is rendered for conversations older than seven days — they would sit
 * under a "Previous 7 days" heading while not being part of it.
 */
export function ConversationList({
  conversations,
  activeId,
  onSelect,
  onRename,
  onDelete,
  className,
}: ConversationListProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");

  const grouped = new Map<ConversationGroup, ConversationEntry[]>();
  for (const conversation of conversations) {
    const group = groupFor(conversation.createdAt);
    if (!group) continue;
    const bucket = grouped.get(group);
    if (bucket) bucket.push(conversation);
    else grouped.set(group, [conversation]);
  }
  // Newest first within each group, so the list matches the group order below it.
  for (const bucket of grouped.values()) {
    bucket.sort((a, b) => b.createdAt - a.createdAt);
  }

  const startRename = (conversation: ConversationEntry) => {
    setEditingId(conversation.id);
    setDraft(conversation.title);
  };

  const commitRename = (id: string) => {
    const trimmed = draft.trim();
    if (trimmed) onRename?.(id, trimmed);
    setEditingId(null);
  };

  const visible = GROUP_ORDER.filter((group) => (grouped.get(group)?.length ?? 0) > 0);

  return (
    <nav aria-label="Conversations" className={cn("flex w-full flex-col", className)}>
      {visible.map((group) => (
        <div key={group} className="mt-3 first:mt-1">
          <p className="px-2 pb-1 text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground/70">
            {group}
          </p>
          <ul className="space-y-0.5">
            {grouped.get(group)!.map((conversation) => {
              const isActive = conversation.id === activeId;
              const isEditing = editingId === conversation.id;

              return (
                <li key={conversation.id} className="group/item relative">
                  {isEditing ? (
                    <div className="flex items-center gap-1 rounded-lg bg-accent px-2 py-1">
                      <input
                        autoFocus
                        value={draft}
                        onChange={(event) => setDraft(event.target.value)}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") commitRename(conversation.id);
                          if (event.key === "Escape") setEditingId(null);
                        }}
                        aria-label={`Rename ${conversation.title}`}
                        className="min-w-0 flex-1 bg-transparent text-[12.5px] outline-none"
                      />
                      <button
                        type="button"
                        aria-label="Save name"
                        onClick={() => commitRename(conversation.id)}
                        className="rounded p-1 text-muted-foreground hover:text-foreground"
                      >
                        <Check className="size-3.5" />
                      </button>
                      <button
                        type="button"
                        aria-label="Cancel rename"
                        onClick={() => setEditingId(null)}
                        className="rounded p-1 text-muted-foreground hover:text-foreground"
                      >
                        <X className="size-3.5" />
                      </button>
                    </div>
                  ) : (
                    <>
                      <button
                        type="button"
                        aria-current={isActive ? "true" : undefined}
                        onClick={() => onSelect?.(conversation.id)}
                        className={cn(
                          "flex w-full items-center gap-2 rounded-lg py-2 pl-2 pr-14 text-left transition-colors",
                          isActive
                            ? "bg-accent text-foreground"
                            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                        )}
                      >
                        <MessageSquare
                          className={cn(
                            "size-3.5 shrink-0",
                            isActive ? "text-foreground" : "text-muted-foreground/60",
                          )}
                          aria-hidden
                        />
                        <span
                          className={cn(
                            "min-w-0 flex-1 truncate text-[12.5px]",
                            isActive && "font-medium",
                          )}
                        >
                          {conversation.title}
                        </span>
                      </button>

                      {/* Actions stay hidden until hover or keyboard focus so the
                          list reads as plain titles at rest. */}
                      <div
                        className={cn(
                          "absolute right-1.5 top-1/2 flex -translate-y-1/2 items-center gap-0.5",
                          "opacity-0 transition-opacity focus-within:opacity-100 group-hover/item:opacity-100",
                        )}
                      >
                        <button
                          type="button"
                          aria-label={`Rename ${conversation.title}`}
                          title="Rename"
                          onClick={() => startRename(conversation)}
                          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                        >
                          <Pencil className="size-3" />
                        </button>
                        <button
                          type="button"
                          aria-label={`Delete ${conversation.title}`}
                          title="Delete"
                          onClick={() => onDelete?.(conversation.id)}
                          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-destructive"
                        >
                          <Trash2 className="size-3" />
                        </button>
                      </div>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
