#!/usr/bin/env python3
"""Cross-session coordination, computed from the repository instead of remembered (#1010).

`parallel-session-lane` is good doctrine and nothing runs it. Coordination fell to whichever
session took it on, by hand and reactively, and the failures were all POLLING GAPS: the
information existed, in git or in the session list, and nobody looked. Six of them in one day —
two PRs finished with their authors idle; two escalations at sessions whose work was proceeding
normally; `dev` carried at a SHA it had left hours earlier; decision numbers recited from memory
when a git query knew better.

WHAT THIS IS. A read-only reporter that crosses the session list against the forge and prints
findings, each carrying the command that produced it. It is the measuring half of a coordinator;
the deciding half is a session reading this output and sending messages.

WHY A SCRIPT AND NOT AN AGENT PROMPT. #1010's acceptance says the coordinator "cannot merge a PR
or write to a repository -- ENFORCED, not documented". An instruction in a command file is
documented. So every subprocess this module runs goes through `run()`, which refuses any
invocation not on `READ_ONLY`, and `--selftest` proves the refusal fires on `gh pr merge`,
`git push` and `git commit`. Authority over other sessions is messages, and messages are the
caller's to send.

WHY IT DOES NOT POLL BY ITSELF. The skill says "no tmux and no daemon", which is about not
REQUIRING infrastructure. This requires none: it is one command with no state and no server. A
session that chooses to re-run it on a timer is the operator's decision, and a supported one --
but nothing here depends on that choice, so a machine with no scheduler loses nothing.

THE CHARACTERISTIC FAILURE IS A FALSE ESCALATION, not a missed defect: chasing a session whose
work is proceeding normally. A wrong age is indistinguishable from a real stall except in the
number, and the number is the one thing a human reading a board will not re-derive. The day this
was written produced two false escalations inside five minutes from one unit error -- a local WAT
clock compared against UTC timestamps from the forge, so "70 minutes" was 13 and "90" was 33.
Hence `age_minutes` REFUSES a naive clock rather than assuming one, and the selftest asserts the
13-minute PR produces no stall finding at all.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from fnmatch import fnmatch
from pathlib import Path

# -------------------------------------------------------------------------------------------
# The read-only boundary. This is the enforcement the issue asks for.
# -------------------------------------------------------------------------------------------

# (binary, subcommand, sub-subcommand or None). Exact tuples, hand-declared: a prefix rule like
# "any `gh pr`" would admit `gh pr merge`, which is precisely the authority this must not have.
READ_ONLY: frozenset[tuple[str, ...]] = frozenset({
    ("git", "log"), ("git", "diff"), ("git", "show"), ("git", "rev-parse"), ("git", "merge-base"),
    ("git", "for-each-ref"), ("git", "grep"), ("git", "status"), ("git", "ls-files"),
    ("gh", "pr", "list"), ("gh", "pr", "view"), ("gh", "pr", "checks"), ("gh", "pr", "diff"),
    ("gh", "issue", "list"), ("gh", "issue", "view"), ("gh", "run", "list"),
})

# Everything a caller might reach for that would make this an actor rather than a reporter. Named
# explicitly so the selftest can prove the refusal, rather than trusting the allowlist's shape.
WRITE_VERBS: tuple[tuple[str, ...], ...] = (
    ("gh", "pr", "merge"), ("gh", "pr", "create"), ("gh", "pr", "close"), ("gh", "pr", "comment"),
    ("gh", "issue", "close"), ("gh", "issue", "comment"), ("gh", "release", "create"),
    ("git", "push"), ("git", "commit"), ("git", "add"), ("git", "checkout"), ("git", "merge"),
    ("git", "rebase"), ("git", "worktree"), ("git", "reset"), ("git", "restore"),
)


class WriteAttempted(RuntimeError):
    """Raised when something asks this module to act on the world instead of read it."""


class ReadFailed(RuntimeError):
    """A read-only command that did not succeed, CARRYING ITS RETURN CODE.

    The code is the whole point (#1018). `git grep` exits 1 on "no match" and 128 on "your pattern
    has unbalanced brackets"; catching the exception type alone folds a fatal error into the
    no-match bucket and reports "matched nothing on any remote ref" about a search that never ran.
    A session then concludes no numbers are claimed and takes one that is — with a false "I asked
    git" behind it, which is worse than not asking.
    """

    def __init__(self, argv: list[str], returncode: int, stderr: str):
        super().__init__(f"{' '.join(argv)} failed (exit {returncode}): {stderr.strip()[:200]}")
        self.returncode = returncode


def _key(argv: list[str]) -> tuple[str, ...]:
    """The allowlist key: two tokens for `git`, three for `gh` (its verbs are one level deeper)."""
    depth = 3 if argv and argv[0] == "gh" else 2
    return tuple(argv[:depth])


def run(argv: list[str], cwd: Path, execute=subprocess.run) -> str:
    """A read-only subprocess, or an exception. The output is discarded on failure, never guessed.

    `execute` is injected for one reason: the selftest attempts every write verb with a spy that
    raises if it is ever called, so "the boundary refused it" is proved by NOTHING RUNNING rather
    than by an exception that might have come from the command failing. A test that proves a merge
    was refused by running the merge is not a test.

    A failing read is NOT an empty read: `gh` unauthenticated returns nothing in exactly the shape
    of "no open pull requests", and a coordinator that reports the second when the first is true is
    worse than one that reports nothing.
    """
    if _key(argv) not in READ_ONLY:
        raise WriteAttempted(
            f"refused: {' '.join(argv[:3])} is not on the read-only allowlist. This module reports; "
            "acting on another session's work is the caller's to do, with a message."
        )
    result = execute(argv, cwd=cwd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise ReadFailed(argv, result.returncode, result.stderr)
    return result.stdout


# -------------------------------------------------------------------------------------------
# Time. Computed, never eyeballed.
# -------------------------------------------------------------------------------------------

def age_minutes(created_iso: str, now: datetime) -> int:
    """Whole minutes between an ISO-8601 UTC timestamp and `now`, which MUST be timezone-aware.

    The refusal is the point. `datetime.now()` is naive local; the forge returns UTC; subtracting
    one from the other is silent and off by the offset -- sixty minutes here, which turned a
    13-minute-old PR into "70 minutes" and produced two escalations that had to be walked back.
    A naive clock is therefore an error, not an assumption.
    """
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError(
            "age_minutes needs a timezone-aware clock: a naive one is how a 13-minute PR was "
            "reported as 70. Pass datetime.now(timezone.utc)."
        )
    created = datetime.fromisoformat(created_iso.replace("Z", "+00:00"))
    if created.tzinfo is None:
        raise ValueError(f"{created_iso!r} carries no timezone; the forge always sends one")
    return int((now - created).total_seconds() // 60)


# -------------------------------------------------------------------------------------------
# What counts as generated. Hand-declared, like doctrine_map's CLAIMS.
# -------------------------------------------------------------------------------------------

# A conflict in a generated file is not a judgement -- regenerate it and the question disappears.
# Resolving one by hand nearly deleted a subsystem from an architecture graph. A conflict in an
# authored file IS a judgement and belongs to its author; this module's job is saying which is
# which, and never choosing for them.
#
# Hand-declared rather than derived from the generators, deliberately: deriving it would make this
# a check on the INDEX of the generated set rather than on the set, which is the defect class that
# produced #1006 and #1008 in one afternoon.
#
# THE COST OF THAT CHOICE IS REAL AND IS PAID HERE. The first version of this list was two entries
# short, and a peer deriving the set from the generators caught it within the hour. So: re-derive
# against `scripts/rebuild_generated.py` whenever a generator is added, and treat a path that is
# generated but absent from this list as the failure mode -- it sends someone to hand-resolve a
# file whose conflict is not a judgement at all.
GENERATED: tuple[tuple[str, str], ...] = (
    ("docs/wiki/*.md", "python3 scripts/build_wiki.py"),
    ("docs/architecture/doctrine-map.html", "python3 scripts/doctrine_map.py"),
    ("docs/evidence/coverage.html", "python3 scripts/build_coverage_artifact.py"),
    ("dist/*.skill", "python3 scripts/package_core.py"),
    (".claude/skills/*/SKILL.md", "python3 scripts/build_maintainer_skills.py"),
    # Both of these were missing from the first hand-written list, and a peer deriving the set from
    # the generators found them. The first is the expensive one to get wrong: it lives under
    # `plugins/`, so a rule of thumb like "everything under plugins/ is authored" sends someone to
    # hand-resolve a file they should regenerate.
    ("plugins/rails-flow/mandated_gems.json", "python3 scripts/derive_mandated_gems.py"),
    ("skills/design-system/references/coverage.md", "python3 scripts/build_coverage.py"),
    ("db/schema.rb", "bin/rails db:migrate"),
    ("docs/architecture/*.svg", "the architecture graph builder"),
)


def load_generated(declared: Path | None) -> tuple[tuple[str, str], ...]:
    """`GENERATED`, plus whatever the project declares in a JSON file of {glob: command}.

    THE DEFAULTS ARE THIS MARKETPLACE'S, AND THIS SCRIPT SHIPS. A downstream Rails app has
    `db/schema.rb` and none of `docs/wiki/`, `dist/*.skill` or `.claude/skills/` — so a built-in
    list is a starting point and never the answer. A project declares its own, and the two are
    merged with the project's entries LAST so they win.

    Suggested by a peer that this read the maintainer repo's `scripts/rebuild_generated.py`, whose
    `BUILDERS` now carries each generator's output paths. It cannot: that script is maintainer-only
    and this one is shipped inside `rails-flow`, so importing it would break for every downstream
    installation — the same per-audience boundary that kept the HEAD-read helper unextracted. A
    maintainer who wants that list here can generate the JSON from `BUILDERS` and pass it.
    """
    if declared is None:
        return GENERATED
    extra = json.loads(declared.read_text(encoding="utf-8"))
    return GENERATED + tuple((str(k), str(v)) for k, v in extra.items())


def regenerator(path: str, generated: tuple[tuple[str, str], ...] = GENERATED) -> str | None:
    """The command that rebuilds `path`, or None when the file is authored."""
    for pattern, command in generated:
        if fnmatch(path, pattern):
            return command
    return None


# -------------------------------------------------------------------------------------------
# Findings
# -------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Finding:
    """One thing worth a message, and the command that proves it.

    `command` is not decoration. Every correction that stuck between sessions on the day this was
    written carried the command that produced it, and every one that did not was re-litigated.
    """

    kind: str
    subject: str
    detail: str
    command: str
    to: str | None = None          # the session this should be said to, when there is one

    def render(self) -> str:
        who = f" -> {self.to}" if self.to else ""
        return f"[{self.kind}]{who} {self.subject}\n    {self.detail}\n    $ {self.command}"


@dataclass
class Session:
    """A peer, as `ListAgents` describes it plus what it announced under §2."""

    name: str
    state: str = "unknown"           # idle | busy | unknown
    repo: str | None = None          # the repository it is authorised in
    paths: list[str] = field(default_factory=list)   # announced under §2, moment 1
    branch: str | None = None

    @property
    def idle(self) -> bool:
        return self.state.lower() == "idle"


# Exactly what `gh pr list` is asked for, as a constant rather than a string literal inside the
# call. A fixture that invents a field the collector never emits tests a PR that cannot exist, and
# that is how the idle-guard below sat dead through a green selftest (#1018): every fixture set a
# `session` key by hand, and `gh` has never produced one.
COLLECTED_FIELDS: tuple[str, ...] = (
    "number", "title", "createdAt", "mergeStateStatus", "headRefName", "author",
)


# A PR younger than this is proceeding normally, not stalled. The number is a floor on how long CI
# takes to answer: the two false escalations were at 13 and 33 minutes, both of which were CI and
# review latency rather than a stall.
STALL_MINUTES = 45


def branch_key(name: str | None) -> str | None:
    """A branch name in the one spelling both sides can be compared in.

    A session announcing `origin/fix/a` and a PR reporting `fix/a` are the same branch, and an exact
    join reads the second as unannounced — which produces a `parked` finding against a session that
    is busy and working. That is the characteristic failure through a narrower door than #1018's,
    and it costs two lines to close. Found by QA driving the join rather than reading it.
    """
    if not name:
        return None
    for prefix in ("refs/heads/", "refs/remotes/", "origin/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name or None


def branch_claimants(sessions: list[Session]) -> dict[str, list[Session]]:
    """Every session that announced each branch, normalised. More than one is a finding."""
    claims: dict[str, list[Session]] = {}
    for session in sessions:
        key = branch_key(session.branch)
        if key:
            claims.setdefault(key, []).append(session)
    return claims


def branch_collisions(sessions: list[Session]) -> list[Finding]:
    """Two sessions claiming ONE branch — the cheapest detector for the day's actual incident.

    `path_collisions` compares announced paths and cannot see this. Twice in one afternoon a session
    arrived on a branch a peer had pushed and read its open PR as its own work, and a second read a
    peer's uncommitted file the same way. Both were branch-level collisions that no path list
    predicted, because neither session had announced a path yet.
    """
    findings = []
    for branch, claiming in sorted(branch_claimants(sessions).items()):
        if len(claiming) < 2:
            continue
        names = ", ".join(s.name for s in claiming)
        findings.append(Finding(
            kind="collision-branch",
            subject=f"{len(claiming)} sessions claim branch {branch}: {names}",
            detail="one branch means one HEAD and one index — agree who holds it before either "
                   "commits, and the other takes a worktree",
            command="(announced under §2 moment 1, compared here rather than remembered)",
            to=claiming[0].name,
        ))
    return findings


def parked_work(prs: list[dict], sessions: list[Session], now: datetime) -> list[Finding]:
    """The crossing nobody had: a session is idle AND its PR is green and mergeable.

    Neither half is new -- `ListAgents` has had busy/idle all along and the forge has always known
    what is open. Both of the day's stalls were exactly this shape and both were found only when a
    human asked whether anyone was waiting.
    """
    # THE JOIN IS THE BRANCH (#1018). The previous key was `pr["session"]`, which `gh` has never
    # returned, so `by_author.get("")` was always None and the "do not chase a busy session" guard
    # below could not be reached in production -- every green PR past the floor escalated, addressed
    # to nobody, which is the false escalation this detector exists to avoid. `author.login` is no
    # help: every PR in both repositories is the same human. The branch is what a session announces
    # under §2 and what `headRefName` reports.
    # NOT last-wins. A dict comprehension resolved two sessions claiming one branch by list order,
    # so the verdict depended on whatever order `ListAgents` happened to return. A branch claimed
    # twice is AMBIGUOUS, and the honest answer is to name nobody and let `collision-branch` say why.
    claimants = branch_claimants(sessions)
    by_branch = {b: s[0] for b, s in claimants.items() if len(s) == 1}
    findings = []
    for pr in prs:
        age = age_minutes(pr["createdAt"], now)
        session = by_branch.get(branch_key(pr.get("headRefName")))
        green = pr.get("mergeStateStatus") == "CLEAN"
        if not green:
            continue
        if age < STALL_MINUTES:
            # The negative case, stated deliberately: a green PR that is young is NOT a finding.
            # Escalating here is the module's characteristic failure, and it happened twice.
            continue
        if session is not None and not session.idle:
            continue
        if session is not None:
            subject = (f"PR #{pr['number']} is green and {age} minutes old; {session.name} is "
                       f"{session.state}")
            detail = "the author lands their own work — say it is ready, do not merge it for them"
        else:
            # Said plainly rather than dressed as a verdict: NO session announced this branch, so
            # nothing here knows whether anyone is on it.
            subject = (f"PR #{pr['number']} is green and {age} minutes old, on branch "
                       f"{pr.get('headRefName', '?')} that no session announced")
            detail = ("nobody has claimed this branch, so this is an age reading and not a stall "
                      "verdict — find out who owns it before chasing anyone")
        findings.append(Finding(
            kind="parked",
            subject=subject,
            detail=detail,
            command="gh pr list --state open --limit 100 --json " + ",".join(COLLECTED_FIELDS),
            to=session.name if session else None,
        ))
    return findings


def path_collisions(sessions: list[Session]) -> list[Finding]:
    """Two sessions announcing the same file. Issue numbers never predicted these; paths do."""
    findings = []
    for i, a in enumerate(sessions):
        for b in sessions[i + 1:]:
            shared = sorted(set(a.paths) & set(b.paths))
            if not shared:
                continue
            findings.append(Finding(
                kind="collision",
                subject=f"{a.name} and {b.name} both announced {len(shared)} path(s)",
                detail="; ".join(shared[:5]) + " — agree who holds each before either pushes",
                command="(announced under §2 moment 1; compared here, not remembered)",
                to=a.name,
            ))
    return findings


def conflict_triage(pr: dict, overlapping: list[str],
                    generated: tuple[tuple[str, str], ...] = GENERATED) -> list[Finding]:
    """For a conflicted PR, name the files and say for each: regenerate, or the author's call."""
    findings = []
    for path in overlapping:
        command = regenerator(path, generated)
        if command:
            findings.append(Finding(
                kind="conflict-generated",
                subject=f"PR #{pr['number']}: {path}",
                detail=f"generated — do not resolve by hand; take either side and re-run: {command}",
                command=f"git diff --name-only $(git merge-base origin/dev HEAD) origin/dev",
            ))
        else:
            findings.append(Finding(
                kind="conflict-authored",
                subject=f"PR #{pr['number']}: {path}",
                detail="authored — the author's judgement, not the coordinator's; ask, do not resolve",
                command=f"git diff --name-only $(git merge-base origin/dev HEAD) origin/dev",
            ))
    return findings


def highest_claim(claimed: list[str]) -> str | None:
    """The highest claim number seen anywhere, or None. Pure, so the fixture is the real thing.

    The failure this answers: three sessions coordinated by a hand-kept ledger that said "highest
    merged is D-073; two branches hold D-075/D-076 unmerged". The query across every remote ref
    answered **D-079, all of them already merged** -- four numbers stale inside a day. A registry
    file would have drifted identically, because it needs somebody to update it; the refs did not,
    because every branch that takes a number writes it into the file the query reads.
    """
    return max(claimed) if claimed else None


def claim_ledger(repo_root: Path, ledger: str, pattern: str, runner=run) -> Finding:
    """Ask git, across every remote ref, what the highest claimed number actually is.

    Reports ABSENT rather than silently returning nothing when no ref holds the ledger: a search
    that finds nothing and a search that ran against the wrong path produce the same empty string,
    and silence reads as confirmation.
    """
    refs = runner(["git", "for-each-ref", "--format=%(refname)", "refs/remotes/origin"],
                  repo_root).split()
    command = f"git grep -ho '{pattern}' $(git for-each-ref --format='%(refname)' " \
              f"refs/remotes/origin) -- {ledger} | sort -u | tail -1"
    if not refs:
        return Finding("claims-absent", f"no remote refs to search for {ledger}",
                       "nothing was checked — this is a skip, not a clean result", command)
    try:
        found = runner(["git", "grep", "-ho", pattern] + refs + ["--", ledger], repo_root)
    except ReadFailed as failure:
        if failure.returncode != 1:     # 1 is "no match"; 128 is "your pattern is malformed"
            return Finding("claims-unknown", f"the query for {ledger} did not run",
                           f"{failure} — nothing was checked, and this is NOT the same as finding "
                           "no claims; `--claim-pattern` reaches `git grep` unescaped",
                           command)
        found = ""
    highest = highest_claim(sorted(set(found.split())))
    if highest is None:
        return Finding("claims-absent", f"{ledger} matched nothing on any remote ref",
                       "nothing was checked — either no claims exist yet, or the path is wrong, "
                       "and those two look identical", command)
    return Finding("claims", f"the highest claimed number across every remote ref is {highest}",
                   "ask git, not a peer and not a ledger — a hand-kept one was four numbers stale "
                   "inside a day", command)


def migration_ordering(added: list[str], schema_version: str) -> list[Finding]:
    """A migration numbered at or below `schema.rb`'s version is marked applied and never runs.

    Announcing timestamps prevented the collision the protocol was worried about and did nothing
    about ORDERING, which is a different failure: two branches shipped without their columns. Pure,
    so the fixture is the real comparison rather than a mock of it.
    """
    findings = []
    for path in added:
        name = path.rsplit("/", 1)[-1]
        stamp = name.split("_", 1)[0]
        if not stamp.isdigit() or "db/migrate/" not in path:
            continue
        if stamp <= schema_version:
            findings.append(Finding(
                kind="migration-order",
                subject=f"{path} is numbered at or below schema.rb ({schema_version})",
                detail="Rails records it as already applied and never runs it — the columns never "
                       "arrive, and the suite fails somewhere else entirely. Renumber it above the "
                       "schema version before merging.",
                command="git diff --name-only origin/dev...HEAD -- db/migrate/ && "
                        "git show origin/dev:db/schema.rb | head -20",
            ))
    return findings


def assignment(issue: dict, sessions: list[Session], repo: str) -> Finding | None:
    """Match an issue to the session that already has the context, and SAY WHY.

    Two rules, both paid for. **Context over queue order**: the good pairings were made on what a
    session already knew -- the files it had touched, the defect it had just learned. **Never
    across a boundary**: the one bad hand-off was an issue in a repository the receiving session
    was not in; it refused, correctly, because a peer's relay is not authorisation. Sequencing is
    this module's call; access is never anyone's but the owner's.
    """
    best: Session | None = None
    best_shared: list[str] = []
    for session in sessions:
        if session.repo is not None and session.repo != repo:
            continue                      # a boundary, not a preference
        shared = sorted(set(session.paths) & set(issue.get("paths", [])))
        if len(shared) > len(best_shared):
            best, best_shared = session, shared
    if best is None:
        return None
    return Finding(
        kind="assign",
        subject=f"#{issue['number']} suits {best.name}",
        detail=f"they have already announced {', '.join(best_shared)} — the pairing is stated so "
               "it can be argued with, not so it can be obeyed",
        command=f"gh issue view {issue['number']} --json number,title",
        to=best.name,
    )


# -------------------------------------------------------------------------------------------
# The board
# -------------------------------------------------------------------------------------------

def board(repo_root: Path, base: str = "origin/main", head: str = "origin/dev") -> list[str]:
    """Facts about the repository, each printed with the command that produced it."""
    lines = []
    ahead = run(["git", "log", "--oneline", f"{base}..{head}"], repo_root).strip()
    count = len(ahead.splitlines()) if ahead else 0
    lines.append(f"{head} is {count} commit(s) ahead of {base}"
                 f"\n    $ git log --oneline {base}..{head}")
    sha = run(["git", "rev-parse", "--short", head], repo_root).strip()
    lines.append(f"{head} is at {sha}\n    $ git rev-parse --short {head}")
    return lines


def collect_prs(repo_root: Path, limit: int = 100, runner=run) -> list[dict]:
    """Open PRs. BOUNDED: `gh pr list` defaults to 30 and reports one page as the whole truth."""
    raw = runner(["gh", "pr", "list", "--state", "open", "--limit", str(limit), "--json",
                  ",".join(COLLECTED_FIELDS)], repo_root)
    return json.loads(raw or "[]")


def migration_findings(repo_root: Path, base: str = "origin/dev") -> list[Finding]:
    """Migrations this branch adds, checked against the schema version on `base`.

    Returns nothing when the project has no `db/schema.rb` — it is a Rails-shaped check and this
    script also runs in repositories that are not Rails apps.
    """
    try:
        schema = run(["git", "show", f"{base}:db/schema.rb"], repo_root)
    except RuntimeError:
        return []
    match = re.search(r"define\(version:\s*[\"']?([0-9_]+)", schema)
    if not match:
        return []
    version = match.group(1).replace("_", "")
    added = run(["git", "diff", "--name-only", f"{base}...HEAD", "--", "db/migrate/"],
                repo_root).split()
    return migration_ordering(added, version)


def report(sessions: list[Session], prs: list[dict], now: datetime,
           board_lines: list[str], extra: list[Finding] | None = None
           ) -> tuple[list[str], list[Finding]]:
    """The whole output. SILENT on one session, and silent when there is nothing to say.

    Silence is a feature with a cost attached: the lane hook under-detects deliberately because an
    advisory that nags is an advisory that gets switched off, and a coordinator that posts a board
    every tick trains its readers to skip it.
    """
    if len(sessions) < 2:
        return [], []
    findings = (parked_work(prs, sessions, now) + path_collisions(sessions)
                + branch_collisions(sessions) + list(extra or []))
    if not findings:
        return [], []
    return board_lines, findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", help="JSON file: [{name, state, repo, paths, branch}] from ListAgents")
    ap.add_argument("--repo-root", default=".")
    ap.add_argument("--generated", help="JSON {glob: rebuild command} this project generates, "
                                        "merged over the built-in defaults")
    ap.add_argument("--ledger", help="a claims ledger to query across every remote ref, "
                                     "e.g. docs/brain/DECISIONS.md")
    ap.add_argument("--claim-pattern", default="D-0[0-9][0-9]",
                    help="the claim token to search for in --ledger")
    ap.add_argument("--json", action="store_true", help="machine-readable findings")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    root = Path(args.repo_root).resolve()
    sessions = [Session(**s) for s in json.loads(Path(args.sessions).read_text(encoding="utf-8"))] \
        if args.sessions else []
    now = datetime.now(timezone.utc)
    extra = migration_findings(root)
    if args.ledger:
        extra.append(claim_ledger(root, args.ledger, args.claim_pattern))
    lines, findings = report(sessions, collect_prs(root), now, board(root), extra)

    if args.json:
        print(json.dumps([f.__dict__ for f in findings], indent=2))
        return 0
    for line in lines:
        print(line)
    for finding in findings:
        print(finding.render())
    return 0


# -------------------------------------------------------------------------------------------
# Selftest — every detector must fire on the day it was written for, and STAY SILENT otherwise.
# -------------------------------------------------------------------------------------------

NOW = datetime(2026, 9, 17, 15, 33, 20, tzinfo=timezone.utc)


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, condition: bool) -> None:
        if not condition:
            failures.append(label)

    # 1. The write boundary, proved by attempting every verb with a spy that must never be called.
    def never(*_args, **_kwargs):
        raise AssertionError("EXECUTED a write command instead of refusing it")

    for verb in WRITE_VERBS:
        try:
            run(list(verb) + ["1"], Path("."), execute=never)
            failures.append(f"{' '.join(verb)} was NOT refused — this module can act on the world")
        except WriteAttempted:
            pass
        except AssertionError as exc:
            failures.append(f"{' '.join(verb)}: {exc}")

    # 2. Time: the real numbers from the day. 15:20:39Z against 15:33:20Z is 12 minutes, not 72.
    check("age_minutes did not compute 12 minutes for the 15:20:39Z PR",
          age_minutes("2026-09-17T15:20:39Z", NOW) == 12)
    try:
        age_minutes("2026-09-17T15:20:39Z", datetime(2026, 9, 17, 16, 33, 20))
        failures.append("age_minutes accepted a NAIVE clock — the 60-minute error is back")
    except ValueError:
        pass
    except TypeError:
        failures.append("age_minutes accepted a NAIVE clock and died subtracting it — the refusal "
                        "is gone, and a crash is not a diagnosis")

    # THE FIXTURE IS BUILT FROM THE COLLECTOR'S OWN FIELD LIST, and checked against it below. The
    # previous one invented a `session` key, so both the firing and the silent case were tested
    # against a PR shape `gh` cannot produce, and the guard between them was dead (#1018).
    green = {"number": 1009, "title": "x", "createdAt": "2026-09-17T15:20:39Z",
             "mergeStateStatus": "CLEAN", "headRefName": "fix/a", "author": {"login": "someone"}}
    check("the PR fixture uses a field the collector never requests",
          set(green) <= set(COLLECTED_FIELDS))
    idle = [Session("s-a", "idle", branch="fix/a"), Session("s-b", "busy", branch="fix/b")]

    # 3. THE NEGATIVE CASE FIRST. A green PR 12 minutes old is proceeding normally. Escalating here
    #    is this module's characteristic failure and it happened twice in five minutes.
    check("a 12-minute green PR was reported as parked — that is the false escalation",
          parked_work([green], idle, NOW) == [])

    # 4. The positive: the same PR, older than the stall floor, with its author idle.
    old = dict(green, createdAt="2026-09-17T13:00:00Z")
    parked = parked_work([old], idle, NOW)
    check("an idle session with a green 153-minute-old PR produced no finding", len(parked) == 1)
    check("the parked finding does not carry its command", bool(parked and parked[0].command))
    check("the parked finding tells the coordinator to merge it",
          bool(parked) and "do not merge it for them" in parked[0].detail)

    # 5. A busy author is not parked, however old the PR — THE ARM THAT COULD NOT FAIL BEFORE.
    check("a BUSY author's old green PR was reported as parked",
          parked_work([dict(old, headRefName="fix/b")], idle, NOW) == [])
    # And an unclaimed branch is reported as an age reading, never as a verdict about a person.
    orphan = parked_work([dict(old, headRefName="fix/nobody")], idle, NOW)
    check("an unclaimed branch produced no reading at all", len(orphan) == 1)
    check("an unclaimed branch was dressed up as a stall verdict",
          bool(orphan) and "not a stall verdict" in orphan[0].detail and orphan[0].to is None)

    # 5b. Spellings. `origin/fix/b` and `fix/b` are one branch, and reading them as two escalates
    #     at a session that is busy and working.
    spelled = [Session("s-a", "idle", branch="refs/heads/fix/a"),
               Session("s-b", "busy", branch="origin/fix/b")]
    check("a session announcing `origin/fix/b` was treated as not having announced it",
          parked_work([dict(old, headRefName="fix/b")], spelled, NOW) == [])
    check("a session announcing `refs/heads/fix/a` lost its parked finding",
          len(parked_work([dict(old, headRefName="fix/a")], spelled, NOW)) == 1)
    check("branch_key mangled a plain name", branch_key("fix/a") == "fix/a")
    check("branch_key invented a branch from nothing", branch_key(None) is None)

    # 5c. Two sessions on ONE branch: reported, and never resolved by list order.
    both = [Session("peer-a", "busy", branch="fix/shared"),
            Session("peer-b", "idle", branch="origin/fix/shared")]
    check("two sessions claiming one branch produced no collision",
          len(branch_collisions(both)) == 1)
    check("one session on its own branch was reported as a collision",
          branch_collisions([Session("solo", "idle", branch="fix/solo")]) == [])
    ambiguous = parked_work([dict(old, headRefName="fix/shared")], both, NOW)
    check("an ambiguously-claimed branch named one of the claimants anyway",
          len(ambiguous) == 1 and ambiguous[0].to is None)
    check("reversing the session list changed the verdict",
          [f.subject for f in parked_work([dict(old, headRefName="fix/shared")], both[::-1], NOW)]
          == [f.subject for f in ambiguous])

    # 6. Collisions come from paths, not issue numbers.
    a = Session("s-a", "idle", paths=["app/models/card.rb", "app/views/cards/index.html.erb"])
    b = Session("s-b", "busy", paths=["app/models/card.rb"])
    c = Session("s-c", "busy", paths=["lib/totp.rb"])
    check("two sessions announcing app/models/card.rb produced no collision",
          len(path_collisions([a, b])) == 1)
    check("sessions with disjoint paths produced a collision", path_collisions([a, c]) == [])

    # 7. Conflict triage: generated vs authored, and it must not choose for the author.
    triage = conflict_triage({"number": 7}, ["docs/wiki/Skills-Reference.md", "app/models/card.rb"])
    check("a generated conflict was not named as regenerable",
          any(f.kind == "conflict-generated" and "build_wiki" in f.detail for f in triage))
    check("an authored conflict was not left to its author",
          any(f.kind == "conflict-authored" and "author's judgement" in f.detail for f in triage))
    check("triage resolved an authored file itself",
          all("take either side" not in f.detail for f in triage if f.kind == "conflict-authored"))

    # 8. Assignment: on context, with the reason stated, and never across a boundary.
    issue = {"number": 401, "paths": ["app/models/card.rb"]}
    pick = assignment(issue, [a, c], repo="retask")
    check("assignment did not pick the session that had touched the file", pick is not None)
    check("assignment did not state why", bool(pick and "app/models/card.rb" in pick.detail))
    elsewhere = Session("s-d", "idle", repo="other-repo", paths=["app/models/card.rb"])
    check("assignment crossed a repository boundary the session was not authorised into",
          assignment(issue, [elsewhere], repo="retask") is None)

    # 8b. Claims are a query. The numbers are the ones the ledger got wrong.
    check("highest_claim did not return the highest number across the refs",
          highest_claim(["D-073", "D-079", "D-075", "D-076"]) == "D-079")
    check("highest_claim invented a claim from an empty search", highest_claim([]) is None)

    # 8c. Migration ordering: at or below the schema version is the silent one.
    ordering = migration_ordering(
        ["db/migrate/20260901120000_add_reference_to_cards.rb",
         "db/migrate/20260930090000_add_batch_cap.rb"], schema_version="20260915000000")
    check("a migration numbered BELOW schema.rb produced no finding", len(ordering) == 1)
    check("the wrong migration was flagged",
          bool(ordering) and "20260901120000" in ordering[0].subject)
    check("a migration numbered ABOVE schema.rb was flagged anyway",
          all("20260930090000" not in f.subject for f in ordering))
    check("a non-migration path was treated as a migration",
          migration_ordering(["app/models/card.rb"], "20260915000000") == [])
    # The boundary itself: EQUAL to the schema version is already recorded as applied, so `<=` and
    # `<` are different answers and only this fixture can tell them apart.
    check("a migration numbered EXACTLY at the schema version was not flagged",
          len(migration_ordering(["db/migrate/20260915000000_exactly_at_the_version.rb"],
                                 "20260915000000")) == 1)

    # 8d. The ledger query's three outcomes, against a runner that needs no repository.
    def fake(matches: str, refs: str = "refs/remotes/origin/dev\n"):
        def runner(argv, _cwd):
            return refs if argv[1] == "for-each-ref" else matches
        return runner

    found = claim_ledger(Path("."), "docs/brain/DECISIONS.md", "D-0[0-9][0-9]",
                         runner=fake("D-073\nD-079\nD-075\n"))
    check("the ledger query did not report the highest claim from the refs",
          found.kind == "claims" and "D-079" in found.subject)
    check("the ledger query dropped the command that produced it", bool(found.command))
    check("an empty search was reported as a clean result rather than as absent",
          claim_ledger(Path("."), "x.md", "D-0[0-9][0-9]", runner=fake("")).kind == "claims-absent")
    check("a repository with no remote refs was reported as a clean result",
          claim_ledger(Path("."), "x.md", "D-0[0-9][0-9]",
                       runner=fake("", refs="")).kind == "claims-absent")

    def exploding(code: int):
        def runner(argv, _cwd):
            if argv[1] == "for-each-ref":
                return "refs/remotes/origin/dev\n"
            raise ReadFailed(argv, code, "fatal: brackets ([ ]) not balanced")
        return runner

    check("a FATAL git failure was reported as 'matched nothing' — a result never obtained",
          claim_ledger(Path("."), "d.md", "[", runner=exploding(128)).kind == "claims-unknown")
    check("exit 1 (genuinely no match) was reported as a failed query",
          claim_ledger(Path("."), "d.md", "D-0[0-9][0-9]",
                       runner=exploding(1)).kind == "claims-absent")

    # 8e. The collector asks for exactly COLLECTED_FIELDS. Without this the constant is
    #     decorative and a fixture can drift from the query all over again.
    asked: list[str] = []

    def spy(argv, _cwd):
        asked.extend(argv)
        return "[]"

    collect_prs(Path("."), runner=spy)
    check("collect_prs does not ask for the fields the fixtures are checked against",
          ",".join(COLLECTED_FIELDS) in asked)
    check("collect_prs left its page size unbounded",
          "--limit" in asked)

    # 9. Silence: one session, and nothing to report.
    check("a single session produced output", report([a], [old], NOW, ["board"]) == ([], []))
    check("two sessions with nothing wrong produced output",
          report([Session("s-a", "busy"), Session("s-b", "busy")], [], NOW, ["board"]) == ([], []))

    for f in failures:
        print(f"SELFTEST FAILED: {f}")
    if not failures:
        print(f"selftest: ok — {len(WRITE_VERBS)} write verbs refused; the 12-minute PR is silent, "
              "the 153-minute one is not; collisions from paths; generated and authored conflicts "
              "separated; assignment stays inside its boundary; the highest claim comes from the "
              "refs; a migration at or below the schema version is caught and one above it is not")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
