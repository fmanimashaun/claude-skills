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
Marker kinds: `{"file": path}`, `{"dir": path}`, `{"package_dependency": name}` (in `package.json`'s
dependencies or devDependencies). A marker kind this script does not know is a PROBLEM, never a
silent no-match: a stack that cannot be judged must not read as absent.

WHERE MANIFESTS ARE FOUND. The same two shapes `project_gates.plugin_roots` handles -- sibling
`plugins/*` in a source checkout, `<plugin>/<version>/` in the installed cache -- plus the repo root
itself, because `rails-stack`'s marketplace source is `./`. Several versions of one plugin collapse to
the highest, by the manifest's own `plugin` and `version`, not by directory names (a cache dir is a
version number, a checkout dir is a plugin name).

Exit 0 one or more stacks detected · 1 none detected · 2 a manifest could not be read or judged.

Run:  python3 detect_stack.py [project-dir] [--json]
      python3 detect_stack.py --selftest

Stdlib only, no network.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

MANIFEST = "stacks.json"
KINDS = ("file", "dir", "package_dependency")


def version_tuple(raw: object) -> tuple[int, ...]:
    parts = []
    for chunk in str(raw or "0").split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def manifest_dirs(start: Path) -> list[Path]:
    """Every directory that ships a `stacks.json`, in either layout. Duplicates are collapsed later."""
    own = start.resolve().parents[1]          # <plugin>/scripts/x.py -> <plugin>, or <plugin>/<ver>
    found: set[Path] = set()

    def take(directory: Path) -> None:
        if (directory / MANIFEST).is_file():
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
        if not plugin:
            problems.append(f"{path}: names no `plugin`")
            continue
        data["_path"] = str(path)
        version = version_tuple(data.get("version"))
        if plugin not in best or best[plugin][0] < version:
            best[plugin] = (version, data)
    return [data for _, data in sorted(best.values(), key=lambda v: v[1]["plugin"])], problems


