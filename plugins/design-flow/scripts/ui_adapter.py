#!/usr/bin/env python3
"""Which UI adapter a project uses, and where it lives. #2185 (design-flow commands dispatch on `descriptor.ui`).

WHAT IS TRUE TODAY. design-flow's core is stack-neutral; what reads or writes one stack's UI lives in
`ui/<implementation>/` (#2178), and a stack plugin's descriptor names its own with `ui.implementation`.
A command such as `/design-flow:port` must therefore ask the PROJECT's stack which adapter to run and
never assume one. The stack is detected by `detect_stack.py` BESIDE THIS FILE: a byte-identical mirror of
rails-flow's (and pipeline's), held equal by the `detect-stack-drift` rule, so design-flow works with no
other plugin installed and there is no "detector missing" path.

    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ui_adapter.py" [project]               # detect, then resolve
    python3 "${CLAUDE_PLUGIN_ROOT}/scripts/ui_adapter.py" --implementation <id>   # no detector: name the adapter

Prints JSON: `{implementation, dir, agents: {porter, composer}, checks: [...], stack: <id or null>,
tokens_file}`. `dir` is the adapter directory; a command reads `<dir>/<command>.md` for the stack-specific
steps.

EXIT 0 resolved. EXIT 2 it cannot say, with the reason on stderr and nothing on stdout: the detector could not judge the project, the detected stacks declare no `ui.implementation`, two
stacks declare different ones, or the named implementation has no adapter in this plugin (a stack whose adapter has not shipped
yet, #2171). There is no default adapter: "no answer" is never a stack.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PLUGIN = HERE.parent
DETECTOR = HERE / "detect_stack.py"          # the mirrored copy beside this file


def detect(project: Path, detector: Path = DETECTOR) -> dict:
    """The detector's `--descriptor` JSON; raises `Unresolved` for a verdict that is not a clean answer."""
    run = subprocess.run([sys.executable, str(detector), str(project), "--descriptor"], capture_output=True, text=True, check=False)
    try:
        out = json.loads(run.stdout)
    except ValueError:
        raise Unresolved(f"the stack detector printed no JSON (exit {run.returncode}): {(run.stderr or run.stdout).strip()[:300]}")
    if run.returncode == 2 or out.get("problems"):
        raise Unresolved("the stack detector could not judge this project: " + "; ".join(map(str, out.get("problems") or ["exit 2"])))
    if run.returncode == 1 or not out.get("stacks"):
        raise Unresolved("no installed stack plugin recognises this project, so no UI adapter can be chosen; "
                         "name one with --implementation <id>")
    return out


class Unresolved(Exception):
    """Cannot say which adapter: reported, never defaulted."""


def implementations(detected: dict) -> set[str]:
    """The distinct `ui.implementation` values the detected stacks declare (merged descriptor first, per-stack as a cross-check)."""
    found: set[str] = set()
    ui = (detected.get("descriptor") or {}).get("ui")
    if isinstance(ui, dict) and ui.get("implementation"):
        found.add(ui["implementation"])
    return found


