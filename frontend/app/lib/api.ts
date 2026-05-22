export const BACKEND =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export type Stack = "static" | "react-vite";

export type GeneratedFile = { path: string; content: string };

export type AgentStep = { agent: string; summary: string };

export type GenerateResponse = {
  project_id: string;
  name: string;
  stack: Stack;
  entry: string;
  files: GeneratedFile[];
  trail: AgentStep[];
  message: string;
};

export async function generate(
  prompt: string,
  projectId: string | null,
): Promise<GenerateResponse> {
  const res = await fetch(`${BACKEND}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, project_id: projectId }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
}

export async function saveFile(
  projectId: string,
  path: string,
  content: string,
): Promise<void> {
  const res = await fetch(`${BACKEND}/projects/${projectId}/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ path, content }),
  });
  if (!res.ok) throw new Error(await res.text());
}
