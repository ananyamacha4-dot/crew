export const BACKEND =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "https://crew-41zs.onrender.com";

export type Stack = "static" | "react-vite";

export type GeneratedFile = { path: string; content: string };

export type AgentStep = { agent: string; summary: string };

export type PaletteColor = { name: string; hex: string };

export type GenerateResponse = {
  project_id: string;
  name: string;
  stack: Stack;
  entry: string;
  files: GeneratedFile[];
  trail: AgentStep[];
  message: string;
  suggestions: string[];
  intent: "math" | "research" | "chat" | "build" | "design" | "image";
  palette: PaletteColor[];
  sources: string[];
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

export type OptimizePromptResponse = {
  optimized_prompt: string;
  category: string | null;
};

export async function optimizePrompt(prompt: string): Promise<OptimizePromptResponse> {
  const res = await fetch(`${BACKEND}/optimize-prompt`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
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

// --- Image generation ---

export type GenerateImageResponse = {
  image_url: string;
  prompt: string;
  width: number;
  height: number;
  seed: number | null;
};

export async function generateImage(
  prompt: string,
  width = 1024,
  height = 576,
): Promise<GenerateImageResponse> {
  const res = await fetch(`${BACKEND}/generate-image`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, width, height }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// --- Project history ---

export type ProjectSummary = {
  id: string;
  name: string;
  entry: string;
  created_at: number;
  updated_at: number;
};

export type ProjectDetail = ProjectSummary & {
  files: { path: string; content: string }[];
};

export type ChatMessage = {
  id: number;
  role: string;
  content: string;
  agent: string | null;
  created_at: number;
};

export async function listProjects(): Promise<ProjectSummary[]> {
  const res = await fetch(`${BACKEND}/projects`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  const res = await fetch(`${BACKEND}/projects/${projectId}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export async function getMessages(projectId: string): Promise<ChatMessage[]> {
  const res = await fetch(`${BACKEND}/projects/${projectId}/messages`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
