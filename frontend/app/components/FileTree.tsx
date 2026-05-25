"use client";

import { motion } from "framer-motion";

import type { GeneratedFile } from "../lib/api";

type Props = {
  files: GeneratedFile[];
  active: string | null;
  onPick: (path: string) => void;
};

const listVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.03, delayChildren: 0.05 } },
};

const itemVariants = {
  hidden: { opacity: 0, x: -10 },
  visible: { opacity: 1, x: 0, transition: { type: "spring" as const, stiffness: 500, damping: 30 } },
};

export function FileTree({ files, active, onPick }: Props) {
  const sorted = [...files].sort((a, b) => a.path.localeCompare(b.path));

  return (
    <motion.ul
      className="filetree"
      variants={listVariants}
      initial="hidden"
      animate="visible"
    >
      {sorted.map((f) => (
        <motion.li
          key={f.path}
          className={f.path === active ? "active" : ""}
          onClick={() => onPick(f.path)}
          variants={itemVariants}
          whileHover={{ x: 3, backgroundColor: "rgba(31, 111, 235, 0.08)" }}
          transition={{ type: "spring", stiffness: 400, damping: 25 }}
        >
          <span className="icon">{iconFor(f.path)}</span>
          <span className="path">{f.path}</span>
        </motion.li>
      ))}
    </motion.ul>
  );
}

function iconFor(path: string): string {
  if (path.endsWith(".html")) return "\u25c6";
  if (path.endsWith(".css")) return "\u2726";
  if (path.endsWith(".js") || path.endsWith(".jsx") || path.endsWith(".ts") || path.endsWith(".tsx")) return "\u25b8";
  if (path.endsWith(".json")) return "{ }";
  if (path.endsWith(".md")) return "\u2261";
  return "\u00b7";
}
