#!/usr/bin/env python3
"""Audit and restructure a project's CLAUDE.md -- rule-first, history one link away, a ceiling that holds.

    python3 claude_md_structure.py --report [CLAUDE.md]                 # what loads at session start, and what it is made of
    python3 claude_md_structure.py --propose [CLAUDE.md] [--history F]  # the diff that moves history OUT, verbatim; writes nothing
    python3 claude_md_structure.py --propose CLAUDE.md --write          # apply it
    python3 claude_md_structure.py --set-ceiling [CLAUDE.md] [--write]  # record the ceiling at the measured size
    python3 claude_md_structure.py --json CLAUDE.md
    python3 claude_md_structure.py --selftest

WHY (#875, after #870). CLAUDE.md is loaded by every session, so every line in it is paid for on every
turn -- and it accretes. Facts land beside the rule they explain, then the incident behind the fact, then
the issue number, until the file is mostly the story of how it came to say what it says. The marketplace's
own went from a page to 754 lines; 59 % of its words sat in paragraphs carrying an incident rather than a
rule. `setup-flow` ships the advice "keep CLAUDE.md under 200 lines" and nothing performed it. And the
obvious remedy -- compress it -- is the dangerous one: a summarised rule loses the reasoning that made an
agent follow it instead of "simplifying" it away.

THE BALANCE, AS A MECHANISM. Token economy and quality pull against each other only if the fix is deletion.
It is not:

  * The RULE stays in CLAUDE.md. The HISTORY moves -- **verbatim, never summarised** -- to a linked file
    (`docs/brain/claude-md-history.md` by default -- the project's in-repo memory) that nothing loads until a rule's reasoning is wanted. One
    pointer line per section replaces what moved. `--propose` asserts the move is lossless: every moved
    paragraph must appear byte-for-byte in the proposed history file, or it refuses.
  * The CEILING is on what loads, recorded IN the file as `<!-- claude-md: max-lines N -->`, and it is a
    RATCHET at the measured size, not an aspiration: lower it when the file shrinks; raise it in a change
    that says why. A fixed "under 200" is red on day one and switched off in a week.
  * Classification is mechanical and stated (HISTORY_MARKERS below), so a finding is always checkable.
    It will call some rule-bearing paragraphs history when they lean on their incident; the proposal is a
    diff a human approves, not an edit the tool performs unasked.

Exit codes for --report: 0 within the ceiling; 1 past it (the finding says which paragraphs to move);
3 when no ceiling marker is recorded -- not applicable, NOT a pass: `setup-flow` writes the marker at
scaffold time so the choice is on the record, and `--set-ceiling` writes it later. Stdlib only.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

DEFAULT_HISTORY = "docs/brain/claude-md-history.md"  # the project's in-repo memory lives under docs/brain/
MARKER = re.compile(r"<!--\s*claude-md:\s*max-lines\s+(\d+)\s*-->")
HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")

# A paragraph is HISTORY when it carries a reference to a past event AND narrates it. Both halves are
# required: an issue number alone is a citation, a past-tense verb alone is English. The lists are the
# whole classifier -- there is no model, so a disagreement is settled by reading the paragraph.
HISTORY_REFERENCE = re.compile(r"(?<![\w/])#\d{2,}\b|\bv\d+\.\d+\.\d+\b|\b20\d\d-\d\d(?:-\d\d)?\b")
HISTORY_NARRATIVE = re.compile(
    r"\b(?:used to|was|were|had|happened|bit|shipped|broke|caught|found|reverted|reported|"
    r"turned out|until recently|earlier|once|the first version|the old|before this)\b", re.I)
RULE_SIGNAL = re.compile(r"\b(?:must|never|always|do not|don't|only|run|use|keep|read|check|stage|branch|"
                         r"merge|bump|commit|write|report)\b", re.I)


def paragraphs(text: str) -> list[dict]:
    """Blank-line-separated blocks with their section, keeping fences and tables whole (they are STRUCTURE)."""
    out: list[dict] = []
    section = "(preamble)"
    buf: list[str] = []
    start = 1
    in_fence = False
    kind_hint = None

    def flush(end_line: int) -> None:
        nonlocal buf, kind_hint
        if buf and any(l.strip() for l in buf):
            body = "\n".join(buf).rstrip("\n")
            out.append({"section": section, "start": start, "end": end_line, "text": body,
                        "kind": kind_hint or classify(body)})
        buf = []
        kind_hint = None

    for i, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("```"):
            if not in_fence:
                flush(i - 1); start = i
            in_fence = not in_fence
            buf.append(line); kind_hint = "structure"
            if not in_fence:
                flush(i)
            continue
        if in_fence:
            buf.append(line); continue
        m = HEADING.match(line)
        if m:
            flush(i - 1)
            section = m.group(2)
            out.append({"section": section, "start": i, "end": i, "text": line, "kind": "heading"})
            start = i + 1
            continue
        if not line.strip():
            flush(i - 1); start = i + 1
            continue
        if not buf:
            start = i
        if line.lstrip().startswith("|"):
            kind_hint = "structure"
        buf.append(line)
    flush(text.count("\n") + 1)
    return out


def classify(body: str) -> str:
    """rule | history | mixed | structure -- see HISTORY_* and RULE_SIGNAL."""
    if body.lstrip().startswith(("|", "```", "<!--", "@")):
        return "structure"
    ref, narr = bool(HISTORY_REFERENCE.search(body)), bool(HISTORY_NARRATIVE.search(body))
    rule = bool(RULE_SIGNAL.search(body))
    if ref and narr:
        return "mixed" if rule else "history"
    return "rule" if rule else "structure"


def ceiling(text: str) -> int | None:
    m = MARKER.search(text)
    return int(m.group(1)) if m else None


def has_checklist(text: str, within_lines: int = 60) -> bool:
    """A numbered list of at least five steps near the top -- the "start here" a newcomer needs."""
    head = "\n".join(text.split("\n")[:within_lines])
    return len(re.findall(r"^\s*\d+\.\s+\S", head, re.M)) >= 5


def report(text: str, path: str = "CLAUDE.md") -> dict:
    paras = paragraphs(text)
    lines = text.count("\n") + (0 if text.endswith("\n") else 1)
    by_kind = {k: sum(1 for p in paras if p["kind"] == k) for k in ("rule", "history", "mixed", "structure", "heading")}
    words = lambda k: sum(len(p["text"].split()) for p in paras if p["kind"] == k)
    total_words = sum(len(p["text"].split()) for p in paras if p["kind"] != "heading")
    history_words = words("history") + words("mixed")
    sections: dict[str, dict] = {}
    for p in paras:
        s = sections.setdefault(p["section"], {"paragraphs": 0, "history": 0})
        if p["kind"] != "heading":
            s["paragraphs"] += 1
            s["history"] += p["kind"] in ("history", "mixed")
    return {
        "path": path, "lines": lines, "tokens_est": len(text) // 4, "ceiling": ceiling(text),
        "checklist_near_top": has_checklist(text), "paragraphs": by_kind,
        "history_word_share": round(history_words / total_words, 2) if total_words else 0.0,
        "sections": sections,
        "movable": [{"section": p["section"], "lines": f"{p['start']}-{p['end']}", "kind": p["kind"],
                     "first_line": p["text"].split("\n")[0][:100]} for p in paras if p["kind"] in ("history", "mixed")],
    }


def propose(text: str, history_text: str, history_rel: str, path: str = "CLAUDE.md") -> tuple[str, str]:
    """(new CLAUDE.md, new history file). Verbatim relocation of HISTORY paragraphs (not `mixed`: those carry a
    rule and need a human to split them); one pointer per section; lossless by assertion."""
    paras = paragraphs(text)
    moving = [p for p in paras if p["kind"] == "history"]
    if not moving:
        return text, history_text
    drop = {(p["start"], p["end"]) for p in moving}
    src = text.split("\n")
    keep: list[str] = []
    pointer_done: set[str] = set()
    i = 1
    while i <= len(src):
        para = next((p for p in moving if p["start"] == i), None)
        if para:
            if para["section"] not in pointer_done:
                keep.append(f"(History: *{para['section']}* in `{history_rel}`.)")
                pointer_done.add(para["section"])
            i = para["end"] + 1
            continue
        keep.append(src[i - 1]); i += 1
    new_text = re.sub(r"\n{3,}", "\n\n", "\n".join(keep))
    blocks: dict[str, list[str]] = {}
    for p in moving:
        blocks.setdefault(p["section"], []).append(p["text"])
    appended = [history_text.rstrip("\n"), "" if history_text.strip() else f"# {Path(path).name} — history\n\n"
                "Moved here verbatim from `" + path + "` by `claude_md_structure.py --propose`. Rules stay in that file; "
                "the paragraphs below are the incidents that produced them. Nothing is summarised."]
    for section, texts in blocks.items():
        appended.append(f"\n## {section}\n\n" + "\n\n".join(texts))
    new_history = "\n".join(a for a in appended if a is not None).strip("\n") + "\n"
    assert_lossless(moving, new_history)
    return new_text if new_text.endswith("\n") else new_text + "\n", new_history


def assert_lossless(moving: list[dict], new_history: str) -> None:
    """Every moved paragraph must appear byte-for-byte in the history text, or the relocation is refused.

    A separate function so the selftest can hand it a history that DROPPED a paragraph: in `propose` the
    move is lossless by construction, which made a mutation deleting this check unobservable.
    """
    for p in moving:
        if p["text"] not in new_history:
            raise RuntimeError(f"relocation would lose a paragraph verbatim (lines {p['start']}-{p['end']}); refusing")


def unified(old: str, new: str, name: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), f"a/{name}", f"b/{name}"))


def selftest() -> int:
    checks = 0
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    check("a bare imperative is a rule", classify("Never commit to main directly. Stage what you authored.") == "rule")
    check("an issue number plus a past-tense verb is history",
          classify("This bit us on #143: the fix PR bumped three components and #144 reverted it.") == "history")
    check("a rule that leans on its incident is mixed",
          classify("Never squash a promotion. v1.83.0 was squashed and v1.84.0 could not merge.") == "mixed")
    check("an issue number alone is a citation, not history", classify("See #206 for the decision. Never pool traceability.") == "rule")
    check("a table is structure", classify("| a | b |\n|---|---|") == "structure")
    doc = ("@AGENTS.md\n<!-- claude-md: max-lines 12 -->\n# T\n\n## Ship a fix\n\n1. a\n2. b\n3. c\n4. d\n5. e\n\n"
           "## Git flow\n\nBranch off dev. Never commit to main.\n\n"
           "This happened on #95: a promotion used to close the epic, and it was reopened twice.\n\n"
           "```bash\n# #123 was here\n```\n\n| x | y |\n|---|---|\n")
    r = report(doc)
    check("the ceiling marker is read", r["ceiling"] == 12, f"{r['ceiling']}")
    check("a five-step numbered list near the top counts as a checklist", r["checklist_near_top"])
    check("a fence mentioning '#123 was' is structure, not history",
          not any(m["lines"].startswith(str(doc.split(chr(10)).index("```bash") + 1)) for m in r["movable"]), f"{r['movable']}")
    check("exactly the one narrative paragraph is movable", len(r["movable"]) == 1 and r["movable"][0]["section"] == "Git flow", f"{r['movable']}")
    new_doc, hist = propose(doc, "", "docs/claude-md-history.md")
    check("propose keeps the rule", "Never commit to main." in new_doc)
    check("propose removes the history paragraph from CLAUDE.md", "This happened on #95" not in new_doc)
    check("...and places it VERBATIM in the history file", "This happened on #95: a promotion used to close the epic, and it was reopened twice." in hist)
    check("...under a heading naming the section it came from", "## Git flow" in hist)
    check("...leaving one pointer line in its place", new_doc.count("(History: *Git flow*") == 1, new_doc)
    check("the fence and table are untouched", "```bash" in new_doc and "| x | y |" in new_doc)
    check("a document with nothing to move is returned unchanged", propose("## A\n\nDo x.\n", "", "h.md") == ("## A\n\nDo x.\n", ""))
    try:
        assert_lossless([{"text": "this paragraph moved", "start": 3, "end": 3}], "# history\n\n(nothing here)\n")
        lossy_refused = False
    except RuntimeError:
        lossy_refused = True
    check("a history that dropped a moved paragraph is REFUSED, not written", lossy_refused)
    check("a document with no marker reports no ceiling", report("# T\n\nDo x.\n")["ceiling"] is None)
    over = "<!-- claude-md: max-lines 3 -->\n" + "rule\n" * 5
    check("past the ceiling is a verdict of 1", verdict(report(over)) == 1)
    check("within the ceiling is 0", verdict(report("<!-- claude-md: max-lines 30 -->\n" + "rule\n" * 5)) == 0)
    # #917: a fresh file, --set-ceiling, then --report must be 0 -- the marker is a line too.
    fresh = "# X\n\nrule one.\n\nrule two.\n"
    r0 = report(fresh)
    marker = f"<!-- claude-md: max-lines {ceiling_for(fresh, r0)} -->"
    once = fresh.replace("\n", "\n" + marker + "\n", 1)
    check("--set-ceiling on a file with no marker records the size WITH the marker (5 lines -> 6), and --report is 0",
          ceiling_for(fresh, r0) == 6 and verdict(report(once)) == 0, f"{ceiling_for(fresh, r0)} / {verdict(report(once))}")
    r1 = report(once)
    check("--set-ceiling again is idempotent: an existing marker is replaced with the same number", ceiling_for(once, r1) == 6 and MARKER.sub(f"<!-- claude-md: max-lines {ceiling_for(once, r1)} -->", once, 1) == once)
    check("no marker is 3 -- not applicable, not a pass", verdict(report("rule\n" * 5)) == 3)

    if failures:
        print(f"claude_md_structure selftest: {len(failures)} of {checks} checks FAILED", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"claude_md_structure selftest: {checks} checks passed")
    return 0


def ceiling_for(text: str, r: dict) -> int:
    """What --set-ceiling records: the current line count, plus one when the marker is about to be a new line."""
    return r["lines"] + (0 if r["ceiling"] is not None else 1)


def verdict(r: dict) -> int:
    if r["ceiling"] is None:
        return 3
    return 1 if r["lines"] > r["ceiling"] else 0


def print_report(r: dict, history_rel: str) -> None:
    print(f"{r['path']}: {r['lines']} lines, ≈{r['tokens_est']} tokens, ceiling "
          f"{r['ceiling'] if r['ceiling'] is not None else 'NOT RECORDED'}; "
          f"checklist near the top: {'yes' if r['checklist_near_top'] else 'no'}")
    p = r["paragraphs"]
    print(f"  paragraphs: {p['rule']} rule, {p['history']} history, {p['mixed']} mixed (rule + incident), "
          f"{p['structure']} structure; history is {int(r['history_word_share'] * 100)}% of the words")
    if r["movable"]:
        print(f"  {len(r['movable'])} paragraph(s) read as incident narrative. Relocate verbatim to `{history_rel}` with "
              f"`--propose` (writes nothing until --write); `mixed` ones need a human to split the rule from its story:")
        for m in r["movable"][:12]:
            print(f"    - {m['section']}  lines {m['lines']}  [{m['kind']}]  {m['first_line']}")
        if len(r["movable"]) > 12:
            print(f"    … {len(r['movable']) - 12} more")
    v = verdict(r)
    if v == 1:
        print(f"  FAIL: {r['lines']} lines is past the recorded ceiling of {r['ceiling']}. Move history out (above), "
              "then lower the ceiling to the new size; or raise it in a change that says why. Nothing is deleted "
              "either way.", file=sys.stderr)
    elif v == 3:
        print("  not applicable — no `<!-- claude-md: max-lines N -->` marker. Record one at the measured size with "
              "`--set-ceiling --write`; a ceiling nobody set is not a pass.")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("path", nargs="?", default="CLAUDE.md")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--propose", action="store_true", help="print the lossless relocation diff (CLAUDE.md + history file)")
    ap.add_argument("--set-ceiling", action="store_true", help="the marker line at the measured size")
    ap.add_argument("--history", default=DEFAULT_HISTORY, help=f"history file, relative to the project (default {DEFAULT_HISTORY})")
    ap.add_argument("--write", action="store_true", help="apply --propose / --set-ceiling instead of printing")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    path = Path(a.path)
    if not path.is_file():
        print(f"claude_md_structure: {path} does not exist — nothing to audit (not a pass)", file=sys.stderr)
        return 3
    text = path.read_text(encoding="utf-8")
    r = report(text, str(path))
    if a.set_ceiling:
        # The ceiling is the size the file HAS once the marker is in it (#917): a new marker is one more
        # line, so recording the pre-insertion count left every first run one line over its own ceiling.
        marker = f"<!-- claude-md: max-lines {ceiling_for(text, r)} -->"
        if a.write:
            new = MARKER.sub(marker, text, 1) if r["ceiling"] is not None else text.replace("\n", "\n" + marker + "\n", 1)
            path.write_text(new, encoding="utf-8")
            print(f"recorded: {marker} in {path}")
        else:
            print(marker)
        return 0
    if a.propose:
        hist_path = path.parent / a.history
        hist_text = hist_path.read_text(encoding="utf-8") if hist_path.is_file() else ""
        new_doc, new_hist = propose(text, hist_text, a.history, str(path))
        if new_doc == text:
            print("nothing to move: no paragraph reads as pure incident narrative"); return 0
        if a.write:
            hist_path.parent.mkdir(parents=True, exist_ok=True)
            hist_path.write_text(new_hist, encoding="utf-8"); path.write_text(new_doc, encoding="utf-8")
            print(f"moved {len([p for p in paragraphs(text) if p['kind'] == 'history'])} paragraph(s) verbatim to {hist_path}; "
                  f"{path}: {text.count(chr(10))} -> {new_doc.count(chr(10))} lines. Review the diff, then lower the ceiling.")
        else:
            sys.stdout.write(unified(text, new_doc, str(path)))
            sys.stdout.write(unified(hist_text, new_hist, a.history))
        return 0
    if a.json:
        print(json.dumps(r, indent=2)); return verdict(r)
    print_report(r, a.history)
    return verdict(r)


if __name__ == "__main__":
    sys.exit(main())
