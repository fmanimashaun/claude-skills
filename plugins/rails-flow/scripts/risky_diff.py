#!/usr/bin/env python3
"""Decide whether a branch's diff is RISKY enough to need an adversarial pass, and whether that pass was recorded (#1819).

Run:  risky_diff.py [--base dev] [--root DIR] [--record docs/evidence/reviews/prs/<slug>/adversary.md]
      risky_diff.py --selftest
Exit: 0 not risky, or risky with a recorded `VERDICT: CLEAN` for this HEAD
      1 risky and no usable record: run the `adversary` agent (model: fable) and record its verdict at --record
      2 cannot classify (the base does not resolve): an unknown diff is not "not risky"
      3 risky, and the recorded verdict is BLOCKED: a finding for a human to decide, never an automatic stop of the work

WHY (#1819, the owner's rule of 2026-10-08). Fable is the model for adversarial attack passes, the ones that try to break a change.
Retask sessions ran one by hand and recorded a "Fable adversary HOLDS" verdict on several PRs, so it depended on someone remembering.
This is the part of the remembering a script can do: say which diffs are risky, and whether the pass left its record. It is the
sibling of `classify_door.py` (is the change reversible) and `check_mockup_gate.py` (did a user-visible change get a mock-up).

RISKY means the diff touches one of five things, by PATH or by a line it adds or removes (never in spec/ or test/):
  * auth       the authentication concern, session and password controllers, the Session and Current models, an
               auth/devise/omniauth/session_store/rack_attack/cors initializer; `has_secure_password`, `authenticate_by`,
               `reset_session`, signed or encrypted cookies
  * access     app/policies/, abilities; `authorize`, `policy_scope`, `can?`, `skip_before_action`, `allow_unauthenticated_access`
  * parsing    app/parsers/, a parser or importer class; JSON/YAML/Marshal/CSV/Nokogiri/Oj parsing, and strong parameters
               (`params.require`, `params.permit`)
  * privacy    the parameter-log filter, redact/mask/privacy/pii concerns; `filter_attributes`, `filter_parameters`, `encrypts`
  * (the one pattern list below is the whole definition; a path or line outside it is not risky)

THE RECORD. `--record` names the file the pass leaves. It counts only if it has a line `Head: <sha>` that is a prefix of the
CURRENT HEAD (a record for an earlier commit says nothing about this one) and ends with a line `VERDICT: CLEAN` or
`VERDICT: BLOCKED` (the LAST such line decides). BLOCKED is recorded and reported, never swallowed: the human decides.

LIMITS. This is a classifier over paths and added/removed lines, in the spirit of `classify_door.py`: a trigger is not proof of
a defect, and a risky change in a place the lists do not know is not caught. It cannot make a model follow the agent's
instructions; the record is a file the pass writes, and nothing here stops a session that writes one by hand.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_door import Unusable, diff  # noqa: E402  (one diff reader, not a copy that drifts)

_INIT = r"^config/initializers/(?:[^/]*[_-])?(?:auth|authentication|devise|omniauth|session_store|rack_attack|cors)(?:[_-][^/]*)?\.rb$"
PATHS: tuple[tuple[str, re.Pattern], ...] = (
    ("auth", re.compile(r"^app/controllers/concerns/authentication\.rb$|^app/controllers/(?:sessions|passwords|registrations|omniauth_callbacks)_controller\.rb$"
                        r"|^app/models/(?:session|current)\.rb$|" + _INIT)),
    ("access", re.compile(r"^app/policies/|^app/abilities?/|^app/models/ability\.rb$")),
    ("parsing", re.compile(r"^app/parsers?/|^(?:app|lib)/(?:[^/]+/)*[^/]*_(?:parser|importer)\.rb$")),
    ("privacy", re.compile(r"^config/initializers/filter_parameter_logging\.rb$|^app/models/concerns/[^/]*(?:redact|mask|privacy|pii)[^/]*\.rb$")),
)
LINES: tuple[tuple[str, re.Pattern], ...] = (
    ("auth", re.compile(r"\b(?:has_secure_password|authenticate_by|reset_session)\b|\bcookies\.(?:signed|encrypted)\b")),
    ("access", re.compile(r"\b(?:authorize!?|policy_scope|skip_before_action|allow_unauthenticated_access)\b|\bcan\?|\bcannot\?")),
    ("parsing", re.compile(r"\b(?:JSON\.parse|YAML\.(?:load|unsafe_load)|Marshal\.load|CSV\.(?:parse|foreach)|Oj\.load)\b|\bNokogiri::|\bparams\.(?:require|permit)\b")),
    ("privacy", re.compile(r"\b(?:filter_attributes|filter_parameters)\b|^\s*encrypts\s")),
)
CODE_ROOTS = ("app/", "lib/", "config/")
VERDICT = re.compile(r"^VERDICT:\s*(CLEAN|BLOCKED)\s*$")
HEAD_LINE = re.compile(r"^Head:\s*([0-9a-f]{7,40})\s*$")


def classify(changes: dict[str, tuple[list[str], list[str]]]) -> list[str]:
    """One reason per (class, file). A spec or test file is never risky: it is the code under attack, not the attack surface."""
    reasons: list[str] = []
    for path, (added, removed) in sorted(changes.items()):
        if path.startswith(("spec/", "test/")) or "/spec/" in path or "/test/" in path:
            continue
        seen: set[str] = set()
        for cls, pattern in PATHS:
            if pattern.search(path) and cls not in seen:
                seen.add(cls)
                reasons.append(f"{cls:<8} {path}: a file on the {cls} surface changed")
        if path.endswith(".rb") and path.startswith(CODE_ROOTS):
            for cls, pattern in LINES:
                if cls in seen:
                    continue
                hit = next((line.strip() for line in added + removed if pattern.search(line)), None)
                if hit:
                    seen.add(cls)
                    reasons.append(f"{cls:<8} {path}: {hit[:70]}")
    return reasons


def head_sha(root: Path) -> str:
    proc = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise Unusable(f"git rev-parse HEAD: {proc.stderr.strip() or 'failed'}")
    return proc.stdout.strip()


def read_record(path: Path, head: str) -> tuple[str, str]:
    """(kind, detail): kind is CLEAN or BLOCKED for a usable record of THIS head, else missing / no-head / stale / no-verdict."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", f"no record at {path}"
    except (OSError, UnicodeDecodeError) as exc:
        return "no-verdict", f"{path} could not be read: {exc}"
    lines = text.splitlines()
    heads = [m.group(1) for line in lines if (m := HEAD_LINE.match(line.strip()))]
    if not heads:
        return "no-head", f"{path} has no `Head: <sha>` line, so it cannot be tied to this commit"
    if not any(head.startswith(h) for h in heads):
        return "stale", f"{path} is for {heads[-1][:12]}, and HEAD is {head[:12]}"
    verdicts = [m.group(1) for line in lines if (m := VERDICT.match(line.strip()))]
    if not verdicts:
        return "no-verdict", f"{path} ends with no `VERDICT: CLEAN` or `VERDICT: BLOCKED` line"
    return verdicts[-1], f"{path}: VERDICT: {verdicts[-1]}"


