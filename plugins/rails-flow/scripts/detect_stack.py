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

Exit 0 one or more stacks detected · 1 none detected · 2 a manifest or the project could not be judged.

Run:  python3 detect_stack.py [project-dir] [--json]
      python3 detect_stack.py --selftest

Stdlib only, no network.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
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
    grandparent = own.parent.parent           # the repo root is NOT taken (#2182): rails-stack is a plugin dir now
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


def run(project: Path, dirs: list[Path]) -> tuple[int, dict]:
    manifests, problems = load_manifests(dirs)
    if not project.is_dir():
        # A missing path, or a file, has no markers to read: "cannot judge", never "no stack" (#2188 review).
        problems.append(f"{project}: not a directory, so no stack can be judged")
        matched = []
    else:
        matched, more = detect(project, manifests)
        problems += more
    report = {"project": str(project), "stacks": matched, "manifests": [m["_path"] for m in manifests], "problems": problems}
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
        cache = root / "installed" / "claude-skills"
        (cache / "rails-flow" / "1.64.0" / "scripts").mkdir(parents=True)
        plugin_dir(cache / "rails-stack" / "1.76.0")
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

    for f in failures:
        print(f"FAIL {f}")
    if failures:
        print(f"detect_stack selftest: {len(failures)} of {count} cases failed")
        return 1
    print(f"detect_stack selftest: {count} cases pass")
    return 0


def main(argv: list[str], dirs: list[Path] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?", default=".", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    code, report = run(args.project.resolve(), dirs if dirs is not None else manifest_dirs(Path(__file__)))
    print(json.dumps(report, indent=2) if args.json else render(code, report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