def resolve(implementation: str, stack: str | None = None, tokens_file: str | None = None, plugin: Path = PLUGIN) -> dict:
    adapter_dir = plugin / "ui" / implementation
    spec_file = adapter_dir / "adapter.json"
    if not spec_file.is_file():
        have = sorted(p.name for p in (plugin / "ui").glob("*/adapter.json") for p in [p.parent]) if (plugin / "ui").is_dir() else []
        raise Unresolved(f"ui.implementation {implementation!r} has no adapter in design-flow ({spec_file} does not exist); "
                         f"adapters shipped: {', '.join(have) or 'none'}")
    try:
        spec = json.loads(spec_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unresolved(f"{spec_file} is unreadable: {exc}")
    return {"implementation": implementation, "dir": str(adapter_dir), "agents": spec.get("agents", {}),
            "checks": spec.get("checks", []), "stack": stack, "tokens_file": tokens_file}


def resolve_project(project: Path) -> dict:
    """Detect the project's stack and resolve its adapter: what `main` does, for a caller that wants the dict."""
    detected = detect(project)
    impls = implementations(detected)
    if not impls:
        raise Unresolved("the detected stack(s) "
                         f"{[s.get('id') for s in detected['stacks']]} declare no ui.implementation, so there is no UI adapter to run")
    if len(impls) > 1:
        raise Unresolved(f"the detected stacks declare different ui.implementation values {sorted(impls)}; pass --implementation <id>")
    ui = detected["descriptor"]["ui"]
    return resolve(next(iter(impls)), stack=",".join(s.get("id", "") for s in detected["stacks"]), tokens_file=ui.get("tokens_file"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project", nargs="?", default=None, help="the project directory (default: $CLAUDE_PROJECT_DIR, else the working directory)")
    ap.add_argument("--implementation", help="skip detection and resolve this adapter id")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        if args.implementation:
            result = resolve(args.implementation)
        else:
            project = Path(args.project or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
            result = resolve_project(project)
    except Unresolved as exc:
        print(f"ui_adapter: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2))
    return 0


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal checks
        checks += 1
        if not cond:
            failures.append(label)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plugin = root / "plugins" / "design-flow"
        (plugin / "ui" / "demo-ui").mkdir(parents=True)
        (plugin / "ui" / "demo-ui" / "adapter.json").write_text(json.dumps(
            {"id": "demo-ui", "agents": {"porter": "demo-porter", "composer": "demo-composer"}, "checks": ["token-drift"]}))
        got = resolve("demo-ui", stack="demo", tokens_file="a.css", plugin=plugin)
        check("a declared implementation resolves to its adapter dir", got["dir"].endswith("ui/demo-ui"))
        check("...with its agents and checks", got["agents"]["porter"] == "demo-porter" and got["checks"] == ["token-drift"])
        for bad, why in (("nextjs-tsx", "an implementation with no adapter is refused, not defaulted to another stack"),
                         ("../etc", "a path-shaped id cannot escape ui/")):
            try:
                resolve(bad, plugin=plugin)
                check(why, False)
            except Unresolved:
                check(why, True)
        (plugin / "ui" / "broken").mkdir()
        (plugin / "ui" / "broken" / "adapter.json").write_text("{not json")
        try:
            resolve("broken", plugin=plugin)
            check("an unreadable adapter.json is refused", False)
        except Unresolved:
            check("an unreadable adapter.json is refused", True)

        check("no ui in the descriptor means no implementation", implementations({"descriptor": {}}) == set())
        check("a ui block names its implementation", implementations({"descriptor": {"ui": {"implementation": "x"}}}) == {"x"})

        # the detector's verdicts: only a clean answer resolves
        fake = root / "fake_detector.py"
        for code, payload, label in ((1, {"stacks": [], "problems": []}, "exit 1 (no stack) is refused"),
                                     (2, {"stacks": [], "problems": ["manifest unreadable"]}, "exit 2 (cannot judge) is refused"),
                                     (0, {"stacks": [{"id": "demo"}], "problems": ["conflict"], "descriptor": {}}, "problems beside stacks are refused")):
            fake.write_text(f"import sys, json\nprint(json.dumps({payload!r}))\nsys.exit({code})\n")
            try:
                detect(root, fake)
                check(label, False)
            except Unresolved:
                check(label, True)
        fake.write_text("print('not json')\n")
        try:
            detect(root, fake)
            check("a detector that prints no JSON is refused", False)
        except Unresolved:
            check("a detector that prints no JSON is refused", True)
        fake.write_text('import json\nprint(json.dumps({"stacks": [{"id": "demo"}], "problems": [], "descriptor": {"ui": {"implementation": "demo-ui"}}}))\n')
        check("a clean answer is returned", detect(root, fake)["stacks"][0]["id"] == "demo")

    # every adapter this plugin ships resolves, and names its porter and composer
    shipped = sorted(p.parent.name for p in (PLUGIN / "ui").glob("*/adapter.json"))
    check("at least one adapter ships", bool(shipped))
    for name in shipped:
        got = resolve(name)
        check(f"the shipped adapter {name} names a porter and a composer", bool(got["agents"].get("porter") and got["agents"].get("composer")))
    if failures:
        print("ui_adapter selftest FAILED:\n  - " + "\n  - ".join(failures))
        return 1
    print(f"ui_adapter selftest: {checks} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
