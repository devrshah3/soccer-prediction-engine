"use client";

import { useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Message = { role: "user" | "assistant"; text: string; sources?: unknown[]; mode?: string };

export default function AssistantPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  async function send() {
    const question = input.trim();
    if (!question || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }]);
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/assistant/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      const body = await res.json();
      setMessages((m) => [...m, { role: "assistant", text: body.text, sources: body.sources, mode: body.mode }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", text: "Couldn't reach the KickCast API. Is the backend running?" }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex h-[70vh] flex-col">
      <div>
        <h1 className="text-2xl font-bold text-zinc-50">Ask about soccer</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Answers come from our own database first. Without a Gemini key configured, this runs in DB-only
          mode - it can answer about a specific team&apos;s next match, last result, league position, or a
          head-to-head prediction.
        </p>
      </div>
      <div className="mt-4 flex-1 space-y-3 overflow-y-auto rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        {messages.length === 0 && (
          <p className="text-sm text-zinc-600">Try: &quot;When does Arsenal play next?&quot;</p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <span
              className={`inline-block max-w-[85%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "bg-emerald-700 text-white" : "bg-zinc-800 text-zinc-100"
              }`}
            >
              {m.text}
            </span>
            {m.role === "assistant" && m.mode && (
              <p className="mt-1 text-[10px] text-zinc-600">mode: {m.mode}</p>
            )}
          </div>
        ))}
        {loading && <p className="text-sm text-zinc-500">Thinking...</p>}
      </div>
      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about a team, fixture, table, or prediction..."
          className="flex-1 rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600"
        />
        <button
          onClick={send}
          disabled={loading}
          className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
