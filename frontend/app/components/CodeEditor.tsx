"use client";

import dynamic from "next/dynamic";

const Monaco = dynamic(() => import("@monaco-editor/react").then((m) => m.default), {
  ssr: false,
  loading: () => <div className="editor-loading">loading editor...</div>,
});

type Props = {
  path: string;
  content: string;
  onChange: (next: string) => void;
};

export function CodeEditor({ path, content, onChange }: Props) {
  return (
    <Monaco
      path={path}
      defaultLanguage={languageFor(path)}
      value={content}
      onChange={(v) => onChange(v ?? "")}
      theme="vs-dark"
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
  if (path.endsWith(".jsx") || path.endsWith(".tsx")) return "javascript";
  if (path.endsWith(".ts")) return "typescript";
  if (path.endsWith(".js")) return "javascript";
  return "plaintext";
}
