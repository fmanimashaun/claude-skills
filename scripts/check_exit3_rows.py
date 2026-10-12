#!/usr/bin/env python3
"""check_exit3_rows.py -- every exit 3 a shipped check can give is proven, by its selftest, to mean "not applicable" (#1873).

`plugins/rails-flow/scripts/project_gates.py` grades a check's exit 3 as NOT APPLICABLE, which never
fails a run. So a 3 that means "could not look" passes silently; #1864, #1867 and #1872 each found
one by reading code. This gate makes the next one visible at authoring time.

For every script a `plugins/*/checks.json` names, it PARSES the script (ast, never a grep) and counts the
EXIT-3 SITES: each `return` or exit call (`sys.exit`, `exit`, `SystemExit`) whose value can be 3 -- a literal,
either arm of `x if c else 3`, the first element of `return 3, findings`, or a module-level name bound to 3.
It counts the N/A ROWS in the selftest (the script, plus a sibling `<stem>_selftest.py`): each `== 3` or
`!= 3`, or 3 passed positionally to a call, whose OWN statement holds a string saying why -- "n/a",
"not applicable" / "not-applicable", or "skip". For an `if`, its statement is its test and the first line of
its body. Comments and docstrings are not code, so they are never rows; a `print(` is output, not a test. A
script with fewer rows than sites is a finding.

What it cannot see: whether a row exercises the site it is counted against. A `!= 3` counts only as the test
of an `if` (`if code != 3: fail(...)`); asserted as a value it says the exit is NOT 3. Counting is the floor;
each row's mutant (the script's own guard) is what proves the row reaches its site.

Exit: 0 every site has its row · 1 findings. Maintainer tooling; not shipped.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WHY = re.compile(r"n/a|not[ -]applicable|\bskip", re.I)
EXITS = {"exit", "_exit", "SystemExit"}          # sys.exit(3), exit(3), os._exit(3), raise SystemExit(3)
COMPOUND = (ast.If, ast.While, ast.For, ast.With, ast.Try)


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


def _threes(tree: ast.Module) -> set[str]:
    """Module-level names bound to the literal 3, so `NA = 3; return NA` is a site too."""
    return {t.id for n in tree.body if isinstance(n, ast.Assign) and _is3(n.value, set())
            for t in n.targets if isinstance(t, ast.Name)}


def _is3(node: ast.AST | None, names: set[str]) -> bool:
    """Can this value be an exit of 3? A literal, a name bound to one, either arm of `x if c else 3`, or the
    first element of a `return 3, findings` tuple."""
    if isinstance(node, ast.Constant):
        return node.value == 3 and type(node.value) is int
    if isinstance(node, ast.Name):
        return node.id in names
    if isinstance(node, ast.IfExp):
        return _is3(node.body, names) or _is3(node.orelse, names)
    if isinstance(node, ast.Tuple) and node.elts:
        return _is3(node.elts[0], names)
    return False


def _callee(call: ast.Call) -> str:
    f = call.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def sites(text: str) -> int:
    """Each `return` or exit call whose value can be 3. Parsed, not grepped: a comment or a docstring is no site."""
    tree = ast.parse(text)
    names = _threes(tree)
    n = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Return) and _is3(node.value, names):
            n += 1
        elif isinstance(node, ast.Call) and _callee(node) in EXITS and node.args and _is3(node.args[0], names):
            n += 1
    return n


def _strings(nodes: list[ast.AST]) -> str:
    return " ".join(c.value for root in nodes for c in ast.walk(root) if isinstance(c, ast.Constant) and isinstance(c.value, str))


def rows(text: str) -> int:
    """Each assertion of an exit of 3 -- `== 3`, `!= 3`, or 3 passed positionally to a call -- whose OWN statement
    carries a reason string. For an `if`/`while`, the statement is its test and the first line of its body, so
    `if code != 3: fail("... skip ...")` counts and the rest of a long block does not. Comments and docstrings
    are not code, so they are never rows; a `print(` is output, not a test."""
    tree = ast.parse(text)
    parent = {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}

    def statement(node: ast.AST) -> list[ast.AST]:
        while not isinstance(node, ast.stmt):
            node = parent[node]
        if isinstance(node, COMPOUND):
            head = [getattr(node, "test", None) or getattr(node, "iter", None)] + [i.context_expr for i in getattr(node, "items", [])]
            return [h for h in head if h is not None] + node.body[:1]
        return [node]

    def in_print(node: ast.AST) -> bool:
        while node in parent:
            node = parent[node]
            if isinstance(node, ast.Call) and _callee(node) == "print":
                return True
        return False

    n = 0
    for node in ast.walk(tree):
        asserts = (isinstance(node, ast.Compare) and any(isinstance(o, (ast.Eq, ast.NotEq)) for o in node.ops)
                   and any(_is3(x, set()) and isinstance(x, ast.Constant) for x in [node.left, *node.comparators])) or \
                  (isinstance(node, ast.Call) and _callee(node) not in EXITS | {"print"}
                   and any(isinstance(x, ast.Constant) and _is3(x, set()) for x in node.args))
        # `!= 3` proves an exit of 3 only as the test of an if that fails otherwise; asserted as a value
        # (`check('...skip', code != 3)`) it says the exit is NOT 3 (#1891 review).
        if isinstance(node, ast.Compare) and not any(isinstance(o, ast.Eq) for o in node.ops) \
                and not (isinstance(parent.get(node), ast.If) and parent[node].test is node):
            continue
        if asserts and not in_print(node) and WHY.search(_strings(statement(node))):
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
        # #1891 review (a0): forgeries the line-based draft credited, and spellings it could not see as sites.
        ("a comment that reads like a row is not a row", {"a.py": site + "# code == 3 is n/a\n"}, 1),
        ("a docstring line that reads like a row is not a row", {"a.py": site + "def t():\n    \"\"\"rc == 3 when we skip\"\"\"\n"}, 1),
        ("a list holding 3 is not 3 passed as an exit", {"a.py": site + "x = [1, 3, 5]  # skip\n"}, 1),
        ("CONTROL: a row inside an if, reason in its first body line, counts", {"a.py": site + "if code != 3:\n    fail('no app is a skip')\n"}, 0),
        ("a reason later in the if block is not this row's", {"a.py": site + "if code != 3:\n    fail('wrong')\n    note('n/a elsewhere')\n"}, 1),
        ("a != 3 asserted as a value says NOT 3, so it is not a row", {"a.py": site + "check('it does not skip', code != 3)\n"}, 1),
        ("`else 3` is a site", {"a.py": "def main():\n    return 0 if ok else 3\n"}, 1),
        ("sys.exit(3) is a site", {"a.py": "import sys\nsys.exit(3)\n"}, 1),
        ("raise SystemExit(3) is a site", {"a.py": "raise SystemExit(3)\n"}, 1),
        ("a name bound to 3 and returned is a site", {"a.py": "NA = 3\ndef main():\n    return NA\n"}, 1),
        ("`return 3, findings` is a site", {"a.py": "def check():\n    return 3, [], ['none']\n"}, 1),
        ("CONTROL: a constant 3 that is never returned is no site", {"a.py": "MAX_EXAMPLES = 3\ndef main():\n    return 0\n"}, 0),
        ("a float 3.0 is not an exit 3", {"a.py": "def main():\n    return 3.0\n"}, 0),
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
