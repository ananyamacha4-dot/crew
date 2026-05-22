"use client";

import { Sandpack } from "@codesandbox/sandpack-react";
import { useMemo } from "react";

import type { GeneratedFile } from "../lib/api";

type Props = {
  files: GeneratedFile[];
  /** Bumps when files change so the sandbox remounts. */
  generation: number;
};

type SandpackFiles = Record<string, { code: string; hidden?: boolean; active?: boolean }>;

/** Render a generated React+Vite+TS project inside an in-browser Sandpack bundler.
 *  Reads the generated package.json to extract deps, prefixes every file with '/',
 *  and lets the 'vite-react-ts' template handle the rest of the build pipeline.
 */
export function SandpackPreview({ files, generation }: Props) {
  const { sandpackFiles, dependencies, devDependencies } = useMemo(
    () => buildSandpackInput(files),
    [files],
  );

  return (
    <div className="sandpack-host" key={generation}>
      <Sandpack
        template="react-ts"
        theme="dark"
        files={sandpackFiles}
        customSetup={{ dependencies, devDependencies, entry: "/src/index.tsx" }}
        options={{
          showNavigator: true,
          showTabs: false,
          showLineNumbers: false,
          showRefreshButton: true,
          showInlineErrors: true,
          editorHeight: "100%",
          editorWidthPercentage: 0,
          autoReload: true,
          recompileMode: "delayed",
          recompileDelay: 400,
        }}
      />
    </div>
  );
}

// Known-good versions. The engineer (Llama) writes stale or invalid version
// strings (e.g. lucide-react ^0.2.2 doesn't exist). For any package the
// engineer LISTED, we override its version with the one here. We do NOT
// add packages from this list that the engineer didn't ask for.
// Every entry must be a REAL npm package (Sandpack hits the npm registry).
const PINNED_VERSIONS: Record<string, string> = {
  react: "^18.3.1",
  "react-dom": "^18.3.1",
  "react-router-dom": "^6.26.0",
  "lucide-react": "^0.460.0",
  "framer-motion": "^11.11.0",
  sonner: "^1.5.0",
  clsx: "^2.1.1",
  "tailwind-merge": "^2.5.0",
  "class-variance-authority": "^0.7.0",
  "@radix-ui/react-accordion": "^1.2.1",
  "@radix-ui/react-alert-dialog": "^1.1.2",
  "@radix-ui/react-avatar": "^1.1.1",
  "@radix-ui/react-checkbox": "^1.1.2",
  "@radix-ui/react-dialog": "^1.1.2",  // <- shadcn Sheet uses this internally
  "@radix-ui/react-dropdown-menu": "^2.1.2",
  "@radix-ui/react-hover-card": "^1.1.2",
  "@radix-ui/react-label": "^2.1.0",
  "@radix-ui/react-navigation-menu": "^1.2.1",
  "@radix-ui/react-popover": "^1.1.2",
  "@radix-ui/react-progress": "^1.1.0",
  "@radix-ui/react-radio-group": "^1.2.1",
  "@radix-ui/react-scroll-area": "^1.2.0",
  "@radix-ui/react-select": "^2.1.2",
  "@radix-ui/react-separator": "^1.1.0",
  "@radix-ui/react-slider": "^1.2.1",
  "@radix-ui/react-slot": "^1.1.0",
  "@radix-ui/react-switch": "^1.1.1",
  "@radix-ui/react-tabs": "^1.1.1",
  "@radix-ui/react-toast": "^1.2.2",
  "@radix-ui/react-tooltip": "^1.1.4",
  "react-hook-form": "^7.53.0",
  "@hookform/resolvers": "^3.9.0",
  zod: "^3.23.8",
  recharts: "^2.13.0",
};

// Packages the engineer often invents that DON'T exist on npm. Drop them
// entirely — the corresponding shadcn primitive is implemented on top of
// another radix package.
const FAKE_PACKAGES = new Set([
  "@radix-ui/react-sheet",  // shadcn Sheet uses @radix-ui/react-dialog
  "@radix-ui/react-form",   // not a real package
  "@radix-ui/react-card",
  "@radix-ui/react-button",
  "@radix-ui/react-badge",
  "@radix-ui/react-input",
  "@radix-ui/react-textarea",
  "@radix-ui/react-skeleton",
  "@radix-ui/react-alert",
  "@radix-ui/react-table",
  "shadcn-ui",
  "shadcn",
]);

function buildSandpackInput(files: GeneratedFile[]) {
  const sandpackFiles: SandpackFiles = {};
  let dependencies: Record<string, string> = {};
  let devDependencies: Record<string, string> = {};

  for (const f of files) {
    const slashPath = f.path.startsWith("/") ? f.path : `/${f.path}`;

    if (f.path === "package.json") {
      const parsed = tryParseJson(f.content) as
        | { dependencies?: Record<string, string>; devDependencies?: Record<string, string> }
        | null;
      if (parsed) {
        dependencies = parsed.dependencies ?? {};
        devDependencies = parsed.devDependencies ?? {};
      }
      // Don't include package.json as a sandpack file — customSetup owns it.
      continue;
    }

    sandpackFiles[slashPath] = { code: f.content };
  }

  // Drop fake packages the engineer hallucinated.
  for (const fake of FAKE_PACKAGES) {
    delete dependencies[fake];
    delete devDependencies[fake];
  }

  // For every dep the engineer listed, if we have a known-good version, use it.
  // Don't add packages the engineer didn't ask for.
  for (const key of Object.keys(dependencies)) {
    if (PINNED_VERSIONS[key]) {
      dependencies[key] = PINNED_VERSIONS[key];
    }
  }

  // Floor the essentials in case the engineer forgot them.
  if (!dependencies.react) dependencies.react = PINNED_VERSIONS.react;
  if (!dependencies["react-dom"]) dependencies["react-dom"] = PINNED_VERSIONS["react-dom"];

  return { sandpackFiles, dependencies, devDependencies };
}

function tryParseJson(s: string): unknown {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}
