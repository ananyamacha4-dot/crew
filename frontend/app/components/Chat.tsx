"use client";

import { useEffect, useRef } from "react";
import Skeleton from "react-loading-skeleton";
import "react-loading-skeleton/dist/skeleton.css";

import type { AgentStep, PaletteColor } from "../lib/api";

export type Message = {
  role: "user" | "assistant" | "system";
  content: string;
  trail?: AgentStep[];
  suggestions?: string[];
  palette?: PaletteColor[];
  sources?: string[];
  intent?: string;
};

type Props = {
  messages: Message[];
  loading: boolean;
  input: string;
  onInput: (v: string) => void;
  onSend: () => void;
  hasProject: boolean;
  onPickExample?: (s: string) => void;
  onPickSuggestion?: (s: string) => void;
};

const EXAMPLES = [
  "a snake game",
  "a calculator with dark theme",
  "a landing page for a coffee shop",
  "a pomodoro timer",
];

export function Chat({ messages, loading, input, onInput, onSend, hasProject, onPickExample, onPickSuggestion }: Props) {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  function renderAssistantContent(content: string) {
    const lines = content.split("\n");
    const textLines: React.ReactNode[] = [];
    const imageUrls: string[] = [];

    lines.forEach((line, li) => {
      const trimmed = line.trim();
      // Detect image URLs
      if (
        trimmed.startsWith("https://image.pollinations.ai/") ||
        trimmed.match(/^https?:\/\/.+\.(png|jpg|jpeg|webp|gif)(\?|$)/i) ||
        trimmed.match(/^data:image\//)
      ) {
        imageUrls.push(trimmed);
      } else if (trimmed) {
        textLines.push(
          <p key={`t${li}`} className={textLines.length === 0 ? "msg-headline" : ""}>{trimmed}</p>
        );
      }
    });

    return (
      <>
        {textLines}
        {imageUrls.length > 0 && (
          <div className="image-grid">
            {imageUrls.map((url, idx) => (
              <img
                key={idx}
                src={url}
                alt={`Generated ${idx + 1}`}
                className="msg-image"
                loading="lazy"
                onClick={() => window.open(url, "_blank")}
              />
            ))}
          </div>
        )}
      </>
    );
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  }

  const lastAssistant = [...messages].reverse().find((m) => m.role === "assistant");
  const suggestions = !loading && lastAssistant?.suggestions?.length ? lastAssistant.suggestions : [];
  const palette = !loading && lastAssistant?.palette?.length ? lastAssistant.palette : [];

  return (
    <div className="chat">
      <div className="chat-messages">
        {/* Hero state */}
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

        {/* Messages */}
        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            {m.role === "assistant" ? (
              <div className="msg-content assistant-rich">
                {renderAssistantContent(m.content)}
              </div>
            ) : (
              <div className="msg-content">{m.content}</div>
            )}
            {m.trail && m.trail.length > 0 && (
              <details className="trail">
                <summary>agent trail · {m.trail.length} steps</summary>
                <ol>
                  {m.trail.map((s, j) => (
                    <li key={j}>
                      <strong>{s.agent}</strong> - {s.summary}
                    </li>
                  ))}
                </ol>
              </details>
            )}
            {m.sources && m.sources.length > 0 && (
              <div className="sources">
                <span className="sources-label">Sources:</span>
                {m.sources.map((url, si) => {
                  let hostname = url;
                  try { hostname = new URL(url).hostname; } catch {}
                  return (
                    <a key={si} href={url} target="_blank" rel="noopener noreferrer" className="source-link">
                      {hostname}
                    </a>
                  );
                })}
              </div>
            )}
          </div>
        ))}

        {/* Loading skeleton */}
        {loading && (
          <div className="msg assistant skeleton-msg">
            <div className="skeleton-header">
              <div className="skeleton-dot-pulse"><span className="dot" /><span className="dot" /><span className="dot" /></div>
              <span className="skeleton-label">Agents working...</span>
            </div>
            <Skeleton
              count={3}
              baseColor="#141c28"
              highlightColor="#1e2a3a"
              borderRadius={6}
              height={14}
              style={{ marginBottom: 6 }}
            />
            <Skeleton
              baseColor="#141c28"
              highlightColor="#1e2a3a"
              borderRadius={6}
              width="60%"
              height={14}
            />
          </div>
        )}

        {/* Palette */}
        {palette.length > 0 && (
          <div className="palette-bar">
            <span className="suggestions-label">Palette:</span>
            <div className="palette-swatches">
              {palette.map((c) => (
                <div key={c.name} className="swatch" title={`${c.name}: ${c.hex}`}>
                  <span className="swatch-dot" style={{ background: c.hex }} />
                  <span className="swatch-label">{c.name}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Suggestions */}
        {suggestions.length > 0 && (
          <div className="suggestions">
            <span className="suggestions-label">Try next:</span>
            <div className="suggestions-chips">
              {suggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="suggestion-chip"
                  onClick={() => onPickSuggestion?.(s)}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <div ref={endRef} />
      </div>

      {/* Composer — always visible */}
      <div className="composer">
        <div className="composer-inner">
          <textarea
            value={input}
            onChange={(e) => onInput(e.target.value)}
            onKeyDown={onKey}
            placeholder={hasProject ? "Describe a change..." : "Describe what you want to build..."}
            disabled={loading}
            rows={1}
          />
          <button onClick={onSend} disabled={loading || !input.trim()}>
            {loading ? "..." : hasProject ? "Update" : "Build"}
          </button>
        </div>
      </div>
    </div>
  );
}
