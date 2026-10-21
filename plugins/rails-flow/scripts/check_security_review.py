#!/usr/bin/env python3
"""A threat model in this change needs a CURRENT per-row `security-auditor` record before the PR is ready (#2119, decision D3 on #2115).

Run:  check_security_review.py [--base dev] [--root DIR]            every threat model this change adds or edits
      check_security_review.py --model FILE --record FILE           one model, one record
      check_security_review.py --selftest
Exit: 0 nothing owed (no threat model in the change) or every model has a current, complete, clean record
      1 a record is missing, stale, or does not answer every row: run `security-auditor` against the model on this HEAD;
        or BLOCKING: the record says BLOCKED, a `mitigate` row is "not implemented", or an `accept` row is stale (a finding
        for a human). Never 3: the project gates grade 3 as not applicable, which would let a blocking finding pass (#1873).
      2 unusable: a model that exists but has no readable Threats table, an unreadable record, no git, an unknown base

WHY. `security-auditor` ran "if auth, authorization, APIs or data handling changed", a judgement the session makes, against a generic list
because nothing said what THIS unit must resist. The threat model (#2117) says; this makes the answer checkable, row by row, and tied to the
commit the way the adversary pass is (`risky_diff.py`).

HOW IT BINDS `gh pr ready`. It is registered in `checks.json`, so `project_gates.py` runs it, and `gh pr ready` is refused without a green
sweep record for HEAD (`guard-pr-ready.sh`, #1565). A model with no current security record therefore turns the sweep red. No chaining.

THE RECORD, `docs/evidence/reviews/prs/<slug>/security-audit.md` (`<slug>` is the model's file name), is `security-auditor`'s answer saved
verbatim. It counts only with a line `Head: <sha>` that is a prefix of the CURRENT HEAD, one line per threat row, and a last line
`VERDICT: CLEAN` or `VERDICT: BLOCKED`. A row line is `TM-n: <answer>`:
  * `mitigate` row  `TM-n: implemented <file:line>` (the file is read as committed at HEAD, with no absolute or `..` path, and that line must be code: not blank, not a comment, not inside =begin/=end or a /* */ span, not a heredoc body) or `TM-n: not implemented` (BLOCKING)
  * `accept` row    `TM-n: holds <why>` or `TM-n: stale <what changed>` (a finding: the model must be updated, the article's fourth question)
  * `transfer` and `eliminate` rows may be answered the same way and are not required.
A row the model has and the record omits, or a row the record names that the model lacks, is exit 1: the record answers another model.

STRICT (#2214 adversary). A cited file must be a regular file (mode 100644 or 100755) whose type a detected stack declares in
`security.code_syntax`; any other file type is refused ("declare this file type's comment syntax"), never read with neutral rules. A row
answered twice is refused, never "last wins".

LIMITS. It proves the record is current, complete and cites a line of code that exists, not that the cited line implements the control. The
code-line reading is line-by-line, not a parser: a `<<ID` or a comment marker inside a string is misread; a language's multi-line string
literals (a percent-literal, a quoted string spanning lines) read as code; dead code (`if false`) reads as code; a byte-order mark before line 1
makes a column-0 opener on line 1 not count. That is the auditor's work and the reviewer's. Nothing stops a session that writes the record by hand, as with `risky_diff.py`. The model is found only
when the change adds or edits it, so a unit that has a boundary and no model is `security_scope.py`'s concern, not this check's.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_threat_model import threat_rows  # noqa: E402
from classify_door import Unusable, diff  # noqa: E402
from risky_diff import head_sha, read_record  # noqa: E402

MODEL_DIR = "docs/security/threat-models"
RECORD_DIR = "docs/evidence/reviews/prs"
MODEL_RE = re.compile(rf"^{re.escape(MODEL_DIR)}/([^/]+)\.md$")
ROW_RE = re.compile(r"^\s*(?:[-*]\s*)?(?:\*\*)?(TM-\d+)(?:\*\*)?\s*[:—–-]+\s*(implemented|not implemented|holds|stale)\b\s*(.*)$", re.I)
EVIDENCE_RE = re.compile(r"([\w./@+-]+\.\w+):(\d+)")


# WHAT IS NOT CODE (#2119; stack-neutral per #2162). The neutral rules: a blank line, a `#` or `//` comment, a `/* */` span.
# Each stack adds its own (a language's own block comment, a heredoc) in its descriptor's `security.code_syntax`, scoped by file
# extension, so this script names no language. A heredoc pattern names the terminator as the group `id`.
# (open, close, column0): a column0 opener counts only at the very start of the raw line, for a language that honours it only there (#2214 review).
NEUTRAL_BLOCKS: tuple[tuple[str, str, bool], ...] = (("/*", "*/", False),)


def _open_after(text: str, blocks: tuple[tuple[str, str, bool], ...], pos: int = 0) -> str | None:
    """The closer of the span `text` leaves open, walking every opener and closer pair from `pos` (#2214 adversary: `<%# a %> t <%# b`
    closes the first comment and leaves the second open); None when every span on the line closes. Column0 blocks are not looked for."""
    while True:
        hits = [(text.find(o, pos), o, c) for o, c, col0 in blocks if not col0 and text.find(o, pos) >= 0]
        if not hits:
            return None
        at, o, c = min(hits)
        end = text.find(c, at + len(o))
        if end < 0:
            return c
        pos = end + len(c)


def non_code_lines(lines: list[str], blocks: tuple[tuple[str, str, bool], ...] = NEUTRAL_BLOCKS, heredoc: "re.Pattern | None" = None,
                   end_markers: tuple[str, ...] = ()) -> set[int]:
    """1-based numbers of lines that are not code: blank, a `#` or `//` comment, inside a block comment (`blocks`: open, close, column0),
    the body (and terminator) of a heredoc (`heredoc`), or anything from a data marker on (`end_markers`, a line that is exactly the
    marker, such as `__END__` in a language that has one). A line-by-line reading, not a parser: a heredoc opener inside a string or a comment still opens
    one, and a comment marker inside a string closes nothing.

    A column0 block opens and closes only at the very start of the raw line (#2214 adversary: an indented or mid-line `=end` closes
    nothing). Any other block opens wherever its opener appears, after code on the same line too (`foo(); /* begin`), and closes at the
    first closer after it. A heredoc opened with `~` or `-` ends at a line that is its terminator after stripping; a bare one ends only at
    a line that is exactly the terminator."""
    out: set[int] = set()
    closing: tuple[str, bool] | None = None
    heredocs: list[tuple[str, bool]] = []
    for n, raw in enumerate(lines, 1):
        raw = raw.rstrip("\r\n")
        t = raw.strip()
        if raw in end_markers:
            out.update(range(n, len(lines) + 1))
            break
        if heredocs:
            out.add(n)
            ident, indented = heredocs[0]
            if (t if indented else raw) == ident:
                heredocs.pop(0)
            continue
        if closing is not None:
            out.add(n)
            close, col0 = closing
            if col0:
                if raw.startswith(close):
                    closing = None
            elif close in raw:
                again = _open_after(raw, blocks, raw.find(close) + len(close))  # a span can reopen on the line that closed one
                closing = (again, False) if again else None
            continue
        opened = next(((o, c, col0) for o, c, col0 in blocks if (raw if col0 else t).startswith(o)), None)
        if opened:
            out.add(n)
            o, c, col0 = opened
            if col0:
                closing = (c, True)
            else:
                left = _open_after(t, blocks)
                closing = (left, False) if left else None
            continue
        if not t or t.startswith(("#", "//")):
            out.add(n)
            continue
        # This line is code; a span it leaves open, after any number of closed ones, still covers the lines below.
        left = _open_after(raw, blocks)
        if left:
            closing = (left, False)
        if closing is None and heredoc is not None:
            heredocs = [(m.group("id"), bool(re.match(r"<<[~-]", m.group(0)))) for m in heredoc.finditer(raw)]
    return out


def code_syntax(root: Path) -> list[dict]:
    """The detected stacks' `security.code_syntax` rows for the project at `root` (#2119); empty when none or not judged."""
    if str(root) in _SYNTAX:
        return _SYNTAX[str(root)]
    import detect_stack  # noqa: E402  (a sibling script)

    _, report = detect_stack.run(root, detect_stack.manifest_dirs(Path(__file__).resolve()))
    rows = [row for surface in report.get("security") or [] for row in surface.get("code_syntax") or []]
    _SYNTAX[str(root)] = rows
    _MARKERS[str(root)] = [m for surface in report.get("security") or [] for m in surface.get("data_markers") or []]
    return rows


