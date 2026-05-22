"use client";

import { useEffect, useRef } from "react";

import type { AgentStep } from "../lib/api";

export type Message = {
  role: "user" | "assistant" | "system";
  content: string;
  trail?: AgentStep[];
};

type Props = {
  messages: Message[];
  loading: boolean;
  input: string;
  onInput: (v: string) => void;
  onSend: () => void;
  hasProject: boolean;
  onPickExample?: (s: string) => void;
};

const EXAMPLES = [
  "a snake game",
  "a calculator with dark theme",
  "a landing page for a coffee shop",
  "a pomodoro timer",
];

export function Chat({ messages, loading, input, onInput, onSend, hasProject, onPickExample }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  return (
    <div className="chat">
      <div className="chat-messages">
        {messages.length === 0 && !loading && (
          <div className="empty-state">
            <h1>What do you want to build?</h1>
            <p className="hero-sub">Describe an app or game. The agents will plan, code, and ship it.</p>
            <div className="example-chips">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  className="chip"
                  onClick={() => onPickExample?.(ex)}
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className="msg-content">{m.content}</div>
            {m.trail && m.trail.length > 0 && (
              <details className="trail">
                <summary>agent trail &middot; {m.trail.length} steps</summary>
                <ol>
                  {m.trail.map((s, j) => (
                    <li key={j}>
                      <strong>{s.agent}</strong> - {s.summary}
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </div>
        ))}

        {loading && (
          <div className="msg assistant">
            <div className="thinking">
              <span className="dot" />
              <span className="dot" />
              <span className="dot" />
              <span style={{ marginLeft: 8 }}>building...</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </div>

      <div className="composer">
        <div className="composer-inner">
          <textarea
            value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={onKey}
            placeholder={hasProject ? "Describe a change..." : "Describe what you want to build..."}
            disabled={loading}
            rows={2}
          />
          <button onClick={onSend} disabled={loading || !input.trim()}>
            {loading ? "..." : hasProject ? "Update" : "Build"}
          </button>
        </div>
      </div>
    </div>
  );
}
