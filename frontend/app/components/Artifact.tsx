"use client";

import { useEffect, useState } from "react";

import type { GeneratedFile, Stack } from "../lib/api";
import { CodeEditor } from "./CodeEditor";
import { FileTree } from "./FileTree";
import { Preview } from "./Preview";
import { SandpackPreview } from "./SandpackPreview";

type Props = {
  projectId: string;
  name: string;
  stack: Stack;
  entry: string;
  files: GeneratedFile[];
  /** Bumps every successful /generate response. */
  generation: number;
  onSaveFile: (path: string, content: string) => Promise<void>;
};

type Tab = "preview" | "code";

export function Artifact({ projectId, name, stack, entry, files, generation, onSaveFile }: Props) {
  const [tab, setTab] = useState<Tab>("preview");
  const [active, setActive] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!active && files.length > 0) {
      const initial = files.find((f) => f.path === entry)?.path
        ?? files.find((f) => f.path.endsWith(".html"))?.path
        ?? files[0].path;
      setActive(initial);
    }
  }, [files, entry, active]);

  useEffect(() => {
    if (active) {
      const f = files.find((x) => x.path === active);
      setDraft(f?.content ?? "");
      setDirty(false);
    }
  }, [active, files, generation]);

  async function save() {
    if (!active || !dirty) return;
    setSaving(true);
    try {
      await onSaveFile(active, draft);
      setDirty(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="artifact">
      <header className="artifact-header">
        <div className="artifact-title">
          <span className="artifact-name">{name}</span>
          <span className="artifact-badge">{stack}</span>
          <span className="artifact-id">id: {projectId}</span>
        </div>
        <nav className="artifact-tabs">
          <button
            className={tab === "preview" ? "active" : ""}
            onClick={() => setTab("preview")}
          >
            Preview
          </button>
          <button
            className={tab === "code" ? "active" : ""}
            onClick={() => setTab("code")}
          >
            Code &middot; {files.length}
          </button>
        </nav>
      </header>

      <div className="artifact-body">
        {tab === "preview" && (
          stack === "react-vite"
            ? <SandpackPreview files={files} generation={generation} />
            : <Preview files={files} entry={entry} stack={stack} generation={generation} />
        )}
        {tab === "code" && (
          <div className="code-pane">
            <aside className="code-sidebar">
              <FileTree files={files} active={active} onPick={setActive} />
            </aside>
            <section className="code-main">
              {active ? (
                <>
                  <div className="code-toolbar">
                    <span className="code-path">{active}</span>
                    <button
                      className="code-save"
                      onClick={save}
                      disabled={!dirty || saving}
                    >
                      {saving ? "saving..." : dirty ? "Save" : "Saved"}
                    </button>
                  </div>
                  <div className="code-editor">
                    <CodeEditor
                      path={active}
                      content={draft}
                      onChange={(v) => {
                        setDraft(v);
                        setDirty(true);
                      }}
                    />
                  </div>
                </>
              ) : (
                <div className="empty-state">no file selected</div>
              )}
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
