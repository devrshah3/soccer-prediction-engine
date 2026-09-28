"use client";

import { useRef, useState } from "react";
import { AssistantSourceCard } from "./AssistantSourceCard";
import { ChatBubbleIcon, CloseIcon, ExpandIcon, MinimizeIcon, SendIcon } from "./Icons";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Message = { role: "user" | "assistant"; text: string; sources?: unknown[]; mode?: string };

const STARTERS = [
  "When does Arsenal play next?",
  "Where do Man City stand in the table?",
  "Predict Real Madrid vs Barcelona",
  "What was Liverpool's last result?",
];

const WAKING_TEXT = "Waking up the server, this can take up to a minute...";

// The free backend sleeps when idle. A first question can therefore time out: say so and retry
// (up to ~75s in total) instead of showing an error. Rate-limit and validation replies (HTTP 429/400)
// carry a friendly {detail} that is shown as the answer.
async function askWithWakeRetry(
  question: string,
  conversationId: string,
  onWaking: (waking: boolean) => void
): Promise<{ text: string; sources?: unknown[]; mode?: string }> {
  const deadline = Date.now() + 75_000;
  let notified = false;
  for (;;) {
    try {
      const res = await fetch(`${API_BASE}/assistant/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, conversation_id: conversationId }),
        signal: AbortSignal.timeout(12_000),
      });
      if (res.status >= 502 && res.status <= 504) throw new Error("waking");
      const body = await res.json().catch(() => null);
      if (notified) onWaking(false);
      if (body && typeof body.text === "string") return body;
      if (body && typeof body.detail === "string") return { text: body.detail, mode: "notice" };
      return { text: "Something went wrong. Please try again in a moment.", mode: "notice" };
    } catch {
      if (Date.now() > deadline) {
        onWaking(false);
        return { text: "I couldn't reach the server. It may be restarting - please try again in a minute.", mode: "notice" };
      }
      if (!notified) {
        notified = true;
        onWaking(true);
      }
      await new Promise((r) => setTimeout(r, 4000));
    }
  }
}

// Mounted once in the root layout, so this state survives client-side navigation between
// pages (the layout tree isn't remounted on route change) without needing any persistence.
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  // One random id per widget lifetime. The server keeps the last match/team discussed under it
  // (30 minutes, nothing personal) so follow-ups like "a video link" or "who scored" make sense.
  const conversationId = useRef<string | null>(null);

  function scrollToBottom() {
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    });
  }

  async function send(question: string) {
    const q = question.trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setLoading(true);
    scrollToBottom();
    try {
      const body = await askWithWakeRetry(q, (conversationId.current ??= crypto.randomUUID()), (waking) =>
        setMessages((m) => (waking ? [...m.filter((x) => x.mode !== "waking"), { role: "assistant", text: WAKING_TEXT, mode: "waking" }] : m.filter((x) => x.mode !== "waking")))
      );
      setMessages((m) => [...m, { role: "assistant", text: body.text, sources: body.sources, mode: body.mode }]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "Something went wrong. Please try again in a moment." },
      ]);
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        aria-label="Open assistant"
        className="glass glass-float fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center !rounded-full text-accent-text shadow-[0_0_20px_var(--accent-glow)] transition-transform hover:scale-105 sm:bottom-6"
      >
        <ChatBubbleIcon className="h-6 w-6" />
      </button>
    );
  }

  const panelClasses = expanded
    ? "glass glass-float fixed inset-2 z-50 flex flex-col !rounded-3xl sm:inset-6"
    : "glass glass-float fixed bottom-5 right-5 z-50 flex h-[min(600px,calc(100vh-7rem))] w-[min(380px,calc(100vw-2rem))] flex-col overflow-hidden sm:bottom-6";

  return (
    <div className={panelClasses}>
      <div className={`flex shrink-0 items-center justify-between border-b border-border px-4 py-3 ${expanded ? "mx-auto w-full max-w-2xl" : ""}`}>
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-accent-text">
            <ChatBubbleIcon className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold text-foreground">Assistant</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setExpanded((e) => !e)}
            aria-label={expanded ? "Restore chat panel" : "Expand to full screen"}
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-raised hover:text-foreground"
          >
            {expanded ? <MinimizeIcon className="h-4 w-4" /> : <ExpandIcon className="h-4 w-4" />}
          </button>
          <button
            onClick={() => setOpen(false)}
            aria-label="Close assistant"
            className="flex h-8 w-8 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-raised hover:text-foreground"
          >
            <CloseIcon className="h-4 w-4" />
          </button>
        </div>
      </div>

      <div ref={scrollRef} className={`flex-1 space-y-3 overflow-y-auto px-4 py-4 ${expanded ? "mx-auto w-full max-w-2xl" : ""}`}>
        {messages.length === 0 && (
          <div className="space-y-4">
            <p className="text-sm text-muted">
              Ask about a team&apos;s next match, last result, league position, or a head-to-head prediction.
            </p>
            <div className="flex flex-wrap gap-2">
              {STARTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => send(s)}
                  className="rounded-full border border-border-strong bg-surface-raised px-3 py-1.5 text-xs text-muted transition-colors hover:border-accent/50 hover:text-foreground"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
            <div className={`max-w-[85%] ${expanded ? "max-w-[70%]" : ""}`}>
              <div
                className={`rounded-2xl px-3.5 py-2 text-sm leading-relaxed ${
                  m.role === "user"
                    ? "rounded-br-sm bg-accent text-accent-foreground"
                    : "rounded-bl-sm border border-border bg-surface-raised text-foreground"
                }`}
              >
                {m.text}
              </div>
              {m.role === "assistant" && m.sources && m.sources.length > 0 && (
                <div className="mt-2 space-y-2">
                  {(m.sources as Parameters<typeof AssistantSourceCard>[0]["source"][]).map((s, si) => (
                    <AssistantSourceCard key={si} source={s} />
                  ))}
                </div>
              )}
              {m.role === "assistant" && m.mode && <p className="mt-1 text-[10px] text-muted-2">mode: {m.mode}</p>}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex justify-start">
            <div className="rounded-2xl rounded-bl-sm border border-border bg-surface-raised px-3.5 py-2 text-sm text-muted">
              <span className="inline-flex gap-1">
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-2 [animation-delay:-0.3s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-2 [animation-delay:-0.15s]" />
                <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-2" />
              </span>
            </div>
          </div>
        )}
      </div>

      <div className={`shrink-0 border-t border-border p-3 ${expanded ? "mx-auto w-full max-w-2xl" : ""}`}>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send(input)}
            placeholder="Ask about a team, fixture, table, or prediction..."
            className="flex-1 rounded-lg border border-border-strong bg-surface-raised px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-2 focus:border-accent"
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            aria-label="Send"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-accent-foreground transition-colors hover:bg-accent-hover disabled:opacity-40"
          >
            <SendIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
