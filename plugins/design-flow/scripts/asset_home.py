#!/usr/bin/env python3
"""Where design-flow keeps its asset library, and what to do about the old place (#1779).

The library moved from `docs/assets/` to `docs/design/assets/`. The old place failed rails-flow's own docs-layout gate
(`rails-flow/docs-layout`: `assets/ is not a layout directory`), so a project that followed design-flow's docs failed
`bin/doctrine`; the layout already homes "images and brand files under `assets/`" in `design/`.

A MOVED FILE MUST NEVER READ AS AN EMPTY LIBRARY. A script that looked only at the new place would find no manifest in a project
that still has the old one, and treat the library as empty, which hides present data. So every design-flow script that reads the
library calls `refusal(root)` first and stops, loudly, naming the one command that moves it:

    python3 asset_home.py --migrate        move docs/assets/ to docs/design/assets/ and rewrite the paths the JSON and Markdown files carry

A LEAF: it imports nothing from design-flow, so `asset_plan.py`, which is deliberately standalone, can use it.

Run:  python3 asset_home.py --selftest
"""
from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

HOME = Path("docs/design/assets")
LEGACY = Path("docs/assets")
# What marks the old place as design-flow's: the indexes it writes and the two folders it scaffolds.
MARKERS = ("manifest.json", "plan.json", "plan.md", "assets-library", "prompts-library")
RENAMED = ("manifest.json", "plan.json", "plan.md", "prompts.json", "prompts.md")


def legacy_found(root: Path) -> list[str]:
    return [name for name in MARKERS if (root / LEGACY / name).exists()]


def refusal(root: Path) -> str | None:
    """The message a script prints and stops with, or None when nothing sits at the old place."""
    found = legacy_found(root)
    if not found:
        return None
    if (root / HOME).exists():
        return (f"design-flow's asset library lives at {HOME}/ now (#1779), and {LEGACY}/ still holds {', '.join(found)}. "
                f"Both exist, so nothing is moved for you: merge {LEGACY}/ into {HOME}/, delete {LEGACY}/, and re-run. "
                f"Stopping rather than reading a library that may be half of two.")
    return (f"design-flow's asset library moved from {LEGACY}/ to {HOME}/ (#1779), and this project still has it at the old place "
            f"({', '.join(found)}). Stopping rather than reading an empty library. Move it with:\n"
            f"  python3 \"${{CLAUDE_PLUGIN_ROOT}}/scripts/asset_home.py\" --migrate\n"
            f"then stage the move, and re-render the plan and prompts views (`asset_plan.py --render`, `prompt_library.py --render`).")


def migrate(root: Path) -> tuple[int, str]:
    """Move the library and rewrite the old path wherever the moved JSON and Markdown files carry it."""
    found = legacy_found(root)
    if not found:
        return 0, f"nothing at {LEGACY}/ to move."
    if (root / HOME).exists():
        return 1, refusal(root) or ""
    (root / HOME).parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(root / LEGACY), str(root / HOME))
    rewritten = []
    for path in sorted((root / HOME).rglob("*")):
        if path.is_file() and path.suffix in (".json", ".md") and path.name in RENAMED:
            text = path.read_text(encoding="utf-8")
            new = text.replace(f"{LEGACY.as_posix()}/", f"{HOME.as_posix()}/")
            if new != text:
                path.write_text(new, encoding="utf-8")
                rewritten.append(path.relative_to(root).as_posix())
    note = f"moved {LEGACY}/ to {HOME}/"
    if rewritten:
        note += f"; rewrote the old path in {', '.join(rewritten)}"
    return 0, (note + ". Next: stage the move, re-render the plan and prompts views (`asset_plan.py --render`, "
               "`prompt_library.py --render`), and grep the project for any other file that names docs/assets/.")


def selftest() -> int:
    failures: list[str] = []
    ran = [0]

    def check(label: str, ok: bool) -> None:
        ran[0] += 1
        if not ok:
            failures.append(label)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        check("a project with no library at all is silent", refusal(root) is None)
        (root / "docs/assets/assets-library").mkdir(parents=True)
        (root / "docs/assets/manifest.json").write_text('{"assets": [{"file": "docs/assets/hero.svg"}]}\n', encoding="utf-8")
        (root / "docs/assets/plan.md").write_text("see docs/assets/plan.json\n", encoding="utf-8")
        msg = refusal(root) or ""
        check("a library at the old place stops the script", "moved from docs/assets/ to docs/design/assets/" in msg)
        check("...and names the one command that moves it", "asset_home.py" in msg and "--migrate" in msg)
        check("...and says it is not reading an empty library", "empty library" in msg)

        code, said = migrate(root)
        check("--migrate succeeds", code == 0)
        check("...moving the library", (root / "docs/design/assets/manifest.json").is_file() and not (root / "docs/assets").exists())
        check("...keeping its folders", (root / "docs/design/assets/assets-library").is_dir())
        moved = (root / "docs/design/assets/manifest.json").read_text(encoding="utf-8")
        check("...rewriting the old path inside the manifest", "docs/design/assets/hero.svg" in moved and '"docs/assets/' not in moved)
        check("...and inside the plan view", "docs/design/assets/plan.json" in (root / "docs/design/assets/plan.md").read_text(encoding="utf-8"))
        check("...and says what to do next", "re-render" in said)
        check("after it, the script is no longer stopped", refusal(root) is None)
        code, said = migrate(root)
        check("--migrate again is a no-op, not an error", code == 0 and "nothing" in said)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "docs/assets").mkdir(parents=True)
        (root / "docs/assets/plan.json").write_text("{}\n", encoding="utf-8")
        (root / "docs/design/assets").mkdir(parents=True)
        msg = refusal(root) or ""
        check("both places existing is refused, never merged silently", "Both exist" in msg)
        code, _ = migrate(root)
        check("--migrate refuses to merge two libraries", code == 1 and (root / "docs/assets/plan.json").is_file())

    for label in failures:
        print(f"FAIL: {label}")
    print(f"asset_home selftest: {ran[0]} checks passed" if not failures else f"asset_home selftest: {len(failures)} of {ran[0]} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--migrate", action="store_true", help="move docs/assets/ to docs/design/assets/ in the current directory")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.migrate:
        code, said = migrate(Path.cwd())
        print(said)
        return code
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
