#!/usr/bin/env python3
"""CHANGELOG fragments: each PR adds `changelog.d/<issue>-<slug>.md`; the arm folds them into CHANGELOG.md (#1825).

Run:  python3 scripts/changelog_fragments.py --check               # every fragment is well-formed and placeable (a doctor gate)
      python3 scripts/changelog_fragments.py --fold                # at the arm: put each fragment under its section's `### Unreleased`, delete it
      python3 scripts/changelog_fragments.py --fold --into v1.157.0   # after the arm: into the already-armed release block
      python3 scripts/changelog_fragments.py --fold --dry-run      # print the result, change nothing
      python3 scripts/changelog_fragments.py --selftest

WHY (owner's decision on #1825; measured 2026-10-10). Every PR added its bullet at the same place, the top of the component's `### Unreleased`, so
two PRs open at once edited the same lines and whichever merged second conflicted: of 85 merges into `dev` since 2026-10-09, 67 (79%) touched
CHANGELOG.md. A new file cannot conflict with another PR's new file, so each PR adds one and the arm folds them in.

A FRAGMENT is one bullet for one component, so traceability stays one bullet per issue:

    section: rails-flow
    - **The headline — `path/it/changed`** (#1234). The body, as it would stand in CHANGELOG.md.
      Continuation lines are indented two spaces.

* `section:` is a PREFIX of the `## ` heading it belongs to (`rails-flow`, `qa-flow`, `Repository hygiene`). It must name ONE heading: where two headings share the
  prefix, the one that has a `### Unreleased` wins; if that still leaves two (or the arm has converted them all), write more of the heading. An unknown or
  ambiguous prefix is an error, never a guess.
* The bullet must cite a path in backticks that exists in the repo, and one that belongs to the component of the section: the same rule the CHANGELOG's own
  bullets are held to (`changelog-bullet-unplaceable`, `changelog-bullet-misfiled`), read from `lint_self_consistency.py`, so there is one home for it.
* A change that spans two components is two files: `1234-rails-flow.md` and `1234-qa-flow.md`. The name starts with the issue number, which is the fold's order.

THE FOLD IS THE DANGEROUS PART, because a hand-resolved CHANGELOG conflict is what dropped a bullet at the v1.94.0 arm (#728). So it is deterministic (numeric
issue, then name), refuses to run on a CHANGELOG.md with uncommitted changes, writes nothing unless it can place EVERY fragment, and asserts that the bullet
count after is the count before plus the fragments. A fragment is deleted only after the file is written.

`--promotion` in extract_release_notes.py refuses an unfolded fragment, the way it refuses a `### Unreleased`: a promotion carries neither.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "plugins" / "rails-flow" / "scripts"))
import fixture_git  # noqa: E402  (#1588: a fixture's git touches only its own temp repo)
FRAG_DIR = "changelog.d"
NAME = re.compile(r"^(\d+)-[a-z0-9][a-z0-9-]*\.md$")
_CITATION = re.compile(r"\(#(\d+)\b")
UNRELEASED = "### Unreleased"
RELEASE_NOTE = "The release number is assigned at promotion."


class FragmentError(Exception):
    pass


def fragment_files(root: Path) -> list[Path]:
    """The fragments, in fold order: issue number, then name. README.md is not one."""
    d = root / FRAG_DIR
    if not d.is_dir():
        return []
    files = [p for p in d.glob("*.md") if p.name != "README.md"]
    return sorted(files, key=lambda p: (int(m.group(1)) if (m := re.match(r"(\d+)-", p.name)) else 10 ** 9, p.name))


def parse(text: str, name: str) -> tuple[str, list[str]]:
    """(the section prefix, the bullet's lines) of one fragment."""
    if not NAME.match(name):
        raise FragmentError(f"{name}: the name must be `<issue number>-<slug>.md` (lower case, digits and hyphens)")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n").split("\n")      # a fragment saved with CRLF endings parses the same
    first = next((i for i, l in enumerate(lines) if l.strip()), None)
    if first is None:
        raise FragmentError(f"{name}: empty")
    m = re.match(r"^section:[ \t]*(\S.*?)[ \t]*$", lines[first])
    if m is None:
        raise FragmentError(f"{name}: the first line must be `section: <heading prefix>`")
    body = [l.rstrip() for l in lines[first + 1:]]
    while body and not body[0].strip():
        body.pop(0)
    if not body or not body[0].startswith("- "):
        raise FragmentError(f"{name}: after `section:` comes ONE bullet, starting `- `")
    for l in body[1:]:
        if l.startswith("- "):
            raise FragmentError(f"{name}: two bullets; one fragment is one bullet (use one file per component or issue)")
        if l.strip() and not l.startswith("  "):
            raise FragmentError(f"{name}: a continuation line must be indented two spaces: {l[:60]!r}")
    while body and not body[-1].strip():
        body.pop()
    if len(" ".join(body)) < 40:
        raise FragmentError(f"{name}: the bullet is too short to be a release note")
    return m.group(1), body


_RELEASE = re.compile(r"\(release (v\d+\.\d+\.\d+)\)")


def sections(changelog: str) -> list[tuple[int, str, bool, frozenset]]:
    """(line index, heading, has a `### Unreleased`, the `(release vX)` tags its blocks carry) for every `## ` section."""
    out: list[list] = []
    for i, line in enumerate(changelog.split("\n")):
        if line.startswith("## "):
            out.append([i, line[3:].strip(), False, set()])
        elif out and line.strip() == UNRELEASED:
            out[-1][2] = True
        elif out and line.startswith("### "):
            out[-1][3].update(_RELEASE.findall(line))
    return [(i, h, u, frozenset(t)) for i, h, u, t in out]


def resolve(prefix: str, secs: list[tuple[int, str, bool, frozenset]], name: str, into: str | None = None) -> tuple[int, str]:
    """The `## ` section a prefix names. Where several share it: the one with a `### Unreleased`; else, for `--into`, the one holding that release block;
    else, if they are the SAME heading (`## Repository hygiene` appears twice), the first, which is the live one at the top. Different headings with
    nothing to tell them apart are an error: guessing which rails-stack section is live would file a note under a dead one."""
    hits = [s for s in secs if s[1].startswith(prefix)]
    if not hits:
        raise FragmentError(f"{name}: no `## ` heading of the CHANGELOG starts with {prefix!r}")
    if len(hits) > 1:
        pool = [s for s in hits if s[2]] or hits
        if into is not None:
            pool = [s for s in pool if into in s[3]] or pool
        if len(pool) == 1 or len({s[1] for s in pool}) == 1:
            hits = [pool[0]]
        else:
            raise FragmentError(f"{name}: {prefix!r} starts {len(hits)} headings ({'; '.join(repr(s[1]) for s in hits)}): write more of the heading")
    return hits[0][0], hits[0][1]


def _section_end(lines: list[str], start: int) -> int:
    return next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))