def decide(reasons: list[str], record: Path | None, head: str | None) -> tuple[int, list[str]]:
    """(exit code, lines to print): the whole decision, apart from reading the diff."""
    if not reasons:
        return 0, ["NOT RISKY -- nothing in the diff touches auth, access, parsing or privacy by these rules"]
    body = [f"  {r}" for r in reasons]
    if record is None or head is None:
        return 1, [f"RISKY ({len(reasons)} reason(s)) -- run the `adversary` agent (model: fable) and record its verdict:", *body]
    kind, detail = read_record(record, head)
    if kind == "CLEAN":
        return 0, [f"RISKY ({len(reasons)} reason(s)), adversary pass recorded: {detail}", *body]
    if kind == "BLOCKED":
        return 3, [f"RISKY ({len(reasons)} reason(s)), adversary pass recorded BLOCKED -- a finding for a human to decide: {detail}", *body]
    return 1, [f"RISKY ({len(reasons)} reason(s)), and the record is not usable ({kind}: {detail}) -- run the `adversary` agent on this HEAD:", *body]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="risky_diff.py", description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="dev")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--record", type=Path, help="the file the adversary pass writes: docs/evidence/reviews/prs/<slug>/adversary.md")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        reasons = classify(diff(a.root, a.base))
        head = head_sha(a.root) if a.record else None
    except Unusable as exc:
        print(f"UNUSABLE: {exc} -- an unclassified diff is not 'not risky'; run the adversary pass", file=sys.stderr)
        return 2
    code, lines = decide(reasons, (a.root / a.record) if a.record and not a.record.is_absolute() else a.record, head)
    print("\n".join(lines))
    return code


