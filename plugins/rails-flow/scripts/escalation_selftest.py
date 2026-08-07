#!/usr/bin/env python3
"""Selftest for escalation.py — pillar 3 of the autonomous driver (#488).

Paired fixtures throughout: every check has a case that must fire and one that must stay silent.

The four that encode the API facts, rather than logic, are the ones to keep if this is ever
trimmed. Each was verified against the real API, and each breaks the loop completely:

  same-login      the agent and the human share a login, so replies are found by MARKER
  quoted-marker   a human quoting the agent must still count as a reply
  label-first     a missing label errors — do not park on a question nobody is emailed about
  edit-not-reply  an edited old comment is not an answer
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import escalation as esc

RESULTS: list[tuple[bool, str]] = []


def check(name: str, got, want) -> None:
    RESULTS.append((got == want, f"{name}: got {got!r}, want {want!r}"))


class FakeGh(esc.Gh):
    """Records calls instead of making them. `existing` starts WITHOUT the escalation labels, so
    the default path exercises creating them."""

    def __init__(self, *, existing=None, comments=None, fail=()):
        self.existing = list(existing if existing is not None else ["bug"])
        self._comments = list(comments or [])
        self.fail = set(fail)
        self.calls: list[tuple] = []

    def labels(self):
        self.calls.append(("labels",))
        return None if "labels" in self.fail else list(self.existing)

    def create_label(self, name, colour, description):
        self.calls.append(("create_label", name))
        if "create_label" in self.fail:
            return False
        self.existing.append(name)
        return True

    def comment(self, issue, body):
        self.calls.append(("comment", issue, body))
        if "comment" in self.fail:
            return False
        self._comments.append({"body": body, "createdAt": "2026-08-07T12:00:00Z"})
        return True

    def add_label(self, issue, label):
        self.calls.append(("add_label", issue, label))
        return "add_label" not in self.fail

    def remove_label(self, issue, label):
        self.calls.append(("remove_label", issue, label))
        return True

    def comments(self, issue):
        self.calls.append(("comments", issue))
        return None if "comments" in self.fail else list(self._comments)


def agent(body, at):
    return {"body": f"{esc.MARKER}\n{body}", "createdAt": at}


def human(body, at):
    return {"body": body, "createdAt": at}


def run() -> int:
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # -- same-login: the marker, not the author, tells them apart --------------------
        # Both of these would be authored by the SAME login in reality, which is why no fixture
        # here carries an author at all — the field is unusable and must not creep back in.
        check("same-login: agent comment recognised",
              esc.is_agent_comment(f"{esc.MARKER}\nWhich database?"), True)
        check("same-login: human comment is not",
              esc.is_agent_comment("Postgres, please."), False)
        # SILENCE: the agent's own question must never be mistaken for the answer to itself.
        found = esc.find_answer([agent("Which database?", "2026-08-07T12:00:00Z")],
                                "2026-08-07T11:59:00Z")
        check("same-login: own question is not an answer", found, None)
        found = esc.find_answer([agent("Which database?", "2026-08-07T12:00:00Z"),
                                 human("Postgres.", "2026-08-07T12:05:00Z")],
                                "2026-08-07T12:00:00Z")
        check("same-login: the human reply is found", (found or {}).get("body"), "Postgres.")

        # -- quoted-marker: a human quoting the agent still counts as a reply -------------
        # `in` instead of `startswith` would strand this thread parked forever — the one failure
        # the loop cannot recover from on its own, because nothing else ever re-reads it.
        quoted = human(f"> {esc.MARKER}\n> Which database?\n\nPostgres.", "2026-08-07T12:05:00Z")
        check("quoted-marker: a quoted question is not agent-authored",
              esc.is_agent_comment(quoted["body"]), False)
        check("quoted-marker: and it resolves the thread",
              esc.find_answer([agent("Which database?", "2026-08-07T12:00:00Z"), quoted],
                              "2026-08-07T12:00:00Z") is not None, True)

        # -- edit-not-reply: only createdAt counts ---------------------------------------
        old = human("Unrelated remark.", "2026-08-07T10:00:00Z")
        old["updatedAt"] = "2026-08-07T12:30:00Z"          # edited AFTER the question
        check("edit-not-reply: an edited old comment is not an answer",
              esc.find_answer([old, agent("Q?", "2026-08-07T12:00:00Z")], "2026-08-07T12:00:00Z"),
              None)
        # SILENCE: a genuinely new comment at the same instant is still an answer.
        check("edit-not-reply: a new comment after is an answer",
              esc.find_answer([human("Yes.", "2026-08-07T12:00:01Z")], "2026-08-07T12:00:00Z")
              is not None, True)

        # -- label-first: never park on a question nobody is emailed about ---------------
        proj = tmp / "p1"
        gh = FakeGh(fail={"create_label"})
        code, lines = esc.ask(gh, proj, 42, "Which database?", "step-2")
        check("label-first: a label that cannot be created blocks the ask", code, esc.EXIT_FINDINGS)
        check("label-first: nothing was posted",
              any(c[0] == "comment" for c in gh.calls), False)
        check("label-first: and nothing was parked",
              esc.state_path(proj).exists(), False)
        # SILENCE: with labels creatable, the ask goes through and parks.
        proj2 = tmp / "p2"
        gh2 = FakeGh()
        code, _ = esc.ask(gh2, proj2, 42, "Which database?", "step-2")
        check("label-first: a healthy ask succeeds", code, esc.EXIT_OK)
        check("label-first: both labels were created",
              sorted(c[1] for c in gh2.calls if c[0] == "create_label"),
              sorted(esc.LABEL_SPECS))
        check("label-first: awaiting label applied",
              ("add_label", 42, esc.AWAITING_LABEL) in gh2.calls, True)
        check("label-first: the marker opens the posted body",
              next(c[2] for c in gh2.calls if c[0] == "comment").startswith(esc.MARKER), True)
        # Existing labels must NOT be recreated — idempotence, not just success.
        gh3 = FakeGh(existing=["bug", esc.AWAITING_LABEL, esc.ANSWERED_LABEL])
        esc.ask(gh3, tmp / "p3", 7, "Q?", "s")
        check("label-first: silent when labels already exist",
              [c for c in gh3.calls if c[0] == "create_label"], [])
        # A comment that posts but a label that will not apply is NOT a successful park.
        gh4 = FakeGh(fail={"add_label"})
        code, _ = esc.ask(gh4, tmp / "p4", 8, "Q?", "s")
        check("label-first: unlabelled post is treated as unsent", code, esc.EXIT_FINDINGS)

        # -- the loop: park, poll, resume ------------------------------------------------
        threads = esc.load_state(proj2)["threads"]
        check("loop: one thread parked", len(threads), 1)
        check("loop: parked as awaiting", threads[0]["status"], "awaiting-input")

        # No reply yet -> stays parked, and NOTHING is relabelled.
        gh5 = FakeGh(comments=list(gh2._comments))
        code, lines, answered = esc.poll(gh5, proj2)
        check("loop: no reply keeps it parked", answered, [])
        check("loop: and says so", any("still awaiting" in l for l in lines), True)
        check("loop: no premature answered label",
              any(c[0] == "add_label" and c[2] == esc.ANSWERED_LABEL for c in gh5.calls), False)

        # The human replies -> resumes, relabels, and records the answer.
        gh6 = FakeGh(comments=list(gh2._comments) + [human("Postgres.", "2026-08-07T13:00:00Z")])
        code, lines, answered = esc.poll(gh6, proj2)
        check("loop: the reply resumes the thread", len(answered), 1)
        check("loop: the answer is recorded", answered[0]["answer"], "Postgres.")
        check("loop: resume step survived", answered[0]["resume_step"], "step-2")
        check("loop: relabelled answered",
              ("add_label", 42, esc.ANSWERED_LABEL) in gh6.calls, True)
        check("loop: awaiting label removed",
              ("remove_label", 42, esc.AWAITING_LABEL) in gh6.calls, True)

        # Idempotent: polling again does not re-answer an already-answered thread.
        gh7 = FakeGh(comments=list(gh6._comments))
        _, _, again = esc.poll(gh7, proj2)
        check("loop: a second poll is a no-op", again, [])

        # DURABILITY — the whole point. State is re-read from disk, as a new session would.
        reloaded = esc.load_state(proj2)["threads"]
        check("loop: state survives a fresh read", reloaded[0]["status"], "answered")
        check("loop: the answer survives too", reloaded[0]["answer"], "Postgres.")

        # -- non-blocking: an unreadable thread must not stop the others -----------------
        proj5 = tmp / "p5"
        ghA = FakeGh()
        esc.ask(ghA, proj5, 10, "Q10?", "s10")
        ghB = FakeGh()
        esc.ask(ghB, proj5, 11, "Q11?", "s11")
        check("non-blocking: two threads parked", len(esc.load_state(proj5)["threads"]), 2)
        ghC = FakeGh(fail={"comments"})
        code, lines, _ = esc.poll(ghC, proj5)
        check("non-blocking: unreadable comments do not fail the run", code, esc.EXIT_OK)
        check("non-blocking: both threads reported", len(lines), 2)
        check("non-blocking: and both stay parked",
              [t["status"] for t in esc.load_state(proj5)["threads"]],
              ["awaiting-input", "awaiting-input"])

        # -- unusable input ---------------------------------------------------------------
        check("unusable: --ask with no question", esc.main(["--ask", "1"], gh=FakeGh()),
              esc.EXIT_UNUSABLE)
        check("unusable: an empty question", esc.main(["--ask", "1", "--question", "   "],
                                                      gh=FakeGh()), esc.EXIT_UNUSABLE)
        # SILENCE: --list on a project with no state is a clean 0, not unusable.
        check("unusable: --list with no state is clean",
              esc.main(["--list", "--project", str(tmp / "empty")], gh=FakeGh()), esc.EXIT_OK)
        # A corrupt state file degrades to empty rather than crashing an unattended run.
        bad = tmp / "p6"
        esc.state_path(bad).parent.mkdir(parents=True, exist_ok=True)
        esc.state_path(bad).write_text("{ not json", encoding="utf-8")
        check("unusable: corrupt state reads as empty", esc.load_state(bad), {"threads": []})

    failed = [m for ok, m in RESULTS if not ok]
    for m in failed:
        print(f"  FAIL {m}")
    print(f"{len(RESULTS) - len(failed)} passed, {len(failed)} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    import sys
    sys.exit(run())
