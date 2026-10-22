#!/usr/bin/env python3
"""Which stacks a project is built on, from markers each stack plugin declares. #2163 (slice 1 of #2162)

WHAT THIS IS. One detector in the stack-neutral core. It reads a project and reports every stack it
matches -- a project can be several at once (Next.js + Supabase + Vercel). It knows no stack itself:
each stack plugin ships a `stacks.json` declaring its own markers, and this script discovers those
manifests the way `project_gates.py` discovers `checks.json`. ADDING A STACK IS A NEW MANIFEST, NEVER
AN EDIT HERE (`.claude/skills/plugin-boundaries` rule 1); the selftest proves that with fixture
manifests for stacks no plugin ships yet.

THE MANIFEST, `stacks.json` at a plugin's root:

    {"plugin": "rails-stack",
     "stacks": [{"id": "rails", "name": "Rails",
                 "all": [{"file": "Gemfile"}, {"file": "config/application.rb"}]}]}

A stack matches when every marker in `all` holds and, if it lists `any`, at least one of those does.
Marker kinds: `{"file": path}`, `{"dir": path}` (a path inside the project: never absolute, never `..`),
`{"package_dependency": name}` (in `package.json`'s dependencies or devDependencies).

"CANNOT JUDGE" IS NEVER "NO STACK" (#2188 review). Every way a stack could be misread is a PROBLEM,
exit 2, never the "none detected" code: an unreadable or nameless manifest, a manifest or stack of the
wrong shape, an unknown marker kind, a marker value that is not a contained path or a name, a stack
with no markers (it would match every project), two manifests for one plugin at the same version, and a
`package.json` that exists but does not parse when a stack needs its dependencies. A missing
`package.json` is simply no dependency.

WHERE MANIFESTS ARE FOUND. Only at PLUGIN ROOTS -- a directory carrying `.claude-plugin/plugin.json`,
or `.claude-plugin/marketplace.json` for a marketplace whose plugin is its own root -- so a stray
`stacks.json` in any other directory is never read. The two shapes `project_gates.plugin_roots` handles:
sibling `plugins/*` in a checkout, `<plugin>/<version>/` in the installed cache. The repo root is not
searched: since #2182 rails-stack is `plugins/rails-stack/` and ships its `stacks.json` there. Several versions of one plugin collapse to the highest, by the
manifest's own `plugin` and `version`, not by directory names.

THE DESCRIPTOR (#2181, plan step 2 of #2162). Each stack may carry a `descriptor`: how that stack tests,
lints, boots, deploys and draws its UI, and which agent plays each role. `--descriptor` prints the merged
descriptor of the stacks the project matches, so a flow asks the stack instead of naming Rails. Stacks
from ONE plugin merge (Next.js + Supabase + Vercel is three stacks in one plugin); a key declared by TWO
plugins, or one leaf given two values, is a conflict reported with both sources, never a silent pick. Every
key is from `DESCRIPTOR_SCHEMA`, with its declared shape: an unknown key or a wrong type is a problem
(`descriptor-key-undeclared`), so a flow can never read a key nobody declared.

Exit 0 one or more stacks detected · 1 none detected · 2 a manifest or the project could not be judged.

Run:  python3 detect_stack.py [project-dir] [--json]
      python3 detect_stack.py [project-dir] --descriptor
      python3 detect_stack.py --check          (every discovered manifest is valid, whatever the project)
      python3 detect_stack.py --available [--json]   (every stack the installed plugins declare: a new project's choices)
      python3 detect_stack.py [project-dir] --stack ID [--stack ID] --descriptor   (take the chosen stacks, detect nothing)

SETUP SECTIONS (#2180). A stack's `setup_section` names a file inside its own plugin that `/rails-flow:setup-flow` runs
after its neutral scaffold. It is per stack, never merged: every matched stack's section is listed (`setup_sections`), and
one that leaves its plugin or names no file is a problem.
      python3 detect_stack.py --selftest

Stdlib only, no network.
"""
from __future__ import annotations

import argparse
import contextlib
import fnmatch
import io
import json
import re
import sys
import tempfile
from pathlib import Path, PurePosixPath

