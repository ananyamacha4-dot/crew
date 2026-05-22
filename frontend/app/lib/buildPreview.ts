import type { GeneratedFile, Stack } from "./api";

/** Build an HTML string suitable for <iframe srcdoc> from a project's files.
 *  Static stack: returns the entry file as-is (the Coder is instructed to
 *    inline CSS/JS into a single index.html).
 *  React-vite stack: returns a placeholder document — preview requires a
 *    bundler. Use the Code tab to view source.
 */
export function buildPreviewHtml(
  files: GeneratedFile[],
  entry: string,
  stack: Stack,
): string {
  if (stack === "static") {
    const entryFile = files.find((f) => f.path === entry)
      ?? files.find((f) => f.path.endsWith(".html"));
    if (!entryFile) return notFoundHtml(entry, files);

    // If the entry references sibling .css/.js by relative path, inline them.
    let html = entryFile.content;
    html = inlineLinkedCss(html, files);
    html = inlineLinkedJs(html, files);
    return html;
  }

  return reactPreviewPlaceholder(files, entry);
}

function inlineLinkedCss(html: string, files: GeneratedFile[]): string {
  return html.replace(
    /<link\s+[^>]*rel=["']stylesheet["'][^>]*href=["']([^"']+)["'][^>]*>/gi,
    (full, href) => {
      const f = files.find((x) => sameFile(x.path, href));
      return f ? `<style>\n${f.content}\n</style>` : full;
    },
  );
}

function inlineLinkedJs(html: string, files: GeneratedFile[]): string {
  return html.replace(
    /<script\s+[^>]*src=["']([^"']+)["'][^>]*><\/script>/gi,
    (full, src) => {
      const f = files.find((x) => sameFile(x.path, src));
      return f ? `<script>\n${f.content}\n</script>` : full;
    },
  );
}

function sameFile(filePath: string, ref: string): boolean {
  const norm = (s: string) => s.replace(/^\.?\//, "").replace(/\\/g, "/");
  return norm(filePath) === norm(ref);
}

function notFoundHtml(entry: string, files: GeneratedFile[]): string {
  const list = files.map((f) => `<li><code>${escapeHtml(f.path)}</code></li>`).join("");
  return `<!doctype html><html><body style="font-family:system-ui;padding:24px;color:#888;background:#111;">
    <h3>No preview</h3>
    <p>Entry file <code>${escapeHtml(entry)}</code> not found.</p>
    <p>Files in project:</p><ul style="color:#aaa">${list}</ul>
  </body></html>`;
}

function reactPreviewPlaceholder(files: GeneratedFile[], entry: string): string {
  const list = files.map((f) => `<li><code>${escapeHtml(f.path)}</code></li>`).join("");
  return `<!doctype html><html><body style="font-family:system-ui;padding:24px;color:#e6edf3;background:#0d1117;">
    <h3 style="margin:0 0 12px;">React + Vite project</h3>
    <p style="color:#8b949e;margin:0 0 16px;">In-browser preview for React projects is coming. For now, open the <strong>Code</strong> tab to view the source, or run locally:</p>
    <pre style="background:#161b22;padding:12px;border-radius:8px;color:#79c0ff;overflow:auto;">npm install
npm run dev</pre>
    <p style="color:#8b949e;margin:16px 0 4px;">Generated files:</p>
    <ul style="color:#c9d1d9;">${list}</ul>
  </body></html>`;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]!));
}
