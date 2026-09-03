#!/usr/bin/env python3
"""docs_layout.py -- one docs/ layout for every project: a map agents follow, a check that enforces it, a
--propose that reworks an existing tree (#886).

The rule: a file's directory answers the question a reader would ask to find it. Code goes in scripts/,
never in docs/. A script's output goes under a directory marked generated. Binaries go under
design/assets/ or evidence/, never at a root. Memos go under brain/memos/<type>/.

  docs/README.md      the map -- one line per directory + the rule; the first thing an agent reads
  product/            WHAT we are building: spec, roadmap, routes, features/, roles/, acceptance/
  design/             WHAT IT LOOKS LIKE: briefs, prompts, UI decisions; assets/ beneath it
  architecture/       HOW IT IS BUILT -- generated from code (/rails-flow:graph); never hand-edited
  runbooks/           HOW TO OPERATE IT: setup, deploy, on-call, integrations
  evidence/           WHAT WE MEASURED: spikes, screenshots, coverage, validation -- dated, immutable
  wiki/               REFERENCE -- generated pages from the codebase + hand-written pages left alone
  brain/              WHAT WE LEARNED AND DECIDED: STATUS, DECISIONS, HYPOTHESES, PROGRESS-LOG, MEMORY, memos/

  --report            every file classified; the findings; exit 0 conforming, 1 findings, 3 no docs/
  --propose           the move plan AND the link rewrites it needs across the repo, as a diff; writes nothing
  --write             apply the plan (with --propose); then assert every rewritten link resolves
  --scaffold          print (or with --write, create) docs/README.md and the directory READMEs that are missing
  --json / --selftest

A move whose references live in a file this tool cannot rewrite (a binary) is REFUSED, not guessed.
Nothing here summarises or edits prose: files move byte-for-byte; only path strings are rewritten.
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

DOCS = Path("docs")
ROOT_ALLOWED = {"README.md", "GUIDE.md"}           # the map, and setup-flow §7b's human guide
LAYOUT: dict[str, tuple[str, str]] = {
    # dir: (question it answers, what belongs -- the directory README)
    "product":      ("WHAT are we building?", "the spec, roadmap, routes, `features/F-NN-*.md`, `roles/`, `acceptance/`. Authored. Not: how it is built, how to run it."),
    "design":       ("WHAT does it look like?", "briefs, prompts, UI decisions; images and brand files under `assets/`. Authored. Not: screenshots as evidence (evidence/)."),
    "architecture": ("HOW is it built?", "GENERATED from code by `/rails-flow:graph` (`graph.json`, `graph.md`, `index.html`). Never hand-edited; regenerate instead."),
    "runbooks":     ("HOW do I operate it?", "setup guides, deploy, on-call, integrations (SSO, mail, payments). Authored. Dated where a step depends on a version."),
    "evidence":     ("WHAT did we measure?", "spikes, screenshots, coverage reports, validation results. Dated, immutable: add a new file, never edit an old one."),
    "wiki":         ("WHERE is the reference?", "GENERATED reference pages from the codebase plus hand-written pages the generator leaves alone. Rebuilt at ship."),
    "brain":        ("WHAT did we learn and decide?", "`STATUS.md`, `DECISIONS.md`, `HYPOTHESES.md`, `PROGRESS-LOG.md`, `MEMORY.md`, memos under `memos/<type>/`, `history/`. Not: product specs (product/)."),
}
GENERATED_DIRS = {"architecture", "wiki"}
BRAIN_ROOT_ALLOWED = {"README.md", "STATUS.md", "DECISIONS.md", "HYPOTHESES.md", "PROGRESS-LOG.md", "MEMORY.md", "FEDERATION.md", "BRIEF.md", ".last-review"}
BRAIN_SUBDIRS = {"memos", "history"}
CODE_EXT = {".py", ".rb", ".sh", ".js", ".ts", ".mjs", ".bash", ".zsh"}
BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".pdf", ".webp", ".ico", ".mp4", ".mov", ".zip", ".woff", ".woff2", ".ttf"}
PROSE_EXT = {".md", ".markdown", ".txt", ".html", ".rst"}
GENERATED_HEADER = re.compile(r"generated (by|from|at)|do not (hand-)?edit|auto-?generated", re.I)
MEMO_SHAPED = re.compile(r"^(feedback|decision)[-_]")

# Name-based homing for top-level directories and root files the layout does not name. Order matters:
# first match wins. `sure` says whether --propose may place it without a human confirming.
RENAMES = {"role-specs": "roles", "brand-assets": "brand", "brand": "brand", "spike-evidence": "spikes", "img": "images"}
DIR_HOMES: list[tuple[re.Pattern, str, bool]] = [
    (re.compile(r"^(features?|specs?|roles?|role-specs|acceptance|requirements|prd)$", re.I), "product/{name}", True),
    (re.compile(r"^(brand|brand-assets|assets|images|img|logos?)$", re.I), "design/assets/{name}", True),
    (re.compile(r"^(spikes?|spike-evidence|screenshots|validation|coverage|benchmarks?|audits?)$", re.I), "evidence/{name}", True),
    (re.compile(r"^(runbooks?|ops|operations|setup|deploy(ment)?|integrations?)$", re.I), "runbooks/{name}", True),
    (re.compile(r"^(adr|adrs|decisions)$", re.I), "brain/{name}", True),
]
FILE_HOMES: list[tuple[re.Pattern, str, bool]] = [
    (re.compile(r"(runbook|setup|deploy|oncall|on-call|sso|install)", re.I), "runbooks", True),
    (re.compile(r"(spike|validation|evidence|coverage|benchmark|audit)", re.I), "evidence", True),
    (re.compile(r"(design|prompt|brand|style|mockup|wireframe)", re.I), "design", True),
    (re.compile(r"(spec|roadmap|routes|sitemap|requirements|prd|feature|backlog|plan)", re.I), "product", True),
]


# ----------------------------------------------------------------------------- classification

def is_binary(p: Path) -> bool:
    try:
        return b"\0" in p.read_bytes()[:8000]
    except OSError:
        return False


def kind_of(p: Path, docs: Path) -> str:
    """authored | generated | code | binary | memory -- by directory, extension, marker or header."""
    rel = p.relative_to(docs)
    top = rel.parts[0] if len(rel.parts) > 1 else None
    if top == "brain":
        return "memory"
    if p.suffix.lower() in CODE_EXT:
        return "code"
    if p.suffix.lower() in BINARY_EXT or (p.suffix.lower() not in PROSE_EXT and is_binary(p)):
        return "binary"
    if top in GENERATED_DIRS or (top and (docs / top / ".generated").exists()) or (p.parent / ".generated").exists():
        return "generated"
    if p.suffix.lower() in PROSE_EXT | {".json"}:
        try:
            head = p.read_text(encoding="utf-8", errors="replace")[:600]
        except OSError:
            head = ""
        if GENERATED_HEADER.search(head):
            return "generated"
    return "authored"


def home_for(p: Path, docs: Path, kind: str, declared: set[str] = frozenset(), rules: list[tuple[str, str]] = ()) -> tuple[str | None, bool, str]:
    """(new relative path under docs/ or None if it is fine where it is, sure?, reason)."""
    import fnmatch
    rel = p.relative_to(docs)
    parts = rel.parts
    top = parts[0] if len(parts) > 1 else None
    if top is None and rel.name not in ROOT_ALLOWED:
        for glob, dest in rules:                                       # the map's own word on a root file wins
            if fnmatch.fnmatch(rel.name, glob):
                return f"{dest}{rel.name}", True, f"root file; the map's `## Root files` says {dest}"
    if top in declared:                                               # the project's map says this directory exists
        return None, True, ""
    if kind == "code":
        return None, True, "code does not live in docs/ -- move it to scripts/ (outside this tool's tree)"
    if top is None:                                                   # a file at the docs root
        if rel.name in ROOT_ALLOWED:
            return None, True, ""
        if kind == "binary":
            return f"design/assets/{rel.name}", False, "a binary at the docs root"
        if kind == "generated":
            return f"architecture/{rel.name}", False, "a generated file at the docs root -- architecture/ if it is derived from code or the spec, evidence/ if it is a point-in-time measurement"
        for pat, dest, sure in FILE_HOMES:
            if pat.search(rel.stem):
                return f"{dest}/{rel.name}", sure, f"root file; name says {dest}/"
        return f"product/{rel.name}", False, "root file with no recognisable kind -- product/ unless you know better"
    if top in LAYOUT:
        if top == "brain":
            if len(parts) == 2 and rel.name not in BRAIN_ROOT_ALLOWED:
                if MEMO_SHAPED.match(rel.name):
                    m = MEMO_SHAPED.match(rel.name)
                    memo_type = m.group(1)
                    return f"brain/memos/{memo_type}/{rel.name[len(m.group(0)):]}", True, "a memo at the brain root belongs under memos/<type>/"
                return f"product/{rel.name}", False, "a non-brain file at the brain root"
            if len(parts) > 2 and parts[1] not in BRAIN_SUBDIRS:
                sub = RENAMES.get(parts[1], parts[1])
                return f"product/{sub}/{'/'.join(parts[2:])}", True, f"`brain/{parts[1]}/` is product content inside memory (specs, roles, open questions)"
            return None, True, ""
        if kind == "binary" and top not in {"design", "evidence"}:
            return f"design/assets/{'/'.join(parts[1:])}", False, f"a binary under {top}/ -- design/assets/ or evidence/"
        return None, True, ""
    for pat, dest, sure in DIR_HOMES:                                 # an unknown top-level directory
        if pat.match(top):
            return dest.format(name=RENAMES.get(top, top)) + "/" + "/".join(parts[1:]), sure, f"`{top}/` is not a layout directory; its name says {dest.split('/')[0]}/"
    return f"product/{'/'.join(parts)}", False, f"`{top}/` is not a layout directory and its name says nothing -- product/ unless you know better"


MAP_ROW = re.compile(r"^\|\s*`([a-z][a-z0-9_-]*)/`\s*\|", re.M)


ROOT_FILE_ROW = re.compile(r"^\|\s*`([^`|]+)`\s*\|\s*`([a-z][A-Za-z0-9_/-]*/)`\s*\|", re.M)


def root_file_rules(root: Path) -> list[tuple[str, str]]:
    """`## Root files` rows in docs/README.md: (glob, `dir/[sub/]`) -- where a root file the layout cannot
    name belongs. The map is the source of truth; the tool reads it rather than guessing twice."""
    readme = root / DOCS / "README.md"
    if not readme.is_file():
        return []
    text = readme.read_text(encoding="utf-8", errors="replace")
    section = text.split("## Root files", 1)
    return ROOT_FILE_ROW.findall(section[1]) if len(section) == 2 else []


def declared_dirs(root: Path) -> set[str]:
    """Directories the project's own map (docs/README.md) declares, beyond the layout's eight."""
    readme = root / DOCS / "README.md"
    if not readme.is_file():
        return set()
    return {m for m in MAP_ROW.findall(readme.read_text(encoding="utf-8", errors="replace"))} - set(LAYOUT)


def classify(root: Path) -> list[dict]:
    docs = root / DOCS
    extra = declared_dirs(root)
    rules = root_file_rules(root)
    rows = []
    for p in sorted(x for x in docs.rglob("*") if x.is_file() and ".git" not in x.parts):
        if p.name == ".generated":
            continue
        kind = kind_of(p, docs)
        dest, sure, reason = home_for(p, docs, kind, extra, rules)
        rows.append({"path": p.relative_to(root).as_posix(), "kind": kind, "dest": (DOCS / dest).as_posix() if dest else None,
                     "sure": sure, "reason": reason})
    return rows


def findings(root: Path, rows: list[dict]) -> list[str]:
    out = []
    docs = root / DOCS
    if not (docs / "README.md").is_file():
        out.append("docs/README.md is missing -- the map agents read before creating a file (--scaffold writes it)")
    for d in GENERATED_DIRS:
        if (docs / d).is_dir() and not (docs / d / ".generated").exists():
            out.append(f"docs/{d}/ is a generated directory with no `.generated` marker (--scaffold writes it)")
    for r in rows:
        if r["kind"] == "code":
            out.append(f"{r['path']}: code in docs/ -- {r['reason']}")
        elif r["dest"]:
            out.append(f"{r['path']}: {r['reason']} -> {r['dest']}" + ("" if r["sure"] else "  (unsure -- confirm)"))
    return out


# ----------------------------------------------------------------------------- the plan

def text_files(root: Path) -> list[Path]:
    """Every tracked text file, plus untracked non-ignored ones -- the set whose path strings we rewrite."""
    try:
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root,
                             capture_output=True, check=True).stdout.decode("utf-8", "replace")
        paths = [root / p for p in out.split("\0") if p]
    except (subprocess.CalledProcessError, FileNotFoundError):
        paths = [p for p in root.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [p for p in paths if p.is_file() and not is_binary(p)]


def references(root: Path, old_rel: str, files: list[Path]) -> tuple[list[Path], list[Path]]:
    """Files whose text mentions the old path, by its repo-relative string or its docs-relative tail."""
    tail = old_rel[len("docs/"):]
    text_hits, binary_hits = [], []
    for f in files:
        try:
            s = f.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if old_rel in s or tail in s:          # a hit is a candidate; plan() keeps only rewrites that change text
            text_hits.append(f)
    # binaries that mention the path cannot be rewritten: refuse rather than guess
    try:
        grep = subprocess.run(["git", "grep", "-l", "-I", "--", old_rel], cwd=root, capture_output=True, text=True)
        # -I skips binaries; a second pass WITHOUT -I finds the ones that hold the string and were skipped
        grep_all = subprocess.run(["git", "grep", "-l", "--", old_rel], cwd=root, capture_output=True, text=True)
        skipped = set(grep_all.stdout.split()) - set(grep.stdout.split())
        binary_hits = [root / p for p in skipped]
    except FileNotFoundError:
        pass
    return text_hits, binary_hits


def _protected(key: str, s: str, fn) -> str:
    """Apply `fn` to the text, except inside the map's `## Root files` table, whose globs name files by
    their ROOT name on purpose (the first --write on this repo renamed them)."""
    if key == "docs/README.md" and "## Root files" in s:
        head, tail = s.split("## Root files", 1)
        return fn(head) + "## Root files" + tail
    return fn(s)


def _rewrite_text(key: str, s: str, old: str, new: str) -> str:
    return _protected(key, s, lambda t: t.replace(old, new))


def dir_moves(moves: list[dict]) -> dict[str, str]:
    """`docs/audits/` -> `docs/evidence/audits/` when every moved file under a top-level docs directory lands
    under one new parent -- so directory MENTIONS follow the files."""
    by_dir: dict[str, set[str]] = {}
    for m in moves:
        old_parts, new_parts = m["path"].split("/"), m["dest"].split("/")
        if len(old_parts) > 2:                                       # docs/<dir>/...
            old_dir = "/".join(old_parts[:2]) + "/"
            new_dir = "/".join(new_parts[:len(new_parts) - (len(old_parts) - 2)]) + "/"
            by_dir.setdefault(old_dir, set()).add(new_dir)
    return {o: next(iter(n)) for o, n in by_dir.items() if len(n) == 1}


def plan(root: Path, rows: list[dict]) -> dict:
    moves = [r for r in rows if r["dest"] and r["kind"] != "code"]
    files = text_files(root)
    rewrites: dict[str, str] = {}           # file -> new text
    refused, applied = [], []
    for m in moves:
        hits, binaries = references(root, m["path"], files)
        if binaries:
            refused.append((m, [b.relative_to(root).as_posix() for b in binaries]))
            continue
        applied.append(m)
        for f in hits:
            key = f.relative_to(root).as_posix()
            s = rewrites.get(key) or f.read_text(encoding="utf-8")
            s = _rewrite_text(key, s, m["path"], m["dest"])
            # a docs-relative link from inside docs/ (e.g. `](ROUTES.md)` or `](brain/x.md)`)
            if f.is_relative_to(root / DOCS) or key.startswith("docs/"):
                pat = re.compile(r"(\]\(|`|\s|^)" + re.escape(m["path"][len("docs/"):]) + r"(?=[\s)\]`.,;:]|$)", re.M)
                s = _protected(key, s, lambda t: pat.sub(lambda mm: mm.group(1) + m["dest"][len("docs/"):], t))
            if s != (rewrites.get(key) or f.read_text(encoding="utf-8")):
                rewrites[key] = s
    for old_dir, new_dir in dir_moves(applied).items():             # directory mentions follow the files
        for f in files:
            key = f.relative_to(root).as_posix()
            try:
                s = rewrites.get(key) or f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if old_dir in s:
                s2 = _rewrite_text(key, s, old_dir, new_dir)
                if s2 != s:
                    rewrites[key] = s2
    return {"moves": applied, "refused": refused, "rewrites": rewrites}


AREAS = (("doctrine", re.compile(r"^(CLAUDE|AGENTS|GUARDRAILS|README|loop)\.md$|^\.claude/")),
         ("docs", re.compile(r"^docs/")),
         ("ci", re.compile(r"^\.github/")),
         ("code", re.compile(r"^(app|lib|config|db|bin|test|spec|scripts?)/|\.(rb|py|js|ts|erb|yml|yaml|json)$")))


def rewrite_summary(rewrites: dict[str, str]) -> str:
    """One line per area naming the files whose path strings change. Code and CI are listed in full:
    a path inside `config/routes.rb` is still a path, and the human confirms it before --write."""
    groups: dict[str, list[str]] = {}
    for key in sorted(rewrites):
        area = next((a for a, pat in AREAS if pat.search(key)), "other")
        groups.setdefault(area, []).append(key)
    lines = []
    for area in ("doctrine", "docs", "ci", "code", "other"):
        if area in groups:
            names = groups[area]
            shown = ", ".join(names) if area in ("code", "ci", "other") or len(names) <= 6 else ", ".join(names[:6]) + f", … {len(names) - 6} more"
            lines.append(f"# rewrites in {area} ({len(names)}): {shown}")
    return "\n".join(lines)


def render_plan(root: Path, p: dict) -> str:
    out = []
    if p["rewrites"]:
        out.append(rewrite_summary(p["rewrites"]))
    for m in p["moves"]:
        out.append(f"git mv {m['path']} {m['dest']}" + ("" if m["sure"] else "    # unsure -- confirm"))
    for m, bins in p["refused"]:
        out.append(f"# REFUSED {m['path']} -> {m['dest']}: referenced from a binary this tool cannot rewrite: {', '.join(bins)}")
    for key, new in sorted(p["rewrites"].items()):
        old = (root / key).read_text(encoding="utf-8")
        out.append("".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{key}", f"b/{key}")))
    return "\n".join(out)


def apply_plan(root: Path, p: dict) -> list[str]:
    """Move byte-for-byte, rewrite path strings, then assert every moved destination exists and every
    rewritten file names no path that is now missing. Returns the problems (empty = clean)."""
    problems = []
    for m in p["moves"]:
        src, dst = root / m["path"], root / m["dest"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["git", "mv", "-k", m["path"], m["dest"]], cwd=root, capture_output=True, text=True)
        if r.returncode != 0 or not dst.exists():
            src.rename(dst)
    dest_of = {m["path"]: m["dest"] for m in p["moves"]}
    for key, new in p["rewrites"].items():
        target = root / dest_of.get(key, key)
        if not target.exists():
            problems.append(f"rewrite target {target.relative_to(root).as_posix()} does not exist (key {key}) -- not written")
            continue
        target.write_text(new, encoding="utf-8")   # a moved file is rewritten AT ITS NEW PATH
    for m in p["moves"]:
        if not (root / m["dest"]).is_file():
            problems.append(f"{m['dest']} does not exist after the move")
        if (root / m["path"]).exists():
            problems.append(f"{m['path']} still exists after the move")
    for key in p["rewrites"]:
        for ref in re.findall(r"docs/[A-Za-z0-9_./-]+\.[a-z0-9]+", (root / dest_of.get(key, key)).read_text(encoding="utf-8")):
            if not (root / ref).exists() and any(ref == m["dest"] for m in p["moves"]):
                problems.append(f"{key} names {ref}, which does not exist")
    return problems


# ----------------------------------------------------------------------------- scaffold

def scaffold_files(root: Path) -> dict[str, str]:
    """docs/README.md (the map), a README per layout directory that exists or is being created, and the
    generated markers -- only those that are MISSING. Never touches a populated file."""
    docs = root / DOCS
    out: dict[str, str] = {}
    if not (docs / "README.md").is_file():
        lines = ["# docs/ — the map", "",
                 "A file's directory answers the question a reader would ask to find it. Code goes in `scripts/`, never here.",
                 "A script's output goes under a directory marked `.generated`. Binaries go under `design/assets/` or `evidence/`, never at a root.",
                 "Memos go under `brain/memos/<type>/`. Before creating a file, find its question below; if none fits, ask — do not invent a directory.", "",
                 "| directory | question | what belongs |", "|---|---|---|"]
        for d, (q, what) in LAYOUT.items():
            lines.append(f"| `{d}/` | {q} | {what} |")
        lines += ["", "Check: `python3 <rails-flow>/scripts/docs_layout.py --report` · rework an existing tree: `--propose`, then `--write`.", ""]
        out["docs/README.md"] = "\n".join(lines)
    for d, (q, what) in LAYOUT.items():
        if (docs / d).is_dir() and not (docs / d / "README.md").is_file() and d != "brain":
            out[f"docs/{d}/README.md"] = f"# {d}/ — {q}\n\n{what}\n" + ("\nGenerated: do not hand-edit; the command named above rebuilds it.\n" if d in GENERATED_DIRS else "")
        if d in GENERATED_DIRS and (docs / d).is_dir() and not (docs / d / ".generated").exists():
            out[f"docs/{d}/.generated"] = "files here are generated; see README.md for the command that rebuilds them\n"
    return out


# ----------------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--report", action="store_true")
    g.add_argument("--propose", action="store_true")
    g.add_argument("--scaffold", action="store_true")
    g.add_argument("--selftest", action="store_true")
    ap.add_argument("--write", action="store_true", help="with --propose: apply the plan; with --scaffold: create the files")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root)
    if not (root / DOCS).is_dir():
        print(f"n/a: no docs/ under {root.resolve()}")
        return 3
    rows = classify(root)
    if a.scaffold:
        files = scaffold_files(root)
        for rel, text in files.items():
            if a.write:
                (root / rel).parent.mkdir(parents=True, exist_ok=True); (root / rel).write_text(text, encoding="utf-8")
            print(("wrote " if a.write else "would write ") + rel)
        if not files:
            print("nothing to scaffold: the map, the directory READMEs and the generated markers are all present")
        return 0
    if a.propose:
        p = plan(root, rows)
        print(render_plan(root, p) or "nothing to move")
        if a.write:
            problems = apply_plan(root, p)
            for pr in problems:
                print(f"PROBLEM {pr}")
            left = findings(root, classify(root))
            print(f"\napplied {len(p['moves'])} move(s), rewrote {len(p['rewrites'])} file(s); {len(problems)} problem(s); {len(left)} finding(s) remain")
            return 1 if problems else 0
        print(f"\n{len(p['moves'])} move(s), {len(p['rewrites'])} file(s) to rewrite, {len(p['refused'])} refused -- re-run with --write to apply")
        return 0
    f = findings(root, rows)
    if a.json:
        print(json.dumps({"files": rows, "findings": f}, indent=2))
        return 1 if f else 0
    by_kind: dict[str, int] = {}
    for r in rows:
        by_kind[r["kind"]] = by_kind.get(r["kind"], 0) + 1
    for line in f:
        print(f"- {line}")
    tally = f"docs/: {len(rows)} file(s) -- " + ", ".join(f"{k} {v}" for k, v in sorted(by_kind.items()))
    print(("no findings: every file is where its question says. " if not f else f"\n{len(f)} finding(s). `--propose` prints the moves and the link rewrites; `--write` applies them. ") + tally)
    return 1 if f else 0


# ----------------------------------------------------------------------------- selftest

def selftest() -> int:
    n, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    def make_retask_like(root: Path) -> None:
        """A tree shaped like the case study (#886): five kinds of thing at the root, product specs in the
        brain, brand binaries, a numbered features/ that is already right, and doctrine that names paths."""
        d = root / "docs"
        for rel, text in {
            "docs/Retask-Build-Spec.md": "# Spec\n\nSee [routes](ROUTES.md) and features/F-01-x.md.\n",
            "docs/ROADMAP.md": "# Roadmap\n", "docs/ROUTES.md": "# Routes\n",
            "docs/zoho-sso-setup.md": "# Zoho SSO\n", "docs/validation-Spike.md": "# Spike\n",
            "docs/SITEMAP-COVERAGE.md": "<!-- generated by docs/sitemap_from_spec.py -->\n# Coverage\n",
            "docs/sitemap_from_spec.py": "print('x')\n",
            "docs/features/F-01-x.md": "# F-01\n", "docs/features/F-02-y.md": "# F-02\n",
            "docs/brain/STATUS.md": "# Status\n", "docs/brain/MEMORY.md": "- [x](memos/feedback/x.md) — y\n",
            "docs/brain/memos/feedback/x.md": "---\nname: feedback-x\ndescription: d\ntype: feedback\n---\n\nbody\n",
            "docs/brain/feedback_old.md": "---\nname: feedback-old\ndescription: d\ntype: feedback\n---\n\nold\n",
            "docs/brain/role-specs/admin.md": "# Admin — target state\n",
            "docs/brain/role-specs/OPEN-QUESTIONS.md": "# Open\n",
            "docs/architecture/graph.md": "<!-- generated by /rails-flow:graph -->\n# Graph\n",
            "docs/design/home-page-prompt.md": "# Prompt\n",
            "CLAUDE.md": "Spec: `docs/Retask-Build-Spec.md`. Routes: `docs/ROUTES.md`. Roles: docs/brain/role-specs/admin.md. Specs live in `docs/features/`.\n",
            "loop.md": "run `python3 docs/sitemap_from_spec.py`\n",
        }.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True); (root / rel).write_text(text, encoding="utf-8")
        (d / "brand-assets" / "RH Global Logo").mkdir(parents=True)
        (d / "brand-assets" / "RH Global Logo" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0fake")
        (d / "Retask-Sitemap.png").write_bytes(b"\x89PNG\r\n\x1a\n\0\0fake")
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)   # a fixture repo, not this one

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "proj"; root.mkdir()
        check("no docs/ is n/a (exit 3)", main(["--report", "--root", str(root)]) == 3)
        make_retask_like(root)
        rows = {r["path"]: r for r in classify(root)}
        check("a .py in docs is code", rows["docs/sitemap_from_spec.py"]["kind"] == "code")
        check("a PNG is binary, at the root it is a finding homed under design/assets/",
              rows["docs/Retask-Sitemap.png"]["kind"] == "binary" and rows["docs/Retask-Sitemap.png"]["dest"] == "docs/design/assets/Retask-Sitemap.png")
        check("under architecture/ a file is generated by location and fine where it is",
              rows["docs/architecture/graph.md"]["kind"] == "generated" and rows["docs/architecture/graph.md"]["dest"] is None)
        check("a `generated by` header at the root makes a file generated, homed under architecture/ unsure",
              rows["docs/SITEMAP-COVERAGE.md"]["kind"] == "generated" and rows["docs/SITEMAP-COVERAGE.md"]["dest"] == "docs/architecture/SITEMAP-COVERAGE.md"
              and not rows["docs/SITEMAP-COVERAGE.md"]["sure"], f"{rows['docs/SITEMAP-COVERAGE.md']}")
        check("the spec at the root is homed under product/ by its name, sure",
              rows["docs/Retask-Build-Spec.md"]["dest"] == "docs/product/Retask-Build-Spec.md" and rows["docs/Retask-Build-Spec.md"]["sure"])
        check("an SSO setup guide is homed under runbooks/", rows["docs/zoho-sso-setup.md"]["dest"] == "docs/runbooks/zoho-sso-setup.md")
        check("a spike write-up is homed under evidence/", rows["docs/validation-Spike.md"]["dest"] == "docs/evidence/validation-Spike.md")
        check("features/ (not a layout dir, name says product) moves under product/features/ keeping its files",
              rows["docs/features/F-01-x.md"]["dest"] == "docs/product/features/F-01-x.md")
        check("role specs inside the brain are product content -> product/roles/ (maintainer's name)",
              rows["docs/brain/role-specs/admin.md"]["dest"] == "docs/product/roles/admin.md" and rows["docs/brain/role-specs/admin.md"]["sure"])
        check("a memo at the brain root belongs under memos/<type>/",
              rows["docs/brain/feedback_old.md"]["dest"] == "docs/brain/memos/feedback/old.md")
        check("a memo already under memos/<type>/ and STATUS.md are fine",
              rows["docs/brain/memos/feedback/x.md"]["dest"] is None and rows["docs/brain/STATUS.md"]["dest"] is None)
        check("brand-assets/ with a space in a subfolder name moves under design/assets/",
              rows["docs/brand-assets/RH Global Logo/logo.png"]["dest"] == "docs/design/assets/brand/RH Global Logo/logo.png")
        check("design/ content stays", rows["docs/design/home-page-prompt.md"]["dest"] is None)
        f = findings(root, classify(root))
        check("the report names the missing map and the code in docs",
              any("docs/README.md is missing" in x for x in f) and any("code in docs/" in x for x in f))

        snap = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file() and ".git" not in p.parts}
        p = plan(root, rows_list := classify(root))
        rendered = render_plan(root, p)
        check("propose writes nothing", snap == {q.relative_to(root).as_posix(): q.read_bytes() for q in root.rglob("*") if q.is_file() and ".git" not in q.parts})
        check("the plan moves the spec and rewrites CLAUDE.md's path to it",
              "git mv docs/Retask-Build-Spec.md docs/product/Retask-Build-Spec.md" in rendered
              and "CLAUDE.md" in p["rewrites"] and "docs/product/Retask-Build-Spec.md" in p["rewrites"]["CLAUDE.md"], rendered[:300])
        check("a directory that moves whole has its MENTIONS rewritten (docs/features/ -> docs/product/features/)",
              "`docs/product/features/`" in p["rewrites"]["CLAUDE.md"], p["rewrites"].get("CLAUDE.md", ""))
        check("a docs-relative link inside docs is rewritten too (ROUTES.md -> product/ROUTES.md)",
              "docs/Retask-Build-Spec.md" in p["rewrites"] and "](product/ROUTES.md)" in p["rewrites"]["docs/Retask-Build-Spec.md"], p["rewrites"].get("docs/Retask-Build-Spec.md", "")[:200])
        check("code is never moved by the plan (it leaves docs/, which is the human's move)", not any(m["kind"] == "code" for m in p["moves"]))
        check("the plan names, by area, every file whose path strings change -- doctrine and code in full",
              "# rewrites in doctrine" in rendered and "CLAUDE.md" in rewrite_summary(p["rewrites"])
              and rewrite_summary({"config/routes.rb": "", "CLAUDE.md": ""}).count("\n") == 1
              and "rewrites in code (1): config/routes.rb" in rewrite_summary({"config/routes.rb": ""}), rendered[:200])
        check("nothing refused in a text-only repo", p["refused"] == [])
        problems = apply_plan(root, p)
        check("write applies every move and every rewritten link resolves", problems == [] and (root / "docs/product/Retask-Build-Spec.md").is_file() and not (root / "docs/ROUTES.md").exists() and (root / "docs/product/roles/admin.md").is_file(), "; ".join(problems))
        check("the moved spec is byte-identical apart from its own rewritten links",
              (root / "docs/product/Retask-Build-Spec.md").read_text(encoding="utf-8") == "# Spec\n\nSee [routes](ROUTES.md) and features/F-01-x.md.\n".replace("](ROUTES.md)", "](product/ROUTES.md)").replace("features/F-01-x.md", "product/features/F-01-x.md"))
        left = findings(root, classify(root))
        check("after the write only the map, the markers and the code-in-docs remain as findings",
              all(("README.md is missing" in x) or (".generated" in x) or ("code in docs/" in x) for x in left), "; ".join(left))
        sc = scaffold_files(root)
        check("scaffold offers the map, a README per present directory, and the architecture marker",
              "docs/README.md" in sc and "docs/product/README.md" in sc and "docs/architecture/.generated" in sc and "docs/brain/README.md" not in sc, ", ".join(sc))
        for rel, text in sc.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True); (root / rel).write_text(text, encoding="utf-8")
        check("scaffold is idempotent and never rewrites a populated file", scaffold_files(root) == {})
        (root / "docs/sitemap_from_spec.py").unlink(missing_ok=True)
        check("a conforming tree has no findings and exits 0", findings(root, classify(root)) == [] and main(["--report", "--root", str(root)]) == 0)
        check("the second propose has nothing to move", plan(root, classify(root))["moves"] == [])
        # a directory the project's map declares is honoured; an undeclared one is not
        (root / "docs/doctrine").mkdir(); (root / "docs/doctrine/harness.md").write_text("# h\n", encoding="utf-8")
        undeclared = {r["path"]: r for r in classify(root)}["docs/doctrine/harness.md"]["dest"]
        with (root / "docs/README.md").open("a", encoding="utf-8") as fh:
            fh.write("| `doctrine/` | WHAT do our agents follow? | the rules the plugins ship |\n")
        declared = {r["path"]: r for r in classify(root)}["docs/doctrine/harness.md"]["dest"]
        check("a directory declared in the map is honoured; the same directory undeclared is homed elsewhere",
              undeclared == "docs/product/doctrine/harness.md" and declared is None, f"{undeclared} / {declared}")
        # the map's `## Root files` table homes a root file the layout cannot name -- into a declared dir or a layout subdir
        (root / "docs/harness-doctrine.md").write_text("# hd\n", encoding="utf-8"); (root / "docs/maintainer-history.md").write_text("# mh\n", encoding="utf-8")
        unruled = {r["path"]: r for r in classify(root)}
        with (root / "docs/README.md").open("a", encoding="utf-8") as fh:
            fh.write("\n## Root files\n\n| file | home |\n|---|---|\n| `*-doctrine.md` | `doctrine/` |\n| `maintainer-history.md` | `brain/history/` |\n")
        ruled = {r["path"]: r for r in classify(root)}
        # a code file that mentions only the docs-relative tail is NOT a rewrite; one that names the full path is
        (root / "scripts").mkdir(exist_ok=True); (root / "scripts/a.py").write_text("x = 'harness-doctrine.md'\n", encoding="utf-8")
        (root / "scripts/b.py").write_text("x = 'docs/harness-doctrine.md'\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        p_r = plan(root, classify(root))
        check("outside docs/, only the full repo path is a reference: the tail alone is not rewritten",
              "scripts/b.py" in p_r["rewrites"] and "scripts/a.py" not in p_r["rewrites"], str(sorted(p_r["rewrites"])))
        check("a listed rewrite always changes text", all((root / k).read_text(encoding="utf-8") != v for k, v in p_r["rewrites"].items()))
        rules_before = root_file_rules(root)
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        apply_plan(root, plan(root, classify(root)))
        check("the map's `## Root files` globs survive a --write (a rewrite must not rename them)", root_file_rules(root) == rules_before, str(root_file_rules(root)))
        check("a `## Root files` rule in the map homes a root file where the map says, sure; without the rule it is unsure product/",
              unruled["docs/harness-doctrine.md"]["dest"] == "docs/product/harness-doctrine.md" and not unruled["docs/harness-doctrine.md"]["sure"]
              and ruled["docs/harness-doctrine.md"]["dest"] == "docs/doctrine/harness-doctrine.md" and ruled["docs/harness-doctrine.md"]["sure"]
              and ruled["docs/maintainer-history.md"]["dest"] == "docs/brain/history/maintainer-history.md", f"{ruled['docs/harness-doctrine.md']} {ruled['docs/maintainer-history.md']}")

        # a binary that names the old path: the move is REFUSED, not guessed
        (root / "docs/ROADMAP2.md").write_text("# r2\n", encoding="utf-8")
        (root / "docs/design/assets/blob.bin").write_bytes(b"\0\0docs/ROADMAP2.md\0")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True)
        p2 = plan(root, classify(root))
        check("a move referenced from a binary is refused and named",
              any(m["path"] == "docs/ROADMAP2.md" for m, _ in p2["refused"]) and not any(m["path"] == "docs/ROADMAP2.md" for m in p2["moves"]), str(p2["refused"]))

    for f in failures:
        print(f"FAIL {f}")
    print(f"docs_layout selftest: {n} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
