"use client";

import { useState } from "react";

import { Artifact } from "./components/Artifact";
import { Chat, type Message } from "./components/Chat";
import { ProjectHistory } from "./components/ProjectHistory";
import {
  generate,
  getProject,
  getMessages,
  saveFile,
  type GenerateResponse,
  type GeneratedFile,
  type Stack,
} from "./lib/api";

type Project = {
  id: string;
  name: string;
  stack: Stack;
  entry: string;
  files: GeneratedFile[];
};

export default function Page() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [project, setProject] = useState<Project | null>(null);
  const [generation, setGeneration] = useState(0);
  const [showHistory, setShowHistory] = useState(false);

  async function sendPrompt(prompt: string) {
    if (!prompt.trim() || loading) return;

    setMessages((m) => [...m, { role: "user", content: prompt.trim() }]);
    setInput("");
    setLoading(true);

    try {
      const res: GenerateResponse = await generate(prompt.trim(), project?.id ?? null);

      if (res.files.length > 0) {
        setProject({
          id: res.project_id,
          name: res.name,
          stack: res.stack,
          entry: res.entry,
          files: res.files,
        });
        setGeneration((g) => g + 1);
      }

      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: res.message,
          trail: res.trail,
          suggestions: res.suggestions,
          palette: res.palette,
          sources: res.sources,
          intent: res.intent,
        },
      ]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
        { role: "system", content: `Error: ${e.message ?? e}` },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function onSend() {
    sendPrompt(input);
  }

  async function loadProject(projectId: string) {
    try {
      const proj = await getProject(projectId);
      const msgs = await getMessages(projectId);

      setProject({
        id: proj.id,
        name: proj.name,
        stack: "react-vite",
        entry: proj.entry,
        files: proj.files,
      });

      setMessages(
        msgs.map((m) => ({
          role: m.role as "user" | "assistant" | "system",
          content: m.content,
        })),
      );

      setGeneration((g) => g + 1);
    } catch (e: any) {
      setMessages([{ role: "system", content: `Failed to load project: ${e.message}` }]);
    }
  }

  async function onSaveFile(path: string, content: string) {
    if (!project) return;
    await saveFile(project.id, path, content);
    setProject((p) =>
      p
        ? { ...p, files: p.files.map((f) => (f.path === path ? { ...f, content } : f)) }
        : p,
    );
    setGeneration((g) => g + 1);
  }

  const hero = !project && messages.length === 0;

  return (
    <div className={`shell ${project ? "with-artifact" : ""} ${hero ? "hero" : ""}`}>
      <section className="chat-pane">
        <header className="chat-header">
          <span className="brand">{"\u26a1"} AI Builder</span>
          <span className="brand-sub">prompt -&gt; app</span>
          <div className="header-actions">
            <button
              className="header-btn"
              onClick={() => setShowHistory(true)}
              title="Project history"
            >
              History
            </button>
            {(project || messages.length > 0) && (
              <button
                className="header-btn primary"
                onClick={() => {
                  setProject(null);
                  setMessages([]);
                  setInput("");
                  setGeneration(0);
                }}
              >
                + New
              </button>
            )}
          </div>
        </header>
        <Chat
          messages={messages}
          loading={loading}
          input={input}
          onInput={setInput}
          onSend={onSend}
          hasProject={!!project}
          onPickExample={(s) => setInput(s)}
          onPickSuggestion={(s) => sendPrompt(s)}
        />
      </section>

      {project && (
        <section className="artifact-pane">
          <Artifact
            projectId={project.id}
            name={project.name}
            stack={project.stack}
            entry={project.entry}
            files={project.files}
            generation={generation}
            onSaveFile={onSaveFile}
          />
        </section>
      )}

      {showHistory && (
        <ProjectHistory
          onSelect={loadProject}
          onClose={() => setShowHistory(false)}
          currentProjectId={project?.id}
        />
      )}
    </div>
  );
}
