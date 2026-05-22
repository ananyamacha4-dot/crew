"use client";

import { useState } from "react";

import { Artifact } from "./components/Artifact";
import { Chat, type Message } from "./components/Chat";
import {
  generate,
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

  async function onSend() {
    const prompt = input.trim();
    if (!prompt || loading) return;

    setMessages((m) => [...m, { role: "user", content: prompt }]);
    setInput("");
    setLoading(true);

    try {
      const res: GenerateResponse = await generate(prompt, project?.id ?? null);
      setProject({
        id: res.project_id,
        name: res.name,
        stack: res.stack,
        entry: res.entry,
        files: res.files,
      });
      setGeneration((g) => g + 1);
      setMessages((m) => [
        ...m,
        { role: "assistant", content: res.message, trail: res.trail },
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

  async function onSaveFile(path: string, content: string) {
    if (!project) return;
    await saveFile(project.id, path, content);
    setProject((p) =>
      p
        ? {
            ...p,
            files: p.files.map((f) =>
              f.path === path ? { ...f, content } : f,
            ),
          }
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
        </header>
        <Chat
          messages={messages}
          loading={loading}
          input={input}
          onInput={setInput}
          onSend={onSend}
          hasProject={!!project}
          onPickExample={(s) => setInput(s)}
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
    </div>
  );
}