MANIFEST = "stacks.json"
KINDS = ("file", "dir", "package_dependency")
PLUGIN_MARKERS = (".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
CORRUPT = object()   # package.json exists and does not parse


def version_tuple(raw: object) -> tuple[int, ...]:
    parts = []
    for chunk in str(raw or "0").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def is_plugin_root(directory: Path) -> bool:
    return any((directory / marker).is_file() for marker in PLUGIN_MARKERS)


def manifest_dirs(start: Path) -> list[Path]:
    """Every plugin root that ships a `stacks.json`, in either layout. Duplicates are collapsed later."""
    own = start.resolve().parents[1]          # <plugin>/scripts/x.py -> <plugin>, or <plugin>/<ver>
    found: set[Path] = set()

    def take(directory: Path) -> None:
        if (directory / MANIFEST).is_file() and is_plugin_root(directory):
            found.add(directory)

    def scan(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir():
                take(child)

    take(own)
    # ONLY IN A RECOGNISED LAYOUT (#2117, the #1475 lesson): anywhere else -- a copy staged under the system temp directory -- the
    # parent is the temp root, and scanning it walked every other process's tempdir (measured: one selftest over ten minutes).
    in_checkout = own.parent.name == "plugins"                    # <repo>/plugins/<plugin>
    in_cache = own.parent.parent.parent.name == "cache"           # <plugins>/cache/<marketplace>/<plugin>/<version>
    if not (in_checkout or in_cache):
        return sorted(found)
    scan(own.parent)                          # sibling plugins (checkout) or sibling versions (cache)
    if in_cache:
        grandparent = own.parent.parent       # the marketplace directory; a checkout's repo root is NOT taken (#2182)
        try:
            peers = sorted(grandparent.iterdir())
        except OSError:
            peers = []
        for peer in peers:
            if peer.is_dir() and peer != own.parent:
                scan(peer)                    # every plugin's every version in the cache
    return sorted(found)


def load_manifests(dirs: list[Path]) -> tuple[list[dict], list[str]]:
    """The newest manifest per plugin, and every problem met on the way."""
    best: dict[str, tuple[tuple[int, ...], dict]] = {}
    problems: list[str] = []
    for directory in dirs:
        path = directory / MANIFEST
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path}: unreadable manifest ({exc})")
            continue
        plugin = data.get("plugin") if isinstance(data, dict) else None
        if not isinstance(plugin, str) or not plugin:
            problems.append(f"{path}: names no `plugin`")
            continue
        if not isinstance(data.get("stacks"), list):
            problems.append(f"{path}: `stacks` must be a list of stacks")
            continue
        data["_path"] = str(path)
        version = version_tuple(data.get("version"))
        if plugin in best and best[plugin][0] == version:
            problems.append(f"{path}: a second manifest for {plugin} at the same version as {best[plugin][1]['_path']}; "
                            "give each a `version` so the newer can win")
            continue
        if plugin not in best or best[plugin][0] < version:
            best[plugin] = (version, data)
    return [data for _, data in sorted(best.values(), key=lambda v: v[1]["plugin"])], problems


def package_dependencies(project: Path) -> set[str] | object | None:
    """The names in package.json's dependencies and devDependencies; None when there is no package.json,
    CORRUPT when there is one that does not parse."""
    path = project / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return CORRUPT
    if not isinstance(data, dict):
        return CORRUPT                     # valid JSON that is not an object is no package.json a dependency can be read from
    names: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        section = data.get(key)
        if section is None:
            continue
        if not isinstance(section, dict):
            return CORRUPT                 # a `dependencies` list is no map of names, so "none" would be a guess (#2188 review)
        names.update(section)
    return names


def escapes(value: str) -> bool:
    """Whether a relative path leaves the directory it is read from: absolute, `..`, or a Windows drive or UNC root."""
    parts = PurePosixPath(value)
    return parts.is_absolute() or ".." in parts.parts or value.startswith("\\") or bool(parts.parts and ":" in parts.parts[0])


def holds(marker: object, project: Path, deps: set[str] | object | None) -> bool:
    """Whether one marker holds. Raises ValueError for a marker this script cannot judge."""
    if not isinstance(marker, dict) or len(marker) != 1 or next(iter(marker)) not in KINDS:
        raise ValueError(f"unknown marker {marker!r} (kinds: {', '.join(KINDS)})")
    kind, value = next(iter(marker.items()))
    if not isinstance(value, str) or not value:
        raise ValueError(f"marker {marker!r}: the value must be a non-empty string")
    if kind == "package_dependency":
        if deps is CORRUPT:
            raise ValueError("package.json exists but does not parse, so its dependencies cannot be read")
        return deps is not None and value in deps
    if value.strip().rstrip("/") in ("", "."):
        # THE PROJECT ROOT IS NOT A MARKER (#2188 review): every project has one, so a stack keyed on it would match them all.
        raise ValueError(f"marker {marker!r}: names the project root, which every project has")
    if escapes(value):
        raise ValueError(f"marker {marker!r}: a path must stay inside the project (no absolute path, no `..`)")
    return (project / value).is_file() if kind == "file" else (project / value).is_dir()


def detect(project: Path, manifests: list[dict]) -> tuple[list[dict], list[str]]:
    """The stacks the project matches, and the problems that stopped a stack being judged."""
    deps = package_dependencies(project)
    matched: list[dict] = []
    problems: list[str] = []
    for manifest in manifests:
        for index, stack in enumerate(manifest["stacks"]):
            if not isinstance(stack, dict):
                problems.append(f"{manifest['_path']}: stacks[{index}] must be a stack object, got {stack!r}")
                continue
            label = f"{manifest['_path']}: stack {stack.get('id')!r}"
            if not isinstance(stack.get("id"), str) or not stack.get("id"):
                problems.append(f"{label}: needs an `id`, a non-empty string, to be reported by")
                continue
            all_of, any_of = stack.get("all", []), stack.get("any", [])
            if not isinstance(all_of, list) or not isinstance(any_of, list):
                problems.append(f"{label}: `all` and `any` must be lists of markers")
                continue
            if not all_of and not any_of:
                problems.append(f"{label} declares no markers, so it would match every project")
                continue
            try:
                every = [holds(m, project, deps) for m in all_of]       # judged in full, so a bad marker anywhere is reported
                some = [holds(m, project, deps) for m in any_of]
            except ValueError as exc:
                problems.append(f"{label}: {exc}")
                continue
            except Exception as exc:   # noqa: BLE001 -- a shape no check above foresaw: still "cannot judge", never a crash with the "none" code
                problems.append(f"{label}: cannot judge this stack ({type(exc).__name__}: {exc})")
                continue
            if all(every) and (not any_of or any(some)):
                matched.append({"id": stack.get("id"), "name": stack.get("name", stack.get("id")), "plugin": manifest["plugin"]})
    return matched, problems


STR, INT, STRS, BOOL = "str", "int", "list[str]", "bool"
# EVERY KEY A FLOW MAY READ, and its shape (#2181). A dict is a block whose keys are the only ones allowed; `{"*": STR}` is a
# block of free names (scripts) each holding a string. Adding a key a flow needs is an edit HERE, reviewed once, never a key a
# manifest invents.
DESCRIPTOR_SCHEMA: dict = {
    "runner_prefix": STRS,
    "tests": {"command": STRS, "glob": STR, "preflight": STRS},
    "lint": {"command": STRS, "extensions": STRS},
    "layout": {"source": STRS, "migrations": STR, "schema": STR, "views": STR, "components": STR},
    "boot": {"command": STR, "port": INT, "health": STR, "routes": STRS},
    "agents": {"developer": STR, "migrations": STR, "test_runner": STR, "security": STR, "reviewer": STR, "design_auditor": STR},
    "deploy": {"target": STR, "artifact": STR, "agent": STR},
    "ui": {"implementation": STR, "tokens_file": STR, "porter": STR, "composer": STR},
    "dangerous_commands": [{"pattern": STR, "allowed": STR}],
    "setup_section": STR,
    # THE STACK'S SECURITY SURFACE (#2117). The secure-design PROCESS is neutral (when to threat-model, the template, TM-n
    # ids, the audit before ready); what to look for is per stack: its checklist, its scanners, and the spellings in a plan
    # or a planned path that mean a boundary in that stack (security_scope.py reads both).
    # code_syntax (#2119): what in this stack's files is not code (a block comment, a heredoc), so a security-review citation
    # `file:line` can be refused when it points inside one; scoped by extension. syntax_cases proves it.
    "security": {"checklist": STR, "scanners": STRS, "cases": STR, "syntax_cases": STR,
                 # A key ending in `?` is optional in its record (#2260): a language with no heredoc declares none. `line_comments` are markers that
                 # make a line that STARTS with them a comment; `refuse_when` names a pattern which, on any line of the file, means a reader that
                 # goes line by line cannot be sure what is code (a template literal spanning lines), so the whole file is refused, with `why`.
                 "code_syntax": [{"extensions": STRS, "block_comments": [{"open": STR, "close": STR, "column0": BOOL}], "heredoc?": STR,
                                  "line_comments?": STRS, "refuse_when?": [{"pattern": STR, "why": STR}]}],
                 "boundary_text": [{"boundary": STR, "pattern": STR}],
                 "boundary_paths": [{"boundary": STR, "pattern": STR}],
                 # data_markers (#2214): a line that is exactly the marker (an end-of-code line such as `__END__`) ends code for the rest of the file.
                 "data_markers": [{"extensions": STRS, "marker": STR}]},
    # WHICH PATHS A USER SEES (#2219). The mock-up gate holds a user-visible change until a mock-up is approved, and which files are
    # user-visible is per stack: Rails views, Next.js pages. Each stack declares its own (never merged: a Rails app with a Next.js front
    # end has both); regexes matched with `re.search`. `not_paths` are files under them a person does not see (a JSON template, an API
    # route handler); `seen_anyway` wins over `not_paths` (the PWA manifest is JSON a person installs). `cases` is a JSON list of
    # `{"path", "ui"}` rows that proves the patterns, run by check_mockup_gate's selftest.
    "ui_scope": {"paths": STRS, "not_paths?": STRS, "seen_anyway?": STRS, "cases": STR},
    # THE STACK'S TOOLCHAIN (#2168): what a project of this stack needs installed for the flows to work, so the toolchain audit
    # names each missing piece with the steps to fix it (advisory). `plugins`: a Claude Code plugin id (`name@marketplace`) and
    # the line that installs it. `clis`: a binary on PATH, the line that installs it, and optionally `ready`, a command that exits
    # 0 only when the tool is usable (logged in, its daemon running), with `ready_hint` saying how to get there.
    "toolchain": {"plugins": [{"id": STR, "install": STR}],
                  # `project_paths`: where inside the project the binary may live instead of PATH (a dev-dependency CLI in
                  # `node_modules/.bin/`); `version`: the arguments that print its version, reported beside it.
                  # `auto_install` (#2288): how `stack_toolchain.py --install` installs it unattended, methods in order of preference, each
                  # naming the vendor repository the package must come from; `token`: the briefing-file variable its commands need.
                  "clis": [{"bin": STR, "install": STR, "ready?": STRS, "ready_hint?": STR, "project_paths?": STRS, "version?": STRS,
                            "auto_install?": [{"method": STR, "package": STR, "repo": STR, "os?": STR}], "token?": STR}]},
    "scripts": {"*": STR},
    "review_checklist": STRS,
}
# WHAT A FLOW CANNOT DO WITHOUT (#2189 review). A plugin whose stacks declare any descriptor must, across them, carry these:
# a flow told "run the tests" or "hand it to the developer" has no fallback, so an absent key is a problem, never a default.
# Per plugin, not per stack, because an add-on stack (Supabase beside Next.js) adds a key or two and owns no test runner.
REQUIRED = ("tests.command", "tests.glob", "agents.developer", "agents.test_runner", "agents.reviewer")
# The values that name an agent, `<plugin>:<agent>`, resolved to `<plugin>/agents/<agent>.md` in the discovered tree.
AGENT_VALUES = ("agents.*", "deploy.agent", "ui.porter", "ui.composer")
PORTS = range(1, 65536)


def shape_problems(value: object, shape: object, where: str) -> list[str]:
    """Why `value` does not have `shape`; empty when it does."""
    if shape == STR:
        return [] if isinstance(value, str) and value else [f"{where} must be a non-empty string"]
    if shape == INT:
        if not isinstance(value, int) or isinstance(value, bool):
            return [f"{where} must be a whole number"]
        return [] if not where.endswith(".port") or value in PORTS else [f"{where} must be a port, 1-65535 (got {value})"]
    if shape == BOOL:
        return [] if isinstance(value, bool) else [f"{where} must be true or false"]
    if shape == STRS:
        ok = isinstance(value, list) and value and all(isinstance(v, str) and v for v in value)
        return [] if ok else [f"{where} must be a non-empty list of strings"]
    if isinstance(shape, list):
        if not isinstance(value, list) or not value:
            return [f"{where} must be a non-empty list"]
        found = [p for i, item in enumerate(value) for p in shape_problems(item, shape[0], f"{where}[{i}]")]
        if isinstance(shape[0], dict):
            # A LIST ITEM IS A RECORD (#2189 review): a reader takes every key of it (`.allowed`), so each one is required.
            found += [f"{where}[{i}] needs `{key}`" for i, item in enumerate(value) if isinstance(item, dict)
                      for key in shape[0] if key != "*" and not key.endswith("?") and key not in item]
        return found
    if not isinstance(value, dict) or not value:
        return [f"{where} must be a non-empty block"]
    found = []
    for key, item in value.items():
        sub = shape.get(key, shape.get(key + "?", shape.get("*")))
        if sub is None:
            found.append(f"{where}.{key} is not a declared descriptor key (descriptor-key-undeclared)")
        else:
            found.extend(shape_problems(item, sub, f"{where}.{key}"))
    return found


# KEYS THAT BELONG TO ONE STACK, NOT TO THE PROJECT (#2180). A Rails app with a Next.js front end runs BOTH stacks' setup
# sections, so a setup section is never merged (two plugins declaring it is no conflict); each detected stack's is listed.
PER_STACK_KEYS = ("setup_section", "security", "ui_scope", "toolchain")  # security: #2117, ui_scope: #2219, toolchain: #2168; each stack reports its own


def plugin_root(manifest: dict) -> Path:
    return Path(manifest["_path"]).parent


def setup_section_problems(manifest: dict, stack: dict, where: str) -> list[str]:
    """A `setup_section` is a file inside its own plugin, so setup-flow never reads a path a manifest points elsewhere."""
    value = (stack.get("descriptor") or {}).get("setup_section") if isinstance(stack.get("descriptor"), dict) else None
    if not isinstance(value, str) or not value:
        return []                               # absent, or a shape problem shape_problems already reports
    if escapes(value):
        return [f"{where}.setup_section {value!r} must stay inside its plugin (no absolute path, no `..`)"]
    if not (plugin_root(manifest) / value).is_file():
        return [f"{where}.setup_section {value!r} names no file in {plugin_root(manifest)}"]
    return []


# A CHECKLIST IN ONE STRICT SHAPE (#2210, the coordinator's rule from #2213): it is read as text, never interpreted as Markdown, so
# anything a renderer would hide or reshape is refused rather than read around. A claim id (`C-n`, a row of the stack's audit) is a
# citation only in the slot at the END of its line, and only for a row its audit marks CONFIRMED (#2210 adversary).
# The alphabet is a whitelist (printable ASCII plus the two marks the checklists use), so a look-alike citation (a zero-width
# character, a Cyrillic C, a non-ASCII dash) or a line break only Python sees (U+0085, U+001C) is refused, not normalised.
CHECKLIST_EXTRA_CHARS = "—§"
CITATION_SLOT = re.compile(r"\((C-\d+(?:, C-\d+)*)\)$")
CLAIM_LIKE = re.compile(r"c\s*[-\u2014]\s*\d", re.I)   # the em dash is in the alphabet, so it is a citation dash too
AUDIT_PATH = re.compile(r"`(docs/evidence/audits/[\w.-]+\.md)`")


def checklist_format_problems(text: str) -> list[str]:
    """`<line>: <why>` for each line of a security checklist outside its strict shape; empty when it holds."""
    found = []
    prev_blank = True
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.rstrip(" ")
        odd = sorted({c for c in line if not (" " <= c <= "~" or c in CHECKLIST_EXTRA_CHARS)})
        if odd:
            found.append(f"{n}: characters outside the checklist alphabet {[hex(ord(c)) for c in odd]} (a tab, CR, look-alike or hidden character)")
        if "<!--" in line or "-->" in line:
            found.append(f"{n}: an HTML comment hides text from the reader; delete it, don't hide it")
        elif re.search(r"<[A-Za-z/!?]", line):
            found.append(f"{n}: raw HTML; a renderer can hide or reshape it (`<details>`, `hidden`), so a checklist holds none")
        if re.search(r"&(?:#\d+|#x[0-9a-f]+|[a-z][a-z0-9]*);", line, re.I):
            found.append(f"{n}: an HTML entity; it renders as a character the check never sees (`&#67;` is C)")
        if "![" in line or re.search(r"\]\([^)]*\s[\"'(]", line):
            found.append(f"{n}: an image or a link title; a rendered page hides its text")
        if re.match(r"\s*(?:`{3,}|~{3,})", line):
            found.append(f"{n}: a code fence; a checklist asks questions in prose and holds no fenced block")
        if prev_blank and re.match(r" {4,}\S", line):
            found.append(f"{n}: an indented code block (four spaces after a blank line)")
        if re.match(r" {0,3}\[[^\]]+\]:", line):
            found.append(f"{n}: a link reference definition; a renderer shows none of it")
        if line.lstrip().startswith("|") and not line.startswith("|"):
            found.append(f"{n}: an indented table row; every row starts with `|` in the first column")
        if not line.startswith("|") and "|" in line and re.fullmatch(r"[\s|:-]*-{3,}[\s|:-]*", line):
            found.append(f"{n}: a table delimiter row that does not start with `|`; every row starts with `|`")
        slot = CITATION_SLOT.search(line)
        outside = line[:slot.start()] if slot else line
        if CLAIM_LIKE.search(outside):
            found.append(f"{n}: a claim id outside its end-of-line slot `(C-n)` (or a malformed one)")
        prev_blank = not line.strip()
    return found


def checklist_citations(text: str) -> set[str]:
    """Every `C-n` a checklist cites, read from the end-of-line slots only."""
    out: set[str] = set()
    for line in text.split("\n"):
        slot = CITATION_SLOT.search(line.rstrip(" "))
        if slot:
            out.update(slot.group(1).split(", "))
    return out


def confirmed_claims(audit: str) -> set[str]:
    """The `C-n` rows of an audit whose own section (`## C-n — ...` up to the next heading) has `Verdict: CONFIRMED` as its first verdict line."""
    out: set[str] = set()
    unfenced = re.sub(r"(?ms)^(`{3,}|~{3,}).*?^\1[ \t]*$", "", audit)   # a quotes block holds no verdict
    heads = re.findall(r"(?m)^## (C-\d+) ", unfenced)
    twice = {h for h in heads if heads.count(h) > 1}                # a row given twice has no one verdict: neither counts
    for section in re.split(r"(?m)^(?=#+ )", unfenced):            # any heading ends a section, so a nested one cannot lend its verdict
        head = re.match(r"## (C-\d+) ", section)
        if head and head.group(1) in twice:
            continue
        verdict = re.search(r"(?m)^Verdict:(.*)$", section)       # the section's FIRST verdict line is its verdict
        if head and verdict and re.fullmatch(r" CONFIRMED(?: \[(?:quotes|waived):[^\]]*\])?", verdict.group(1)):
            out.add(head.group(1))
    return out


def citation_problems(text: str, plugin: Path) -> list[str]:
    """A cited `C-n` is a CONFIRMED row of the one audit the checklist names. The audit is maintainer evidence, so it is read only
    in a marketplace checkout (where the gate runs); an installed copy has no audit beside it and was proved before it shipped."""
    cited = checklist_citations(text)
    if not cited:
        return []
    audits = sorted(set(AUDIT_PATH.findall(text)))
    if len(audits) != 1:
        return [f" cites {sorted(cited)} but names {len(audits)} audits; name exactly one `docs/evidence/audits/<file>.md`"]
    repo = plugin.parent.parent
    if not (repo / ".claude-plugin" / "marketplace.json").is_file():
        return []
    try:
        confirmed = confirmed_claims((repo / audits[0]).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as err:
        return [f" names the audit {audits[0]}, which cannot be read: {err}"]
    missing = sorted(cited - confirmed, key=lambda c: int(c[2:]))
    return [f" cites {', '.join(missing)}, not a CONFIRMED row of {audits[0]}"] if missing else []


def security_problems(manifest: dict, stack: dict, where: str) -> list[str]:
    """A security checklist is a file inside its own plugin, and every boundary pattern compiles (#2117)."""
    value = (stack.get("descriptor") or {}).get("security") if isinstance(stack.get("descriptor"), dict) else None
    if not isinstance(value, dict):
        return []                               # absent, or a shape problem shape_problems already reports
    found = []
    for key in ("checklist", "cases", "syntax_cases"):
        named = value.get(key)
        if isinstance(named, str) and named:
            if escapes(named):
                found.append(f"{where}.security.{key} {named!r} must stay inside its plugin (no absolute path, no `..`)")
            elif not (plugin_root(manifest) / named).is_file():
                found.append(f"{where}.security.{key} {named!r} names no file in {plugin_root(manifest)}")
            elif key == "checklist":
                try:
                    text = (plugin_root(manifest) / named).read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError) as err:
                    found.append(f"{where}.security.checklist {named!r} cannot be read: {err}")
                else:
                    found.extend(f"{where}.security.checklist {named}:{p}" for p in checklist_format_problems(text))
                    found.extend(f"{where}.security.checklist {named}{p}" for p in citation_problems(text, plugin_root(manifest)))
    for key in ("boundary_text", "boundary_paths"):
        for i, row in enumerate(value.get(key) or []):
            if isinstance(row, dict) and isinstance(row.get("pattern"), str):
                try:
                    re.compile(row["pattern"])
                except re.error as err:
                    found.append(f"{where}.security.{key}[{i}].pattern does not compile: {err}")
    for i, row in enumerate(value.get("code_syntax") or []):
        for j, refusal in enumerate(row.get("refuse_when") or [] if isinstance(row, dict) and isinstance(row.get("refuse_when"), list) else []):
            if isinstance(refusal, dict) and isinstance(refusal.get("pattern"), str):
                try:
                    re.compile(refusal["pattern"])
                except re.error as err:
                    found.append(f"{where}.security.code_syntax[{i}].refuse_when[{j}].pattern does not compile: {err}")
        if isinstance(row, dict) and isinstance(row.get("heredoc"), str):
            try:
                groups = re.compile(row["heredoc"]).groupindex
            except re.error as err:
                found.append(f"{where}.security.code_syntax[{i}].heredoc does not compile: {err}")
            else:
                # check_security_review reads the terminator from the `id` group (#2214 review): without it the reader would crash, not judge.
                if "id" not in groups:
                    found.append(f"{where}.security.code_syntax[{i}].heredoc needs a named group `(?P<id>...)` holding the terminator")
    return found


PLUGIN_ID = re.compile(r"[a-z0-9][a-z0-9._-]*@[a-z0-9][a-z0-9._-]*")
AUTO_INSTALL_METHODS = ("npm-global", "brew-tap", "npm-dev")          # the only install methods stack_toolchain.py --install runs (#2288)
VENDOR_REPO = re.compile(r"github\.com/[A-Za-z0-9][A-Za-z0-9-]*/[A-Za-z0-9._-]+")


def toolchain_problems(stack: dict, where: str) -> list[str]:
    """A toolchain block names each plugin as `name@marketplace`, and every install line, binary and ready command is non-empty
    (#2168): a blank one would print an empty fix, and an id without its marketplace cannot be looked up in installed_plugins.json."""
    value = (stack.get("descriptor") or {}).get("toolchain") if isinstance(stack.get("descriptor"), dict) else None
    if not isinstance(value, dict):
        return []
    found = []
    for i, row in enumerate(value.get("plugins") or []):
        if isinstance(row, dict):
            if isinstance(row.get("id"), str) and not PLUGIN_ID.fullmatch(row["id"]):
                found.append(f"{where}.toolchain.plugins[{i}].id {row['id']!r} must be `name@marketplace`")
            if isinstance(row.get("install"), str) and not row["install"].strip():
                found.append(f"{where}.toolchain.plugins[{i}].install is empty")
    for i, row in enumerate(value.get("clis") or []):
        if isinstance(row, dict):
            for key in ("bin", "install"):
                if isinstance(row.get(key), str) and not row[key].strip():
                    found.append(f"{where}.toolchain.clis[{i}].{key} is empty")
            if isinstance(row.get("bin"), str) and ("/" in row["bin"] or " " in row["bin"].strip()):
                found.append(f"{where}.toolchain.clis[{i}].bin {row['bin']!r} must be a bare command name, looked up on PATH")
            ready = row.get("ready")
            if isinstance(ready, list) and (not ready or not all(isinstance(a, str) and a.strip() for a in ready)):
                found.append(f"{where}.toolchain.clis[{i}].ready must be a non-empty command (a list of arguments)")
            for path in row.get("project_paths") or []:
                if isinstance(path, str) and escapes(path):
                    found.append(f"{where}.toolchain.clis[{i}].project_paths {path!r} must stay inside the project (no absolute path, no `..`)")
            if isinstance(ready, list) and ready and isinstance(ready[0], str) and ("/" in ready[0] or " " in ready[0].strip()):
                found.append(f"{where}.toolchain.clis[{i}].ready[0] {ready[0]!r} must be a bare command name, looked up on PATH")
            for j, how in enumerate(row.get("auto_install") or []):
                if isinstance(how, dict) and how.get("method") not in AUTO_INSTALL_METHODS and isinstance(how.get("method"), str):
                    found.append(f"{where}.toolchain.clis[{i}].auto_install[{j}].method {how['method']!r} is not one of {sorted(AUTO_INSTALL_METHODS)}")
                if isinstance(how, dict) and isinstance(how.get("repo"), str) and not VENDOR_REPO.fullmatch(how["repo"]):
                    found.append(f"{where}.toolchain.clis[{i}].auto_install[{j}].repo {how['repo']!r} must be `github.com/<owner>/<repo>`")
            if isinstance(row.get("token"), str) and not re.fullmatch(r"[A-Z][A-Z0-9_]*", row["token"]):
                found.append(f"{where}.toolchain.clis[{i}].token {row['token']!r} must be an environment variable name")
            if "ready" in row and not row.get("ready_hint"):
                found.append(f"{where}.toolchain.clis[{i}] has a `ready` check but no `ready_hint` saying how to pass it")
    return found


def toolchains(manifests: list[dict], matched: list[dict]) -> list[dict]:
    """Each matched stack's toolchain block, in detection order (#2168): the plugins and CLIs a project of that stack needs."""
    by_plugin = {m["plugin"]: m for m in manifests}
    out = []
    for found in matched:
        stack = next(s for s in by_plugin[found["plugin"]]["stacks"] if isinstance(s, dict) and s.get("id") == found["id"])
        value = (stack.get("descriptor") or {}).get("toolchain")
        if isinstance(value, dict):
            out.append({"stack": found["id"], "plugin": found["plugin"], **json.loads(json.dumps(value))})
    return out


def ui_scope_problems(manifest: dict, stack: dict, where: str) -> list[str]:
    value = (stack.get("descriptor") or {}).get("ui_scope") if isinstance(stack.get("descriptor"), dict) else None
    if not isinstance(value, dict):
        return []                               # absent, or a shape problem shape_problems already reports
    found = [f"{where}.ui_scope needs `{key}`" for key in ("paths", "cases") if key not in value]
    for key in ("paths", "not_paths", "seen_anyway"):
        for i, pattern in enumerate(value.get(key) or [] if isinstance(value.get(key), list) else []):
            if isinstance(pattern, str):
                try:
                    re.compile(pattern)
                except re.error as err:
                    found.append(f"{where}.ui_scope.{key}[{i}] does not compile: {err}")
    named = value.get("cases")
    if isinstance(named, str) and named:
        if escapes(named):
            found.append(f"{where}.ui_scope.cases {named!r} must stay inside its plugin (no absolute path, no `..`)")
        elif not (plugin_root(manifest) / named).is_file():
            found.append(f"{where}.ui_scope.cases {named!r} names no file in {plugin_root(manifest)}")
    return found


def ui_scopes(manifests: list[dict], matched: list[dict]) -> list[dict]:
    """Each matched stack's `ui_scope`, its cases as a readable path, in detection order (#2219)."""
    by_plugin = {m["plugin"]: m for m in manifests}
    out = []
    for found in matched:
        manifest = by_plugin[found["plugin"]]
        stack = next(s for s in manifest["stacks"] if isinstance(s, dict) and s.get("id") == found["id"])
        value = (stack.get("descriptor") or {}).get("ui_scope")
        if isinstance(value, dict):
            entry = {"stack": found["id"], "plugin": found["plugin"], **json.loads(json.dumps(value))}
            if isinstance(value.get("cases"), str):
                entry["cases"] = str(plugin_root(manifest) / value["cases"])
            out.append(entry)
    return out


def security_surfaces(manifests: list[dict], matched: list[dict]) -> list[dict]:
    """Each matched stack's security block, its checklist as a readable path, in detection order (#2117)."""
    by_plugin = {m["plugin"]: m for m in manifests}
    out = []
    for found in matched:
        manifest = by_plugin[found["plugin"]]
        stack = next(s for s in manifest["stacks"] if isinstance(s, dict) and s.get("id") == found["id"])
        value = (stack.get("descriptor") or {}).get("security")
        if isinstance(value, dict):
            entry = {"stack": found["id"], "plugin": found["plugin"], **json.loads(json.dumps(value))}
            if isinstance(value.get("checklist"), str):
                entry["checklist"] = str(plugin_root(manifest) / value["checklist"])
            out.append(entry)
    return out


def leaves(value: object, path: str = "") -> dict[str, object]:
    """`{"tests.command": [...], ...}`: every leaf of a descriptor by its dotted path."""
    if not isinstance(value, dict):
        return {path: value}
    out: dict[str, object] = {}
    for key, item in value.items():
        out.update(leaves(item, f"{path}.{key}" if path else key))
    return out


def agent_file(name: str, roots: list[Path]) -> Path | None:
    """`plugin:agent` as a file, in a checkout (`<root>/<plugin>/agents/`) or the cache (`<root>/<plugin>/<ver>/agents/`)."""
    if ":" not in name:
        return None
    plugin, agent = name.split(":", 1)
    for root in roots:
        for candidate in [root / plugin / "agents" / f"{agent}.md", *sorted((root / plugin).glob(f"*/agents/{agent}.md"))]:
            if candidate.is_file():
                return candidate
    return None


def agent_problems(found: dict[str, object], where: str, roots: list[Path] | None) -> list[str]:
    """Every agent-naming value is `<plugin>:<agent>`, and, when the tree is known, names an agent file that exists."""
    out = []
    for path, value in found.items():
        if not any(path == pattern or (pattern.endswith(".*") and path.startswith(pattern[:-1])) for pattern in AGENT_VALUES):
            continue
        if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9-]*:[a-z0-9][a-z0-9-]*", value):
            out.append(f"{where}.{path} {value!r} must name an agent as `<plugin>:<agent>`")
        elif roots is not None and agent_file(value, roots) is None:
            out.append(f"{where}.{path} {value!r} names no agent: no {value.partition(':')[0]}/agents/{value.partition(':')[2]}.md in the plugins found")
    return out


