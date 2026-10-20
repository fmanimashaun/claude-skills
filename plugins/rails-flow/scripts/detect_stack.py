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
or `.claude-plugin/marketplace.json` for a marketplace whose plugin is its own root (`rails-stack`'s
source is `./`) -- so a stray `stacks.json` in any other directory is never read. The same two shapes
`project_gates.plugin_roots` handles (sibling `plugins/*` in a checkout, `<plugin>/<version>/` in the
installed cache) plus the repo root. Several versions of one plugin collapse to the highest, by the
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
      python3 detect_stack.py --selftest

Stdlib only, no network.
"""
from __future__ import annotations

import argparse
import contextlib
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
    scan(own.parent)                          # sibling plugins (checkout) or sibling versions (cache)
    grandparent = own.parent.parent
    take(grandparent)                         # the repo root in a checkout: rails-stack's source is "./"
    try:
        peers = sorted(grandparent.iterdir())
    except OSError:
        peers = []
    for peer in peers:
        if peer.is_dir() and peer != own.parent:
            scan(peer)                        # every plugin's every version in the cache
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
    parts = PurePosixPath(value)
    if parts.is_absolute() or ".." in parts.parts or value.startswith("\\") or (parts.parts and ":" in parts.parts[0]):
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


STR, INT, STRS = "str", "int", "list[str]"
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
                      for key in shape[0] if key != "*" and key not in item]
        return found
    if not isinstance(value, dict) or not value:
        return [f"{where} must be a non-empty block"]
    found = []
    for key, item in value.items():
        sub = shape.get(key, shape.get("*"))
        if sub is None:
            found.append(f"{where}.{key} is not a declared descriptor key (descriptor-key-undeclared)")
        else:
            found.extend(shape_problems(item, sub, f"{where}.{key}"))
    return found


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
    """Every descriptor in a manifest checked against `DESCRIPTOR_SCHEMA`, its agents resolved, and the plugin complete."""
    found = []
    declared: set[str] = set()
    for stack in manifest.get("stacks") or []:
        if isinstance(stack, dict) and "descriptor" in stack:
            where = f"{manifest['_path']}: stack {stack.get('id')!r} descriptor"
            found.extend(shape_problems(stack["descriptor"], DESCRIPTOR_SCHEMA, where))
            values = leaves(stack["descriptor"]) if isinstance(stack["descriptor"], dict) else {}
            found.extend(agent_problems(values, where, roots))
            declared |= set(values)
    if declared:
        missing = [key for key in REQUIRED if key not in declared]
        if missing:
            found.append(f"{manifest['_path']}: {manifest['plugin']}'s descriptors declare no {', '.join(missing)}: a flow has no fallback for them")
    return found


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


def run(project: Path, dirs: list[Path], roots: list[Path] | None = None) -> tuple[int, dict]:
    """Detect the project's stacks. `roots`, when given, is where agent names must resolve; None checks their shape only."""
    manifests, problems = load_manifests(dirs)
    for manifest in manifests:
        problems += descriptor_problems(manifest, roots)
    if not project.is_dir():
        # A missing path, or a file, has no markers to read: "cannot judge", never "no stack" (#2188 review).
        problems.append(f"{project}: not a directory, so no stack can be judged")
        matched = []
    else:
        matched, more = detect(project, manifests)
        problems += more
    descriptor, sources, conflicts = merged_descriptor(manifests, matched)
    problems += conflicts
    report = {"project": str(project), "stacks": matched, "manifests": [m["_path"] for m in manifests], "problems": problems,
              "descriptor": descriptor, "descriptor_sources": sources}
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

        # DISCOVERY, in the checkout shape: a sibling plugin and the repo root are found; a stray stacks.json is not.
        repo = root / "repo"
        (repo / "plugins" / "rails-flow" / "scripts").mkdir(parents=True)
        plugin_dir(repo, ".claude-plugin/marketplace.json")
        plugin_dir(repo / "plugins" / "nextjs-stack")
        (repo / "docs" / "notes").mkdir(parents=True)
        for d in (repo, repo / "plugins" / "nextjs-stack", repo / "docs" / "notes"):
            (d / MANIFEST).write_text(json.dumps({"plugin": d.name, "stacks": []}), encoding="utf-8")
        (repo / "plugins" / "loose").mkdir()
        (repo / "plugins" / "loose" / MANIFEST).write_text("{}", encoding="utf-8")
        seen = {p.name for p in manifest_dirs(repo / "plugins" / "rails-flow" / "scripts" / "detect_stack.py")}
        case(seen == {"repo", "nextjs-stack"}, f"discovery reads plugin roots only (the repo root and a sibling, not a stray stacks.json): {sorted(seen)}")

        # AND IN THE CACHE SHAPE: <plugin>/<version>/ under one marketplace directory.
        cache = root / "installed" / "claude-skills"
        (cache / "rails-flow" / "1.64.0" / "scripts").mkdir(parents=True)
        plugin_dir(cache / "rails-stack" / "1.76.0", ".claude-plugin/marketplace.json")
        (cache / "rails-stack" / "1.76.0" / MANIFEST).write_text(json.dumps({"plugin": "rails-stack", "stacks": []}), encoding="utf-8")
        seen_cache = [p.parent.name for p in manifest_dirs(cache / "rails-flow" / "1.64.0" / "scripts" / "detect_stack.py")]
        case(seen_cache == ["rails-stack"], f"discovery finds a stack plugin in the installed cache: {seen_cache}")

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
        case(run(go_app, [go], [agents_root])[0] == 0, "agent names that resolve to agent files pass (checkout layout)")
        cached = plug("cached-stack", [{"id": "go", "all": [{"file": "go.mod"}],
                                        "descriptor": {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS, "deploy": {"agent": "ops:deployer"}}}])
        case(run(go_app, [cached], [agents_root])[0] == 0, "an agent in a cached version directory resolves (cache layout)")
        for n, (label, agents, needle) in enumerate((
            ("a misspelt agent is a problem", {**AGENTS, "developer": "dev-flow:developr"}, "names no agent"),
            ("an agent of a plugin that is not there is a problem", {**AGENTS, "reviewer": "ghost:reviewer"}, "names no agent"),
            ("a sentence is not an agent name", {**AGENTS, "developer": "just a sentence"}, "`<plugin>:<agent>`"),
        )):
            bad = plug(f"agent-{n}", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": agents}}])
            code, report = run(go_app, [bad], [agents_root])
            case(code == 2 and any(needle in p for p in report["problems"]), f"{label}: {code} {report['problems']}")
        for n, (label, extra, needle) in enumerate((
            ("a deploy agent that names no agent is a problem", {"deploy": {"agent": "ghost:deployer"}}, "deploy.agent 'ghost:deployer' names no agent"),
            ("a ui composer that names no agent is a problem", {"ui": {"composer": "ghost:composer"}}, "ui.composer 'ghost:composer' names no agent"),
        )):
            bad = plug(f"agent-extra-{n}", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS, **extra}}])
            code, report = run(go_app, [bad], [agents_root])
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
        )):
            descriptor = {"tests": {"command": ["go"], "glob": "*_test.go"}, "agents": AGENTS, **extra}
            code, report = run(go_app, [plug(f"value-{n}", [{"id": "go", "all": [{"file": "go.mod"}], "descriptor": descriptor}])])
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
            code, report = run(Path(empty), dirs, roots)
        print("\n".join(report["problems"]) if report["problems"] else f"{len(report['manifests'])} stack manifest(s) valid")
        return 2 if report["problems"] else 0
    code, report = run(args.project.resolve(), dirs, roots)
    if args.descriptor:
        print(json.dumps({"stacks": [s["id"] for s in report["stacks"]], "descriptor": report["descriptor"],
                          "sources": report["descriptor_sources"], "problems": report["problems"]}, indent=2))
    else:
        print(json.dumps(report, indent=2) if args.json else render(code, report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
