"use client";

import { useMemo } from "react";

import type { GeneratedFile, Stack } from "../lib/api";
import { buildPreviewHtml } from "../lib/buildPreview";

type Props = {
  files: GeneratedFile[];
  entry: string;
  stack: Stack;
  /** Bumps when files change so the iframe re-mounts. */
  generation: number;
};

export function Preview({ files, entry, stack, generation }: Props) {
  const srcdoc = useMemo(
    () => buildPreviewHtml(files, entry, stack),
    [files, entry, stack],
  );

  return (
    <iframe
      key={generation}
      className="preview-frame"
      sandbox="allow-scripts allow-same-origin allow-pointer-lock allow-popups"
      srcDoc={srcdoc}
      title="Preview"
    />
  );
}
