#!/usr/bin/env python3
"""check_exit3_rows.py -- every exit 3 a shipped check can give is proven, by its selftest, to mean "not applicable" (#1873).

`plugins/rails-flow/scripts/project_gates.py` grades a check's exit 3 as NOT APPLICABLE, which never
fails a run. So a 3 that means "could not look" passes silently; #1864, #1867 and #1872 each found
one by reading code. This gate makes the next one visible at authoring time.

For every script a `plugins/*/checks.json` names, it counts the EXIT-3 SITES (`return 3`, `exit(3)`)
in the script, and the N/A ROWS in its selftest (the script itself, plus a sibling
`<stem>_selftest.py` when there is one). A row is a line that asserts an exit of 3 -- `== 3`,
`!= 3`, or 3 passed as an expected exit (`, 3,`) -- whose statement (the line and the two either
side, only when the line carries no label of its own) says WHY: "n/a", "not applicable" / "not-applicable", or "skip". A `print(` line is output,
not a test, and never counts. A script with fewer rows than sites is a finding.

What it cannot see: whether a row exercises the site it is counted against. Counting is the floor;
each row's mutant (the script's own guard) is what proves the row reaches its site.

Exit: 0 every site has its row · 1 findings. Maintainer tooling; not shipped.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = re.compile(r"\breturn 3\b|\bexit\(3\)")
ROW = re.compile(r"[=!]=\s*3\b|,\s*3\s*,")
WHY = re.compile(r"n/a|not[ -]applicable|\bskip", re.I)
LABEL = re.compile(r"[\"'][^\"']*[A-Za-z]{2} [A-Za-z]{2}[^\"']*[\"']")   # prose: a word, a space, a word


def scripts(root: Path) -> list[Path]:
    """Every distinct `{plugin}/...py` a checks.json command names, in a stable order."""
    seen: list[Path] = []
    for manifest in sorted(root.glob("plugins/*/checks.json")):
        doc = json.loads(manifest.read_text(encoding="utf-8"))
        for check in doc["checks"] if isinstance(doc, dict) else doc:
            for tok in check.get("command", []):
                if tok.startswith("{plugin}/") and tok.endswith(".py"):
                    path = manifest.parent / tok[len("{plugin}/"):]
                    if path not in seen:
                        seen.append(path)
    return seen


def sites(text: str) -> int:
    return len(SITE.findall(text))


def rows(text: str) -> int:
    lines = text.splitlines()
    n = 0
    for i, line in enumerate(lines):
        if not ROW.search(line) or SITE.search(line) or "print(" in line:
            continue
        # A line that carries its own label must give the reason in it: a neighbouring row's words are not this
        # row's reason. Only a bare comparison (`code == 3)` under its label) reads one line either side.
        window = line if LABEL.search(line) else " ".join(lines[max(0, i - 1):i + 2])
        if WHY.search(window):
            n += 1
    return n


def findings(root: Path) -> list[str]:
    out = []
    for path in scripts(root):
        if not path.is_file():
            out.append(f"{path.relative_to(root)}: named by checks.json and not there")
            continue
        text = path.read_text(encoding="utf-8")
        need = sites(text)
        if not need:
            continue
        sibling = path.with_name(f"{path.stem}_selftest.py")
        have = rows(text) + (rows(sibling.read_text(encoding="utf-8")) if sibling.is_file() else 0)
        if have < need:
            out.append(f"{path.relative_to(root)}: {need} exit-3 site(s), {have} selftest row(s) asserting 3 with an n/a reason "
                       f"-- add a row per site, or exit 2 if the check could not look (#1873)")
    return out


def selftest() -> int:
    import tempfile
    failures: list[str] = []

    def tree(files: dict[str, str]) -> list[str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "plugins/p").mkdir(parents=True)
            (root / "plugins/p/checks.json").write_text(json.dumps({"checks": [
                {"id": "a", "command": ["python3", "{plugin}/scripts/a.py"]}]}), encoding="utf-8")
            for rel, body in files.items():
                (root / "plugins/p/scripts" / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / "plugins/p/scripts" / rel).write_text(body, encoding="utf-8")
            return findings(root)

    site = "def main():\n    if nothing:\n        return 3\n"
    for label, files, want in (
        ("a site with no row is a finding", {"a.py": site}, 1),
        ("a row asserting 3 with no reason is a finding", {"a.py": site + "check('it exits three', code == 3)\n"}, 1),
        ("a row asserting 3 with an n/a reason is clean", {"a.py": site + "check('no app is n/a', code == 3)\n"}, 0),
        ("a not-applicable row is clean", {"a.py": site + "check('no config is not-applicable', code == 3)\n"}, 0),
        ("a row whose reason is on the next line is clean", {"a.py": site + "if code != 3:\n    fail('no config is a skip')\n"}, 0),
        ("3 passed as the expected exit is a row", {"a.py": site + "row('no registry is n/a', '', gh, 3, 'none')\n"}, 0),
        ("two sites and one row is a finding", {"a.py": site + "    return 3\ncheck('n/a', code == 3)\n"}, 1),
        ("a print of the n/a verdict is output, not a row", {"a.py": site + "print('n/a' if code == 3 else 'ok')\n"}, 1),
        ("a return 3 on the row's own line is a site, not a row", {"a.py": "def main():\n    if code == 3: return 3  # n/a\n"}, 1),
        ("a neighbouring row's reason is not this row's", {"a.py": site + "row('it exits three', '', gh, 3, 'none')\nrow('gh missing grades as not applicable', '', gh, 2, 'x')\n"}, 1),
        ("an argv string is not a label, so the label above still counts", {"a.py": site + "check('off GitHub is n/a',\n      main(['--check', '--root', r]) == 3)\n"}, 0),
        ("a label on the line above a bare comparison is its reason", {"a.py": site + "expect('no config is n/a',\n       code == 3)\n"}, 0),
        ("a row in the sibling <stem>_selftest.py counts", {"a.py": site, "a_selftest.py": "check('stale is n/a', rc == 3, True)\n"}, 0),
        ("a script with no exit 3 needs no row", {"a.py": "def main():\n    return 2\n"}, 0),
        ("a 30 is not an exit 3", {"a.py": "def main():\n    return 30\n"}, 0),
        ("a named script that is not there is a finding", {}, 1),
    ):
        got = tree(files)
        if len(got) != want:
            failures.append(f"{label}: wanted {want} finding(s), got {got!r}")
    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_exit3_rows selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=str(ROOT), help="the repository root (default: this checkout)")
    ap.add_argument("--selftest", action="store_true", help="prove each rule fires and stays silent")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root).resolve()
    found = findings(root)
    for f in found:
        print(f"- {f}")
    print(f"check_exit3_rows: {len(scripts(root))} checks.json script(s); "
          + (f"{len(found)} with an unproven exit 3" if found else "every exit 3 has its n/a row"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