def data_markers(root: Path) -> list[dict]:
    """The detected stacks' `security.data_markers` (#2214): a line from which nothing is code, scoped by extension."""
    code_syntax(root)
    return _MARKERS.get(str(root), [])


_SYNTAX: dict[str, list[dict]] = {}
_MARKERS: dict[str, list[dict]] = {}


def declared(path: str, rows: list[dict]) -> bool:
    """Whether a detected stack declares the comment syntax of `path`'s file type (#2214 adversary: never fall back to neutral rules)."""
    return any(path.endswith(ext) for row in rows for ext in row.get("extensions") or [])


def rules_for(path: str, rows: list[dict], markers: list[dict] | None = None) -> tuple[tuple[tuple[str, str, bool], ...], "re.Pattern | None", tuple[str, ...]]:
    """The block comments, heredoc pattern and data markers that apply to `path`: the neutral blocks plus every row for its extension."""
    blocks, heredoc = list(NEUTRAL_BLOCKS), None
    for row in rows:
        if any(path.endswith(ext) for ext in row.get("extensions") or []):
            blocks += [(b["open"], b["close"], bool(b.get("column0"))) for b in row.get("block_comments") or []]
            heredoc = heredoc or (re.compile(row["heredoc"]) if row.get("heredoc") else None)
    ends = tuple(m["marker"] for m in markers or [] if any(path.endswith(ext) for ext in m.get("extensions") or []))
    return tuple(blocks), heredoc, ends


