"use client";

import type { GeneratedFile } from "../lib/api";

type Props = {
  files: GeneratedFile[];
  active: string | null;
  onPick: (path: string) => void;
};

export function FileTree({ files, active, onPick }: Props) {
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));

  return (
    <ul className="filetree">
      {sorted.map((f) => (
        <li
          key={f.path}
          className={f.path === active ? "active" : ""}
          onClick={() => onPick(f.path)}
        >
          <span className="icon">{iconFor(f.path)}</span>
          <span className="path">{f.path}</span>
        </li>
      ))}
    </ul>
  );
}

function iconFor(path: string): string {
  if (path.endsWith(".html")) return "◆";
  if (path.endsWith(".css")) return "✦";
  if (path.endsWith(".js") || path.endsWith(".jsx") || path.endsWith(".ts") || path.endsWith(".tsx")) return "▸";
  if (path.endsWith(".json")) return "{ }";
  if (path.endsWith(".md")) return "≡";
  return "·";
}
