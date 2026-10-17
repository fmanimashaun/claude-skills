#!/usr/bin/env python3
"""A threat model in this change needs a CURRENT per-row `security-auditor` record before the PR is ready (#2119, decision D3 on #2115).

Run:  check_security_review.py [--base dev] [--root DIR]            every threat model this change adds or edits
      check_security_review.py --model FILE --record FILE           one model, one record
      check_security_review.py --selftest
Exit: 0 nothing owed (no threat model in the change) or every model has a current, complete, clean record
      1 a record is missing, stale, or does not answer every row: run `security-auditor` against the model on this HEAD
      2 unusable: a model that exists but has no readable Threats table, an unreadable record, no git, an unknown base
      3 the record says BLOCKED, a `mitigate` row is "not implemented", or an `accept` row is stale: a finding for a human

WHY. `security-auditor` ran "if auth, authorization, APIs or data handling changed", a judgement the session makes, against a generic list
because nothing said what THIS unit must resist. The threat model (#2117) says; this makes the answer checkable, row by row, and tied to the
commit the way the adversary pass is (`risky_diff.py`).

HOW IT BINDS `gh pr ready`. It is registered in `checks.json`, so `project_gates.py` runs it, and `gh pr ready` is refused without a green
sweep record for HEAD (`guard-pr-ready.sh`, #1565). A model with no current security record therefore turns the sweep red. No chaining.

THE RECORD, `docs/evidence/reviews/prs/<slug>/security-audit.md` (`<slug>` is the model's file name), is `security-auditor`'s answer saved
verbatim. It counts only with a line `Head: <sha>` that is a prefix of the CURRENT HEAD, one line per threat row, and a last line
`VERDICT: CLEAN` or `VERDICT: BLOCKED`. A row line is `TM-n: <answer>`:
  * `mitigate` row  `TM-n: implemented <file:line>` (the file must exist at HEAD and that line must be code: not blank, not a comment, not inside =begin/=end) or `TM-n: not implemented` (BLOCKING)
  * `accept` row    `TM-n: holds <why>` or `TM-n: stale <what changed>` (a finding: the model must be updated, the article's fourth question)
  * `transfer` and `eliminate` rows may be answered the same way and are not required.
A row the model has and the record omits, or a row the record names that the model lacks, is exit 1: the record answers another model.

LIMITS. It proves the record is current, complete and cites a line of code that exists, not that the cited line implements the control; that is the
auditor's work and the reviewer's. Nothing stops a session that writes the record by hand, as with `risky_diff.py`. The model is found only
when the change adds or edits it, so a unit that has a boundary and no model is `security_scope.py`'s concern, not this check's.
"""
from __future__ import annotations

import argparse
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