def descriptor_problems(manifest: dict, roots: list[Path] | None = None) -> list[str]:
    """Every descriptor in a manifest checked against `DESCRIPTOR_SCHEMA`, its agents resolved, its setup section found, and the
    plugin complete."""
    found = []
    declared: set[str] = set()
    for stack in manifest.get("stacks") or []:
        if isinstance(stack, dict) and "descriptor" in stack:
            where = f"{manifest['_path']}: stack {stack.get('id')!r} descriptor"
            found.extend(shape_problems(stack["descriptor"], DESCRIPTOR_SCHEMA, where))
            found.extend(setup_section_problems(manifest, stack, where))
            found.extend(security_problems(manifest, stack, where))
            found.extend(ui_scope_problems(manifest, stack, where))
            found.extend(toolchain_problems(stack, where))
            values = leaves(stack["descriptor"]) if isinstance(stack["descriptor"], dict) else {}
            found.extend(agent_problems(values, where, roots))
            # a setup section or a security block alone is no flow-facing descriptor; leaves are dotted (`security.checklist`)
            declared |= {k for k in values if k.split(".")[0] not in PER_STACK_KEYS}
    if declared:
        missing = [key for key in REQUIRED if key not in declared]
        if missing:
            found.append(f"{manifest['_path']}: {manifest['plugin']}'s descriptors declare no {', '.join(missing)}: a flow has no fallback for them")
    return found


