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

LIMITS. It proves the record is current, complete and cites a line of code that exists, not that the cited line implements the control; the code-line reading is line-by-line, so a `<<ID` or a comment marker inside a string is misread, and a file that is not code at all (README.md) still counts as code; that is the
auditor's work and the reviewer's. Nothing stops a session that writes the record by hand, as with `risky_diff.py`. The model is found only
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
NEUTRAL_BLOCKS: tuple[tuple[str, str], ...] = (("/*", "*/"),)


def non_code_lines(lines: list[str], blocks: tuple[tuple[str, str], ...] = NEUTRAL_BLOCKS, heredoc: "re.Pattern | None" = None) -> set[int]:
    """1-based numbers of lines that are not code: blank, a `#` or `//` comment, inside a block comment (`blocks`: open, close),
    or the body (and terminator) of a heredoc (`heredoc`). A line-by-line reading, not a parser: a heredoc opener inside a string
    or a comment still opens one, and a comment marker inside a string closes nothing."""
    out: set[int] = set()
    closing: str | None = None
    heredocs: list[str] = []
    for n, raw in enumerate(lines, 1):
        t = raw.strip()
        if heredocs:
            out.add(n)
            if t == heredocs[0]:
                heredocs.pop(0)
            continue
        if closing is not None:
            out.add(n)
            if closing in raw:
                closing = None
            continue
        opened = next(((o, c) for o, c in blocks if t.startswith(o)), None)
        if opened:
            out.add(n)
            if opened[1] not in t[len(opened[0]):]:
                closing = opened[1]
        elif not t or t.startswith(("#", "//")):
            out.add(n)
        elif heredoc is not None:
            heredocs = [m.group("id") for m in heredoc.finditer(raw)]
    return out


def code_syntax(root: Path) -> list[dict]:
    """The detected stacks' `security.code_syntax` rows for the project at `root` (#2119); empty when none or not judged."""
    if str(root) in _SYNTAX:
        return _SYNTAX[str(root)]
    import detect_stack  # noqa: E402  (a sibling script)

    _, report = detect_stack.run(root, detect_stack.manifest_dirs(Path(__file__).resolve()))
    rows = [row for surface in report.get("security") or [] for row in surface.get("code_syntax") or []]
    _SYNTAX[str(root)] = rows
    return rows


_SYNTAX: dict[str, list[dict]] = {}


def rules_for(path: str, rows: list[dict]) -> tuple[tuple[tuple[str, str], ...], "re.Pattern | None"]:
    """The block comments and heredoc pattern that apply to `path`: the neutral blocks plus every row for its extension."""
    blocks, heredoc = list(NEUTRAL_BLOCKS), None
    for row in rows:
        if any(path.endswith(ext) for ext in row.get("extensions") or []):
            blocks += [(b["open"], b["close"]) for b in row.get("block_comments") or []]
            heredoc = heredoc or (re.compile(row["heredoc"]) if row.get("heredoc") else None)
    return tuple(blocks), heredoc


def file_at_head(root: Path, path: str) -> list[str] | None:
    """The lines of `path` as committed at HEAD, or None: absolute, `..`, not in HEAD, a symlink (mode 120000), or git failed. Never the working tree."""
    import subprocess
    from pathlib import PurePosixPath

    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts:
        return None
    tree = subprocess.run(["git", "-C", str(root), "ls-tree", "HEAD", "--", p.as_posix()], capture_output=True, text=True)
    if tree.returncode != 0 or not tree.stdout.strip() or tree.stdout.split()[0] == "120000":
        return None  # not in HEAD, or a symlink: `git show` of a link prints its target path, which would read as code
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
            answers[int(m.group(1)[3:])] = (m.group(2).lower(), m.group(3))
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
                    incomplete.append(f"{label}: `implemented` needs evidence as a `file:line` of a file committed at HEAD inside the repository (no absolute or `..` path), got `{rest[:60]}`")
                elif int(ev.group(2)) < 1 or int(ev.group(2)) > len(src):
                    incomplete.append(f"{label}: {ev.group(0)} is past the end of {ev.group(1)}")
                elif int(ev.group(2)) in non_code_lines(src, *rules_for(ev.group(1), code_syntax(root))):
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
        _SYNTAX[str(root)] = [{"extensions": [".x"], "block_comments": [{"open": "=open", "close": "=close"}],
                               "heredoc": r"<<(?P<id>[A-Z_][A-Z0-9_]*)"}]
        (root / "src").mkdir()
        (root / "src/c.x").write_text("a\nb\nc\n# note\n\n=open\nhidden\n=close\nlast\nx = <<TXT\n  select 1\nTXT\n/* block\nmiddle no star\nend */\ntail\n  *args,\ny = [<<X, <<Y]\n  one\nX\n  two\nY\ndone\n")
        git("add", "src/c.x")
        git("commit", "-q", "-m", "base")
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
                got = non_code_lines(c["lines"], *rules_for(c["file"], sec.get("code_syntax") or []))
                if got != set(c["non_code"]):
                    bad += 1
                    print(f"FAIL {label}: {c['name']}: non-code lines {sorted(got)}, expected {c['non_code']}")
    if bad == 0:
        print(f"check_security_review selftest: every row passes, and {ran} stack syntax case(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
