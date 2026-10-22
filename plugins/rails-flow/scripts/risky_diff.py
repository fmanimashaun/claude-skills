#!/usr/bin/env python3
"""Decide whether a branch's diff is RISKY enough to need an adversarial pass, and whether that pass was recorded (#1819).

Run:  risky_diff.py [--base dev] [--root DIR] [--record docs/evidence/reviews/prs/<slug>/adversary.md]
      risky_diff.py --selftest
Exit: 0 not risky, or risky with a recorded `VERDICT: CLEAN` for this HEAD, or recorded BLOCKED with a valid `Override:` line
      1 risky and no usable record: run the `adversary` agent (model: fable) and record its verdict at --record;
        or the recorded verdict is BLOCKED with no valid override: a finding for a human to decide
      2 cannot classify (the base does not resolve, or no branch names the record): an unknown diff is not "not risky"
      Never 3 (#2264). `project_gates.py` grades a check's exit 3 as NOT APPLICABLE, which would pass a blocking finding (#1873), so a
      BLOCKED verdict is exit 1 unless a human decided, in the record, who decided it, why and under which issue.

HOW IT BINDS `gh pr ready` (#2264, the owner's rule that everything must be enforced). It is registered in `checks.json` (`adversary-review`),
so `project_gates.py` runs it, and `gh pr ready` is refused without a green sweep record for HEAD (`guard-pr-ready.sh`, #1565). With no
`--record` the record is `docs/evidence/reviews/prs/<branch-slug>/adversary.md`, where `<branch-slug>` is the branch name with each `/`
replaced by `-`, the prefix KEPT (`feature/x` is `feature-x`), the form `pr-reviewer`, `spec-reviewer` and the commands document and
agents already write. A branch with no name (a detached HEAD) cannot say where its record is: exit 2.

WHY (#1819, the owner's rule of 2026-10-08). Fable is the model for adversarial attack passes, the ones that try to break a change.
Retask sessions ran one by hand and recorded a "Fable adversary HOLDS" verdict on several PRs, so it depended on someone remembering.
This is the part of the remembering a script can do: say which diffs are risky, and whether the pass left its record. It is the
sibling of `classify_door.py` (is the change reversible) and `check_mockup_gate.py` (did a user-visible change get a mock-up).

RISKY means the diff touches one of four things, by PATH or by a line it adds or removes (never in spec/ or test/):
  * auth       the authentication concern, session and password controllers, the Session and Current models, an
               auth/devise/omniauth/session_store/rack_attack/cors initializer; `has_secure_password`, `authenticate_by`,
               `reset_session`, signed or encrypted cookies
  * access     app/policies/, abilities; `authorize`, `policy_scope`, `can?`, `skip_before_action`, `allow_unauthenticated_access`
  * parsing    app/parsers/, a parser or importer class; JSON/YAML/Marshal/CSV/Nokogiri/Oj parsing, and strong parameters
               (`params.require`, `params.permit`)
  * privacy    the parameter-log filter, redact/mask/privacy/pii concerns; `filter_attributes`, `filter_parameters`, `encrypts`
  The pattern lists below are the whole definition; a path or line outside them is not risky. A RENAME counts as a delete and an add
  (`--no-renames`), so moving a policy out of app/policies/ is still a change to it.

THE RECORD. `--record` names the file the pass leaves. It counts only if it has a line `Head: <sha>` that is a prefix of the
CURRENT HEAD (a record for an earlier commit says nothing about this one) and ends with a line `VERDICT: CLEAN` or
`VERDICT: BLOCKED` (the LAST such line decides). BLOCKED is recorded and reported, never swallowed: the human decides, by a line
`Override: <who> | <reason, 20+ characters, not filler> | #<issue>` in the same record (the form `advisory_scope.py` takes for RETHINK, #2262):
who made the call (at least two letters), why it stands, and an ISSUE (not a pull request) that `gh` can read in this repository, which carries
the follow-up. A new commit makes the record stale, so an override is for one HEAD. Lines inside a fenced code block are never read: a
pasted example of the format must not decide a verdict, name a head or grant an override.

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
import advisory_scope  # noqa: E402  (the override line, the filler test, the issue check and the branch slug have one home)

RECORD_DIR = "docs/evidence/reviews/prs"

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


def unfenced(text: str) -> list[str]:
    """The lines of `text` outside fenced code blocks (``` or ~~~; an unclosed fence runs to the end, so what follows it is refused, never read)."""
    out: list[str] = []
    fence = ""
    for line in text.splitlines():
        mark = line.strip()[:3]
        if mark in ("```", "~~~"):
            fence = "" if fence == mark else (fence or mark)
            continue
        if not fence:
            out.append(line)
    return out


def read_record(path: Path, head: str) -> tuple[str, str]:
    """(kind, detail): kind is CLEAN or BLOCKED for a usable record of THIS head, else missing / no-head / stale / no-verdict."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "missing", f"no record at {path}"
    except (OSError, UnicodeDecodeError) as exc:
        return "no-verdict", f"{path} could not be read: {exc}"
    lines = unfenced(text)
    heads = [m.group(1) for line in lines if (m := HEAD_LINE.match(line.strip()))]
    if not heads:
        return "no-head", f"{path} has no `Head: <sha>` line, so it cannot be tied to this commit"
    if not any(head.startswith(h) for h in heads):
        return "stale", f"{path} is for {heads[-1][:12]}, and HEAD is {head[:12]}"
    verdicts = [m.group(1) for line in lines if (m := VERDICT.match(line.strip()))]
    if not verdicts:
        return "no-verdict", f"{path} ends with no `VERDICT: CLEAN` or `VERDICT: BLOCKED` line"
    return verdicts[-1], f"{path}: VERDICT: {verdicts[-1]}"


def issue_readable(root: Path, ref: str) -> bool:
    """Whether `#n` is an ISSUE `gh` can read in the repository at `root` (not the working directory's): a pull request number reads too, and is no
    follow-up. False when it cannot be read (fails closed)."""
    try:
        proc = subprocess.run(["gh", "issue", "view", ref.lstrip("#"), "--json", "number,url"], capture_output=True, text=True, timeout=30, cwd=root)
        return proc.returncode == 0 and "/issues/" in proc.stdout
    except (OSError, subprocess.TimeoutExpired):
        return False


ISSUE_CHECK = issue_readable   # the selftest swaps in a stub, so it never calls the network
WHO_MIN_LETTERS = 2


def override_of(path: Path, root: Path) -> tuple[str, str] | None:
    """(who, #issue) of the first valid `Override:` line in the record, else None. `who` with fewer than two letters, a short or filler reason, a
    missing issue, a pull request number or an issue `gh` cannot read is no override: the decision has to name who, why and where the follow-up lives."""
    try:
        lines = unfenced(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        return None
    for line in lines:
        m = advisory_scope.OVERRIDE_RE.match(line) if line.strip().lower().startswith("override") else None
        if (m and sum(c.isalpha() for c in m.group(1)) >= WHO_MIN_LETTERS and len(m.group(2)) >= advisory_scope.REASON_MIN
                and not advisory_scope._filler(m.group(2)) and ISSUE_CHECK(root, m.group(3))):
            return m.group(1), m.group(3)
    return None


def branch_slug(root: Path) -> str:
    """The branch name with each `/` replaced by `-`, the prefix kept (`feature/x` is `feature-x`); "" on a detached HEAD."""
    out = subprocess.run(["git", "-C", str(root), "symbolic-ref", "--short", "-q", "HEAD"], capture_output=True, text=True).stdout.strip()
    return out.replace("/", "-")


def default_record(root: Path) -> Path:
    """`docs/evidence/reviews/prs/<branch-slug>/adversary.md` for the branch HEAD is on; Unusable when HEAD is on no branch."""
    slug = branch_slug(root)
    if not slug:
        raise Unusable("HEAD is on no branch, so there is no <branch-slug> to name the record (pass --record)")
    return Path(RECORD_DIR) / slug / "adversary.md"


def resolve_base(root: Path, base: str) -> str:
    """`base` if it resolves here, else `origin/<base>` (a CI checkout often has only the remote ref); the first, so the error names it."""
    for candidate in (base, f"origin/{base}"):
        if subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", f"{candidate}^{{commit}}"], capture_output=True).returncode == 0:
            return candidate
    return base


def decide(reasons: list[str], record: Path | None, head: str | None, root: Path = Path(".")) -> tuple[int, list[str]]:
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
        decided = override_of(record, root)
        if decided:
            return 0, [f"RISKY ({len(reasons)} reason(s)), adversary pass recorded BLOCKED and overridden by {decided[0]} ({decided[1]}): {detail}", *body]
        return 1, [f"RISKY ({len(reasons)} reason(s)), adversary pass recorded BLOCKED -- a finding for a human to decide: fix it and run the pass on the new HEAD, "
                   f"or record `Override: <who> | <reason, {advisory_scope.REASON_MIN}+ characters> | #<issue>` in the record: {detail}", *body]
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
        reasons = classify(diff(a.root, resolve_base(a.root, a.base)))
        record = a.record if a.record else (default_record(a.root) if reasons else None)
        head = head_sha(a.root) if reasons else None
    except Unusable as exc:
        print(f"UNUSABLE: {exc} -- an unclassified diff is not 'not risky'; run the adversary pass", file=sys.stderr)
        return 2
    code, lines = decide(reasons, (a.root / record) if record and not record.is_absolute() else record, head, a.root)
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
            before = {rel: ((root / rel).read_text() if (root / rel).exists() else None) for rel in files}
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body)
            reasons = classify(diff(root, "dev"))
            ok = (not reasons) if want is None else any(r.startswith(want) for r in reasons)
            expect(label, ok, reasons)
            # No `reset --hard`: run from the Claude Code Bash tool the git shim refuses it, and the fixture needs only its own files put back (#1982).
            g("reset", "-q")
            for rel, text in before.items():
                if text is None:
                    (root / rel).unlink()
                else:
                    (root / rel).write_text(text)

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
        case("CONTROL: an initializer ending in `auth` with no separator (coauth) is not risky", {"config/initializers/coauth.rb": "x\n"}, None)
        case("an initializer with an auth prefix word (app_auth) is risky", {"config/initializers/app_auth.rb": "x\n"}, "auth")
        case("an initializer with an auth suffix word (auth_settings) is risky", {"config/initializers/auth_settings.rb": "x\n"}, "auth")
        case("CONTROL: app/models/session_replay.rb is not the Session model", {"app/models/session_replay.rb": "x\n"}, None)
        case("CONTROL: a spec that parses JSON is not risky", {"spec/services/feed_spec.rb": "JSON.parse(body)\n"}, None)
        # the paths below are on a risky surface or parse JSON, so only the spec/test skip keeps them out
        case("CONTROL: a file under a nested /spec/ directory is not risky even when it parses JSON",
             {"lib/spec/feed.rb": "JSON.parse(body)\n"}, None)
        case("CONTROL: a file under a nested /test/ directory is not risky even when it parses JSON",
             {"lib/test/feed.rb": "JSON.parse(body)\n"}, None)
        case("CONTROL: a policy-surface path under /spec/ is not risky", {"app/policies/spec/helper.rb": "x\n"}, None)
        case("CONTROL: a test that uses authorize is not risky", {"test/controllers/x_test.rb": "authorize @x\n"}, None)
        case("CONTROL: a comment-free non-code file mentioning JSON.parse is not risky", {"docs/notes.md": "JSON.parse\n"}, None)
        case("CONTROL: `authorized_users` is not `authorize`", {"app/services/report.rb": "authorized_users.map(&:name)\n"}, None)
        # (review of #1834) a rename out of a guarded path, a non-ASCII path, and a path git quotes
        (root / "app/policies").mkdir(parents=True, exist_ok=True)
        (root / "app/policies/p_policy.rb").write_text("def show? = false\n")
        g("checkout", "-q", "dev")      # the policy exists on the BASE; the branch then moves it
        g("add", "."); g("commit", "-q", "-m", "policy")
        g("checkout", "-q", "-B", "feature/y")
        (root / "app/services").mkdir(parents=True, exist_ok=True)
        g("mv", "app/policies/p_policy.rb", "app/services/p.rb")
        expect("a policy RENAMED out of app/policies is risky (access)", any(r.startswith("access") for r in classify(diff(root, "dev"))),
               classify(diff(root, "dev")))
        g("mv", "app/services/p.rb", "app/policies/p_policy.rb")      # put the rename back (no `reset --hard`, see above)
        (root / "app/policies/\u00e9.rb").write_text("x\n")
        expect("a NON-ASCII path under app/policies is risky, not dropped", any(r.startswith("access") for r in classify(diff(root, "dev"))))
        (root / "app/policies/\u00e9.rb").unlink()
        (root / "app/policies/a\"b.rb").write_text("x\n")
        g("add", "."); g("commit", "-q", "-m", "quoted")
        try:
            diff(root, "dev")
            expect("a path git quotes is UNUSABLE, never silently dropped", False)
        except Unusable:
            pass
        g("reset", "-q", "HEAD~1")
        (root / "app/policies/a\"b.rb").unlink()
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
        recorded("a BLOCKED record with no override is a finding for a human, exit 1: never 0, and never 3, which the project gates read as n/a (#1873)",
                 f"Head: {head}\nVERDICT: BLOCKED\n", 1, "human")
        recorded("the LAST verdict decides: BLOCKED after CLEAN is BLOCKED", f"Head: {head}\nVERDICT: CLEAN\nVERDICT: BLOCKED\n", 1, "BLOCKED")
        recorded("a record for another commit is stale (exit 1)", f"Head: {'0' * 40}\nVERDICT: CLEAN\n", 1, "stale")
        recorded("a record with no Head line is refused (exit 1)", "VERDICT: CLEAN\n", 1, "no-head")
        recorded("a record with no verdict line is refused (exit 1)", f"Head: {head}\nlooks fine\n", 1, "no-verdict")
        recorded("a verdict quoted inside a sentence is not a verdict line", f"Head: {head}\nthe pass said VERDICT: CLEAN\n", 1, "no-verdict")
        recorded("an empty record is refused (exit 1)", "", 1)
        # THE OVERRIDE (#2264): who decided, why (20+ characters, not filler), and an issue that can be read. Only #9 "exists" here.
        global ISSUE_CHECK
        saved_check, ISSUE_CHECK = ISSUE_CHECK, (lambda where, ref: ref == "#9")
        try:
            blocked = f"Head: {head}\nVERDICT: BLOCKED\n"
            recorded("BLOCKED with a full override (who, a real reason, a readable issue) passes", blocked + "Override: owner | the finding is accepted for this release, see the issue | #9\n", 0, "overridden by owner")
            recorded("BLOCKED with an override whose reason is short is refused", blocked + "Override: owner | fine | #9\n", 1)
            recorded("BLOCKED with an override whose reason is filler is refused", blocked + "Override: owner | " + "n/a " * 6 + "| #9\n", 1)
            recorded("BLOCKED with an override and no issue is refused", blocked + "Override: owner | the finding is accepted for this release\n", 1)
            recorded("BLOCKED with an override citing an issue that cannot be read is refused", blocked + "Override: owner | the finding is accepted for this release | #404\n", 1)
            recorded("BLOCKED with an override that names nobody is refused", blocked + "Override:  | the finding is accepted for this release | #9\n", 1)
            recorded("an override is not a verdict: a record with only an override line is refused", f"Head: {head}\nOverride: owner | the finding is accepted for this release | #9\n", 1, "no-verdict")
            recorded("a stale record's override is no override (the record is for another head)", f"Head: {'0' * 40}\nVERDICT: BLOCKED\nOverride: owner | the finding is accepted for this release | #9\n", 1, "stale")
            recorded("BLOCKED with an override whose who has one letter is refused", blocked + "Override: x | the finding is accepted for this release | #9\n", 1)
            recorded("BLOCKED with an override whose who has no letters is refused", blocked + "Override: 12 | the finding is accepted for this release | #9\n", 1)
            # a fenced example never decides anything (c2 review, suggestion 3)
            recorded("a VERDICT line inside a fenced block is not the verdict", f"Head: {head}\n```\nVERDICT: CLEAN\n```\n", 1, "no-verdict")
            recorded("a fenced CLEAN after a real BLOCKED does not turn it CLEAN", f"Head: {head}\nVERDICT: BLOCKED\n~~~\nVERDICT: CLEAN\n~~~\n", 1, "BLOCKED")
            recorded("a Head line inside a fenced block is no Head", f"```\nHead: {head}\n```\nVERDICT: CLEAN\n", 1, "no-head")
            recorded("an override inside a fenced block grants nothing", blocked + "```\nOverride: owner | the finding is accepted for this release | #9\n```\n", 1)
            recorded("an unclosed fence hides everything after it", f"Head: {head}\n```\nVERDICT: CLEAN\n", 1, "no-verdict")
            recorded("text after a closed fence is read again", f"Head: {head}\n```\nexample\n```\nVERDICT: CLEAN\n", 0)
        finally:
            ISSUE_CHECK = saved_check
        recorded("the LAST verdict decides: CLEAN after BLOCKED is CLEAN", f"Head: {head}\nVERDICT: BLOCKED\nVERDICT: CLEAN\n", 0)
        code, lines = decide([], rec, head)
        expect("a diff that is not risky needs no record (exit 0), even with a bad one on disk", code == 0, (code, lines))
        code, lines = decide(risky, None, None)
        expect("a risky diff with no --record asks for the pass (exit 1)", code == 1, (code, lines))

        # THE ISSUE CHECK itself (c2 review, suggestion 2): an ISSUE in the repository at --root, not a pull request, not the cwd's repository.
        import os, stat
        bin_dir = root / "stub-bin"
        bin_dir.mkdir()
        stub = bin_dir / "gh"
        stub.write_text('#!/bin/sh\npwd > "$STUB_CWD"\ncase "$3" in\n  9) echo \'{"number":9,"url":"https://github.com/o/r/issues/9"}\' ;;\n'
                        '  10) echo \'{"number":10,"url":"https://github.com/o/r/pull/10"}\' ;;\n  *) exit 1 ;;\nesac\n')
        stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
        saved_path, saved_cwd = os.environ.get("PATH", ""), os.environ.get("STUB_CWD")
        os.environ["PATH"], os.environ["STUB_CWD"] = f"{bin_dir}:{saved_path}", str(root / "stub-cwd.txt")
        try:
            expect("an issue gh can read counts", issue_readable(root, "#9"))
            expect("it is read in the repository at --root, not the caller's working directory",
                   (root / "stub-cwd.txt").read_text().strip() == str(root.resolve()), (root / "stub-cwd.txt").read_text())
            expect("a pull request number is no issue (gh reads it, and it carries no follow-up)", not issue_readable(root, "#10"))
            expect("an issue gh cannot read does not count", not issue_readable(root, "#404"))
        finally:
            os.environ["PATH"] = saved_path
            if saved_cwd is None:
                os.environ.pop("STUB_CWD", None)
            else:
                os.environ["STUB_CWD"] = saved_cwd

        # THE CLI, end to end on a real repo
        (root / "app/models/session.rb").write_text("class Session\nend\n")
        g("add", "."); g("commit", "-q", "-m", "risky")
        head2 = head_sha(root)
        rec.parent.mkdir(parents=True, exist_ok=True)
        base = [sys.executable, str(Path(__file__).resolve()), "--root", str(root), "--base", "dev"]
        # with --record, and (#2264) with NO flag: the record is derived from the branch, feature/y is `feature-y`, so `rec` (…/prs/x/…) is NOT it
        derived = root / "docs/evidence/reviews/prs/feature-y/adversary.md"   # the documented <branch-slug>: `/` becomes `-`, the prefix kept
        for label, text, want in (("no record", None, 1), ("a CLEAN record for the new HEAD", f"Head: {head2}\nVERDICT: CLEAN\n", 0),
                                  ("a record for the OLD head", f"Head: {head}\nVERDICT: CLEAN\n", 1),
                                  ("a BLOCKED record with no override", f"Head: {head2}\nVERDICT: BLOCKED\n", 1)):
            for path, flags in ((rec, ["--record", str(rec.relative_to(root))]), (derived, [])):
                rec.unlink(missing_ok=True)
                derived.unlink(missing_ok=True)
                if text is not None:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(text)
                done = subprocess.run([*base, *flags], capture_output=True, text=True)
                expect(f"CLI: {label} exits {want} ({'--record' if flags else 'record derived from the branch'})", done.returncode == want,
                       (done.returncode, done.stdout, done.stderr))
        rec.unlink(missing_ok=True)
        derived.unlink(missing_ok=True)
        done = subprocess.run([*base], capture_output=True, text=True)
        expect("CLI: the record owed is named after the branch (…/prs/feature-y/adversary.md), not left to the caller", "prs/feature-y/adversary.md" in done.stdout, done.stdout)
        # the OLD form (prefix dropped) is not where the documented agents write: a CLEAN record there is not found
        old_form = root / "docs/evidence/reviews/prs/y/adversary.md"
        old_form.parent.mkdir(parents=True, exist_ok=True)
        old_form.write_text(f"Head: {head2}\nVERDICT: CLEAN\n")
        done = subprocess.run([*base], capture_output=True, text=True)
        expect("CLI: a record at the prefix-dropped path (prs/y/) is not the record: exit 1", done.returncode == 1, (done.returncode, done.stdout))
        old_form.unlink()
        expect("CLI: a risky diff with no record and no flag exits 1 and says where the record goes", done.returncode == 1, (done.returncode, done.stdout))
        # THE SWEEP (#2264): the check is REGISTERED, so `project_gates.py` runs it. Run the registered row's own command in the fixture:
        # a risky diff with no record must turn it red (exit 1), and a CLEAN record for HEAD must turn it green.
        import json
        manifest = json.loads((Path(__file__).resolve().parents[1] / "checks.json").read_text(encoding="utf-8"))
        rows = [c for c in manifest["checks"] if c["id"] == "adversary-review"]
        expect("the check is registered in checks.json as `adversary-review`, once", len(rows) == 1, [c["id"] for c in manifest["checks"]])
        if rows:
            row = rows[0]
            argv = [sys.executable if tok == "python3" else tok.replace("{plugin}", str(Path(__file__).resolve().parents[1])) for tok in row["command"]]
            expect("the registered row needs no flag: the record is derived from the branch", argv[1:] == [str(Path(__file__).resolve())], argv)
            expect("the registered row applies where app/ exists", row.get("applies_when") == ["app"], row.get("applies_when"))
            derived.unlink(missing_ok=True)
            done = subprocess.run(argv, capture_output=True, text=True, cwd=root)
            expect("SWEEP: the registered row is red on a risky diff with no record", done.returncode == 1, (done.returncode, done.stdout))
            derived.parent.mkdir(parents=True, exist_ok=True)
            derived.write_text(f"Head: {head2}\nVERDICT: CLEAN\n")
            done = subprocess.run(argv, capture_output=True, text=True, cwd=root)
            expect("SWEEP: the registered row is green with a CLEAN record for HEAD", done.returncode == 0, (done.returncode, done.stdout))
            derived.write_text(f"Head: {head2}\nVERDICT: BLOCKED\n")
            done = subprocess.run(argv, capture_output=True, text=True, cwd=root)
            expect("SWEEP: the registered row is red on BLOCKED, never exit 3 (n/a to the project gates, #1873)", done.returncode == 1, (done.returncode, done.stdout))
            derived.unlink(missing_ok=True)
        g("update-ref", "refs/remotes/origin/only-remote", "dev")      # a base that exists only as a remote-tracking ref (a CI checkout)
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--root", str(root), "--base", "only-remote"], capture_output=True, text=True)
        expect("CLI: a base that exists only as origin/<base> still resolves (exit 1: risky, no record), not exit 2", done.returncode == 1, (done.returncode, done.stderr))
        g("checkout", "-q", "--detach")
        done = subprocess.run([*base], capture_output=True, text=True)
        expect("CLI: a detached HEAD cannot name its record, exit 2 (never 'not risky')", done.returncode == 2 and "no branch" in done.stderr, (done.returncode, done.stderr))
        g("checkout", "-q", "feature/y")
        done = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--root", str(root), "--base", "no-such-branch"], capture_output=True, text=True)
        expect("CLI: an unresolvable base exits 2", done.returncode == 2 and "UNUSABLE" in done.stderr, (done.returncode, done.stderr))

    for f in failures:
        print(f"FAIL: {f}")
    print(f"risky_diff selftest: {checks[0]} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