def file_at_head(root: Path, path: str) -> list[str] | None:
    """The lines of `path` as committed at HEAD, or None: absolute, `..`, not in HEAD, a symlink (mode 120000), or git failed. Never the working tree."""
    import subprocess
    from pathlib import PurePosixPath

    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts:
        return None
    tree = subprocess.run(["git", "-C", str(root), "ls-tree", "HEAD", "--", p.as_posix()], capture_output=True, text=True)
    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] not in ("100644", "100755"):
        return None  # not in HEAD, a symlink (`git show` prints its target, which would read as code), a directory or a submodule
    proc = subprocess.run(["git", "-C", str(root), "show", f"HEAD:{p.as_posix()}"], capture_output=True)
    return proc.stdout.decode("utf-8", errors="replace").splitlines() if proc.returncode == 0 else None


def record_path(slug: str) -> Path:
    return Path(RECORD_DIR) / slug / "security-audit.md"


def judge(model_text: str, record_text: str, root: Path) -> tuple[list[str], list[str]]:
    """(incomplete, blocking): problems that need another pass, and findings for a human."""
    rows = threat_rows(model_text)
    incomplete: list[str] = []
    blocking: list[str] = []
    answers: dict[int, tuple[str, str]] = {}
    for line in record_text.splitlines():
        m = ROW_RE.match(line)
        if m:
            n = int(m.group(1)[3:])
            if n in answers:
                # Never "last wins" (#2214 adversary): `TM-1: not implemented` then `TM-1: implemented …` would hide the finding.
                incomplete.append(f"TM-{n} is answered twice in the record: one answer per row")
            answers[n] = (m.group(2).lower(), m.group(3))
    known = {n for n, _, _ in rows}
    for n in sorted(set(answers) - known):
        incomplete.append(f"the record answers TM-{n}, which is not a row of the model: it answers another model")
    for n, threat, decision in rows:
        got = answers.get(n)
        label = f"TM-{n} (`{threat[:50]}`, {decision})"
        if decision not in ("mitigate", "accept"):
            continue
        if got is None:
            incomplete.append(f"{label}: no answer in the record")
            continue
        verdict, rest = got
        if decision == "mitigate":
            if verdict == "not implemented":
                blocking.append(f"{label}: not implemented (BLOCKING)")
            elif verdict != "implemented":
                incomplete.append(f"{label}: a mitigate row is answered `implemented <file:line>` or `not implemented`, got `{verdict}`")
            else:
                ev = EVIDENCE_RE.search(rest)
                src = file_at_head(root, ev.group(1)) if ev else None
                if not ev or src is None:
                    incomplete.append(f"{label}: `implemented` needs evidence as a `file:line` of a regular file committed at HEAD inside the repository (no absolute or `..` path, no symlink or directory), got `{rest[:60]}`")
                elif not declared(ev.group(1), code_syntax(root)):
                    incomplete.append(f"{label}: {ev.group(1)}: declare this file type's comment syntax in the stack descriptor (`security.code_syntax`); "
                                      "a file type no detected stack declares is refused, never read with neutral rules")
                elif int(ev.group(2)) < 1 or int(ev.group(2)) > len(src):
                    incomplete.append(f"{label}: {ev.group(0)} is past the end of {ev.group(1)}")
                elif int(ev.group(2)) in non_code_lines(src, *rules_for(ev.group(1), code_syntax(root), data_markers(root))):
                    incomplete.append(f"{label}: {ev.group(0)} is blank, a comment or a heredoc body, so it cannot be where the control is implemented")
        else:
            if verdict == "stale":
                blocking.append(f"{label}: the accepted risk no longer matches the code (stale): update the model")
            elif verdict != "holds":
                incomplete.append(f"{label}: an accept row is answered `holds <why>` or `stale <what changed>`, got `{verdict}`")
    return incomplete, blocking


