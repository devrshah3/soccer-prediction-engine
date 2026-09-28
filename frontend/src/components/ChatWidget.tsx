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

// Mounted once in the root layout, so this state survives client-side navigation between
// pages (the layout tree isn't remounted on route change) without needing any persistence.
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

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
      const res = await fetch(`${API_BASE}/assistant/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      const body = await res.json();
      setMessages((m) => [...m, { role: "assistant", text: body.text, sources: body.sources, mode: body.mode }]);
    } catch {
      setMessages((m) => [
        ...m,
        { role: "assistant", text: "Couldn't reach the KickCast API. Is the backend running?" },
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
        aria-label="Open KickCast assistant"
        className="glass glass-float fixed bottom-5 right-5 z-50 flex h-14 w-14 items-center justify-center !rounded-full text-accent-2 shadow-[0_0_20px_var(--accent-glow)] transition-transform hover:scale-105 sm:bottom-6"
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
          <span className="flex h-7 w-7 items-center justify-center rounded-full bg-accent-soft text-accent">
            <ChatBubbleIcon className="h-4 w-4" />
          </span>
          <span className="text-sm font-semibold text-foreground">KickCast Assistant</span>
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