# A TREE THAT IS STILL A NEW PROJECT (#2199 review). `gh repo create` or a fresh clone holds these and nothing else, and the owner's
# ruling is that a new project is ASKED which stack. Anything beyond them is an existing project of a stack no plugin declares,
# which setup-flow must not scaffold over. The agent files are the ones setup-flow itself writes.
FRESH_ENTRIES = (".git", "README*", "LICENSE*", ".gitignore", ".github", "CLAUDE.md", "AGENTS.md", "GUARDRAILS.md", "loop.md",
                 ".claude", ".rails-flow", "docs")


def fresh(project: Path) -> bool:
    """Whether the project holds only what a brand-new repository and setup-flow's own files hold."""
    try:
        entries = [entry.name for entry in project.iterdir()]
    except OSError:
        return False
    return all(any(fnmatch.fnmatchcase(name, pattern) for pattern in FRESH_ENTRIES) for name in entries)


def available(manifests: list[dict]) -> list[dict]:
    """Every stack an installed plugin declares: what setup-flow offers a new project, never a hard-coded list (#2180)."""
    return [{"id": s["id"], "name": s.get("name", s["id"]), "plugin": m["plugin"]}
            for m in manifests for s in m["stacks"] if isinstance(s, dict) and isinstance(s.get("id"), str) and s["id"]]


def chosen_stacks(manifests: list[dict], ids: list[str]) -> tuple[list[dict], list[str]]:
    """The stacks named on the command line (a new project has no markers to detect), and every id no plugin declares."""
    offered = available(manifests)
    matched = [s for s in offered if s["id"] in ids]
    unknown = [f"--stack {i!r}: no installed plugin declares it (offered: {', '.join(s['id'] for s in offered) or 'none'})"
               for i in ids if i not in {s["id"] for s in offered}]
    return matched, unknown


def setup_sections(manifests: list[dict], matched: list[dict]) -> list[dict]:
    """Each matched stack's setup section, as a path setup-flow can read, in detection order."""
    by_plugin = {m["plugin"]: m for m in manifests}
    out = []
    for found in matched:
        manifest = by_plugin[found["plugin"]]
        stack = next(s for s in manifest["stacks"] if isinstance(s, dict) and s.get("id") == found["id"])
        value = (stack.get("descriptor") or {}).get("setup_section")
        if isinstance(value, str) and value:
            out.append({"stack": found["id"], "plugin": found["plugin"], "path": str(plugin_root(manifest) / value)})
    return out


def merged_descriptor(manifests: list[dict], matched: list[dict]) -> tuple[dict, dict, list[str]]:
    """The detected stacks' descriptors as one, the source of every top-level key, and the conflicts."""
    by_plugin = {m["plugin"]: m for m in manifests}
    merged: dict = {}
    sources: dict[str, set[str]] = {}
    owner: dict[str, str] = {}
    conflicts: list[str] = []

    def merge(into: dict, value: dict, label: str, path: str) -> None:
        for key, item in value.items():
            here = f"{path}.{key}" if path else key
            if isinstance(item, dict) and isinstance(into.get(key), dict):
                merge(into[key], item, label, here)
            elif key in into and into[key] != item:
                conflicts.append(f"descriptor {here}: {into[key]!r} and {item!r} ({', '.join(sorted(sources.get(here.split('.')[0], set())))} and {label})")
            elif key not in into:
                into[key] = json.loads(json.dumps(item))

    for found in matched:
        manifest = by_plugin[found["plugin"]]
        stack = next(s for s in manifest["stacks"] if isinstance(s, dict) and s.get("id") == found["id"])
        label = f"{found['plugin']}:{found['id']}"
        for key, value in (stack.get("descriptor") or {}).items():
            if key in PER_STACK_KEYS:
                continue
            if key in owner and owner[key] != found["plugin"]:
                conflicts.append(f"descriptor {key} is declared by two plugins: {owner[key]} and {found['plugin']}")
                continue
            owner[key] = found["plugin"]
            merge(merged, {key: value}, label, "")
            sources.setdefault(key, set()).add(label)
    return merged, {k: sorted(v) for k, v in sources.items()}, conflicts


def agent_roots(start: Path) -> list[Path]:
    """Where `plugin:agent` names resolve: the sibling plugins of a checkout, and the cache's per-plugin version directories."""
    own = start.resolve().parents[1]
    return [own.parent, own.parent.parent]


def run(project: Path, dirs: list[Path], stacks: list[str] | None = None, roots: list[Path] | None = None) -> tuple[int, dict]:
    """Detect the project's stacks, or, given `stacks` (a new project: nothing to detect), take those. `roots`, when given, is
    where agent names must resolve; None checks their shape only."""
    manifests, problems = load_manifests(dirs)
    for manifest in manifests:
        problems += descriptor_problems(manifest, roots)
    if stacks:
        matched, unknown = chosen_stacks(manifests, stacks)
        problems += unknown
    elif not project.is_dir():
        # A missing path, or a file, has no markers to read: "cannot judge", never "no stack" (#2188 review).
        problems.append(f"{project}: not a directory, so no stack can be judged")
        matched = []
    else:
        matched, more = detect(project, manifests)
        problems += more
    descriptor, sources, conflicts = merged_descriptor(manifests, matched)
    problems += conflicts
    report = {"project": str(project), "stacks": matched, "manifests": [m["_path"] for m in manifests], "problems": problems,
              "descriptor": descriptor, "descriptor_sources": sources, "setup_sections": setup_sections(manifests, matched),
              "security": security_surfaces(manifests, matched), "ui_scope": ui_scopes(manifests, matched),
              "toolchain": toolchains(manifests, matched),
              "available": available(manifests), "fresh": fresh(project)}
    if problems:
        return 2, report
    return (0 if matched else 1), report


def render(code: int, report: dict) -> str:
    if code == 2:
        return "\n".join(["could not judge every stack:", *[f"  - {p}" for p in report["problems"]]])
    if not report["stacks"]:
        return f"no stack detected ({len(report['manifests'])} manifest(s) read)"
    return "\n".join(f"{s['id']}: {s['name']} ({s['plugin']})" for s in report["stacks"])