def _block(lines: list[str], sec_start: int, sec_end: int, into: str | None) -> int | None:
    """The line index of the `### …` heading to put bullets under, or None."""
    for i in range(sec_start + 1, sec_end):
        if into is None and lines[i].strip() == UNRELEASED:
            return i
        if into is not None and lines[i].startswith("### ") and f"(release {into})" in lines[i]:
            return i
    return None


def count_bullets(text: str) -> int:
    return sum(1 for l in text.split("\n") if l.startswith("- "))


def fold_text(changelog: str, frags: list[tuple[str, str, list[str]]], into: str | None = None) -> str:
    """CHANGELOG text with each (name, section prefix, bullet lines) placed. Raises FragmentError, never a partial result."""
    secs = sections(changelog)
    placed: dict[int, list[list[str]]] = {}
    for name, prefix, bullet in frags:
        start, _ = resolve(prefix, secs, name, into)
        placed.setdefault(start, []).append(bullet)
    lines = changelog.split("\n")
    # bottom-up, so an insertion does not move the sections still to be done
    for start in sorted(placed, reverse=True):
        end = _section_end(lines, start)
        heading = _block(lines, start, end, into)
        group: list[str] = []
        for bullet in placed[start]:
            group += bullet
        if heading is None:
            if into is not None:
                raise FragmentError(f"the section {lines[start][3:].strip()!r} has no block `(release {into})`")
            at = start + 1
            while at < end and not lines[at].strip():
                at += 1
            lines[at:at] = [UNRELEASED, "", RELEASE_NOTE, ""] + group + [""]
            continue
        nxt = next((i for i in range(heading + 1, end) if lines[i].startswith("### ")), end)
        first = next((i for i in range(heading + 1, nxt) if lines[i].startswith("- ")), None)
        if first is None:
            at = heading + 1
            while at < nxt and not lines[at].strip():
                at += 1
            lines[at:at] = group + [""] if at < nxt else [""] + group + [""]
        else:
            lines[first:first] = group
    result = "\n".join(lines)
    assert_bullets(changelog, result, len(frags))
    return result