def package_dependencies(project: Path) -> set[str] | None:
    """The names in package.json's dependencies and devDependencies; None when there is no readable package.json."""
    try:
        data = json.loads((project / "package.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    names: set[str] = set()
    for key in ("dependencies", "devDependencies"):
        section = data.get(key) if isinstance(data, dict) else None
        if isinstance(section, dict):
            names.update(section)
    return names


def holds(marker: object, project: Path, deps: set[str] | None) -> bool:
    """Whether one marker holds. Raises ValueError for a marker this script cannot judge."""
    if not isinstance(marker, dict) or len(marker) != 1 or next(iter(marker)) not in KINDS:
        raise ValueError(f"unknown marker {marker!r} (kinds: {', '.join(KINDS)})")
    kind, value = next(iter(marker.items()))
    if kind == "file":
        return (project / value).is_file()
    if kind == "dir":
        return (project / value).is_dir()
    return deps is not None and value in deps


def detect(project: Path, manifests: list[dict]) -> tuple[list[dict], list[str]]:
    """The stacks the project matches, and the problems that stopped a stack being judged."""
    deps = package_dependencies(project)
    matched: list[dict] = []
    problems: list[str] = []
    for manifest in manifests:
        for stack in manifest.get("stacks") or []:
            label = f"{manifest['_path']}: stack {stack.get('id')!r}"
            all_of, any_of = stack.get("all") or [], stack.get("any") or []
            if not all_of and not any_of:
                problems.append(f"{label} declares no markers, so it would match every project")
                continue
            try:
                if all(holds(m, project, deps) for m in all_of) and (not any_of or any(holds(m, project, deps) for m in any_of)):
                    matched.append({"id": stack.get("id"), "name": stack.get("name", stack.get("id")), "plugin": manifest["plugin"]})
            except ValueError as exc:
                problems.append(f"{label}: {exc}")
    return matched, problems


def run(project: Path, dirs: list[Path]) -> tuple[int, dict]:
    manifests, problems = load_manifests(dirs)
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
    """A fixture per stack, a combined one, an empty project, and the ways a manifest can be wrong."""
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def manifest(name: str, data: object) -> Path:
            d = root / "plugins" / name
            d.mkdir(parents=True, exist_ok=True)
            (d / MANIFEST).write_text(data if isinstance(data, str) else json.dumps(data), encoding="utf-8")
            return d

        def project(name: str, files: dict[str, str] = {}, dirs: tuple[str, ...] = ()) -> Path:  # noqa: B006
            p = root / "projects" / name
            p.mkdir(parents=True)
            for rel, body in files.items():
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

        rails_app = project("rails-app", {"Gemfile": "", "config/application.rb": ""})
        if ids(rails_app) != (0, ["rails"]):
            failures.append(f"a Rails project is Rails: {ids(rails_app)}")
        half_rails = project("half-rails", {"Gemfile": ""})
        if ids(half_rails) != (1, []):
            failures.append(f"every `all` marker must hold (a Gemfile alone is not Rails): {ids(half_rails)}")
        next_app = project("next-app", {"package.json": json.dumps({"dependencies": {"next": "15.0.0", "react": "19"}})})
        if ids(next_app) != (0, ["nextjs"]):
            failures.append(f"a next dependency is Next.js: {ids(next_app)}")
        dev_next = project("dev-next", {"package.json": json.dumps({"devDependencies": {"next": "15"}})})
        if ids(dev_next) != (0, ["nextjs"]):
            failures.append(f"a next devDependency is Next.js too: {ids(dev_next)}")
        combined = project("combined", {"package.json": json.dumps({"dependencies": {"next": "15"}}),
                                        "supabase/config.toml": ""}, dirs=(".vercel",))
        if ids(combined) != (0, ["nextjs", "supabase", "vercel"]):
            failures.append(f"a combined project reports every stack it matches: {ids(combined)}")
        vercel_json = project("vercel-json", {"vercel.json": "{}"})
        if ids(vercel_json) != (0, ["vercel"]):
            failures.append(f"any one of an `any` list is enough: {ids(vercel_json)}")
        empty = project("empty")
        if ids(empty) != (1, []):
            failures.append(f"an empty project matches nothing and says so: {ids(empty)}")
        bad_pkg = project("bad-package", {"package.json": "{not json"})
        if ids(bad_pkg) != (1, []):
            failures.append(f"an unreadable package.json is no dependency, not a crash: {ids(bad_pkg)}")

        # ADDING A STACK IS A MANIFEST: a stack no plugin ships is detected the moment its manifest exists.
        go = manifest("go-stack", {"plugin": "go-stack", "stacks": [{"id": "go", "name": "Go", "all": [{"file": "go.mod"}]}]})
        go_app = project("go-app", {"go.mod": "module x"})
        if ids(go_app, dirs + [go]) != (0, ["go"]):
            failures.append(f"a new stack plugin's manifest is enough to detect it: {ids(go_app, dirs + [go])}")

        unknown = manifest("odd-stack", {"plugin": "odd-stack", "stacks": [{"id": "odd", "all": [{"glob": "*.odd"}]}]})
        if run(empty, dirs + [unknown])[0] != 2:
            failures.append("an unknown marker kind is a problem, never a silent no-match")
        markerless = manifest("blank-stack", {"plugin": "blank-stack", "stacks": [{"id": "blank"}]})
        if run(empty, dirs + [markerless])[0] != 2:
            failures.append("a stack with no markers is a problem: it would match every project")
        broken = manifest("broken-stack", "{nope")
        if run(rails_app, dirs + [broken])[0] != 2:
            failures.append("an unreadable manifest is a problem, not a skipped plugin")
        nameless = manifest("nameless-stack", {"stacks": []})
        if run(rails_app, dirs + [nameless])[0] != 2:
            failures.append("a manifest that names no plugin is a problem")

        # TWO VERSIONS OF ONE PLUGIN COLLAPSE TO THE HIGHER, by the manifest's own version.
        old = root / "cache" / "rails-stack" / "1.2.0"
        new = root / "cache" / "rails-stack" / "1.10.0"
        for d, marker in ((old, "Gemfile.lock"), (new, "Gemfile")):
            d.mkdir(parents=True)
            (d / MANIFEST).write_text(json.dumps({"plugin": "rails-stack", "version": d.name,
                                                  "stacks": [{"id": "rails", "all": [{"file": marker}]}]}), encoding="utf-8")
        loaded, _ = load_manifests([old, new])
        if len(loaded) != 1 or loaded[0]["version"] != "1.10.0":
            failures.append(f"two versions of a plugin collapse to the higher one (1.10.0 over 1.2.0): {[m.get('version') for m in loaded]}")

        # DISCOVERY, in the checkout shape: a sibling plugin and the repo root are both found from rails-flow's scripts dir.
        repo = root / "repo"
        (repo / "plugins" / "rails-flow" / "scripts").mkdir(parents=True)
        (repo / "plugins" / "nextjs-stack").mkdir(parents=True)
        (repo / MANIFEST).write_text(json.dumps({"plugin": "rails-stack", "stacks": []}), encoding="utf-8")
        (repo / "plugins" / "nextjs-stack" / MANIFEST).write_text(json.dumps({"plugin": "nextjs-stack", "stacks": []}), encoding="utf-8")
        seen = {p.name for p in manifest_dirs(repo / "plugins" / "rails-flow" / "scripts" / "detect_stack.py")}
        if seen != {"repo", "nextjs-stack"}:
            failures.append(f"discovery finds the repo root (rails-stack) and a sibling plugin: {sorted(seen)}")

        # AND IN THE CACHE SHAPE: <plugin>/<version>/ under one marketplace directory.
        cache = root / "installed" / "claude-skills"
        (cache / "rails-flow" / "1.64.0" / "scripts").mkdir(parents=True)
        (cache / "rails-stack" / "1.76.0").mkdir(parents=True)
        (cache / "rails-stack" / "1.76.0" / MANIFEST).write_text(json.dumps({"plugin": "rails-stack", "stacks": []}), encoding="utf-8")
        seen = [p.parent.name for p in manifest_dirs(cache / "rails-flow" / "1.64.0" / "scripts" / "detect_stack.py")]
        if seen != ["rails-stack"]:
            failures.append(f"discovery finds a stack plugin in the installed cache: {seen}")

    for f in failures:
        print(f"FAIL {f}")
    if failures:
        return 1
    print("detect_stack selftest: 15 cases pass")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?", default=".", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    code, report = run(args.project.resolve(), manifest_dirs(Path(__file__)))
    print(json.dumps(report, indent=2) if args.json else render(code, report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