def check_one(model: Path, record: Path, root: Path, head: str) -> tuple[int, list[str]]:
    try:
        model_text = (root / model).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return 2, [f"{model}: unreadable: {exc}"]
    if not threat_rows(model_text):
        return 2, [f"{model}: exists but has no readable `## Threats` table (ID | Threat | STRIDE | Component | Decision | Reason): an unreadable model is not a clean one"]
    kind, detail = read_record(root / record, head)
    if kind in ("missing", "no-head", "stale", "no-verdict"):
        return 1, [f"{model}: the security review record is not usable ({kind}: {detail}). Run `security-auditor` against the model on this HEAD and save its answer to {record}"]
    try:
        record_text = (root / record).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return 2, [f"{record}: unreadable: {exc}"]
    incomplete, blocking = judge(model_text, record_text, root)
    if incomplete:
        return 1, [f"{model}: the record does not answer the model:", *[f"  {p}" for p in incomplete]]
    if blocking or kind == "BLOCKED":
        # Exit 1, not 3: the project gates read 3 as NOT APPLICABLE, which never fails a run (#1873), so a blocking finding
        # graded 3 would have passed the sweep it is meant to stop.
        return 1, [f"{model}: BLOCKING, a finding for a human to decide:", *[f"  {p}" for p in blocking], *([f"  {record}: VERDICT: BLOCKED"] if kind == "BLOCKED" else [])]
    return 0, [f"{model}: every mitigate and accept row answered, record current for {head[:12]}"]


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    ap = argparse.ArgumentParser(prog="check_security_review.py", description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--model", type=Path)
    ap.add_argument("--record", type=Path)
    a = ap.parse_args(argv)
    root = a.root.resolve()
    try:
        if a.model:
            models = [a.model]
        else:
            base = a.base
            if not base:
                base = next((b for b in ("origin/dev", "dev") if _has_ref(root, b)), "")
            if not base:
                return _say(2, ["no base to compare against (neither origin/dev nor dev resolves): pass --base"])
            models = [Path(p) for p in sorted(diff(root, base)) if MODEL_RE.match(p) and (root / p).is_file()]
        if not models:
            return _say(0, ["no threat model added or edited in this change: nothing owed (#2117 decides when one is)"])
        head = head_sha(root)
    except Unusable as exc:
        return _say(2, [f"UNUSABLE: {exc}"])
    worst = 0
    out: list[str] = []
    for model in models:
        rec = a.record if (a.record and len(models) == 1) else record_path(model.stem)
        code, lines = check_one(model, rec, root, head)
        out += lines
        # 2 (cannot read) outranks 1 (run the pass), which outranks 3 (a human decides): each asks for a different next step.
        worst = code if worst == 0 else (2 if 2 in (worst, code) else (1 if 1 in (worst, code) else max(worst, code)))
    return _say(worst, out)


def _has_ref(root: Path, ref: str) -> bool:
    import subprocess

    return subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"], capture_output=True).returncode == 0


def _say(code: int, lines: list[str]) -> int:
    print("\n".join(lines), file=sys.stderr if code == 2 else sys.stdout)
    return code


MODEL = """# Threat model: t
## What we are building
A webhook.
## Trust boundaries
- Zoho -> app: the callback body
## Threats
| ID | Threat | STRIDE | Component | Decision | Reason |
|---|---|---|---|---|---|
| TM-1 | Forged callback | S | webhook | mitigate | signature checked |
| TM-2 | Replay | R | webhook | accept | idempotent |
## Security requirements
- verify the signature
"""


def selftest() -> int:
    import subprocess
    import tempfile

    bad = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        import fixture_git  # noqa: E402  (hermetic: GIT_DIR bound to this temp repo, no maintenance, no system config)

        def git(*args: str) -> str:
            return fixture_git.run(td, *args, capture_output=True, text=True).stdout.strip()

        fixture_git.init(td, "-b", "dev")
        # A made-up language `.x` (=open/=close blocks, <<ID heredocs) proves the mechanism with no real language in this script;
        # each stack proves its own syntax with its descriptor's syntax_cases (below).
        # Keyed by both spellings of the root: main() resolves it (macOS /var -> /private/var), and a miss is now refused, not neutral.
        for key in {str(root), str(root.resolve())}:
            _SYNTAX[key] = [{"extensions": [".x"], "block_comments": [{"open": "=open", "close": "=close", "column0": True}],
                             "heredoc": r"<<[~-]?(?P<id>[A-Za-z_]\w*)"}]
            _MARKERS[key] = [{"extensions": [".x"], "marker": "__DATA__"}]
        (root / "src").mkdir()
        (root / "src/c.x").write_text("a\nb\nc\n# note\n\n=open\nhidden\n=close\nlast\nx = <<TXT\n  select 1\nTXT\n/* block\nmiddle no star\nend */\ntail\n  *args,\ny = [<<X, <<Y]\n  one\nX\n  two\nY\ndone\n")
        # #2214 adversary: a column0 block that a mid-line or indented closer does not close, a span opened after code, `~` and bare
        # heredocs with lowercase ids, and a data marker. Line numbers are the fixture's API: the cases below cite them.
        D_X = ["code", "=open", "hidden", "x =close", "  =close", "still hidden", "=close", "after", "foo(); /* begin", "hidden span",
               "end */", "tail", "y = <<~low", "  body", "  low", "z = <<bare", "  bare", "bare", "code2", "__DATA__", "data"]
        (root / "src/d.x").write_text("\n".join(D_X) + "\n")
        (root / "src/e.js").write_text("const a = 1;\n")
        (root / "src/dir.x").mkdir()
        (root / "src/dir.x/inner.x").write_text("x\n")
        # #2214 adversary pass 4: a line that closes one span and opens another, and a closing line that reopens one.
        F_X = ["a /* x */ b /* begin", "hidden", "end */ y /* again", "hidden2", "*/", "code"]
        (root / "src/f.x").write_text("\n".join(F_X) + "\n")
        git("add", "src/c.x", "src/d.x", "src/e.js", "src/dir.x/inner.x", "src/f.x")
        git("commit", "-q", "-m", "base")
        got_f = non_code_lines(F_X, *rules_for("src/f.x", _SYNTAX[str(root)], _MARKERS[str(root)]))
        if got_f != {2, 3, 4, 5}:
            bad += 1
            print(f"FAIL every span on a line is walked: got {sorted(got_f)}, expected [2, 3, 4, 5]")
        want_d = {2, 3, 4, 5, 6, 7, 10, 11, 14, 15, 17, 18, 20, 21}
        got_d = non_code_lines(D_X, *rules_for("src/d.x", _SYNTAX[str(root)], _MARKERS[str(root)]))
        if got_d != want_d:
            bad += 1
            print(f"FAIL the adversary fixture's non-code lines: got {sorted(got_d)}, expected {sorted(want_d)}")
        git("checkout", "-q", "-b", "feat")
        (root / "src/untracked.x").write_text("x = 1\n")
        import os as _os

        _os.symlink("/etc/hosts", root / "src/link.x")
        git("add", "src/link.x")
        git("commit", "-q", "-m", "link")
        (root / MODEL_DIR).mkdir(parents=True)
        (root / MODEL_DIR / "t.md").write_text(MODEL)
        git("add", f"{MODEL_DIR}/t.md")
        git("commit", "-q", "-m", "model")
        head = git("rev-parse", "HEAD")
        rec = root / RECORD_DIR / "t" / "security-audit.md"
        rec.parent.mkdir(parents=True)

        def case(label: str, record: str | None, want: int, needle: str = "", base: list[str] | None = None, head_sha_: str | None = None) -> None:
            nonlocal bad
            if record is None:
                rec.unlink(missing_ok=True)
            else:
                rec.write_text(record.replace("HEAD", head_sha_ or head))
            import contextlib
            import io

            buf, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                if base is None:
                    # the record rules only: judged directly, so the diff and rev-parse that `main` adds are not paid 25 times over
                    got, lines = check_one(Path(f"{MODEL_DIR}/t.md"), record_path("t"), root, head)
                    print("\n".join(lines))
                else:
                    got = main(["--root", td, *base])
            text = buf.getvalue() + err.getvalue()
            if got != want or (needle and needle not in text):
                bad += 1
                print(f"FAIL {label}: expected exit {want} naming `{needle}`, got {got}: {text.strip()[:200]}")

        good = "Head: HEAD\nTM-1: implemented src/c.x:2\nTM-2: holds a repeated callback is a no-op\nVERDICT: CLEAN\n"
        case("a complete current record passes", good, 0, "answered")
        case("no record at all asks for the pass", None, 1, "missing")
        case("a record for another commit is stale", good, 1, "stale", head_sha_="0" * 40)
        case("a record without a Head line cannot be tied to a commit", good.replace("Head: HEAD\n", ""), 1, "no-head")
        case("a record with no verdict is unusable as a record", good.replace("VERDICT: CLEAN\n", ""), 1, "no-verdict")
        case("a mitigate row with no answer is incomplete", good.replace("TM-1: implemented src/c.x:2\n", ""), 1, "TM-1")
        case("an accept row with no answer is incomplete", good.replace("TM-2: holds a repeated callback is a no-op\n", ""), 1, "TM-2")
        case("evidence that is not file:line is incomplete", good.replace("src/c.x:2", "somewhere"), 1, "file:line")
        case("evidence for a file that does not exist is incomplete", good.replace("src/c.x:2", "src/nope.x:2"), 1, "file:line")
        case("evidence on a comment line is incomplete", good.replace("src/c.x:2", "src/c.x:4"), 1, "blank, a comment or a heredoc")
        case("evidence on a blank line is incomplete", good.replace("src/c.x:2", "src/c.x:5"), 1, "blank, a comment or a heredoc")
        case("evidence inside a stack block comment is incomplete", good.replace("src/c.x:2", "src/c.x:7"), 1, "blank, a comment or a heredoc")
        case("evidence on the block comment's closing line is incomplete", good.replace("src/c.x:2", "src/c.x:8"), 1, "blank, a comment or a heredoc")
        case("evidence on code after a block comment passes", good.replace("src/c.x:2", "src/c.x:9"), 0, "answered")
        case("evidence inside a heredoc body is incomplete", good.replace("src/c.x:2", "src/c.x:11"), 1, "heredoc")
        case("evidence on a heredoc terminator is incomplete", good.replace("src/c.x:2", "src/c.x:12"), 1, "heredoc")
        NOT_CODE = "blank, a comment or a heredoc"
        for label, cite, want in (
                ("a mid-line closer does not close a column0 block", "src/d.x:4", 1), ("an indented closer does not close a column0 block", "src/d.x:6", 1),
                ("code after a column0 block closes at column 0 passes", "src/d.x:8", 0), ("a line opening a span after code is itself code", "src/d.x:9", 0),
                ("a span opened after code hides the lines below", "src/d.x:10", 1), ("a lowercase `~` heredoc body is not code", "src/d.x:14", 1),
                ("an indented line is not a bare heredoc's terminator", "src/d.x:18", 1), ("code after a bare heredoc passes", "src/d.x:19", 0),
                ("lines after a data marker are not code", "src/d.x:21", 1),
                ("a second span opened after a closed one hides the next line", "src/f.x:2", 1),
                ("a span reopened on its closing line hides the next line", "src/f.x:4", 1),
                ("code after every span closes passes", "src/f.x:6", 0)):
            case(label, good.replace("src/c.x:2", cite), want, NOT_CODE if want else "answered")
        case("a directory is never read as a cited file", good.replace("src/c.x:2", "src/dir.x:1"), 1, "a regular file committed at HEAD")
        case("a file type no stack declares is refused, not read with neutral rules", good.replace("src/c.x:2", "src/e.js:1"), 1,
             "declare this file type's comment syntax in the stack descriptor")
        case("a row answered twice is refused, not last-wins", good.replace("TM-1: implemented src/c.x:2\n", "TM-1: not implemented\nTM-1: implemented src/c.x:2\n"), 1,
             "TM-1 is answered twice in the record")
        case("evidence on the line that opens a heredoc is code", good.replace("src/c.x:2", "src/c.x:10"), 0, "answered")
        case("evidence in the middle of a /* */ span with no leading star is incomplete", good.replace("src/c.x:2", "src/c.x:14"), 1, "heredoc")
        case("evidence on code after a /* */ span passes", good.replace("src/c.x:2", "src/c.x:16"), 0, "answered")
        case("a splat line is code, not a comment", good.replace("src/c.x:2", "src/c.x:17"), 0, "answered")
        case("evidence in the second of two heredocs opened on one line is incomplete", good.replace("src/c.x:2", "src/c.x:21"), 1, "heredoc")
        case("evidence after two heredocs on one line passes", good.replace("src/c.x:2", "src/c.x:23"), 0, "answered")
        case("a committed symlink is refused, never read through its target", good.replace("src/c.x:2", "src/link.x:1"), 1, "committed at HEAD")
        case("an absolute evidence path is refused", good.replace("src/c.x:2", "/etc/hosts:1"), 1, "inside the repository")
        case("a `..` evidence path is refused", good.replace("src/c.x:2", "app/../src/c.x:2"), 1, "inside the repository")
        case("evidence in a file that exists only in the working tree is refused", good.replace("src/c.x:2", "src/untracked.x:1"), 1, "committed at HEAD")
        case("evidence past the end of the file is incomplete", good.replace("src/c.x:2", "src/c.x:99"), 1, "past the end")
        case("a mitigate row not implemented is BLOCKING, exit 1 (never 3, which the gates read as not applicable)", good.replace("implemented src/c.x:2", "not implemented"), 1, "BLOCKING")
        case("a stale accept row is a BLOCKING finding, exit 1", good.replace("holds a repeated callback is a no-op", "stale the signature now has a timestamp"), 1, "no longer matches the code")
        case("a row the model does not have is another model", good + "TM-9: holds x\n", 1, "TM-9")
        case("VERDICT: BLOCKED is exit 1 even with every row answered", good.replace("CLEAN", "BLOCKED"), 1, "BLOCKED")
        case("a CLEAN verdict does not hide a not-implemented row", good.replace("implemented src/c.x:2", "not implemented"), 1, "BLOCKING")
        case("through main(): a complete current record passes", good, 0, "answered", base=["--base", "dev"])
        case("through main(): no record asks for the pass", None, 1, "missing", base=["--base", "dev"])
        case("an unknown base is unusable, not clean", good, 2, "UNUSABLE", base=["--base", "nope"])
        # No model in the change: nothing owed, and that is exit 0 with a sentence.
        git("checkout", "-q", "dev")
        git("checkout", "-q", "-b", "other")
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            got = main(["--root", td, "--base", "dev"])
        if got != 0 or "nothing owed" not in buf.getvalue():
            bad += 1
            print(f"FAIL a change with no threat model owes nothing: exit {got}: {buf.getvalue().strip()[:120]}")
        # A model that exists but cannot be read is exit 2, never 0.
        git("checkout", "-q", "feat")
        (root / MODEL_DIR / "t.md").write_text("# not a model\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            got = main(["--root", td, "--base", "dev", "--model", f"{MODEL_DIR}/t.md"])
        if got != 2:
            bad += 1
            print(f"FAIL an unreadable model is exit 2: got {got}")
    # Every stack this script can see proves its own syntax: its syntax_cases name which lines of a sample are not code.
    # A column0 opener counts only at the start of the raw line (#2214 review), stack-neutral so the staged guard sees it.
    col0 = (("=open", "=close", True),)
    for label, lines, want in (("a column0 opener at column 0 opens a block", ["=open", "hidden", "=close", "code"], {1, 2, 3}),
                               ("an indented column0 opener is code", ["  =open", "code", "=close"], set())):
        got = non_code_lines(lines, col0)
        if got != want:
            bad += 1
            print(f"FAIL {label}: non-code lines {sorted(got)}, expected {sorted(want)}")
    import detect_stack  # noqa: E402
    manifests, _ = detect_stack.load_manifests(detect_stack.manifest_dirs(Path(__file__).resolve()))
    ran = 0
    for manifest in manifests:
        for stack in manifest.get("stacks") or []:
            sec = ((stack or {}).get("descriptor") or {}).get("security") if isinstance(stack, dict) else None
            if not isinstance(sec, dict) or not isinstance(sec.get("syntax_cases"), str):
                continue
            label = f"{manifest['plugin']}:{stack.get('id')}"
            try:
                cases = json.loads((detect_stack.plugin_root(manifest) / sec["syntax_cases"]).read_text(encoding="utf-8"))
            except (OSError, ValueError) as err:
                bad += 1
                print(f"FAIL {label}: cannot read its syntax cases: {err}")
                continue
            for c in cases:
                ran += 1
                got = non_code_lines(c["lines"], *rules_for(c["file"], sec.get("code_syntax") or [], sec.get("data_markers") or []))
                if got != set(c["non_code"]):
                    bad += 1
                    print(f"FAIL {label}: {c['name']}: non-code lines {sorted(got)}, expected {c['non_code']}")
    if bad == 0:
        print(f"check_security_review selftest: every row passes, and {ran} stack syntax case(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
