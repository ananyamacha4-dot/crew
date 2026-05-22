"""Deterministic QA checks on a generated FileSet.

Pure-Python static analysis. No Node, no Playwright. Catches the most common
failure modes that make Llama output look basic / broken:
  - dead onClick={() => {}} and href="#"
  - shadcn components imported from '@/components/ui/X' where X is not real
  - lucide-react icons that don't exist
  - bare imports without a matching package.json dependency
  - <Link to="/X"> with no matching <Route path="/X">
  - lorem ipsum

This runs BEFORE the LLM Critic and feeds its output into the Critic prompt
so the Critic doesn't waste tokens hunting for the obvious issues.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from .catalogs import LUCIDE_ICONS, SHADCN_COMPONENTS
from .schemas import FileSet


@dataclass
class QaReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


_CODE_EXTS = (".tsx", ".jsx", ".ts", ".js")


def _files_dict(fs: FileSet) -> dict[str, str]:
    return {f.path: f.content for f in fs.files}


def _scan_lucide(files: dict[str, str], r: QaReport) -> None:
    icon_set = set(LUCIDE_ICONS)
    pattern = re.compile(
        r"import\s*\{\s*([^}]+)\}\s*from\s*['\"]lucide-react['\"]",
        re.DOTALL,
    )
    for path, content in files.items():
        for group in pattern.findall(content):
            for raw in group.split(","):
                name = raw.strip().split(" as ")[0].strip()
                if not name:
                    continue
                if name not in icon_set:
                    r.errors.append(f"{path}: lucide icon '{name}' is not in the whitelist")


def _scan_shadcn(files: dict[str, str], r: QaReport) -> None:
    known = set(SHADCN_COMPONENTS.keys())
    known.update({"toaster", "use-toast"})  # sonner exports its own Toaster
    pattern = re.compile(r"from\s+['\"]@/components/ui/([a-z0-9-]+)['\"]")
    for path, content in files.items():
        for slug in pattern.findall(content):
            if slug not in known:
                r.errors.append(
                    f"{path}: unknown shadcn component '@/components/ui/{slug}' "
                    f"(must be one of {sorted(known)})"
                )


def _scan_dead_handlers(files: dict[str, str], r: QaReport) -> None:
    dead_patterns = [
        (re.compile(r"onClick=\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}"), "dead onClick={() => {}}"),
        (re.compile(r"onClick=\{\s*\(\s*\)\s*=>\s*null\s*\}"), "dead onClick={() => null}"),
        (re.compile(r"onClick=\{\s*\(\s*\)\s*=>\s*undefined\s*\}"), "dead onClick={() => undefined}"),
        (re.compile(r"\bhref=\"#\""), "dead anchor href=\"#\""),
        (re.compile(r"\bhref='#'"), "dead anchor href='#'"),
    ]
    for path, content in files.items():
        if not path.endswith(_CODE_EXTS):
            continue
        for pat, label in dead_patterns:
            if pat.search(content):
                r.errors.append(f"{path}: {label}")


def _scan_placeholders(files: dict[str, str], r: QaReport) -> None:
    bad = [
        (re.compile(r"lorem\s+ipsum", re.I), "lorem ipsum"),
        (re.compile(r"\bTODO\b"), "TODO placeholder"),
        (re.compile(r"coming soon", re.I), "'coming soon' placeholder"),
        (re.compile(r"placeholder\s+text", re.I), "'placeholder text'"),
    ]
    for path, content in files.items():
        if not path.endswith(_CODE_EXTS + (".html", ".md")):
            continue
        for pat, label in bad:
            if pat.search(content):
                r.errors.append(f"{path}: contains {label}")


def _scan_package_deps(files: dict[str, str], r: QaReport) -> None:
    pkg_raw = files.get("package.json")
    if not pkg_raw:
        r.errors.append("package.json is missing")
        return
    try:
        pkg = json.loads(pkg_raw)
    except json.JSONDecodeError as e:
        r.errors.append(f"package.json: invalid JSON ({e})")
        return
    deps: set[str] = set()
    deps.update((pkg.get("dependencies") or {}).keys())
    deps.update((pkg.get("devDependencies") or {}).keys())

    bare = re.compile(
        r"from\s+['\"]([^./@'\"][^'\"]*|@[^/'\"]+/[^'\"]+)['\"]"
    )
    referenced: set[str] = set()
    for path, content in files.items():
        if not path.endswith(_CODE_EXTS):
            continue
        for hit in bare.findall(content):
            if hit.startswith("@"):
                parts = hit.split("/")
                referenced.add("/".join(parts[:2]))
            else:
                referenced.add(hit.split("/")[0])

    builtins = {"react", "react-dom"}
    for ref in sorted(referenced):
        if ref in builtins:
            continue
        if ref.startswith("@/"):  # path alias
            continue
        if ref not in deps:
            r.errors.append(f"package.json missing dependency: '{ref}'")


def _scan_routes(files: dict[str, str], r: QaReport) -> None:
    link_paths: set[str] = set()
    route_paths: set[str] = set()
    link_pat = re.compile(r"<(?:Link|NavLink)\s+[^>]*to=\{?['\"]([^'\"]+)['\"]")
    route_pat = re.compile(r"<Route\s+[^>]*path=\{?['\"]([^'\"]+)['\"]")
    for content in files.values():
        link_paths.update(link_pat.findall(content))
        route_paths.update(route_pat.findall(content))
    for lp in link_paths:
        if lp.startswith(("#", "http://", "https://", "mailto:")):
            continue
        base = lp.split("#")[0].split("?")[0] or "/"
        if base == "/":
            continue
        if base not in route_paths:
            r.warnings.append(f"<Link to='{lp}'> has no matching <Route> in App.tsx")


def _scan_required_files(files: dict[str, str], r: QaReport) -> None:
    required = [
        "package.json",
        "vite.config.ts",
        "tailwind.config.ts",
        "tsconfig.json",
        "index.html",
        "src/main.tsx",
        "src/App.tsx",
        "src/index.css",
        "src/lib/utils.ts",
    ]
    for req in required:
        if req not in files:
            r.errors.append(f"required file missing: {req}")


def run_qa(fs: FileSet) -> QaReport:
    files = _files_dict(fs)
    r = QaReport()
    _scan_required_files(files, r)
    _scan_lucide(files, r)
    _scan_shadcn(files, r)
    _scan_dead_handlers(files, r)
    _scan_placeholders(files, r)
    _scan_package_deps(files, r)
    _scan_routes(files, r)
    return r