def assert_bullets(before: str, after: str, added: int) -> None:
    """The fold's own check: the bullets after are the bullets before plus the fragments, or nothing is written."""
    want = count_bullets(before) + added
    if count_bullets(after) != want:
        raise FragmentError(f"the fold would leave {count_bullets(after)} bullets, not {want}: refused, nothing written")


def load(root: Path) -> list[tuple[str, str, list[str]]]:
    out = []
    for p in fragment_files(root):
        prefix, bullet = parse(p.read_text(encoding="utf-8"), p.name)
        out.append((p.name, prefix, bullet))
    return out


def check(root: Path = ROOT) -> list[str]:
    """Problems with the fragments: malformed, unplaceable, or naming no path of the component of their section."""
    import json
    findings: list[str] = []
    cl = root / "CHANGELOG.md"
    secs = sections(cl.read_text(encoding="utf-8")) if cl.is_file() else []
    try:
        manifest = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
        plugins = [p["name"] for p in manifest.get("plugins", [])]
    except (OSError, ValueError, KeyError, TypeError):
        plugins = []
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import lint_self_consistency as L          # the one home of the owner rule
    seen: dict[str, str] = {}
    for p in fragment_files(root):
        try:
            prefix, bullet = parse(p.read_text(encoding="utf-8"), p.name)
            _, heading = resolve(prefix, secs, p.name)
        except FragmentError as exc:
            findings.append(str(exc))
            continue
        body = " ".join(bullet)
        cited = {c for c in L._BULLET_PATH.findall(body) if (root / c).exists()}
        owners = {L._changelog_owner(c, plugins) for c in cited}
        if not cited:
            findings.append(f"{p.name}: names no path that exists in this repo, in backticks, so nothing says which component it belongs to (changelog-bullet-unplaceable)")
        elif L._changelog_section_owner(heading, plugins) not in owners:
            findings.append(f"{p.name}: sits under {heading!r} but every path it names belongs to {sorted(owners)} (changelog-bullet-misfiled)")
        m = _CITATION.search(body)          # the first parenthesised `(#n` : `(#1825)` or `(#1825, the coordinator's call)`
        issue = m.group(1) if m else None
        if issue is None:
            findings.append(f"{p.name}: the bullet cites no `(#n)` issue")
        elif not p.name.startswith(f"{issue}-"):
            findings.append(f"{p.name}: the name starts with a different issue number than the bullet's (#{issue})")
        key = f"{prefix}|{' '.join(bullet)}"
        if key in seen:
            findings.append(f"{p.name}: the same bullet as {seen[key]}")
        seen[key] = p.name
    return findings


