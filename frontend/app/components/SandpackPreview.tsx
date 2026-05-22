"use client";

import {
  SandpackLayout,
  SandpackPreview as SPPreview,
  SandpackProvider,
} from "@codesandbox/sandpack-react";
import { useMemo, useState } from "react";

import type { GeneratedFile } from "../lib/api";

type Props = {
  files: GeneratedFile[];
  /** Bumps when files change so the sandbox remounts. */
  generation: number;
};

type SandpackFiles = Record<string, { code: string; hidden?: boolean; active?: boolean }>;

type Viewport = "mobile" | "tablet" | "desktop";

const VIEWPORT_WIDTHS: Record<Viewport, number | null> = {
  mobile: 390,
  tablet: 768,
  desktop: null, // null = fill the container
};

/** Render a generated React project inside an in-browser Sandpack bundler.
 *  Preview-ONLY (no code editor inside the preview pane — the Artifact's
 *  "Code" tab is the proper place to read source). */
export function SandpackPreview({ files, generation }: Props) {
  const [viewport, setViewport] = useState<Viewport>("desktop");

  const { sandpackFiles, dependencies, devDependencies } = useMemo(
    () => buildSandpackInput(files),
    [files],
  );

  const width = VIEWPORT_WIDTHS[viewport];

  return (
    <div className="sandpack-host" key={generation}>
      <div className="sandpack-toolbar">
        <div className="sandpack-viewport-toggle">
          {(Object.keys(VIEWPORT_WIDTHS) as Viewport[]).map((vp) => (
            <button
              key={vp}
              type="button"
              className={vp === viewport ? "active" : ""}
              onClick={() => setViewport(vp)}
            >
              {vp}
            </button>
          ))}
        </div>
        <span className="sandpack-width-label">
          {width ? `${width}px` : "fill"}
        </span>
      </div>

      <div className="sandpack-stage">
        <div
          className="sandpack-frame"
          style={width ? { width: `${width}px`, maxWidth: "100%" } : undefined}
        >
          <SandpackProvider
            template="react-ts"
            theme="dark"
            files={sandpackFiles}
            customSetup={{
              dependencies,
              devDependencies,
              entry: "/src/index.tsx",
            }}
            options={{
              recompileMode: "delayed",
              recompileDelay: 400,
              autoReload: true,
            }}
          >
            <SandpackLayout style={{ height: "100%", border: "none", borderRadius: 0 }}>
              <SPPreview
                showNavigator
                showRefreshButton
                showOpenInCodeSandbox
                showRestartButton
                style={{
                  height: "100%",
                  flex: 1,
                  background: "white",
                }}
              />
            </SandpackLayout>
          </SandpackProvider>
        </div>
      </div>
    </div>
  );
}

// ----------------------------------------------------------------------
// Dependency normalization — keep this in sync with the generated package.json.
// ----------------------------------------------------------------------

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
  "@radix-ui/react-dialog": "^1.1.2",
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

const FAKE_PACKAGES = new Set([
  "@radix-ui/react-sheet",
  "@radix-ui/react-form",
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
      // package.json is owned by customSetup, not a sandpack file.
      continue;
    }

    sandpackFiles[slashPath] = { code: f.content };
  }

  for (const fake of FAKE_PACKAGES) {
    delete dependencies[fake];
    delete devDependencies[fake];
  }

  for (const key of Object.keys(dependencies)) {
    if (PINNED_VERSIONS[key]) {
      dependencies[key] = PINNED_VERSIONS[key];
    }
  }

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
