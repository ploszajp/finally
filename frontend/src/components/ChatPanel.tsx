"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { ChatActions, ChatMessage } from "@/lib/types";
import { formatQuantity, formatUsd } from "@/lib/format";

interface Props {
  open: boolean;
  onToggle: () => void;
  /** Called after a reply in which at least one action executed. */
  onActionsExecuted?: () => void;
}

export function hasExecutedAction(actions: ChatActions | null): boolean {
  if (!actions) return false;
  return [...actions.trades, ...actions.watchlist_changes].some((a) => a.status === "executed");
}

function ActionList({ actions }: { actions: ChatActions }) {
  const items = [
    ...actions.watchlist_changes.map((w, i) => ({
      key: `w${i}`,
      kind: "watchlist" as const,
      status: w.status,
      error: w.error,
      text:
        w.status === "executed"
          ? `${w.action === "add" ? "Added" : "Removed"} ${w.ticker} ${w.action === "add" ? "to" : "from"} watchlist`
          : `${w.action === "add" ? "Add" : "Remove"} ${w.ticker} ${w.action === "add" ? "to" : "from"} watchlist`,
    })),
    ...actions.trades.map((t, i) => ({
      key: `t${i}`,
      kind: "trade" as const,
      status: t.status,
      error: t.error,
      text:
        t.status === "executed"
          ? `${t.side === "buy" ? "Bought" : "Sold"} ${formatQuantity(t.quantity)} ${t.ticker}${t.price != null ? ` at ${formatUsd(t.price)}` : ""}`
          : `${t.side === "buy" ? "Buy" : "Sell"} ${formatQuantity(t.quantity)} ${t.ticker}`,
    })),
  ];
  if (items.length === 0) return null;
  return (
    <ul className="mt-2 flex flex-col gap-1">
      {items.map((a) => (
        <li
          key={a.key}
          data-testid="chat-action"
          data-kind={a.kind}
          data-status={a.status}
          className={`rounded-sm border-l-2 px-2 py-1 text-[12px] ${
            a.status === "executed" ? "border-up bg-up/10 text-text" : "border-down bg-down/10 text-text"
          }`}
        >
          <span className={a.status === "executed" ? "text-up" : "text-down"}>
            {a.status === "executed" ? "✓ " : "✕ "}
          </span>
          {a.text}
          {a.status === "rejected" && a.error && (
            <span className="block text-[11px] text-muted">Not done: {a.error}</span>
          )}
        </li>
      ))}
    </ul>
  );
}

export function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  const llmError = !isUser && message.actions?.error != null;
  return (
    <li
      data-testid="chat-message"
      data-role={message.role}
      data-error={llmError ? "true" : undefined}
      className={`flex flex-col ${isUser ? "items-end" : "items-start"}`}
    >
      <div
        className={`max-w-[92%] whitespace-pre-wrap rounded-md px-2.5 py-1.5 text-[13px] leading-relaxed ${
          isUser
            ? "bg-primary/15 text-text"
            : llmError
              ? "border border-accent/40 bg-accent/10 text-text"
              : "bg-raised text-text"
        }`}
      >
        {message.content}
      </div>
      {!isUser && message.actions && !llmError && (
        <div className="w-[92%]">
          <ActionList actions={message.actions} />
        </div>
      )}
    </li>
  );
}

export default function ChatPanel({ open, onToggle, onActionsExecuted }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .chatHistory()
      .then((history) => {
        if (!cancelled) setMessages((current) => (current.length ? current : history));
      })
      .catch(() => {
        /* history is a convenience; an empty panel is fine */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, loading, open]);

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const text = draft.trim();
    if (!text || loading) return;
    const optimistic: ChatMessage = {
      id: `pending-${Date.now()}`,
      role: "user",
      content: text,
      actions: null,
      created_at: new Date().toISOString(),
    };
    setMessages((m) => [...m, optimistic]);
    setDraft("");
    setError(null);
    setLoading(true);
    try {
      const res = await api.chat(text);
      setMessages((m) => [
        ...m.filter((msg) => msg.id !== optimistic.id),
        res.user_message,
        res.assistant_message,
      ]);
      if (hasExecutedAction(res.assistant_message.actions)) onActionsExecuted?.();
    } catch (err) {
      setMessages((m) => m.filter((msg) => msg.id !== optimistic.id));
      setDraft(text);
      setError(
        `Message not sent: ${err instanceof Error ? err.message : "unknown error"}`,
      );
    } finally {
      setLoading(false);
    }
  };

  if (!open) {
    return (
      <aside data-testid="chat-panel" data-open="false" className="flex w-full shrink-0 flex-col items-center border-t border-line bg-panel py-2 lg:w-9 lg:border-l lg:border-t-0">
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Open AI assistant"
          aria-expanded={false}
          className="flex flex-col items-center gap-2 rounded-sm px-1 py-2 text-[12px] text-muted hover:bg-raised hover:text-text"
        >
          <span className="text-accent">‹</span>
          <span className="[writing-mode:vertical-rl]">AI assistant</span>
        </button>
      </aside>
    );
  }

  return (
    <aside
      data-testid="chat-panel"
      data-open="true"
      aria-label="AI assistant"
      className="flex h-[520px] w-full shrink-0 flex-col border-t border-line bg-panel lg:h-auto lg:w-[340px] lg:border-l lg:border-t-0 xl:w-[380px]"
    >
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <span className="inline-block h-1.5 w-1.5 rounded-full bg-accent" aria-hidden />
        <h2 className="text-[13px] font-medium text-text">AI assistant</h2>
        <span className="text-[11px] text-muted">can trade and edit your watchlist</span>
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Collapse AI assistant"
          aria-expanded
          className="ml-auto rounded-sm px-1.5 text-[14px] text-muted hover:bg-raised hover:text-text"
        >
          ›
        </button>
      </div>

      <ol ref={listRef} data-testid="chat-messages" className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-3 py-3">
        {messages.length === 0 && !loading && (
          <li className="text-[12px] leading-relaxed text-muted">
            Ask about your portfolio, or tell me what to do, for example “Buy 5 NVDA” or “Add PYPL to my
            watchlist”. Trades I make run immediately.
          </li>
        )}
        {messages.map((m) => (
          <MessageBubble key={m.id} message={m} />
        ))}
        {loading && (
          <li data-testid="chat-loading" className="flex items-center gap-2 text-[12px] text-muted" aria-live="polite">
            <span className="typing flex gap-0.5 text-accent" aria-hidden>
              <span>●</span>
              <span>●</span>
              <span>●</span>
            </span>
            Thinking
          </li>
        )}
      </ol>

      {error && (
        <p data-testid="chat-error" role="alert" className="border-t border-line px-3 py-1.5 text-[12px] text-down">
          {error}
        </p>
      )}

      <form onSubmit={send} className="flex gap-2 border-t border-line p-2">
        <textarea
          data-testid="chat-input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          rows={2}
          maxLength={2000}
          placeholder="Message FinAlly"
          aria-label="Message the AI assistant"
          className="min-w-0 flex-1 resize-none rounded-sm border border-line bg-ink px-2 py-1.5 text-[13px] text-text placeholder:text-faint focus:border-primary focus:outline-none"
        />
        <button
          type="submit"
          data-testid="chat-send"
          disabled={loading || !draft.trim()}
          className="self-end rounded-sm bg-submit px-3 py-1.5 text-[12px] font-medium text-white hover:bg-submit-hover disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </aside>
  );
}