def selftest() -> int:
    import tempfile

    failures: list[str] = []
    checks = [0]

    def expect(label: str, ok: bool, detail: object = "") -> None:
        checks[0] += 1
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        import fixture_git as _fg  # the fixture's git touches only its own temp repo (#1588)
        g = lambda *a: _fg.run(root, *a)
        _fg.init(root, "-b", "dev")
        (root / "app/models").mkdir(parents=True)
        (root / "app/models/invoice.rb").write_text("class Invoice\nend\n")
        g("add", "."); g("commit", "-q", "-m", "base")
        g("checkout", "-q", "-b", "feature/x")

        def case(label: str, files: dict[str, str], want: str | None) -> None:
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body)
            reasons = classify(diff(root, "dev"))
            ok = (not reasons) if want is None else any(r.startswith(want) for r in reasons)
            expect(label, ok, reasons)
            g("add", "."); g("reset", "-q", "--hard", "HEAD")

        # by PATH
        case("the authentication concern is risky", {"app/controllers/concerns/authentication.rb": "x\n"}, "auth")
        case("a sessions controller is risky", {"app/controllers/sessions_controller.rb": "x\n"}, "auth")
        case("the Session model is risky", {"app/models/session.rb": "x\n"}, "auth")
        case("a devise initializer is risky", {"config/initializers/devise.rb": "x\n"}, "auth")
        case("a policy is risky", {"app/policies/invoice_policy.rb": "x\n"}, "access")
        case("a parser class is risky", {"app/services/csv_importer.rb": "x\n"}, "parsing")
        case("the parameter-log filter is risky", {"config/initializers/filter_parameter_logging.rb": "x\n"}, "privacy")
        # by LINE
        case("has_secure_password is risky", {"app/models/user.rb": "class User\n  has_secure_password\nend\n"}, "auth")
        case("authorize is risky", {"app/controllers/invoices_controller.rb": "authorize @invoice\n"}, "access")
        case("skip_before_action is risky", {"app/controllers/pages_controller.rb": "skip_before_action :authenticate\n"}, "access")
        case("JSON.parse is risky", {"app/services/feed.rb": "JSON.parse(body)\n"}, "parsing")
        case("strong parameters are risky", {"app/controllers/things_controller.rb": "params.require(:thing).permit(:a)\n"}, "parsing")
        case("encrypts is risky", {"app/models/patient.rb": "class Patient\n  encrypts :ssn\nend\n"}, "privacy")
        # near misses: each is NOT risky
        case("CONTROL: an ordinary model change is not risky", {"app/models/invoice.rb": "class Invoice\n  def total = 1\nend\n"}, None)
        case("CONTROL: an initializer whose name merely contains `auth` (author_names) is not risky",
             {"config/initializers/author_names.rb": "x\n"}, None)
        case("CONTROL: app/models/session_replay.rb is not the Session model", {"app/models/session_replay.rb": "x\n"}, None)
        case("CONTROL: a spec that parses JSON is not risky", {"spec/services/feed_spec.rb": "JSON.parse(body)\n"}, None)
        case("CONTROL: a test that uses authorize is not risky", {"test/controllers/x_test.rb": "authorize @x\n"}, None)
        case("CONTROL: a comment-free non-code file mentioning JSON.parse is not risky", {"docs/notes.md": "JSON.parse\n"}, None)
        case("CONTROL: `authorized_users` is not `authorize`", {"app/services/report.rb": "authorized_users.map(&:name)\n"}, None)
        try:
            diff(root, "no-such-branch")
            expect("an unresolvable base is UNUSABLE, never not-risky", False)
        except Unusable:
            pass

        # THE RECORD
        head = head_sha(root)
        rec = root / "docs/evidence/reviews/prs/x/adversary.md"
        risky = ["auth     app/models/session.rb: a file on the auth surface changed"]

        def recorded(label: str, text: str | None, want: int, mark: str = "") -> None:
            if text is None:
                rec.unlink(missing_ok=True)
            else:
                rec.parent.mkdir(parents=True, exist_ok=True)
                rec.write_text(text)
            code, lines = decide(risky, rec, head)
            expect(label, code == want and (not mark or mark in "\n".join(lines)), f"{code} {lines}")

        recorded("a risky diff with no record needs the pass (exit 1)", None, 1, "missing")
        recorded("a CLEAN record for this HEAD passes (exit 0)", f"Head: {head}\nfindings: none\nVERDICT: CLEAN\n", 0)
        recorded("a CLEAN record naming a SHORT prefix of HEAD passes", f"Head: {head[:9]}\nVERDICT: CLEAN\n", 0)
        recorded("a BLOCKED record is a finding for a human, exit 3, never 0 and never 1", f"Head: {head}\nVERDICT: BLOCKED\n", 3, "human")
        recorded("the LAST verdict decides: BLOCKED after CLEAN is BLOCKED", f"Head: {head}\nVERDICT: CLEAN\nVERDICT: BLOCKED\n", 3)
        recorded("the LAST verdict decides: CLEAN after BLOCKED is CLEAN", f"Head: {head}\nVERDICT: BLOCKED\nVERDICT: CLEAN\n", 0)
        recorded("a record for another commit is stale (exit 1)", f"Head: {'0' * 40}\nVERDICT: CLEAN\n", 1, "stale")
        recorded("a record with no Head line is refused (exit 1)", "VERDICT: CLEAN\n", 1, "no-head")
        recorded("a record with no verdict line is refused (exit 1)", f"Head: {head}\nlooks fine\n", 1, "no-verdict")
        recorded("a verdict quoted inside a sentence is not a verdict line", f"Head: {head}\nthe pass said VERDICT: CLEAN here\n", 1, "no-verdict")
        recorded("an empty record is refused (exit 1)", "", 1)
        code, lines = decide([], rec, head)
        expect("a diff that is not risky needs no record (exit 0), even with a bad one on disk", code == 0, (code, lines))
        code, lines = decide(risky, None, None)
        expect("a risky diff with no --record asks for the pass (exit 1)", code == 1, (code, lines))

        # THE CLI, end to end on a real repo
        (root / "app/models/session.rb").write_text("class Session\nend\n")
        g("add", "."); g("commit", "-q", "-m", "risky")
        head2 = head_sha(root)
        rec.parent.mkdir(parents=True, exist_ok=True)
        base = [sys.executable, str(Path(__file__).resolve()), "--root", str(root), "--base", "dev"]
        for label, text, want in (("no record", None, 1), ("a CLEAN record for the new HEAD", f"Head: {head2}\nVERDICT: CLEAN\n", 0),
                                  ("a record for the OLD head", f"Head: {head}\nVERDICT: CLEAN\n", 1)):
            rec.unlink(missing_ok=True)
            if text is not None:
                rec.write_text(text)
            done = subprocess.run([*base, "--record", str(rec.relative_to(root))], capture_output=True, text=True)
            expect(f"CLI: {label} exits {want}", done.returncode == want, (done.returncode, done.stdout, done.stderr))
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--root", str(root), "--base", "no-such-branch"], capture_output=True, text=True)
        expect("CLI: an unresolvable base exits 2", done.returncode == 2 and "UNUSABLE" in done.stderr, (done.returncode, done.stderr))

    for f in failures:
        print(f"FAIL: {f}")
    print(f"risky_diff selftest: {checks[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
