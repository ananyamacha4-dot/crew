"use client";

import { Sandpack } from "@codesandbox/sandpack-react";
import { useEffect, useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

import type { GeneratedFile } from "../lib/api";

type Props = {
  files: GeneratedFile[];
  generation: number;
};

type SandpackFiles = Record<string, { code: string; hidden?: boolean; active?: boolean }>;

/**
 * The Tailwind CDN config that maps utility classes to CSS custom properties.
 * The actual color/font values live in src/styles.css as :root vars — this
 * just wires Tailwind class names (bg-primary, text-foreground, etc.) to them.
 */
const TAILWIND_SETUP_CODE = `// Configure Tailwind CDN with design-system CSS variables
if (typeof window !== 'undefined') {
  (window as any).tailwind = {
    config: {
      theme: {
        extend: {
          colors: {
            background: "hsl(var(--background))",
            foreground: "hsl(var(--foreground))",
            muted: { DEFAULT: "hsl(var(--muted))", foreground: "hsl(var(--muted-foreground))" },
            primary: { DEFAULT: "hsl(var(--primary))", foreground: "hsl(var(--primary-foreground))" },
            accent: { DEFAULT: "hsl(var(--accent))", foreground: "hsl(var(--accent-foreground))" },
            border: "hsl(var(--border))",
            card: "hsl(var(--card))",
          },
          fontFamily: {
            display: ["var(--font-display)"],
            body: ["var(--font-body)"],
            mono: ["var(--font-mono)"],
          },
          borderRadius: { DEFAULT: "var(--radius)" },
        },
      },
    },
  };
}
export {};
`;

export function SandpackPreview({ files, generation }: Props) {
  const { sandpackFiles, dependencies, devDependencies } = useMemo(
    () => buildSandpackInput(files),
    [files],
  );
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(false);
    const t = setTimeout(() => setReady(true), 2200);
    return () => clearTimeout(t);
  }, [generation]);

  return (
    <div className="sandpack-host" key={generation}>
      <AnimatePresence>
        {!ready && (
          <motion.div
            className="sandpack-loader"
            initial={{ opacity: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.3 } }}
          >
            <motion.div
              className="sandpack-spinner"
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" as const }}
            />
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.2 }}
            >
              Bundling preview...
            </motion.p>
          </motion.div>
        )}
      </AnimatePresence>
      <motion.div
        className="sandpack-inner"
        initial={{ opacity: 0 }}
        animate={{ opacity: ready ? 1 : 0 }}
        transition={{ duration: 0.4 }}
      >
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
            externalResources: ["https://cdn.tailwindcss.com"],
          }}
        />
      </motion.div>
    </div>
  );
}

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
      continue;
    }

    sandpackFiles[slashPath] = { code: f.content };
  }

  // --- Tailwind CDN integration ---
  // Sandpack's react-ts template does NOT use our public/index.html, so the
  // Tailwind CDN <script> tag we put there never loads. Instead we:
  //   1. Load the CDN via Sandpack's externalResources option (in the component)
  //   2. Inject a setup file that configures Tailwind with our design-system
  //      CSS variables BEFORE React renders
  //   3. Prepend the import to index.tsx so it runs first

  // Add the Tailwind config setup module
  sandpackFiles["/src/tailwind-setup.ts"] = {
    code: TAILWIND_SETUP_CODE,
    hidden: true,
  };

  // Prepend the setup import to index.tsx so it runs before anything else
  if (sandpackFiles["/src/index.tsx"]) {
    sandpackFiles["/src/index.tsx"] = {
      code: `import './tailwind-setup';\n${sandpackFiles["/src/index.tsx"].code}`,
    };
  }

  // Drop fake packages the engineer hallucinated
  for (const fake of FAKE_PACKAGES) {
    delete dependencies[fake];
    delete devDependencies[fake];
  }

  // Pin known-good versions for packages the engineer listed
  for (const key of Object.keys(dependencies)) {
    if (PINNED_VERSIONS[key]) {
      dependencies[key] = PINNED_VERSIONS[key];
    }
  }

  // Floor essentials
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
