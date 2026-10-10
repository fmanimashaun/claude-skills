#!/usr/bin/env python3
"""Where design-flow keeps its files under docs/, and what to do about the old places (#1779).

design-flow's files moved under `docs/design/`, because the old places failed rails-flow's own docs-layout gate
(`rails-flow/docs-layout`: `assets/ is not a layout directory`, `design-system/ is not a layout directory`):

    docs/assets/                        ->  docs/design/assets/          the library: manifest, plan, assets-library/, prompts-library/
    docs/design-system/prompts/         ->  docs/design/prompts/         the surface prompts `/design-flow:canvas` writes and `/design-flow:port` reads
    docs/design-system/brand-assets/    ->  docs/design/assets/brand/    the brand logos `/design-flow:setup` reads (the layout's own rename)

A MOVED FILE MUST NEVER READ AS AN ABSENT ONE. A script that looked only at the new place would read a project's existing library as EMPTY, find no
prompt for a port, or scaffold placeholder logos over the real ones, and each of those hides present data. So every design-flow script AND command
that reads one of these asks first (`refusal(root)`, or `asset_home.py --check` from a command) and stops, loudly, naming the one command that moves them:

    python3 asset_home.py --migrate        move all three and rewrite the old paths the moved JSON and Markdown files carry

ANY CONTENT AT AN OLD PLACE COUNTS, not only the files design-flow is known to write: a project that kept an extra file there still has a library to move.

A LEAF: it imports nothing from design-flow, so `asset_plan.py`, which is deliberately standalone, can use it.

Run:  python3 asset_home.py --selftest | --check | --migrate
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

HOME = Path("docs/design/assets")
LEGACY = Path("docs/assets")
BRAND = Path("docs/design/assets/brand")
# (old, new), in the order they must move: the library first, because the brand logos move INTO it.
MOVES = (
    (LEGACY, HOME),
    (Path("docs/design-system/prompts"), Path("docs/design/prompts")),
    (Path("docs/design-system/brand-assets"), BRAND),
)
# The files whose content names these paths, and so are rewritten after the move. Anchored: `mydocs/assets/x` is not a path of ours.
RENAMED = ("manifest.json", "plan.json", "plan.md", "prompts.json", "prompts.md")
REWRITES = tuple((re.compile(r"(?<![\w/.-])" + re.escape(old.as_posix() + "/")), new.as_posix() + "/") for old, new in MOVES)


def _has_content(path: Path) -> bool:
    """A folder with anything in it, or ANYTHING that is not a folder (a file named docs/assets is still something at the old place)."""
    if path.is_dir():
        return any(path.iterdir())
    return path.exists() or path.is_symlink()


def legacy_found(root: Path) -> list[tuple[Path, Path]]:
    """The (old, new) pairs whose old place holds anything at all."""
    return [(old, new) for old, new in MOVES if _has_content(root / old)]


def refusal(root: Path) -> str | None:
    """The message a script prints and stops with, or None when nothing sits at an old place."""
    pairs = legacy_found(root)
    if not pairs:
        return None
    lines = []
    for old, new in pairs:
        note = ""
        if not (root / old).is_dir():
            note = "   (a FILE, not a folder: move it by hand)"
        elif _has_content(root / new):
            note = "   (BLOCKED: both exist, so merge them by hand)"
        elif new == BRAND and _has_content(root / LEGACY / BRAND.name):
            note = f"   (COLLIDES: {LEGACY}/ holds its own {BRAND.name}/, which would sit where these logos go; merge by hand)"
        lines.append(f"  {old}/ -> {new}/" + note)
    return ("design-flow's files moved under docs/design/ (#1779), and this project still has some at the old place:\n" + "\n".join(lines) + "\n"
            "Stopping rather than reading an empty library, finding no prompt, or scaffolding placeholder logos over the real ones. Move them with:\n"
            "  python3 \"${CLAUDE_PLUGIN_ROOT}/scripts/asset_home.py\" --migrate\n"
            "then stage the move, and re-render the plan and prompts views (`asset_plan.py --render`, `prompt_library.py --render`).")


def migrate(root: Path) -> tuple[int, str]:
    """Move what sits at the old places and rewrite the old paths in the moved files. Never merges: a place whose destination exists is left, and the exit code says so."""
    if not legacy_found(root):
        return 0, "nothing at an old place to move."
    moved, left, arrived = [], [], []
    for old, new in MOVES:
        src, dst = root / old, root / new
        if not _has_content(src):
            continue
        if not src.is_dir():
            left.append(f"{old} (a file, not a folder: move it by hand)")
            continue
        if _has_content(dst) or (dst.exists() and not dst.is_dir()):
            why = f"destination {new}/ exists"
            if new.parent in arrived:
                why += f": it arrived with the {new.parent}/ you just moved, which already held its own {new.name}/"
            left.append(f"{old}/ ({why})")
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.rmdir()                       # an empty directory: moving onto it would nest the source inside
        shutil.move(str(src), str(dst))
        moved.append(f"{old}/ to {new}/")
        arrived.append(new)
    parent = root / "docs/design-system"
    if parent.is_dir() and not any(parent.iterdir()):
        parent.rmdir()                         # the two moves emptied it
    rewritten = []
    for path in sorted((root / HOME).rglob("*")):
        if path.is_file() and path.name in RENAMED:
            text = path.read_text(encoding="utf-8")
            new_text = text
            for pattern, replacement in REWRITES:
                new_text = pattern.sub(replacement, new_text)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")
                rewritten.append(path.relative_to(root).as_posix())
    said = ("moved " + "; ".join(moved) if moved else "moved nothing")
    if rewritten:
        said += f"; rewrote the old paths in {', '.join(rewritten)}"
    if left:
        said += ". NOT moved, merge by hand: " + "; ".join(left)
    said += (". Next: stage the move, re-render the plan and prompts views (`asset_plan.py --render`, `prompt_library.py --render`), "
             "and grep the project for any other file that names the old paths.")
    return (1 if left else 0), said


def selftest() -> int:
    failures: list[str] = []
    ran = [0]

    def check(label: str, ok: bool) -> None:
        ran[0] += 1
        if not ok:
            failures.append(label)
            print(f"FAIL: {label}", flush=True)   # at once: a later step that crashes on the broken state must not hide which check died first

    def write(root: Path, rel: str, text: str = "x\n") -> None:
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        check("a project with no old place is silent", refusal(root) is None)
        (root / "docs/assets").mkdir(parents=True)
        check("an EMPTY old directory is not a library to move", refusal(root) is None)
        write(root, "docs/assets/hero.png")
        msg = refusal(root) or ""
        check("ANY content at docs/assets/ counts, not only the known files", "docs/assets/ -> docs/design/assets/" in msg)
        write(root, "docs/assets/manifest.json", '{"assets": [{"file": "docs/assets/hero.svg"}, {"file": "mydocs/assets/x.svg"}]}\n')
        write(root, "docs/assets/plan.md", "see docs/assets/plan.json and docs/design-system/brand-assets/01-logos/a.svg\n")
        (root / "docs/assets/assets-library").mkdir()
        check("a library at the old place stops the script", "moved under docs/design/" in msg)
        check("...naming the one command that moves it", "asset_home.py" in msg and "--migrate" in msg)
        check("...and saying why: not an empty library", "empty library" in msg)

        write(root, "docs/design-system/prompts/pricing.md", "the prompt\n")
        write(root, "docs/design-system/brand-assets/01-logos/logo.svg", "<svg/>\n")
        msg = refusal(root) or ""
        check("prompts at docs/design-system/prompts/ are refused too", "docs/design-system/prompts/ -> docs/design/prompts/" in msg)
        check("brand logos at docs/design-system/brand-assets/ are refused too", "docs/design-system/brand-assets/ -> docs/design/assets/brand/" in msg)
        check("...so /design-flow:setup cannot scaffold placeholders over the real logos", "placeholder logos" in msg)

        code, said = migrate(root)
        check("--migrate succeeds", code == 0)
        check("...moving the library", (root / "docs/design/assets/manifest.json").is_file() and not (root / "docs/assets").exists())
        check("...keeping its folders", (root / "docs/design/assets/assets-library").is_dir())
        check("...moving the prompts", (root / "docs/design/prompts/pricing.md").is_file() and not (root / "docs/design-system/prompts").exists())
        check("...moving the brand logos INTO the library", (root / "docs/design/assets/brand/01-logos/logo.svg").is_file())
        check("...removing the docs/design-system/ it emptied", not (root / "docs/design-system").exists())
        moved = (root / "docs/design/assets/manifest.json").read_text(encoding="utf-8")
        check("...rewriting the old path inside the manifest", "docs/design/assets/hero.svg" in moved and '"docs/assets/' not in moved)
        check("...but not a path that merely ENDS like ours (mydocs/assets/)", "mydocs/assets/x.svg" in moved)
        plan = (root / "docs/design/assets/plan.md").read_text(encoding="utf-8")
        check("...rewriting the plan view, brand path included", "docs/design/assets/plan.json" in plan and "docs/design/assets/brand/01-logos/a.svg" in plan)
        check("...and saying what to do next", "re-render" in said)
        check("after it, nothing stops the scripts", refusal(root) is None)
        code, said = migrate(root)
        check("--migrate again is a no-op, not an error", code == 0 and "nothing" in said)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write(root, "docs/assets/plan.json", "{}\n")
        write(root, "docs/design/assets/other.json", "{}\n")
        check("both places existing is refused, never merged silently", "BLOCKED" in (refusal(root) or ""))
        code, said = migrate(root)
        check("--migrate refuses to merge two libraries", code == 1 and (root / "docs/assets/plan.json").is_file() and "merge by hand" in said)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write(root, "docs/assets/brand/own.svg")
        write(root, "docs/design-system/brand-assets/01-logos/l.svg")
        check("a library holding its own brand/ is warned about BEFORE the move, naming the collision", "COLLIDES" in (refusal(root) or ""))
        code, said = migrate(root)
        check("...--migrate moves the library but not the logos, and exits 1", code == 1 and (root / "docs/design/assets/brand/own.svg").is_file())
        check("...leaving the logos where they were", (root / "docs/design-system/brand-assets/01-logos/l.svg").is_file())
        check("...and names the brand/ collision in the NOT moved text", "NOT moved" in said and "already held its own brand/" in said)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write(root, "docs/assets", "a file where the folder should be\n")
        msg = refusal(root) or ""
        check("a FILE at an old path counts as something there", "docs/assets/ -> docs/design/assets/" in msg and "a FILE" in msg)
        code, said = migrate(root)
        check("--migrate leaves a file at an old path for the owner, and exits 1", code == 1 and (root / "docs/assets").is_file() and "move it by hand" in said)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write(root, "docs/design-system/prompts/a.md")
        check("prompts alone at the old place are refused", "docs/design/prompts/" in (refusal(root) or ""))
        code, _ = migrate(root)
        check("--migrate moves prompts alone", code == 0 and (root / "docs/design/prompts/a.md").is_file())

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        write(root, "docs/design-system/brand-assets/01-logos/l.svg")
        write(root, "docs/design-system/other.md")
        code, _ = migrate(root)
        check("--migrate moves brand logos alone, creating the library folder", code == 0 and (root / "docs/design/assets/brand/01-logos/l.svg").is_file())
        check("...and leaves docs/design-system/ when it still holds something else", (root / "docs/design-system/other.md").is_file())

    print(f"asset_home selftest: {ran[0]} checks passed" if not failures else f"asset_home selftest: {len(failures)} of {ran[0]} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--check", action="store_true", help="exit 1, printing why, when the current directory still has an old place")
    parser.add_argument("--migrate", action="store_true", help="move the old places under docs/design/ in the current directory")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()
    if args.migrate:
        code, said = migrate(Path.cwd())
        print(said)
        return code
    if args.check:
        refused = refusal(Path.cwd())
        print(refused or "no old design-flow place in this project.")
        return 1 if refused else 0
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