def is_code_line(lines: list[str], n: int) -> bool:
    """Whether 1-based line `n` is code: not blank, not a `#`, `//` or `*` comment, not inside a Ruby `=begin`/`=end` block. A minimal reading, not a parser."""
    inside = False
    for i, raw in enumerate(lines[:n], 1):
        if raw.startswith("=begin"):
            inside = True
        elif raw.startswith("=end"):
            inside = False
            if i == n:
                return False
        if i == n:
            t = raw.strip()
            return not inside and bool(t) and not t.startswith(("#", "//", "/*", "*"))
    return False


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
                f = (root / ev.group(1)) if ev else None
                if not ev or f is None or not f.is_file():
                    incomplete.append(f"{label}: `implemented` needs evidence as an existing `file:line`, got `{rest[:60]}`")
                else:
                    src = f.read_text(encoding="utf-8", errors="replace").splitlines()
                    if int(ev.group(2)) < 1 or int(ev.group(2)) > len(src):
                        incomplete.append(f"{label}: {ev.group(0)} is past the end of {ev.group(1)}")
                    elif not is_code_line(src, int(ev.group(2))):
                        incomplete.append(f"{label}: {ev.group(0)} is blank or a comment, so it cannot be where the control is implemented")
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
        return 3, [f"{model}: a finding for a human to decide:", *[f"  {p}" for p in blocking], *([f"  {record}: VERDICT: BLOCKED"] if kind == "BLOCKED" else [])]
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

        def git(*args: str) -> str:
            return subprocess.run(["git", "-C", td, "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
                                  capture_output=True, text=True, check=True).stdout.strip()

        git("init", "-q", "-b", "dev")
        (root / "app").mkdir()
        (root / "app/c.rb").write_text("a\nb\nc\n# note\n\n=begin\nhidden\n=end\nlast\n")
        git("add", "app/c.rb")
        git("commit", "-q", "-m", "base")
        git("checkout", "-q", "-b", "feat")
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
            argv = ["--root", td, *(base if base is not None else ["--base", "dev"])]
            import contextlib
            import io

            buf, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(err):
                got = main(argv)
            text = buf.getvalue() + err.getvalue()
            if got != want or (needle and needle not in text):
                bad += 1
                print(f"FAIL {label}: expected exit {want} naming `{needle}`, got {got}: {text.strip()[:200]}")

        good = "Head: HEAD\nTM-1: implemented app/c.rb:2\nTM-2: holds a repeated callback is a no-op\nVERDICT: CLEAN\n"
        case("a complete current record passes", good, 0, "answered")
        case("no record at all asks for the pass", None, 1, "missing")
        case("a record for another commit is stale", good, 1, "stale", head_sha_="0" * 40)
        case("a record without a Head line cannot be tied to a commit", good.replace("Head: HEAD\n", ""), 1, "no-head")
        case("a record with no verdict is unusable as a record", good.replace("VERDICT: CLEAN\n", ""), 1, "no-verdict")
        case("a mitigate row with no answer is incomplete", good.replace("TM-1: implemented app/c.rb:2\n", ""), 1, "TM-1")
        case("an accept row with no answer is incomplete", good.replace("TM-2: holds a repeated callback is a no-op\n", ""), 1, "TM-2")
        case("evidence that is not file:line is incomplete", good.replace("app/c.rb:2", "somewhere"), 1, "file:line")
        case("evidence for a file that does not exist is incomplete", good.replace("app/c.rb:2", "app/nope.rb:2"), 1, "file:line")
        case("evidence on a comment line is incomplete", good.replace("app/c.rb:2", "app/c.rb:4"), 1, "blank or a comment")
        case("evidence on a blank line is incomplete", good.replace("app/c.rb:2", "app/c.rb:5"), 1, "blank or a comment")
        case("evidence inside =begin/=end is incomplete", good.replace("app/c.rb:2", "app/c.rb:7"), 1, "blank or a comment")
        case("evidence on the =end line is incomplete", good.replace("app/c.rb:2", "app/c.rb:8"), 1, "blank or a comment")
        case("evidence on code after a block comment passes", good.replace("app/c.rb:2", "app/c.rb:9"), 0, "answered")
        case("evidence past the end of the file is incomplete", good.replace("app/c.rb:2", "app/c.rb:99"), 1, "past the end")
        case("a mitigate row not implemented is BLOCKING, exit 3", good.replace("implemented app/c.rb:2", "not implemented"), 3, "not implemented")
        case("a stale accept row is a finding, exit 3", good.replace("holds a repeated callback is a no-op", "stale the signature now has a timestamp"), 3, "stale")
        case("a row the model does not have is another model", good + "TM-9: holds x\n", 1, "TM-9")
        case("VERDICT: BLOCKED is exit 3 even with every row answered", good.replace("CLEAN", "BLOCKED"), 3, "BLOCKED")
        case("a CLEAN verdict does not hide a not-implemented row", good.replace("implemented app/c.rb:2", "not implemented"), 3, "BLOCKING")
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
    if bad == 0:
        print("check_security_review selftest: every row passes")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