def _dirty(root: Path) -> bool:
    r = subprocess.run(["git", "status", "--porcelain", "--", "CHANGELOG.md"], cwd=root, capture_output=True, text=True)
    return r.returncode != 0 or bool(r.stdout.strip())      # a git failure (not a repository, no git) is treated as dirty: refuse, never write blind


def fold(root: Path = ROOT, into: str | None = None, dry_run: bool = False, require_clean: bool = True) -> int:
    frags = load(root)
    if not frags:
        print("changelog fragments: none to fold")
        return 0
    cl = root / "CHANGELOG.md"
    if require_clean and not dry_run and _dirty(root):
        print("changelog fragments: CHANGELOG.md has uncommitted changes; commit or stash them first (a fold must be one reviewable change)", file=sys.stderr)
        return 2
    new = fold_text(cl.read_text(encoding="utf-8"), frags, into)
    if dry_run:
        print(new)
        return 0
    cl.write_text(new, encoding="utf-8")
    for p in fragment_files(root):
        p.unlink()
    print(f"changelog fragments: folded {len(frags)} into CHANGELOG.md" + (f" ({into})" if into else ""))
    return 0


def selftest() -> int:
    failures: list[str] = []
    total = 0

    def ck(label: str, ok: bool, detail: object = "") -> None:
        nonlocal total
        total += 1
        if not ok:
            failures.append(f"{label}{(' -- ' + str(detail)) if detail != '' else ''}")

    def err(fn, *a):
        try:
            fn(*a)
        except FragmentError as exc:
            return str(exc)
        return None

    good = "section: rails-flow\n- **A headline — `plugins/rails-flow/x.sh`** (#12). The body of the release note, long enough to be one.\n  A continuation line.\n"
    prefix, bullet = parse(good, "12-a-thing.md")
    ck("a fragment parses", prefix == "rails-flow" and len(bullet) == 2 and bullet[0].startswith("- **A headline"), (prefix, bullet))
    for label, text, name in (("a bad name", good, "A thing.md"), ("a name with no issue number", good, "thing.md"), ("empty", "\n", "1-a.md"),
                              ("no section line", "- **x — `a/b.md`** (#1) long enough to count as a note here.\n", "1-a.md"),
                              ("no bullet", "section: qa-flow\njust words here that are long enough to be a note\n", "1-a.md"),
                              ("two bullets", good + "- **Another — `a/b.md`** (#13) a second bullet in the same file is refused.\n", "12-a.md"),
                              ("an unindented continuation", good + "not indented\n", "12-a.md"),
                              ("a bullet too short", "section: qa-flow\n- **x**\n", "1-a.md")):
        ck(f"{label} is refused", err(parse, text, name) is not None)
    ck("two bullets is refused for THAT reason", "two bullets" in (err(parse, good + "\n- **Another — `a/b.md`** (#13) a second bullet in the same file is refused.\n", "12-a.md") or ""))

    cl = ("# Changelog\n\n## Repository hygiene\n\n### Unreleased\n\nThe release number is assigned at promotion.\n\n- **old repo — `scripts/a.py`** (#1). old.\n\n"
          "### 2026-10-08 (release v1.155.0)\n\n- **shipped — `scripts/b.py`** (#2). shipped.\n\n"
          "## rails-flow (agentic flow plugin)\n\n### 1.58.0 (release v1.155.0) — 2026-10-08\n\n- **rf shipped — `plugins/rails-flow/a.sh`** (#3). shipped.\n\n"
          "## qa-flow (independent QA plugin)\n\n### Unreleased\n\n- **qa old — `plugins/qa-flow/a.sh`** (#4). old.\n\n### 1.2.0 (release v1.154.0)\n\n- **qa shipped — `plugins/qa-flow/b.sh`** (#5). shipped.\n")
    f = [("20-qa.md", "qa-flow", ["- **qa new — `plugins/qa-flow/c.sh`** (#20). new qa note that is long enough."]),
         ("21-repo.md", "Repository hygiene", ["- **repo new — `scripts/c.py`** (#21). new repo note that is long enough."]),
         ("22-rf.md", "rails-flow", ["- **rf new — `plugins/rails-flow/c.sh`** (#22). new rails-flow note long enough.", "  continued."])]
    def in_order(text: str, *needles: str) -> bool:
        """Every needle is present, and they appear in this order (an absent one is False, never an exception)."""
        at = [text.find(n) for n in needles]
        return all(a >= 0 for a in at) and at == sorted(at)

    def folded(text, frags, into=None):
        """The folded text, or `ERROR: <why>` so a broken fold fails a NAMED check instead of crashing the selftest."""
        try:
            return fold_text(text, frags, into)
        except FragmentError as exc:
            return f"ERROR: {exc}"

    out = folded(cl, f)
    ck("the fold adds exactly the fragments", count_bullets(out) == count_bullets(cl) + 3, (count_bullets(out), count_bullets(cl)))
    ck("a fragment goes ABOVE the section's existing bullets", in_order(out, "#20", "#4"), out[:600])
    ck("...under the right section", in_order(out, "## qa-flow", "#20", "### 1.2.0"))
    ck("a section with no Unreleased gets one", "## rails-flow (agentic flow plugin)\n\n### Unreleased\n\nThe release number is assigned at promotion.\n\n- **rf new" in out, out[out.find("## rails-flow"):][:300])
    ck("a continuation line travels with its bullet", "(#22). new rails-flow note long enough.\n  continued." in out)
    ck("released blocks are untouched", "- **shipped — `scripts/b.py`** (#2). shipped." in out and "(release v1.154.0)\n\n- **qa shipped" in out)
    ck("the fold is deterministic", folded(cl, f) == out)
    ck("the bullet-count assertion refuses a dropped bullet", err(assert_bullets, "- a\n- b\n", "- a\n", 1) is not None)
    ck("...and a duplicated one", err(assert_bullets, "- a\n", "- a\n- a\n- a\n", 1) is not None)
    ck("...and accepts the right count", err(assert_bullets, "- a\n", "- a\n- b\n", 1) is None)
    two = folded(cl, [f[0], ("21-qa.md", "qa-flow", ["- **qa second — `plugins/qa-flow/d.sh`** (#21). second qa note long enough here."])])
    ck("two fragments for one section keep their order", in_order(two, "#20", "#21", "#4"), two[two.find("## qa-flow"):][:400])
    ck("an unknown section is an error", err(fold_text, cl, [("1-x.md", "nope", ["- x"])]) is not None)
    ck("an ambiguous prefix is an error",
       "starts 2 headings" in (err(fold_text, "## rails-flow a\n\n## rails-flow b\n", [("1-x.md", "rails-flow", ["- x"])]) or ""))
    dup = "## Repository hygiene\n\n### 2026-10-08 (release v1.155.0)\n\n- a\n\n## rails-flow x\n\n## Repository hygiene\n\n### 2026-09-01 (release v1.100.0)\n\n- b\n"
    ck("two IDENTICAL headings with no Unreleased resolve to the first (the live one at the top)",
       "### Unreleased" in (folded(dup, [("1-x.md", "Repository hygiene", ["- n (#1)"])]) or "") and folded(dup, [("1-x.md", "Repository hygiene", ["- n (#1)"])]).index("### Unreleased") < dup.index("## rails-flow") + 40)
    armed_dup = "## Repository hygiene\n\n### 2026-09-01 (release v1.100.0)\n\n- a (#1)\n\n## rails-flow x\n\n## Repository hygiene\n\n### 2026-10-10 (release v9.0.0)\n\n- b (#2)\n"
    ck("--into on identical headings goes to the one holding the release block (the SECOND here, not the first)",
       in_order(folded(armed_dup, [("3-x.md", "Repository hygiene", ["- n (#3)"])], "v9.0.0"), "(release v9.0.0)", "- n (#3)", "- b (#2)"))
    two_rs = "## rails-stack (old)\n\n### 1.0 (release v1.0.0)\n\n- a\n\n## rails-stack (live)\n\n### 2.0 (release v9.0.0)\n\n- b\n"
    ck("DIFFERENT headings with nothing to tell them apart are still an error", "write more of the heading" in (err(fold_text, two_rs, [("1-x.md", "rails-stack", ["- n"])]) or ""))
    ck("...but --into picks the one holding the armed block", in_order(folded(two_rs, [("1-x.md", "rails-stack", ["- n (#1)"])], "v9.0.0"), "(release v9.0.0)", "- n (#1)", "- b"))
    ck("a fragment with CRLF endings parses", parse(good.replace("\n", "\r\n"), "12-a-thing.md")[0] == "rails-flow")
    ck("...unless exactly one has an Unreleased",
       err(fold_text, "## rails-flow a\n\n### Unreleased\n\n- o\n\n## rails-flow b\n", [("1-x.md", "rails-flow", ["- x (#1)"])]) is None)
    armed = cl.replace("### Unreleased\n\nThe release number is assigned at promotion.\n\n- **old repo", "### 2026-10-10 (release v1.156.0)\n\n- **old repo")
    into = folded(armed, [f[1]], "v1.156.0")
    ck("--into puts a late fragment in the armed block", in_order(into, "(release v1.156.0)", "#21", "#1)"), into[:500])
    ck("--into a block that does not exist is an error", err(fold_text, cl, [f[1]], "v9.9.9") is not None)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "changelog.d").mkdir()
        (root / "CHANGELOG.md").write_text(cl, encoding="utf-8")
        (root / ".claude-plugin").mkdir()
        (root / ".claude-plugin" / "marketplace.json").write_text('{"plugins": [{"name": "rails-flow"}, {"name": "qa-flow"}]}', encoding="utf-8")
        (root / "scripts").mkdir()
        (root / "scripts" / "c.py").write_text("print(1)\n")
        (root / "plugins" / "qa-flow").mkdir(parents=True)
        (root / "plugins" / "qa-flow" / "c.sh").write_text("#!/bin/sh\n")
        (root / "changelog.d" / "README.md").write_text("not a fragment\n")
        ck("README.md is not a fragment", fragment_files(root) == [])
        for n in ("10-ten.md", "9-nine.md", "9-also.md"):
            (root / "changelog.d" / n).write_text("section: qa-flow\n")
        ck("fragments fold in numeric issue order, then name (9 before 10)", [p.name for p in fragment_files(root)] == ["9-also.md", "9-nine.md", "10-ten.md"], [p.name for p in fragment_files(root)])
        for n in ("10-ten.md", "9-nine.md", "9-also.md"):
            (root / "changelog.d" / n).unlink()
        (root / "changelog.d" / "21-repo.md").write_text("section: Repository hygiene\n" + f[1][2][0] + "\n")
        ck("a placeable fragment checks clean", check(root) == [], check(root))
        (root / "changelog.d" / "22-qa.md").write_text("section: qa-flow\n- **qa — `scripts/c.py`** (#22). a note that names a path of another component.\n")
        ck("a fragment naming only another component's path is misfiled", any("misfiled" in x for x in check(root)), check(root))
        (root / "changelog.d" / "22-qa.md").write_text("section: qa-flow\n- **qa note with no path at all** (#22). a note that names nothing it changed.\n")
        ck("a fragment naming no path is unplaceable", any("unplaceable" in x for x in check(root)), check(root))
        (root / "changelog.d" / "23-qa.md").write_text("section: qa-flow\n- **qa — `plugins/qa-flow/c.sh`** (#99). the name and the bullet cite different issues.\n")
        ck("a name and a bullet that cite different issues are refused", any("different issue" in x for x in check(root)), check(root))
        for n in ("22-qa.md", "23-qa.md"):
            (root / "changelog.d" / n).unlink()
        # a fold that cannot place EVERY fragment writes nothing and deletes nothing
        (root / "changelog.d" / "30-bad.md").write_text("section: no-such-section\n- **bad — `scripts/c.py`** (#30). a fragment whose section does not exist.\n")
        keep = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        refused = err(fold, root, None, False, False)
        ck("a fold with one unplaceable fragment is refused", refused is not None, refused)
        ck("...and writes nothing", (root / "CHANGELOG.md").read_text(encoding="utf-8") == keep)
        ck("...and deletes no fragment", [p.name for p in fragment_files(root)] == ["21-repo.md", "30-bad.md"], [p.name for p in fragment_files(root)])
        (root / "changelog.d" / "30-bad.md").unlink(missing_ok=True)
        before = count_bullets(cl)
        rc = fold(root, require_clean=False)
        after = (root / "CHANGELOG.md").read_text(encoding="utf-8")
        ck("fold exits 0, writes the bullet and deletes the fragment", rc == 0 and "#21" in after and fragment_files(root) == [], (rc, fragment_files(root)))
        ck("the bullet count grew by one", count_bullets(after) == before + 1)
        ck("a second fold finds nothing", fold(root, require_clean=False) == 0 and (root / "CHANGELOG.md").read_text(encoding="utf-8") == after)
    with tempfile.TemporaryDirectory() as td:
        g = Path(td)
        fixture_git.init(g)
        (g / "CHANGELOG.md").write_text("## Repository hygiene\n\n### Unreleased\n\n- **x — `scripts/a.py`** (#1). x.\n")
        (g / "changelog.d").mkdir()
        (g / "changelog.d" / "2-y.md").write_text("section: Repository hygiene\n- **y — `scripts/a.py`** (#2). a note long enough to be one, here.\n")
        fixture_git.run(g, "add", "CHANGELOG.md")
        fixture_git.run(g, "commit", "-qm", "init")
        clean = fold(g, dry_run=True)
        (g / "CHANGELOG.md").write_text((g / "CHANGELOG.md").read_text() + "\nuncommitted edit\n")
        before = (g / "CHANGELOG.md").read_text()
        rc = fold(g)
        ck("a dry-run fold of a clean CHANGELOG works", clean == 0)
        with tempfile.TemporaryDirectory() as notrepo:
            (Path(notrepo) / "CHANGELOG.md").write_text("## Repository hygiene\n")
            (Path(notrepo) / "changelog.d").mkdir()
            (Path(notrepo) / "changelog.d" / "2-y.md").write_text("section: Repository hygiene\n- **y — `scripts/a.py`** (#2). a note long enough to be one, here.\n")
            ck("a git failure is treated as a dirty CHANGELOG (refused, nothing written)", fold(Path(notrepo)) == 2 and (Path(notrepo) / "changelog.d" / "2-y.md").exists())
        ck("a fold refuses a CHANGELOG with uncommitted changes", rc == 2, rc)
        ck("...and changes nothing", (g / "CHANGELOG.md").read_text() == before and (g / "changelog.d" / "2-y.md").exists())
    if failures:
        print(f"changelog_fragments selftest: {len(failures)} failure(s) of {total}")
        for x in failures:
            print(f"  FAIL {x}")
        return 1
    print(f"changelog_fragments selftest: {total} checks passed")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--fold", action="store_true")
    ap.add_argument("--into", help="fold into the already-armed block `(release vX.Y.Z)` instead of `### Unreleased`")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.fold:
        try:
            return fold(ROOT, a.into, a.dry_run)
        except FragmentError as exc:
            print(f"changelog fragments: {exc}", file=sys.stderr)
            return 2
    problems = check(ROOT)
    for p in problems:
        print(p)
    print(f"changelog fragments: {len(fragment_files(ROOT))} checked, {len(problems)} finding(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