def selftest() -> int:
    """A fixture per stack, a combined one, an empty project, and every way a manifest or project can be misread."""
    failures: list[str] = []
    count = 0

    def case(ok: bool, message: str) -> None:
        nonlocal count
        count += 1
        if not ok:
            failures.append(message)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def plugin_dir(path: Path, marker: str = ".claude-plugin/plugin.json") -> Path:
            path.mkdir(parents=True, exist_ok=True)
            (path / marker).parent.mkdir(parents=True, exist_ok=True)
            (path / marker).write_text("{}", encoding="utf-8")
            return path

        def manifest(name: str, data: object) -> Path:
            d = plugin_dir(root / "plugins" / name)
            (d / MANIFEST).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
            return d

        def project(name: str, files: dict[str, str] | None = None, dirs: tuple[str, ...] = ()) -> Path:
            p = root / "projects" / name
            p.mkdir(parents=True)
            for rel, body in (files or {}).items():
                (p / rel).parent.mkdir(parents=True, exist_ok=True)
                (p / rel).write_text(body, encoding="utf-8")
            for rel in dirs:
                (p / rel).mkdir(parents=True)
            return p

        rails = manifest("rails-stack", {"plugin": "rails-stack", "stacks": [{"id": "rails", "name": "Rails",
                         "all": [{"file": "Gemfile"}, {"file": "config/application.rb"}]}]})
        nextjs = manifest("nextjs-stack", {"plugin": "nextjs-stack", "stacks": [
            {"id": "nextjs", "name": "Next.js", "all": [{"package_dependency": "next"}]},
            {"id": "supabase", "name": "Supabase", "all": [{"file": "supabase/config.toml"}]},
            {"id": "vercel", "name": "Vercel", "any": [{"file": "vercel.json"}, {"dir": ".vercel"}]}]})
        dirs = [rails, nextjs]

        def ids(p: Path, use: list[Path] | None = None) -> tuple[int, list[str]]:
            code, report = run(p, use if use is not None else dirs)
            return code, sorted(s["id"] for s in report["stacks"])

        def code_of(p: Path, extra: Path) -> int:
            return run(p, dirs + [extra])[0]

        rails_app = project("rails-app", {"Gemfile": "", "config/application.rb": ""})
        case(ids(rails_app) == (0, ["rails"]), f"a Rails project is Rails: {ids(rails_app)}")
        code, report = run(rails_app, dirs)
        case(report["stacks"][0].get("name") == "Rails" if report["stacks"] else False,
             f"a detected stack carries its declared name: {report['stacks']}")
        case(ids(project("half-rails", {"Gemfile": ""})) == (1, []), "every `all` marker must hold (a Gemfile alone is not Rails)")
        case(ids(project("next-app", {"package.json": json.dumps({"dependencies": {"next": "15", "react": "19"}})})) == (0, ["nextjs"]),
             "a next dependency is Next.js")
        case(ids(project("dev-next", {"package.json": json.dumps({"devDependencies": {"next": "15"}})})) == (0, ["nextjs"]),
             "a next devDependency is Next.js too")
        combined = project("combined", {"package.json": json.dumps({"dependencies": {"next": "15"}}), "supabase/config.toml": ""}, dirs=(".vercel",))
        case(ids(combined) == (0, ["nextjs", "supabase", "vercel"]), f"a combined project reports every stack it matches: {ids(combined)}")
        case(ids(project("vercel-json", {"vercel.json": "{}"})) == (0, ["vercel"]), "any one of an `any` list is enough (a file)")
        case(ids(project("vercel-dir", dirs=(".vercel",))) == (0, ["vercel"]), "any one of an `any` list is enough (a `dir` marker)")
        empty = project("empty")
        case(ids(empty) == (1, []), f"an empty project matches nothing and says so (exit 1): {ids(empty)}")
        case(ids(project("no-vercel", {"vercel.txt": ""})) == (1, []), "a stack whose `any` list holds nothing is not matched")

        # A CORRUPT package.json is "cannot judge", not "no dependency" (#2188 review); a missing one is no dependency.
        bad_pkg = project("bad-package", {"package.json": "{not json"})
        case(ids(bad_pkg)[0] == 2, f"a package.json that does not parse is a problem when a stack reads it: {ids(bad_pkg)}")
        case(ids(bad_pkg, [rails]) == (1, []), "a corrupt package.json is no problem when no stack reads dependencies")
        list_pkg = project("list-package", {"package.json": "[1, 2]"})
        case(ids(list_pkg)[0] == 2, f"a package.json that is valid JSON but not an object is a problem when a stack reads it: {ids(list_pkg)}")
        list_deps = project("list-deps", {"package.json": json.dumps({"dependencies": ["next"]})})
        case(ids(list_deps)[0] == 2, f"a `dependencies` that is not a map is a problem: {ids(list_deps)}")

        # A project path that is missing, or a file, cannot be judged (#2188 review).
        case(ids(empty / "no-such-dir")[0] == 2, f"a missing project path is a problem (exit 2): {ids(empty / 'no-such-dir')}")
        case(ids(empty.parent / "list-deps" / "package.json")[0] == 2, "a project path that is a file is a problem (exit 2)")

        # ADDING A STACK IS A MANIFEST: a stack no plugin ships is detected the moment its manifest exists.
        go = manifest("go-stack", {"plugin": "go-stack", "stacks": [{"id": "go", "name": "Go", "all": [{"file": "go.mod"}]}]})
        case(ids(project("go-app", {"go.mod": "module x"}), dirs + [go]) == (0, ["go"]), "a new stack plugin's manifest is enough to detect it")

        # EVERY WAY A MANIFEST CAN BE MISREAD IS EXIT 2, never the "none detected" code (#2188 review).
        for label, data in (
            ("an unknown marker kind is a problem", {"plugin": "p1", "stacks": [{"id": "x", "all": [{"glob": "*.x"}]}]}),
            ("a stack with no markers is a problem", {"plugin": "p2", "stacks": [{"id": "x"}]}),
            ("`stacks` naming a string is a problem", {"plugin": "p3", "stacks": ["rails"]}),
            ("`stacks` as an object is a problem", {"plugin": "p4", "stacks": {"id": "x"}}),
            ("a non-string marker value is a problem", {"plugin": "p5", "stacks": [{"id": "x", "all": [{"file": 5}]}]}),
            ("an absolute marker path is a problem", {"plugin": "p6", "stacks": [{"id": "x", "all": [{"file": "/etc/hosts"}]}]}),
            ("a marker path with `..` is a problem", {"plugin": "p7", "stacks": [{"id": "x", "all": [{"file": "../x"}]}]}),
            ("`all` that is not a list is a problem", {"plugin": "p8", "stacks": [{"id": "x", "all": {"file": "x"}}]}),
            ("a manifest that names no plugin is a problem", {"stacks": []}),
            ("an unreadable manifest is a problem, not a skipped plugin", "{nope"),
            ("a `dir` marker naming the project root (.) is a problem", {"plugin": "p9", "stacks": [{"id": "x", "all": [{"dir": "."}]}]}),
            ("a `file` marker naming the project root (./) is a problem", {"plugin": "p10", "stacks": [{"id": "x", "all": [{"file": "./"}]}]}),
            ("a stack with no id is a problem", {"plugin": "p11", "stacks": [{"all": [{"file": "Gemfile"}]}]}),
            ("a stack whose id is a list is a problem", {"plugin": "p12", "stacks": [{"id": ["x"], "all": [{"file": "Gemfile"}]}]}),
        ):
            bad = manifest("bad-" + str(len(failures)) + "-" + str(count), data)
            case(code_of(rails_app, bad) == 2, f"{label} (exit 2): got {code_of(rails_app, bad)}")

        # TWO VERSIONS OF ONE PLUGIN COLLAPSE TO THE HIGHER; two at the SAME version are a problem, never a silent first-wins.
        old, new = root / "cache" / "rails-stack" / "1.2.0", root / "cache" / "rails-stack" / "1.10.0"
        for d, marker in ((old, "Gemfile.lock"), (new, "Gemfile")):
            plugin_dir(d)
            (d / MANIFEST).write_text(json.dumps({"plugin": "rails-stack", "version": d.name,
                                                  "stacks": [{"id": "rails", "all": [{"file": marker}]}]}), encoding="utf-8")
        loaded, problems = load_manifests([old, new])
        case(len(loaded) == 1 and loaded[0]["version"] == "1.10.0" and not problems,
             f"two versions of a plugin collapse to the higher one (1.10.0 over 1.2.0): {[m.get('version') for m in loaded]}")
        twin_a, twin_b = root / "twins" / "a", root / "twins" / "b"
        for d in (twin_a, twin_b):
            plugin_dir(d)
            (d / MANIFEST).write_text(json.dumps({"plugin": "twin-stack", "stacks": []}), encoding="utf-8")
        case(bool(load_manifests([twin_a, twin_b])[1]), "two manifests for one plugin at the same version are a problem")

        # DISCOVERY, in the checkout shape: sibling plugins are found; a stray stacks.json is not, and since #2182
        # neither is one at the repo root (rails-stack ships it from plugins/rails-stack/).
        repo = root / "repo"
        (repo / "plugins" / "rails-flow" / "scripts").mkdir(parents=True)
        plugin_dir(repo, ".claude-plugin/marketplace.json")
        plugin_dir(repo / "plugins" / "nextjs-stack")
        plugin_dir(repo / "plugins" / "rails-stack")
        (repo / "docs" / "notes").mkdir(parents=True)
        for d in (repo, repo / "plugins" / "nextjs-stack", repo / "plugins" / "rails-stack", repo / "docs" / "notes"):
            (d / MANIFEST).write_text(json.dumps({"plugin": d.name, "stacks": []}), encoding="utf-8")
        (repo / "plugins" / "loose").mkdir()
        (repo / "plugins" / "loose" / MANIFEST).write_text("{}", encoding="utf-8")
        seen = {p.name for p in manifest_dirs(repo / "plugins" / "rails-flow" / "scripts" / "detect_stack.py")}
        case(seen == {"rails-stack", "nextjs-stack"}, f"discovery reads plugin roots only (siblings, not the repo root or a stray stacks.json): {sorted(seen)}")

        # AND IN THE CACHE SHAPE: <plugin>/<version>/ under one marketplace directory.
        cache = root / "installed" / "cache" / "claude-skills"   # Claude Code's shape: <plugins>/cache/<marketplace>/<plugin>/<version>
        (cache / "rails-flow" / "1.64.0" / "scripts").mkdir(parents=True)
        plugin_dir(cache / "rails-stack" / "1.76.0")
        (cache / "rails-stack" / "1.76.0" / MANIFEST).write_text(json.dumps({"plugin": "rails-stack", "stacks": []}), encoding="utf-8")
        seen_cache = [p.parent.name for p in manifest_dirs(cache / "rails-flow" / "1.64.0" / "scripts" / "detect_stack.py")]
        case(seen_cache == ["rails-stack"], f"discovery finds a stack plugin in the installed cache: {seen_cache}")

        # A COPY STAGED OUTSIDE BOTH LAYOUTS (#2117, the #1475 lesson): only its own plugin is read, never its parent directory,
        # so a sibling tempdir's stacks.json is not found (and the system temp root is never walked).
        staged = root / "tmp" / "stage-a"
        (staged / "scripts").mkdir(parents=True)
        stranger = root / "tmp" / "stage-b"
        plugin_dir(stranger)
        (stranger / MANIFEST).write_text(json.dumps({"plugin": "stranger", "stacks": []}), encoding="utf-8")
        seen_staged = manifest_dirs(staged / "scripts" / "detect_stack.py")
        case(seen_staged == [], f"a staged copy reads no sibling directory's stacks.json: {seen_staged}")

        # THE COMMAND LINE: --json is the report, and the exit code is the run's.
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main([str(combined), "--json"], dirs=dirs)
        try:
            printed = json.loads(out.getvalue())
        except ValueError:
            printed = {}
        case(rc == 0 and sorted(s["id"] for s in printed.get("stacks", [])) == ["nextjs", "supabase", "vercel"] and printed.get("problems") == [],
             f"--json prints the report and exits with the run's code: rc={rc} {out.getvalue()[:120]!r}")

    # THE DESCRIPTOR (#2181). A fixture stack no Rails value fits, a three-stack merge, and every way a descriptor can be wrong.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def plug(name: str, stacks: list) -> Path:
            d = root / "plugins" / name
            (d / ".claude-plugin").mkdir(parents=True, exist_ok=True)
            (d / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
            (d / MANIFEST).write_text(json.dumps({"plugin": name, "stacks": stacks}), encoding="utf-8")
            return d

        def proj(name: str, files: dict) -> Path:
            p = root / "projects" / name
            p.mkdir(parents=True, exist_ok=True)
            for rel, body in files.items():
                (p / rel).parent.mkdir(parents=True, exist_ok=True)
                (p / rel).write_text(body, encoding="utf-8")
            return p

        AGENTS = {"developer": "dev-flow:developer", "test_runner": "dev-flow:test-runner", "reviewer": "dev-flow:reviewer"}
        go = plug("go-stack", [{"id": "go", "name": "Go", "all": [{"file": "go.mod"}],
                                "descriptor": {"tests": {"command": ["go", "test", "./..."], "glob": "**/*_test.go"},
                                               "boot": {"command": "go run .", "port": 8080, "health": "/healthz"},
                                               "agents": AGENTS}}])
        go_app = proj("go-app", {"go.mod": "module x"})
        code, report = run(go_app, [go])
        case(code == 0 and report["descriptor"].get("tests", {}).get("command") == ["go", "test", "./..."] and report["descriptor"]["boot"]["port"] == 8080,
             f"a go stack's descriptor is go's own, not Rails': {code} {report['descriptor']}")

        nextjs = plug("nextjs-stack", [
            {"id": "nextjs", "all": [{"package_dependency": "next"}],
             "descriptor": {"tests": {"command": ["npx", "vitest", "run"], "glob": "**/*.test.ts"}, "layout": {"source": ["app/**/*.tsx"]},
                            "agents": AGENTS}},
            {"id": "supabase", "all": [{"file": "supabase/config.toml"}], "descriptor": {"layout": {"migrations": "supabase/migrations/"}}},
            {"id": "vercel", "any": [{"file": "vercel.json"}], "descriptor": {"deploy": {"target": "vercel"}}}])
        trio = proj("trio", {"package.json": json.dumps({"dependencies": {"next": "15"}}), "supabase/config.toml": "", "vercel.json": "{}"})
        code, report = run(trio, [nextjs])
        want = {"tests": {"command": ["npx", "vitest", "run"], "glob": "**/*.test.ts"}, "layout": {"source": ["app/**/*.tsx"], "migrations": "supabase/migrations/"},
                "deploy": {"target": "vercel"}, "agents": AGENTS}
        case(code == 0 and report["descriptor"] == want and report["descriptor_sources"].get("layout") == ["nextjs-stack:nextjs", "nextjs-stack:supabase"],
             f"three stacks from one plugin merge into one descriptor, each key naming its source: {code} {report['descriptor']} {report['descriptor_sources']}")

        rival = plug("rival-stack", [{"id": "rival", "all": [{"file": "supabase/config.toml"}], "descriptor": {"tests": {"glob": "*.spec.ts"}}}])
        code, report = run(trio, [nextjs, rival])
        case(code == 2 and any("declared by two plugins" in p for p in report["problems"]),
             f"a descriptor key declared by two plugins is a conflict, never a silent pick: {code} {report['problems']}")

        clash = plug("clash-stack", [{"id": "a", "all": [{"file": "a"}], "descriptor": {"deploy": {"target": "kamal"}}},
                                     {"id": "b", "all": [{"file": "b"}], "descriptor": {"deploy": {"target": "vercel"}}}])
        code, report = run(proj("ab", {"a": "", "b": ""}), [clash])
        case(code == 2 and any("deploy.target" in p for p in report["problems"]), f"one plugin giving a leaf two values is a conflict too: {code} {report['problems']}")

        for n, (label, descriptor, needle) in enumerate((
            ("an undeclared descriptor key is a problem", {"testz": {"command": ["x"]}}, "testz is not a declared descriptor key"),
            ("an undeclared key inside a block is a problem", {"tests": {"cmd": ["x"]}}, "tests.cmd is not a declared descriptor key"),
            ("a descriptor value of the wrong type is a problem", {"boot": {"port": "3000"}}, "boot.port must be a whole number"),
        )):
            odd = plug(f"odd-{n}", [{"id": "odd", "all": [{"file": "go.mod"}], "descriptor": descriptor}])
            code, report = run(go_app, [odd])
            case(code == 2 and any(needle in p for p in report["problems"]), f"{label}: {code} {report['problems']}")

        code, report = run(proj("nothing", {}), [go, nextjs])
        case(code == 1 and report["descriptor"] == {}, f"with no stack detected the descriptor is empty: {code} {report['descriptor']}")

        # SETUP SECTIONS AND THE NEW-PROJECT CHOICE (#2180).
        sec_a = plug("sec-a", [{"id": "ruby", "all": [{"file": "Gemfile"}], "descriptor": {"setup_section": "setup/ruby.md"}}])
        (sec_a / "setup").mkdir()
        (sec_a / "setup" / "ruby.md").write_text("# ruby", encoding="utf-8")
        sec_b = plug("sec-b", [{"id": "node", "all": [{"file": "package.json"}], "descriptor": {"setup_section": "setup/node.md"}}])
        (sec_b / "setup").mkdir()
        (sec_b / "setup" / "node.md").write_text("# node", encoding="utf-8")
        both = proj("both", {"Gemfile": "", "package.json": "{}"})
        code, report = run(both, [sec_a, sec_b])
        paths = [Path(x["path"]) for x in report["setup_sections"]]
        case(code == 0 and paths == [sec_a / "setup" / "ruby.md", sec_b / "setup" / "node.md"] and "setup_section" not in report["descriptor"],
             f"two plugins' setup sections are both listed, never a merge conflict: {code} {report['setup_sections']} {report['problems']}")
        for n, (label, value, needle) in enumerate((
            ("a setup section naming no file is a problem", "setup/missing.md", "names no file"),
            ("a setup section leaving its plugin is a problem", "../sec-a/setup/ruby.md", "must stay inside its plugin"),
        )):
            bad = plug(f"sec-bad-{n}", [{"id": "ruby", "all": [{"file": "Gemfile"}], "descriptor": {"setup_section": value}}])
            code, report = run(both, [bad])
            case(code == 2 and any(needle in p for p in report["problems"]), f"{label}: {code} {report['problems']}")
        empty_new = proj("brand-new", {})
        case(run(empty_new, [sec_a, sec_b])[0] == 1, "a new project's empty directory detects nothing (exit 1)")
        new_repo = proj("gh-repo-create", {"README.md": "", "LICENSE": "", ".gitignore": "", ".github/workflows/ci.yml": "", ".git/HEAD": ""})
        case(run(new_repo, [sec_a])[1]["fresh"] is True, "a repo holding only README, LICENSE, .gitignore, .github and .git is still a new project (fresh)")
        cargo = proj("cargo-only", {"Cargo.toml": "", "README.md": ""})
        case(run(cargo, [sec_a])[1]["fresh"] is False, "a repo of a stack no plugin declares (Cargo.toml) is not fresh")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([str(both), "--descriptor"], dirs=[sec_a, sec_b])
        try:
            listed = json.loads(out.getvalue())["stacks"]
        except (ValueError, KeyError):
            listed = []
        case(listed == [{"id": "ruby", "plugin": "sec-a"}, {"id": "node", "plugin": "sec-b"}],
             f"--descriptor names each stack's plugin, so setup-flow can say which it activated: {listed}")
        code, report = run(empty_new, [sec_a, sec_b], ["node"])
        case(code == 0 and [s["id"] for s in report["stacks"]] == ["node"] and [x["stack"] for x in report["setup_sections"]] == ["node"],
             f"--stack takes the chosen stack for a project with nothing to detect: {code} {report['stacks']}")
        code, report = run(empty_new, [sec_a, sec_b], ["cobol"])
        case(code == 2 and any("no installed plugin declares it" in p for p in report["problems"]), f"an unknown --stack is a problem: {code} {report['problems']}")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = main(["--available", "--json"], dirs=[sec_a, sec_b, go])
        try:
            listed = [s["id"] for s in json.loads(out.getvalue())["available"]]
        except (ValueError, KeyError, TypeError):
            listed = []
        case(rc == 0 and sorted(listed) == ["go", "node", "ruby"], f"--available lists every installed stack, from the manifests: rc={rc} {listed}")
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["--available"], dirs=[])
        case(rc == 1, f"--available with no stack plugin installed exits 1: {rc}")
        # #2189 REVIEW. Completeness, agent names, value ranges, nested shapes, the copy, and `--check` itself.
        for n, key in enumerate(("tests", "agents")):
            short = {k: v for k, v in {"tests": {"command": ["go", "test"], "glob": "*_test.go"}, "agents": AGENTS}.items() if k != key}
            code, report = run(go_app, [plug(f"short-{n}", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": short}])])
            case(code == 2 and any("declare no" in p for p in report["problems"]), f"a plugin whose descriptors lack `{key}` is a problem: {code} {report['problems']}")
        markers_only = plug("markers-only", [{"id": "go", "all": [{"file": "go.mod"}]}])
        case(run(go_app, [markers_only], roots=[root / "tree"])[0] == 0,
             "a manifest with markers and no descriptor passes: REQUIRED applies only to one that declares a descriptor")
        addon = plug("addon-stack", [{"id": "core", "all": [{"file": "go.mod"}], "descriptor": {"tests": {"command": ["go", "test"], "glob": "*_test.go"}, "agents": AGENTS}},
                                     {"id": "extra", "all": [{"file": "go.mod"}], "descriptor": {"deploy": {"target": "fly"}}}])
        case(run(go_app, [addon])[0] == 0, f"an add-on stack need not repeat the required keys its plugin's main stack declares: {run(go_app, [addon])[1]['problems']}")
        agents_root = root / "tree"
        (agents_root / "dev-flow" / "agents").mkdir(parents=True)
        for a in ("developer", "test-runner", "reviewer"):
            (agents_root / "dev-flow" / "agents" / f"{a}.md").write_text("x", encoding="utf-8")
        (agents_root / "ops" / "2.0.0" / "agents").mkdir(parents=True)
        (agents_root / "ops" / "2.0.0" / "agents" / "deployer.md").write_text("x", encoding="utf-8")
        case(run(go_app, [go], roots=[agents_root])[0] == 0, "agent names that resolve to agent files pass (checkout layout)")
        cached = plug("cached-stack", [{"id": "go", "all": [{"file": "go.mod"}],
                                        "descriptor": {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS, "deploy": {"agent": "ops:deployer"}}}])
        case(run(go_app, [cached], roots=[agents_root])[0] == 0, "an agent in a cached version directory resolves (cache layout)")
        for n, (label, agents, needle) in enumerate((
            ("a misspelt agent is a problem", {**AGENTS, "developer": "dev-flow:developr"}, "names no agent"),
            ("an agent of a plugin that is not there is a problem", {**AGENTS, "reviewer": "ghost:reviewer"}, "names no agent"),
            ("a sentence is not an agent name", {**AGENTS, "developer": "just a sentence"}, "`<plugin>:<agent>`"),
        )):
            bad = plug(f"agent-{n}", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": agents}}])
            code, report = run(go_app, [bad], roots=[agents_root])
            case(code == 2 and any(needle in p for p in report["problems"]), f"{label}: {code} {report['problems']}")
        for n, (label, extra, needle) in enumerate((
            ("a deploy agent that names no agent is a problem", {"deploy": {"agent": "ghost:deployer"}}, "deploy.agent 'ghost:deployer' names no agent"),
            ("a ui composer that names no agent is a problem", {"ui": {"composer": "ghost:composer"}}, "ui.composer 'ghost:composer' names no agent"),
        )):
            bad = plug(f"agent-extra-{n}", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS, **extra}}])
            code, report = run(go_app, [bad], roots=[agents_root])
            case(code == 2 and any(needle in p for p in report["problems"]), f"{label}: {code} {report['problems']}")
        for n, (label, extra, needle) in enumerate((
            ("a bool is not a port", {"boot": {"port": True}}, "boot.port must be a whole number"),
            ("a port above 65535 is a problem", {"boot": {"port": 99999999}}, "must be a port"),
            ("a negative port is a problem", {"boot": {"port": -1}}, "must be a port"),
            ("an empty list is a problem", {"runner_prefix": []}, "runner_prefix must be a non-empty list of strings"),
            ("an empty string in a list is a problem", {"runner_prefix": ["bundle", ""]}, "runner_prefix must be a non-empty list of strings"),
            ("an empty string is a problem", {"tests": {"command": ["go"], "glob": ""}}, "tests.glob must be a non-empty string"),
            ("a nested list item of the wrong shape is a problem", {"dangerous_commands": [{"pattern": "x", "allowd": "y"}]}, "dangerous_commands[0].allowd is not a declared"),
            ("a list item missing a key a reader takes is a problem", {"dangerous_commands": [{"pattern": "x"}]}, "dangerous_commands[0] needs `allowed`"),
            ("a heredoc pattern with no `id` group is a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": [{"open": "<", "close": ">", "column0": False}], "heredoc": "<<~(\\w+)"}]}}, "needs a named group `(?P<id>...)`"),
            ("extensions that are not a list are a problem", {"security": {"code_syntax": [{"extensions": ".x", "block_comments": [{"open": "<", "close": ">", "column0": False}], "heredoc": "(?P<id>X)"}]}}, "extensions must be a non-empty list of strings"),
            ("block comments that are not a list are a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": {"open": "<"}, "heredoc": "(?P<id>X)"}]}}, "block_comments must be a non-empty list"),
            ("a column0 that is not true or false is a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": [{"open": "<", "close": ">", "column0": "yes"}], "heredoc": "(?P<id>X)"}]}}, "column0 must be true or false"),
            ("a refuse_when pattern that does not compile is a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": [{"open": "<", "close": ">", "column0": False}], "refuse_when": [{"pattern": "(", "why": "w"}]}]}}, "refuse_when[0].pattern does not compile"),
            ("a refuse_when with no why is a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": [{"open": "<", "close": ">", "column0": False}], "refuse_when": [{"pattern": "x"}]}]}}, "refuse_when[0] needs `why`"),
            ("line_comments that are not a list are a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": [{"open": "<", "close": ">", "column0": False}], "line_comments": "<!--"}]}}, "line_comments must be a non-empty list of strings"),
            ("an unknown key in a code_syntax row is a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": [{"open": "<", "close": ">", "column0": False}], "line_comment": ["x"]}]}}, "line_comment is not a declared descriptor key"),
            ("a block comment with no column0 is a problem", {"security": {"code_syntax": [{"extensions": [".x"], "block_comments": [{"open": "<", "close": ">"}], "heredoc": "(?P<id>X)"}]}}, "needs `column0`"),
        )):
            descriptor = {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS, **extra}
            code, report = run(go_app, [plug(f"value-{n}", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": descriptor}])])
            case(code == 2 and any(needle in p for p in report["problems"]), f"{label}: {code} {report['problems']}")
        # #2260: a code_syntax row for a language with no heredoc (only `extensions` and `block_comments` are required) is valid, and so are its optional keys.
        js_row = {"extensions": [".js"], "block_comments": [{"open": "/*", "close": "*/", "column0": False}], "line_comments": ["<!--"],
                  "refuse_when": [{"pattern": "`", "why": "a template literal"}]}
        code, report = run(go_app, [plug("js-row", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS,
                                                                                                         "security": {"code_syntax": [js_row]}}}])])
        case(code == 0 and not report["problems"], f"a code_syntax row with no heredoc, and with line_comments and refuse_when, is valid: {code} {report['problems']}")
        # #2219: a stack's `ui_scope`, per stack, never merged; its patterns must compile and its cases file must exist inside the plugin.
        def ui_stack(name: str, marker: str, scope: dict, with_cases: bool = True, alone: bool = False) -> Path:
            """`alone`: an add-on stack whose descriptor holds only its ui_scope (it owns no test runner, so two such plugins cannot conflict)."""
            descriptor = {"ui_scope": scope} if alone else {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS, "ui_scope": scope}
            d = plug(name, [{"id": name, "all": [{"file": marker}], "descriptor": descriptor}])
            if with_cases:
                (d / "ui-cases.json").write_text("[]", encoding="utf-8")
            return d

        ui_app = project("ui-app", {"a.txt": "", "b.txt": ""})
        good_scope = {"paths": ["^views/"], "not_paths": ["\\.json$"], "seen_anyway": ["^views/pwa/"], "cases": "ui-cases.json"}
        code, report = run(ui_app, [ui_stack("ui-one", "a.txt", good_scope)])
        case(code == 0 and not report["problems"] and len(report["ui_scope"]) == 1 and report["ui_scope"][0]["paths"] == ["^views/"]
             and report["ui_scope"][0]["cases"].endswith("ui-one/ui-cases.json"),
             f"a valid ui_scope is reported with its cases as a path: {code} {report['problems']} {report['ui_scope']}")
        code, report = run(ui_app, [ui_stack("ui-a", "a.txt", good_scope), ui_stack("ui-b", "b.txt", {**good_scope, "paths": ["^pages/"]}, alone=True)])
        case(code == 0 and [e["plugin"] for e in report["ui_scope"]] == ["ui-a", "ui-b"] and "ui_scope" not in report["descriptor"],
             f"two stacks of two plugins each declare their own ui_scope, with no conflict and no merge: {code} {report['problems']}")
        for n, (label, scope, with_cases, needle) in enumerate((
                ("a ui_scope pattern that does not compile is a problem", {**good_scope, "paths": ["("]}, True, "does not compile"),
                ("a not_paths pattern that does not compile is a problem", {**good_scope, "not_paths": ["["]}, True, "does not compile"),
                ("a seen_anyway pattern that does not compile is a problem", {**good_scope, "seen_anyway": ["*"]}, True, "does not compile"),
                ("ui_scope cases naming no file is a problem", good_scope, False, "names no file"),
                ("ui_scope cases that escape the plugin are a problem", {**good_scope, "cases": "../x.json"}, True, "stay inside its plugin"),
                ("an empty paths list is a problem", {**good_scope, "paths": []}, True, "non-empty list"),
                ("a ui_scope with no cases is a problem", {"paths": ["^views/"]}, True, "needs `cases`"),
                ("a ui_scope with no paths is a problem", {"cases": "ui-cases.json"}, True, "needs `paths`"),
                ("an unknown ui_scope key is a problem", {**good_scope, "globs": ["x"]}, True, "descriptor-key-undeclared"))):
            code, report = run(ui_app, [ui_stack(f"ui-bad-{n}", "a.txt", scope, with_cases)])
            case(code == 2 and any(needle in p for p in report["problems"]), f"{label}: {code} {report['problems']}")
        held = {"plugin": "p", "_path": "p/stacks.json", "stacks": [{"id": "s", "descriptor": {"tests": {"command": ["go", "test"]}}}]}
        merged, _, _ = merged_descriptor([held], [{"id": "s", "plugin": "p"}])
        merged["tests"]["command"].append("MUTATED")
        case(held["stacks"][0]["descriptor"]["tests"]["command"] == ["go", "test"],
             f"the merged descriptor is a copy, not the manifest's own lists: {held['stacks'][0]['descriptor']}")
        broken = plug("broken-stack", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": {"testz": {}}}])
        for label, plugs, want_rc, want_text in (("--check on valid manifests exits 0 and says so", [go], 0, "valid"),
                                                 ("--check on a broken manifest exits 2 and prints the problem", [go, broken], 2, "testz")):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["--check"], dirs=plugs, roots=[agents_root])
            case(rc == want_rc and want_text in out.getvalue(), f"{label}: rc={rc} {out.getvalue()[:160]!r}")
        tc_ok = {"plugins": [{"id": "x-stack@m", "install": "/plugin install x-stack@m"}],
                 "clis": [{"bin": "xcli", "install": "npm i -g xcli", "ready": ["xcli", "whoami"], "ready_hint": "xcli login"}]}
        for label, tc, want in (
                ("a toolchain-only descriptor owes no REQUIRED keys", tc_ok, ""),
                ("a plugin id without its marketplace is a problem", {"plugins": [{"id": "x-stack", "install": "i"}]}, "must be `name@marketplace`"),
                ("an empty plugin install line is a problem", {"plugins": [{"id": "x@m", "install": " "}]}, "plugins[0].install is empty"),
                ("an empty CLI install line is a problem", {"clis": [{"bin": "x", "install": ""}]}, "clis[0].install is empty"),
                ("a CLI given as a path is a problem", {"clis": [{"bin": "/usr/bin/x", "install": "i"}]}, "must be a bare command name"),
                ("an empty ready command is a problem", {"clis": [{"bin": "x", "install": "i", "ready": [], "ready_hint": "h"}]}, "ready must be a non-empty command"),
                ("a ready check with no hint is a problem", {"clis": [{"bin": "x", "install": "i", "ready": ["x", "ok"]}]}, "no `ready_hint`"),
                ("a ready command given as a path is a problem", {"clis": [{"bin": "x", "install": "i", "ready": ["/opt/x", "ok"], "ready_hint": "h"}]}, "ready[0] '/opt/x' must be a bare command name"),
                ("a version given as a string is a problem", {"clis": [{"bin": "x", "install": "i", "version": "--version"}]}, "version"),
                ("an empty version list is a problem", {"clis": [{"bin": "x", "install": "i", "version": []}]}, "version"),
                ("an auto_install method we do not run is a problem", {"clis": [{"bin": "x", "install": "i", "auto_install": [{"method": "curl-sh", "package": "x", "repo": "github.com/v/x"}]}]}, "method 'curl-sh' is not one of"),
                ("an auto_install repo that is not a github.com repository is a problem", {"clis": [{"bin": "x", "install": "i", "auto_install": [{"method": "npm-global", "package": "x", "repo": "https://evil.example/x"}]}]}, "must be `github.com/<owner>/<repo>`"),
                ("a token that is not an environment variable name is a problem", {"clis": [{"bin": "x", "install": "i", "token": "my token"}]}, "must be an environment variable name"),
                ("a well-formed auto_install and token pass", {"clis": [{"bin": "x", "install": "i", "token": "X_TOKEN", "auto_install": [{"method": "brew-tap", "package": "v/tap/x", "repo": "github.com/v/homebrew-tap", "os": "darwin"}]}]}, ""),
                ("an unknown toolchain key is a problem", {"clis": [{"bin": "x", "install": "i", "login": ["x"]}]}, "login is not a declared descriptor key")):
            tdir = plug(f"tc-{abs(hash(label)) % 10**8}", [{"id": "tc", "all": [{"file": "tc.txt"}], "descriptor": {"toolchain": tc}}])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                rc = main(["--check"], dirs=[tdir], roots=[agents_root])
            case((rc == 0) if not want else (rc == 2 and want in out.getvalue()), f"{label}: rc={rc} {out.getvalue()[:240]!r}")
        tc_proj = root / "tc-proj"
        tc_proj.mkdir()
        (tc_proj / "tc.txt").write_text("x", encoding="utf-8")
        tc_dir = plug("tc-report", [{"id": "tc", "all": [{"file": "tc.txt"}], "descriptor": {"toolchain": tc_ok}}])
        _, tc_report = run(tc_proj, [tc_dir])
        case(tc_report.get("toolchain") == [{"stack": "tc", "plugin": "tc-report", **tc_ok}],
             f"the report lists each matched stack's toolchain: {tc_report.get('toolchain')}")
        # A checklist in its strict shape (#2210): checked through security_problems, so a stack's real file is what is judged.
        sec_dir = plug("sec-stack", [{"id": "sx", "all": [{"file": "sx.txt"}],
                                      "descriptor": {"security": {"checklist": "sec.md", "scanners": ["x"]}}}])
        sec_manifest = {"_path": str(sec_dir / MANIFEST), "plugin": "sec-stack",
                        "stacks": json.loads((sec_dir / MANIFEST).read_text(encoding="utf-8"))["stacks"]}
        for label, body, want in (
                ("a checklist in its strict shape passes", "# C\n\nRows of `docs/evidence/audits/a.md`.\n\n- Is RLS on? (C-1)\n- Both? (C-1, C-2)\n\n| a | b |\n|---|---|\n", True),
                ("a checklist with an HTML comment is refused", "- Ask. (C-1)\n<!-- hidden -->\n", False),
                ("a comment closing on a later line is refused", "- Ask.\nstill hidden -->\n", False),
                ("a fenced block is refused", "- Ask.\n```\nx\n```\n", False),
                ("a tilde fence is refused", "~~~\nx\n", False),
                ("an indented fence is refused", "- Ask.\n    ```sh\n", False),
                ("an indented table row is refused", "  | a | b |\n", False),
                ("a claim id mid-line is refused", "- Per C-1, is RLS on?\n", False),
                ("a claim id before the slot is refused", "- C-2 says so (C-1)\n", False),
                ("a slot that is not at the end is refused", "- Ask (C-1) then more.\n", False),
                ("a malformed slot is refused", "- Ask. (C-1,C-2)\n", False),
                # #2210 adversary: each input that got through the first rule
                ("a <details> block is refused", "<details><summary>x</summary>\nhidden\n</details>\n", False),
                ("an inline hidden span is refused", "- Ask <span hidden>x</span> now.\n", False),
                ("a link reference definition is refused", "- Ask.\n\n[k]: <> \"hidden text\"\n", False),
                ("an indented code block is refused", "- Ask.\n\n    const x = secret();\n", False),
                ("a list continuation is not a code block", "- Ask a long\n    question here.\n", True),
                ("a pipeless table is refused", "a | b\n--- | ---\n", False),
                ("a zero-width character in a citation is refused", "- Per C\u200b-1 ask\n", False),
                ("a non-ASCII hyphen in the slot is refused", "- Ask (C\u20111)\n", False),
                ("a Cyrillic C in the slot is refused", "- Ask (\u04211)\n- Ask (\u0421-1)\n", False),
                ("a spaced claim id outside the slot is refused", "- Per C - 1, ask\n", False),
                ("a suffixed id in the slot is refused", "- Ask (C-1a)\n", False),
                ("a break only Python sees is refused", "- Ask (C-1)\x1c then more\n", False),
                ("a NEL is refused", "- Ask (C-1)\x85 then more\n", False),
                ("a CRLF line ending is a line end, as in CommonMark", "- Ask. (C-1)\r\n- More. (C-2)\r\n", True),
                ("a tab is refused", "-\tAsk.\n", False),
                ("a BOM is refused", "\ufeff# C\n", False),
                ("the marks the checklists use pass", "# Spoofing — who? (rails-8 §2b)\n", True),
                ("an em-dash claim id outside the slot is refused", "- Per C\u20141 the proxy is bypassed\n", False),
                ("an HTML entity is refused", "- see &#67;-9 too\n", False),
                ("a named entity is refused", "- Ask&nbsp;now.\n", False),
                ("a link title is refused", "- [why](https://x \"hidden\") (C-1)\n", False),
                ("an image is refused", "- ![hidden](x.png)\n", False),
                ("a plain link passes", "- See [the guide](https://x/y) first.\n", True),
                ("an ampersand in prose passes", "- Read & write: who? (C-1)\n", True)):
            # every fixture names its audit, so a refusal is the format rule's and never the "names 0 audits" one
            audit_line = "" if "docs/evidence/audits/" in body else "Rows of `docs/evidence/audits/a.md`.\n"
            (sec_dir / "sec.md").write_text(audit_line + body, encoding="utf-8")
            got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
            case((not got) == want, f"{label}: {got}")
        # A cited row must be a CONFIRMED row of the one audit the checklist names, read in a marketplace checkout.
        named = "Rows in `docs/evidence/audits/a.md`.\n"
        (sec_dir / "sec.md").write_text("- Ask. (C-1)\n", encoding="utf-8")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(any("names 0 audits" in p for p in got), f"a citation with no audit named is refused: {got}")
        (sec_dir / "sec.md").write_text(named + "Also `docs/evidence/audits/b.md`.\n- Ask. (C-1)\n", encoding="utf-8")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(any("names 2 audits" in p for p in got), f"a citation naming two audits is refused: {got}")
        (sec_dir / "sec.md").write_text(named + "- Ask. (C-1, C-3)\n", encoding="utf-8")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(not got, f"outside a marketplace checkout the audit is not read: {got}")
        (root / ".claude-plugin").mkdir(exist_ok=True)
        (root / ".claude-plugin" / "marketplace.json").write_text("{}", encoding="utf-8")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(any("cannot be read" in p for p in got), f"a named audit that is missing is a problem: {got}")
        (root / "docs" / "evidence" / "audits").mkdir(parents=True)
        (root / "docs" / "evidence" / "audits" / "a.md").write_text(
            "# A\n\n## C-1 — x\n\nVerdict: CONFIRMED [quotes: C-1]\n\n## C-2 — y\n\nVerdict: CONFIRMED\n\n## C-3 — z\n\nVerdict: REFUTED\n"
            "\n## C-4 — w\n\nVerdict: CONFIRMED-ish\n\n## C-5 — v\n\nVerdict: REFUTED\n\n### C-9 — nested\n\nVerdict: CONFIRMED\n"
            "\n## C-6 — u\n\nVerdict: REFUTED\nVerdict: CONFIRMED\n\n## C-7 — t\n\n### detail\n\nVerdict: CONFIRMED\n"
            "\n## C-8 — s\n\nVerdict: REFUTED\n\n## C-8 — s again\n\nVerdict: CONFIRMED\n"
            "\n## C-10 — r\n\n```quotes C-10\nVerdict: CONFIRMED\n```\n\nVerdict: REFUTED\n"
            "\n## C-11 — q\n\n```quotes C-11\nhttps://x | d | p\n```\n\nVerdict: CONFIRMED [quotes: C-11]\n",
            encoding="utf-8")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(any("cites C-3, not a CONFIRMED row" in p for p in got), f"a citation of a REFUTED row is refused: {got}")
        (sec_dir / "sec.md").write_text(named + "- Ask. (C-99)\n", encoding="utf-8")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(any("cites C-99" in p for p in got), f"a citation of a row the audit lacks is refused: {got}")
        for cid, why in (("C-4", "a verdict that only starts CONFIRMED"), ("C-5", "a REFUTED row with a nested CONFIRMED heading"),
                         ("C-6", "a row whose first verdict is REFUTED"),
                         ("C-7", "a row with no verdict of its own, only a nested heading's"),
                         ("C-8", "a row headed twice"), ("C-10", "a verdict line inside a quotes block")):
            (sec_dir / "sec.md").write_text(named + f"- Ask. ({cid})\n", encoding="utf-8")
            got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
            case(any(f"cites {cid}," in p for p in got), f"{why} is not CONFIRMED: {got}")
        (sec_dir / "sec.md").write_text(named + "- Ask. (C-1, C-2, C-11)\n", encoding="utf-8")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(not got, f"citations of CONFIRMED rows pass: {got}")
        (root / ".claude-plugin" / "marketplace.json").unlink()
        (sec_dir / "sec.md").write_bytes(b"\xff\xfe bad")
        got = security_problems(sec_manifest, sec_manifest["stacks"][0], "w")
        case(any("cannot be read" in p for p in got), f"an undecodable checklist is a problem, not a pass: {got}")

    for f in failures:
        print(f"FAIL {f}")
    if failures:
        print(f"detect_stack selftest: {len(failures)} of {count} cases failed")
        return 1
    print(f"detect_stack selftest: {count} cases pass")
    return 0


