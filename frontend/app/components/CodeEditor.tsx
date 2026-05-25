"use client";

import dynamic from "next/dynamic";
import { useState } from "react";

const Monaco = dynamic(
  () => import("@monaco-editor/react").then((m) => m.default),
  {
    ssr: false,
    loading: () => <div className="editor-loading">loading editor...</div>,
  },
);

type Props = {
  path: string;
  content: string;
  onChange: (next: string) => void;
};

export function CodeEditor({ path, content, onChange }: Props) {
  const [error, setError] = useState(false);

  if (error) {
    return (
      <div className="editor-loading">
        <p>Editor failed to load.</p>
        <button
          onClick={() => { setError(false); }}
          style={{ color: "#58a6ff", background: "none", border: "1px solid #1e2a3a", borderRadius: 6, padding: "4px 12px", marginTop: 8, cursor: "pointer" }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <Monaco
      path={path}
      defaultLanguage={languageFor(path)}
      value={content}
      onChange={(v) => onChange(v ?? "")}
      theme="vs-dark"
      onMount={() => setError(false)}
      options={{
        minimap: { enabled: false },
        fontSize: 13,
        lineNumbers: "on",
        scrollBeyondLastLine: false,
        wordWrap: "on",
        tabSize: 2,
      }}
    />
  );
}

function languageFor(path: string): string {
  if (path.endsWith(".html")) return "html";
  if (path.endsWith(".css")) return "css";
  if (path.endsWith(".json")) return "json";
  if (path.endsWith(".md")) return "markdown";
  if (path.endsWith(".tsx")) return "typescriptreact";
  if (path.endsWith(".jsx")) return "javascriptreact";
  if (path.endsWith(".ts")) return "typescript";
  if (path.endsWith(".js")) return "javascript";
  return "plaintext";
}
