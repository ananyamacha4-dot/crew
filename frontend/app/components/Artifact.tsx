"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

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
  generation: number;
  onSaveFile: (path: string, content: string) => Promise<void>;
};

type Tab = "preview" | "code";
type Viewport = "mobile" | "tablet" | "desktop";

const VIEWPORT_WIDTHS: Record<Viewport, string> = {
  mobile: "375px",
  tablet: "768px",
  desktop: "100%",
};

const tabContentVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0, transition: { type: "spring" as const, stiffness: 400, damping: 30 } },
  exit: { opacity: 0, y: -6, transition: { duration: 0.12 } },
};

export function Artifact({ projectId, name, stack, entry, files, generation, onSaveFile }: Props) {
  const [tab, setTab] = useState<Tab>("preview");
  const [active, setActive] = useState<string | null>(null);
  const [draft, setDraft] = useState<string>("");
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [viewport, setViewport] = useState<Viewport>("desktop");
  const [refreshBump, setRefreshBump] = useState(0);

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
        <motion.div
          className="artifact-title"
          initial={{ opacity: 0, x: -12 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ type: "spring", stiffness: 400, damping: 28 }}
        >
          <span className="artifact-name">{name}</span>
          <motion.span
            className="artifact-badge"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.1, type: "spring", stiffness: 500, damping: 25 }}
          >
            {stack}
          </motion.span>
          <span className="artifact-id">id: {projectId}</span>
        </motion.div>
        <nav className="artifact-tabs">
          {(["preview", "code"] as Tab[]).map((t) => (
            <button
              key={t}
              className={tab === t ? "active" : ""}
              onClick={() => setTab(t)}
            >
              {t === "preview" ? "Preview" : `Code \u00b7 ${files.length}`}
              {tab === t && (
                <motion.div
                  className="tab-indicator"
                  layoutId="tab-indicator"
                  transition={{ type: "spring", stiffness: 500, damping: 35 }}
                />
              )}
            </button>
          ))}
        </nav>
      </header>

      {/* Preview toolbar — viewport toggle + actions */}
      {tab === "preview" && (
        <div className="preview-toolbar">
          <div className="viewport-toggles">
            {(["mobile", "tablet", "desktop"] as Viewport[]).map((vp) => (
              <button
                key={vp}
                className={`vp-btn ${viewport === vp ? "active" : ""}`}
                onClick={() => setViewport(vp)}
                title={`${vp} (${VIEWPORT_WIDTHS[vp]})`}
              >
                {vp === "mobile" ? "S" : vp === "tablet" ? "M" : "L"}
              </button>
            ))}
          </div>
          <div className="preview-actions">
            <button
              className="vp-btn"
              onClick={() => setRefreshBump((b) => b + 1)}
              title="Refresh preview"
            >
              Reload
            </button>
          </div>
        </div>
      )}

      <div className="artifact-body">
        <AnimatePresence mode="wait">
          {tab === "preview" && (
            <motion.div
              key="preview"
              className="artifact-tab-content"
              variants={tabContentVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
            >
              <div className="preview-viewport" style={{ maxWidth: VIEWPORT_WIDTHS[viewport], margin: viewport !== "desktop" ? "0 auto" : undefined }}>
                {stack === "react-vite"
                  ? <SandpackPreview files={files} generation={generation + refreshBump} />
                  : <Preview files={files} entry={entry} stack={stack} generation={generation + refreshBump} />
                }
              </div>
            </motion.div>
          )}
          {tab === "code" && (
            <motion.div
              key="code"
              className="artifact-tab-content"
              variants={tabContentVariants}
              initial="hidden"
              animate="visible"
              exit="exit"
            >
              <div className="code-pane">
                <aside className="code-sidebar">
                  <FileTree files={files} active={active} onPick={setActive} />
                </aside>
                <section className="code-main">
                  {active ? (
                    <>
                      <div className="code-toolbar">
                        <span className="code-path">{active}</span>
                        <motion.button
                          className="code-save"
                          onClick={save}
                          disabled={!dirty || saving}
                          whileHover={{ scale: 1.05 }}
                          whileTap={{ scale: 0.95 }}
                        >
                          {saving ? "saving..." : dirty ? "Save" : "Saved"}
                        </motion.button>
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
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
