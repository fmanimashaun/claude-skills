#!/usr/bin/env python3
"""Ask the human a question on a GitHub issue, park the thread, and pick the answer up later.

This is pillar 3 of the autonomous flow driver (EPIC #488) — the async human-in-the-loop. When
the driver hits a decision it must not make alone, it comments on the relevant issue, labels it
so GitHub emails the human, records the thread durably, and **moves on to other work**. On a
later tick it re-reads the thread; if the human answered, it resumes from that answer.

The point is that nothing blocks. The human replies on their own schedule; the agent notices
whenever it next cycles, including in a different session after a restart.

TWO THINGS THE EPIC'S DESIGN SKETCH GOT WRONG. Both were found by testing against the real API
rather than reasoning about it, and each breaks the loop completely:

  1. "Fetch comments since its question (by timestamp/AUTHOR)" cannot work, because the agent and
     the human have THE SAME LOGIN. `gh` authenticates with the user's own token, so a comment the
     agent posts is authored by the repo owner — verified: the agent's comment on issue 484 came
     back as `login=fmanimashaun`, identical to `gh api user`. Author filtering therefore either
     never fires (excluding the owner excludes the human too) or fires immediately on the agent's
     own question. Replies are distinguished by a MARKER the agent stamps on its own comments,
     never by who wrote them.

  2. A missing label is not a soft failure. `gh issue edit --add-label` ERRORS and applies nothing
     when the label does not exist — the same defect `lint_self_consistency.py`'s
     `unprovisioned-label` rule exists to catch (#487, #490). For an escalation that is the worst
     possible failure: the label is what sends the human their email, so the driver would park
     believing it had asked while nobody was ever told. The label is ensured before use, and if it
     cannot be ensured the escalation FAILS rather than parking on a question no one will see.

Exit codes:  0 clean · 1 findings (an escalation could not be posted or labelled) · 2 unusable
             input (--ask with no question, an empty question)

`--poll` is 0 whether or not anything was answered, and that is deliberate: "nobody has replied
yet" is the normal state of an async loop, not a failure. A driver that treated it as one would
stop on the very condition this pillar exists to make survivable.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2

# Stamped as the FIRST line of every comment the agent posts. Invisible in rendered markdown, so
# the human never sees it. Position matters: a human quoting the agent's comment reproduces the
# marker, but a quote is prefixed with "> ", so requiring it at the very start keeps a quoted
# question from being mistaken for the agent's own writing — which would strand the thread parked
# forever, the one failure this loop cannot recover from on its own.
MARKER = "<!-- rails-flow:escalation -->"

AWAITING_LABEL = "awaiting-input"
ANSWERED_LABEL = "answered"
LABEL_SPECS = {
    AWAITING_LABEL: ("B60205", "The flow is parked on this issue until a human answers"),
    ANSWERED_LABEL: ("0E8A16", "A human answered; the flow can resume from the reply"),
}

STATE_NAME = ".escalations.json"


# ----------------------------------------------------------------------------- gh

class Gh:
    """The `gh` calls this needs, in one place so tests can substitute them.

    Every method returns None on failure rather than raising, and the callers treat None as a
    fact to report. A network blip must not take down a driver whose whole purpose is to keep
    running unattended.
    """

    def __init__(self, repo: str | None = None):
        self.repo = repo

    def _run(self, *args: str, parse: bool = True):
        cmd = ["gh", *args]
        if self.repo:
            cmd += ["--repo", self.repo]
        try:
            done = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode != 0:
            return None
        if not parse:
            return done.stdout
        try:
            return json.loads(done.stdout) if done.stdout.strip() else None
        except ValueError:
            return None

    def labels(self) -> list[str] | None:
        rows = self._run("label", "list", "--limit", "200", "--json", "name")
        return None if rows is None else [r["name"] for r in rows]

    def create_label(self, name: str, colour: str, description: str) -> bool:
        return self._run("label", "create", name, "--color", colour,
                         "--description", description, parse=False) is not None

    def comment(self, issue: int, body: str) -> bool:
        return self._run("issue", "comment", str(issue), "--body", body, parse=False) is not None

    def add_label(self, issue: int, label: str) -> bool:
        return self._run("issue", "edit", str(issue), "--add-label", label, parse=False) is not None

    def remove_label(self, issue: int, label: str) -> bool:
        return self._run("issue", "edit", str(issue), "--remove-label", label,
                         parse=False) is not None

    def comments(self, issue: int) -> list[dict] | None:
        rows = self._run("issue", "view", str(issue), "--json", "comments")
        return None if rows is None else (rows.get("comments") or [])


# -------------------------------------------------------------------------- state

def state_path(project: Path) -> Path:
    return project / "docs" / "brain" / STATE_NAME


def load_state(project: Path) -> dict:
    try:
        data = json.loads(state_path(project).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"threads": []}
    return data if isinstance(data, dict) and isinstance(data.get("threads"), list) else {"threads": []}


def save_state(project: Path, state: dict) -> None:
    p = state_path(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


# --------------------------------------------------------------------------- ask

def ensure_labels(gh: Gh) -> tuple[bool, list[str]]:
    """Create the escalation labels if absent.

    Finding 2. `gh issue edit --add-label` errors and applies NOTHING when the label is missing,
    so this must succeed before anything is posted. Returns (ok, notes) — `ok=False` means do not
    park, because a parked thread with no label is a question the human is never emailed about.
    """
    existing = gh.labels()
    if existing is None:
        return False, ["could not list labels (gh unavailable or unauthenticated?)"]
    notes = []
    for name, (colour, description) in LABEL_SPECS.items():
        if name in existing:
            continue
        if not gh.create_label(name, colour, description):
            return False, notes + [f"could not create the {name!r} label"]
        notes.append(f"created the {name!r} label")
    return True, notes


def ask(gh: Gh, project: Path, issue: int, question: str, resume_step: str) -> tuple[int, list[str]]:
    """Post the question, label the issue, park the thread. Never blocks on an answer."""
    ok, notes = ensure_labels(gh)
    if not ok:
        return EXIT_FINDINGS, notes + [
            "NOT posting the escalation: without the label the human is never emailed, and a "
            "thread parked on a question nobody sees is worse than no escalation at all"]

    body = f"{MARKER}\n{question.strip()}\n"
    if not gh.comment(issue, body):
        return EXIT_FINDINGS, notes + [f"could not comment on #{issue}"]
    if not gh.add_label(issue, AWAITING_LABEL):
        return EXIT_FINDINGS, notes + [
            f"commented on #{issue} but could not apply {AWAITING_LABEL!r} — the human may not be "
            "emailed; treat this escalation as unsent"]

    posted = gh.comments(issue) or []
    asked_at = posted[-1].get("createdAt", "") if posted else ""

    state = load_state(project)
    state["threads"] = [t for t in state["threads"] if t.get("issue") != issue]
    state["threads"].append({
        "issue": issue, "status": "awaiting-input", "asked_at": asked_at,
        "question": question.strip()[:400], "resume_step": resume_step,
    })
    save_state(project, state)
    return EXIT_OK, notes + [f"asked on #{issue}, parked at {asked_at or 'unknown time'}; "
                             f"continue with other work"]


# -------------------------------------------------------------------------- poll

def is_agent_comment(body: str) -> bool:
    """True only when the marker opens the comment.

    Finding 1 in force: this is the ONLY way to tell the two apart, because the logins are
    identical. `startswith` rather than `in` — a human quoting the agent produces "> <!-- ... -->",
    and treating that as agent-authored would strand the thread parked forever.
    """
    # The BOM is written as an ESCAPE, never as the literal character: putting a real U+FEFF
    # here to strip U+FEFF makes this file trip the repo's own `invisible-character` gate,
    # which it duly did on the first run.
    return body.lstrip("\ufeff").startswith(MARKER)


def find_answer(comments: list[dict], asked_at: str) -> dict | None:
    """The first non-agent comment created strictly after the question.

    Only `createdAt` is consulted. An EDIT to a pre-existing comment is deliberately not a signal:
    `updatedAt` also moves when the agent edits its own comment, and a typo fix on an old comment
    would resume the flow with an answer that predates the question. If the human edits rather
    than replies, the thread stays parked — visibly, under its label — which is recoverable. A
    false resume is not.
    """
    for comment in comments:
        created = comment.get("createdAt", "")
        if asked_at and created <= asked_at:
            continue
        if is_agent_comment(comment.get("body", "")):
            continue
        return comment
    return None


def poll(gh: Gh, project: Path, issue: int | None = None) -> tuple[int, list[str], list[dict]]:
    """Check parked threads for replies. Returns (code, lines, answered)."""
    state = load_state(project)
    parked = [t for t in state["threads"] if t.get("status") == "awaiting-input"]
    if issue is not None:
        parked = [t for t in parked if t.get("issue") == issue]
    if not parked:
        return EXIT_OK, ["no parked escalations"], []

    lines, answered = [], []
    for thread in parked:
        number = thread["issue"]
        comments = gh.comments(number)
        if comments is None:
            lines.append(f"#{number}: could not read comments; staying parked")
            continue
        reply = find_answer(comments, thread.get("asked_at", ""))
        if reply is None:
            lines.append(f"#{number}: still awaiting input")
            continue
        thread["status"] = "answered"
        thread["answer"] = (reply.get("body") or "")[:2000]
        thread["answered_at"] = reply.get("createdAt", "")
        answered.append(thread)
        gh.add_label(number, ANSWERED_LABEL)
        gh.remove_label(number, AWAITING_LABEL)
        lines.append(f"#{number}: ANSWERED — resume at {thread.get('resume_step', 'start')}")
    save_state(project, state)
    return EXIT_OK, lines, answered


# --------------------------------------------------------------------------- main

def main(argv=None, gh: Gh | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--project", type=Path, default=Path.cwd())
    ap.add_argument("--repo", help="owner/name (defaults to the current repo)")
    ap.add_argument("--ask", type=int, metavar="ISSUE", help="post a question and park the thread")
    ap.add_argument("--question", help="the question text, or - to read stdin")
    ap.add_argument("--resume-step", default="start", help="where the driver should resume")
    ap.add_argument("--poll", action="store_true", help="check parked threads for replies")
    ap.add_argument("--issue", type=int, help="limit --poll to one issue")
    ap.add_argument("--list", action="store_true", help="show parked threads, no network")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)

    if args.selftest:
        from escalation_selftest import run
        return run()

    client = gh or Gh(args.repo)

    if args.list:
        threads = load_state(args.project)["threads"]
        if not threads:
            print("no escalations recorded")
        for t in threads:
            print(f"#{t['issue']:<6} {t.get('status','?'):14} {t.get('resume_step','start')}")
        return EXIT_OK

    if args.ask is not None:
        if not args.question:
            print("unusable: --ask needs --question", file=sys.stderr)
            return EXIT_UNUSABLE
        question = sys.stdin.read() if args.question == "-" else args.question
        if not question.strip():
            print("unusable: the question is empty", file=sys.stderr)
            return EXIT_UNUSABLE
        code, lines = ask(client, args.project, args.ask, question, args.resume_step)
        for line in lines:
            print(line)
        return code

    if args.poll:
        code, lines, _ = poll(client, args.project, args.issue)
        for line in lines:
            print(line)
        return code

    ap.print_help()
    return EXIT_UNUSABLE


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    sys.exit(main())
