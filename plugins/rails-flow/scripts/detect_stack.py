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

THE DESCRIPTOR (#2181, plan step 2 of #2162). Each stack may carry a `descriptor`: how that stack tests,
lints, boots, deploys and draws its UI, and which agent plays each role. `--descriptor` prints the merged
descriptor of the stacks the project matches, so a flow asks the stack instead of naming Rails. Stacks
from ONE plugin merge (Next.js + Supabase + Vercel is three stacks in one plugin); a key declared by TWO
plugins, or one leaf given two values, is a conflict reported with both sources, never a silent pick. Every
key is from `DESCRIPTOR_SCHEMA`, with its declared shape: an unknown key or a wrong type is a problem
(`descriptor-key-undeclared`), so a flow can never read a key nobody declared.

Exit 0 one or more stacks detected · 1 none detected · 2 a manifest could not be read or judged.

Run:  python3 detect_stack.py [project-dir] [--json]
      python3 detect_stack.py [project-dir] --descriptor
      python3 detect_stack.py --check          (every discovered manifest is valid, whatever the project)
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


STR, INT, STRS = "str", "int", "list[str]"
# EVERY KEY A FLOW MAY READ, and its shape (#2181). A dict is a block whose keys are the only ones allowed; `{"*": STR}` is a
# block of free names (roles, scripts) each holding a string. Adding a key a flow needs is an edit HERE, reviewed once,
# never a key a manifest invents.
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


def shape_problems(value: object, shape: object, where: str) -> list[str]:
    """Why `value` does not have `shape`; empty when it does."""
    if shape == STR:
        return [] if isinstance(value, str) and value else [f"{where} must be a non-empty string"]
    if shape == INT:
        return [] if isinstance(value, int) and not isinstance(value, bool) else [f"{where} must be a whole number"]
    if shape == STRS:
        ok = isinstance(value, list) and value and all(isinstance(v, str) and v for v in value)
        return [] if ok else [f"{where} must be a non-empty list of strings"]
    if isinstance(shape, list):
        if not isinstance(value, list) or not value:
            return [f"{where} must be a non-empty list"]
        return [p for i, item in enumerate(value) for p in shape_problems(item, shape[0], f"{where}[{i}]")]
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


def descriptor_problems(manifest: dict) -> list[str]:
    """Every descriptor in a manifest checked against `DESCRIPTOR_SCHEMA`."""
    found = []
    for stack in manifest.get("stacks") or []:
        if "descriptor" in stack:
            found.extend(shape_problems(stack["descriptor"], DESCRIPTOR_SCHEMA, f"{manifest['_path']}: stack {stack.get('id')!r} descriptor"))
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
        stack = next(s for s in manifest["stacks"] if s.get("id") == found["id"])
        label = f"{found['plugin']}:{found['id']}"
        for key, value in (stack.get("descriptor") or {}).items():
            if key in owner and owner[key] != found["plugin"]:
                conflicts.append(f"descriptor {key} is declared by two plugins: {owner[key]} and {found['plugin']}")
                continue
            owner[key] = found["plugin"]
            merge(merged, {key: value}, label, "")
            sources.setdefault(key, set()).add(label)
    return merged, {k: sorted(v) for k, v in sources.items()}, conflicts


def run(project: Path, dirs: list[Path]) -> tuple[int, dict]:
    manifests, problems = load_manifests(dirs)
    for manifest in manifests:
        problems += descriptor_problems(manifest)
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

    # THE DESCRIPTOR (#2181). A fixture stack no Rails value fits, a three-stack merge, and every way a descriptor can be wrong.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def plug(name: str, stacks: list) -> Path:
            d = root / "plugins" / name
            d.mkdir(parents=True, exist_ok=True)
            (d / MANIFEST).write_text(json.dumps({"plugin": name, "stacks": stacks}), encoding="utf-8")
            return d

        def proj(name: str, files: dict) -> Path:
            p = root / "projects" / name
            for rel, body in files.items():
                (p / rel).parent.mkdir(parents=True, exist_ok=True)
                (p / rel).write_text(body, encoding="utf-8")
            p.mkdir(parents=True, exist_ok=True)
            return p

        go = plug("go-stack", [{"id": "go", "name": "Go", "all": [{"file": "go.mod"}],
                                "descriptor": {"tests": {"command": ["go", "test", "./..."], "glob": "**/*_test.go"},
                                               "boot": {"command": "go run .", "port": 8080, "health": "/healthz"}}}])
        go_app = proj("go-app", {"go.mod": "module x"})
        code, report = run(go_app, [go])
        if code != 0 or report["descriptor"].get("tests", {}).get("command") != ["go", "test", "./..."] or report["descriptor"]["boot"]["port"] != 8080:
            failures.append(f"a go stack's descriptor is go's own, not Rails': {code} {report['descriptor']}")

        nextjs = plug("nextjs-stack", [
            {"id": "nextjs", "all": [{"package_dependency": "next"}],
             "descriptor": {"tests": {"command": ["npx", "vitest", "run"]}, "layout": {"source": ["app/**/*.tsx"]}}},
            {"id": "supabase", "all": [{"file": "supabase/config.toml"}], "descriptor": {"layout": {"migrations": "supabase/migrations/"}}},
            {"id": "vercel", "any": [{"file": "vercel.json"}], "descriptor": {"deploy": {"target": "vercel"}}}])
        trio = proj("trio", {"package.json": json.dumps({"dependencies": {"next": "15"}}), "supabase/config.toml": "", "vercel.json": "{}"})
        code, report = run(trio, [nextjs])
        want = {"tests": {"command": ["npx", "vitest", "run"]}, "layout": {"source": ["app/**/*.tsx"], "migrations": "supabase/migrations/"},
                "deploy": {"target": "vercel"}}
        if code != 0 or report["descriptor"] != want or report["descriptor_sources"].get("layout") != ["nextjs-stack:nextjs", "nextjs-stack:supabase"]:
            failures.append(f"three stacks from one plugin merge into one descriptor, each key naming its source: {code} {report['descriptor']} {report['descriptor_sources']}")

        rival = plug("rival-stack", [{"id": "rival", "all": [{"file": "supabase/config.toml"}], "descriptor": {"tests": {"glob": "*.spec.ts"}}}])
        code, report = run(trio, [nextjs, rival])
        if code != 2 or not any("declared by two plugins" in p for p in report["problems"]):
            failures.append(f"a descriptor key declared by two plugins is a conflict, never a silent pick: {code} {report['problems']}")

        clash = plug("clash-stack", [{"id": "a", "all": [{"file": "a"}], "descriptor": {"deploy": {"target": "kamal"}}},
                                     {"id": "b", "all": [{"file": "b"}], "descriptor": {"deploy": {"target": "vercel"}}}])
        code, report = run(proj("ab", {"a": "", "b": ""}), [clash])
        if code != 2 or not any("deploy.target" in p for p in report["problems"]):
            failures.append(f"one plugin giving a leaf two values is a conflict too: {code} {report['problems']}")

        for label, descriptor, needle in (
            ("an undeclared descriptor key is a problem", {"testz": {"command": ["x"]}}, "testz is not a declared descriptor key"),
            ("an undeclared key inside a block is a problem", {"tests": {"cmd": ["x"]}}, "tests.cmd is not a declared descriptor key"),
            ("a descriptor value of the wrong type is a problem", {"boot": {"port": "3000"}}, "boot.port must be a whole number"),
        ):
            odd = plug("odd-" + str(abs(hash(label)) % 10000), [{"id": "odd", "all": [{"file": "go.mod"}], "descriptor": descriptor}])
            code, report = run(go_app, [odd])
            if code != 2 or not any(needle in p for p in report["problems"]):
                failures.append(f"{label}: {code} {report['problems']}")

        code, report = run(proj("nothing", {}), [go, nextjs])
        if code != 1 or report["descriptor"] != {}:
            failures.append(f"with no stack detected the descriptor is empty: {code} {report['descriptor']}")

    for f in failures:
        print(f"FAIL {f}")
    if failures:
        return 1
    print("detect_stack selftest: 23 cases pass")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("project", nargs="?", default=".", type=Path)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--descriptor", action="store_true", help="print the detected stacks' merged descriptor as JSON")
    ap.add_argument("--check", action="store_true", help="validate every discovered manifest, whatever the project")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    dirs = manifest_dirs(Path(__file__))
    if args.check:
        manifests, problems = load_manifests(dirs)
        for manifest in manifests:
            problems += descriptor_problems(manifest)
            for stack in manifest.get("stacks") or []:
                try:
                    for marker in (stack.get("all") or []) + (stack.get("any") or []):
                        holds(marker, Path("/nonexistent"), None)
                except ValueError as exc:
                    problems.append(f"{manifest['_path']}: stack {stack.get('id')!r}: {exc}")
                if not (stack.get("all") or stack.get("any")):
                    problems.append(f"{manifest['_path']}: stack {stack.get('id')!r} declares no markers")
        print("\n".join(problems) if problems else f"{len(manifests)} stack manifest(s) valid")
        return 2 if problems else 0
    code, report = run(args.project.resolve(), dirs)
    if args.descriptor:
        print(json.dumps({"stacks": [s["id"] for s in report["stacks"]], "descriptor": report["descriptor"],
                          "sources": report["descriptor_sources"], "problems": report["problems"]}, indent=2))
    else:
        print(json.dumps(report, indent=2) if args.json else render(code, report))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
