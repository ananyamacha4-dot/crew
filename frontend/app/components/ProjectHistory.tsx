"use client";

import { useEffect, useState } from "react";
import { listProjects, type ProjectSummary } from "../lib/api";

type Props = {
  onSelect: (projectId: string) => void;
  onClose: () => void;
  currentProjectId?: string;
};

export function ProjectHistory({ onSelect, onClose, currentProjectId }: Props) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  function timeAgo(ts: number): string {
    const seconds = Math.floor(Date.now() / 1000 - ts);
    if (seconds < 60) return "just now";
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }

  return (
    <div className="history-overlay" onClick={onClose}>
      <div className="history-panel" onClick={(e) => e.stopPropagation()}>
        <div className="history-header">
          <span className="history-title">Projects</span>
          <button className="history-close" onClick={onClose}>x</button>
        </div>
        <div className="history-list">
          {loading && <div className="history-empty">Loading...</div>}
          {!loading && projects.length === 0 && (
            <div className="history-empty">No projects yet. Build something!</div>
          )}
          {projects.map((p) => (
            <button
              key={p.id}
              className={`history-item ${p.id === currentProjectId ? "active" : ""}`}
              onClick={() => { onSelect(p.id); onClose(); }}
            >
              <span className="history-name">{p.name}</span>
              <span className="history-time">{timeAgo(p.updated_at)}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