def main(argv: list[str], dirs: list[Path] | None = None, roots: list[Path] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?", default=".", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--descriptor", action="store_true", help="print the detected stacks' merged descriptor as JSON")
    ap.add_argument("--check", action="store_true", help="validate every discovered manifest, whatever the project")
    ap.add_argument("--available", action="store_true", help="list every stack the installed plugins declare (for a new project)")
    ap.add_argument("--stack", action="append", metavar="ID", help="take this stack instead of detecting (a new project); repeatable")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if roots is None and dirs is None:
        roots = agent_roots(Path(__file__))
    dirs = dirs if dirs is not None else manifest_dirs(Path(__file__))
    if args.check:
        # Judge every stack against an empty project: shape, marker and descriptor problems surface, and nothing is matched.
        with tempfile.TemporaryDirectory() as empty:
            code, report = run(Path(empty), dirs, roots=roots)
        print("\n".join(report["problems"]) if report["problems"] else f"{len(report['manifests'])} stack manifest(s) valid")
        return 2 if report["problems"] else 0
    if args.available:
        manifests, problems = load_manifests(dirs)
        offered = available(manifests)
        if args.json:
            print(json.dumps({"available": offered, "problems": problems}, indent=2))
        else:
            print("\n".join([*(f"{s['id']}: {s['name']} ({s['plugin']})" for s in offered), *(f"problem: {p}" for p in problems)])
                  or "no stack plugin installed")
        return 2 if problems else (0 if offered else 1)
    code, report = run(args.project.resolve(), dirs, args.stack, roots)
    if args.descriptor:
        print(json.dumps({"stacks": [{"id": s["id"], "plugin": s["plugin"]} for s in report["stacks"]], "fresh": report["fresh"],
                          "descriptor": report["descriptor"],
                          "sources": report["descriptor_sources"], "setup_sections": report["setup_sections"],
                          "problems": report["problems"]}, indent=2))
    else:
        print(json.dumps(report, indent=2) if args.json else render(code, report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
