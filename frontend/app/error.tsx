"use client";

import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // ChunkLoadError = stale cache. Auto-reload clears it.
    if (error.message?.includes("ChunkLoadError") || error.message?.includes("Loading chunk")) {
      window.location.reload();
      return;
    }
  }, [error]);

  return (
    <div style={{
      height: "100vh",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      background: "#0a0e16",
      color: "#e6edf3",
      fontFamily: "system-ui",
      gap: 16,
    }}>
      <h2 style={{ fontSize: 20, fontWeight: 600 }}>Something went wrong</h2>
      <p style={{ color: "#6e7a8b", fontSize: 14 }}>{error.message}</p>
      <button
        onClick={() => {
          // Clear caches and retry
          if ("caches" in window) {
            caches.keys().then((names) => names.forEach((n) => caches.delete(n)));
          }
          reset();
        }}
        style={{
          background: "#2563eb",
          color: "white",
          border: "none",
          borderRadius: 8,
          padding: "8px 20px",
          fontSize: 14,
          fontWeight: 600,
          cursor: "pointer",
        }}
      >
        Try again
      </button>
    </div>
  );
}
