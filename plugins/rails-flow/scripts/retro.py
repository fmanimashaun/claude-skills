#!/usr/bin/env python3
"""The retro: which review findings recur, and what check could stop each one being written twice (#1339).

Review findings share one record shape (`findings.py`, #138) and the per-PR reviewers write them to
`docs/evidence/reviews/prs/<branch>/*-findings.jsonl` (a full review writes `docs/evidence/reviews/<date>/findings.jsonl`).
Nothing counted them. This reads those records, groups them, and writes ONE report: what recurs, in how many PRs,
which groups look mechanical (a fixed file pattern or a repeated signature: a check could catch them) and which are
judgement (a line in the review doctrine), each citing the findings behind it. It changes nothing else.

WHAT IT COUNTS, AND WHY NOT MORE:
  * A group "recurs" when its records come from MIN_PRS or more distinct SOURCES (a PR directory, or a dated review
    directory), not when it has many records: five findings in one review is one review's thoroughness, not a habit.
  * Groups are by `category`, then by `signature` (or `rule`). A record without a category is counted and shown as
    `(no category)` and NEVER proposed on: it cannot be classified.
  * `mechanical` is a heuristic that proposes a check for a person to judge, never a verdict: a signature that recurs
    in 2+ sources (the agent's own stable identity for a defect), or a file pattern (the first two directories and the
    suffix) that 60% of the group's records share across MIN_PRS+ sources. Everything else is `judgement`.
  * Severity has no single vocabulary in real records (P1-P3, blocker/major/minor, BLOCKING/SUGGESTION...). The report
    maps the spellings it knows to high/medium/low and LISTS every raw spelling it mapped; a spelling it does not know
    is `unmapped` and listed, never guessed.

WHAT IT REFUSES TO DO: report clean over input it did not read. No findings files, or files with no usable record, is
exit 2 ("nothing to read"), never an empty "nothing recurs". Every line it could not read is counted and named.

Not in this slice (stated, not hidden): PR review comments via `gh`, and session transcripts. Only findings records.

Exit: 0 report produced · 2 unusable (bad arguments, no findings files, no usable record). Stdlib only; `git` only for
the date of a file when --since/--until is used.

Usage:
    python3 retro.py [--root docs/evidence/reviews] [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--min-prs 3]
                     [--date YYYY-MM-DD] [--out docs/brain/retro/<date>.md | --stdout]
    python3 retro.py --selftest
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path, PurePosixPath

MIN_PRS = 3
DOMINANT = 0.6
NO_CATEGORY = "(no category)"
LEVELS = ("high", "medium", "low")
# The spellings seen in real records (Retask, 2026-10-10, 208 records) and their level. Case-insensitive. `resolved` is a
# state, not a severity, so it is deliberately absent: it is reported as unmapped.
SEVERITY_MAP = {
    "p1": "high", "blocker": "high", "blocking": "high",
    "p2": "medium", "major": "medium", "medium": "medium",
    "p3": "low", "minor": "low", "low": "low", "suggestion": "low", "advisory": "low", "info": "low",
}
DATED = re.compile(r"^\d{4}-\d{2}-\d{2}")
# A severity word written into the category ("claims-vs-enforcement (BLOCKING)", "Suggestion coverage-gap") splits one recurring class into
# several one-off groups. Leading or trailing severity words, with or without parentheses, are stripped and the case folded; nothing else
# is merged (a different phrase is a different category), and the report lists every spelling it merged.
SEVERITY_WORDS = r"(?:blocking|blocker|suggestion|advisory|major|minor|medium|low|info|p[123])"
EDGE = re.compile(rf"^(?:\(?{SEVERITY_WORDS}\)?[\s:,-]+)+|(?:[\s:,-]+\(?{SEVERITY_WORDS}\)?)+$", re.IGNORECASE)


class Unusable(Exception):
    """Exit 2: this check could not run, which is not the same as 'nothing recurs'."""


def source_of(path: Path, root: Path) -> str:
    """The review a file belongs to: a PR directory (`prs/<slug>/...`), a dated directory, else its own directory."""
    parts = path.relative_to(root).parts
    if len(parts) >= 3 and parts[0] == "prs":
        return f"prs/{parts[1]}"
    if parts and DATED.match(parts[0]):
        return parts[0]
    return "/".join(parts[:-1]) or "."


def dated_by_name(source: str) -> str | None:
    match = DATED.match(source.split("/")[-1])
    return match.group(0) if match else None


def git_date(path: Path, runner=subprocess.run) -> str | None:
    try:
        out = runner(["git", "log", "-1", "--format=%cs", "--", str(path)], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    line = (out.stdout or "").strip()
    return line if out.returncode == 0 and re.fullmatch(r"\d{4}-\d{2}-\d{2}", line) else None


def read_file(path: Path):
    """(records, skipped): `skipped` is [(line_number, why)]: a line this cannot read is named, never dropped silently."""
    records, skipped = [], []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return [], [(0, f"unreadable file: {exc}")]
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            skipped.append((number, "not JSON"))
            continue
        if not isinstance(record, dict):
            skipped.append((number, f"a {type(record).__name__}, not an object"))
            continue
        records.append(record)
    return records, skipped


def text_of(value) -> str:
    return value.strip() if isinstance(value, str) and value.strip() else ""


def category_of(record) -> tuple[str, str]:
    """(the key records are grouped by, the spelling as written); a missing category is NO_CATEGORY."""
    raw = text_of(record.get("category"))
    if not raw:
        return NO_CATEGORY, NO_CATEGORY
    key = " ".join(EDGE.sub("", raw).lower().split())
    return (key or raw.lower()), raw


def level_of(raw) -> str | None:
    return SEVERITY_MAP.get(raw.strip().lower()) if isinstance(raw, str) else None


def file_pattern(file_field) -> str | None:
    """`app/models/**/*.rb` from `app/models/invoice.rb:41`; None when there is no directory or no suffix to share."""
    name = re.sub(r":\d+(-\d+)?$", "", text_of(file_field))
    path = PurePosixPath(name)
    if len(path.parts) < 2 or not path.suffix:
        return None
    lead = "/".join(path.parts[: 2 if len(path.parts) >= 3 else 1])
    return f"{lead}/**/*{path.suffix}"


def analyse(items, min_prs):
    """`items` is [(source, record)]. Returns the numbers the report is written from."""
    by_cat, spellings = defaultdict(list), defaultdict(Counter)
    for source, record in items:
        key, raw = category_of(record)
        by_cat[key].append((source, record))
        spellings[key][raw] += 1
    sig_sources, sig_cat = defaultdict(set), {}
    for source, record in items:
        sig = text_of(record.get("signature")) or text_of(record.get("rule"))
        if sig:
            sig_sources[sig].add(source)
            sig_cat.setdefault(sig, category_of(record)[0])
    groups = []
    for category, members in by_cat.items():
        sources = sorted({s for s, _ in members})
        levels = Counter(level_of(r.get("severity")) or "unmapped" for _, r in members)
        patterns = Counter(p for _, r in members if (p := file_pattern(r.get("file"))))
        top, top_n = (patterns.most_common(1)[0] if patterns else (None, 0))
        pattern_sources = {s for s, r in members if file_pattern(r.get("file")) == top} if top else set()
        repeated = sorted(sig for sig, srcs in sig_sources.items() if sig_cat.get(sig) == category and len(srcs) >= 2)
        recurs = category != NO_CATEGORY and len(sources) >= min_prs
        mechanical = None
        if recurs and repeated:
            mechanical = f"a signature that recurs in 2+ sources: {', '.join(repeated[:3])}"
        elif recurs and top and top_n / len(members) >= DOMINANT and len(pattern_sources) >= min_prs:
            mechanical = f"a file pattern {top} ({top_n} of {len(members)} records, {len(pattern_sources)} sources)"
        groups.append({"category": category, "spellings": dict(spellings[category]), "records": members, "sources": sources, "levels": levels, "recurs": recurs,
                       "mechanical": mechanical, "repeated": repeated})
    groups.sort(key=lambda g: (-len(g["sources"]), -len(g["records"]), g["category"]))
    recurring_sigs = sorted(((sig, len(srcs)) for sig, srcs in sig_sources.items() if len(srcs) >= 2), key=lambda x: (-x[1], x[0]))
    return groups, recurring_sigs, len(sig_sources)


def cite(members, limit=6):
    cited = [f"{source}:{record['id'] if isinstance(record.get('id'), (str, int)) and str(record.get('id')).strip() else '?'}" for source, record in members]
    shown = ", ".join(cited[:limit])
    return shown + (f", +{len(cited) - limit} more" if len(cited) > limit else "")


def render(day, root, min_prs, filters, files, items, skipped, excluded_undated, groups, recurring_sigs, distinct_sigs):
    raw = defaultdict(Counter)
    for _, record in items:
        spelling = record.get("severity") if isinstance(record.get("severity"), str) else "(none)"
        raw[level_of(spelling) or "unmapped"][spelling] += 1
    lines = [f"# Retro, {day}", "",
             f"Read {len(items)} finding record(s) from {len(files)} file(s) under `{root}` across {len({s for s, _ in items})} source(s) "
             f"(a PR directory or a dated review). A group recurs at {min_prs}+ sources." + (f" Filter: {filters}." if filters else ""), ""]
    if excluded_undated:
        lines += [f"Excluded {excluded_undated} file(s) whose date could not be read (a date filter was given).", ""]
    if skipped:
        lines += [f"**{len(skipped)} line(s) could not be read and are NOT in any count:**"]
        lines += [f"- `{name}:{number}`: {why}" for name, number, why in skipped[:10]]
        lines += ([f"- and {len(skipped) - 10} more"] if len(skipped) > 10 else []) + [""]
    lines += ["## Severity, one vocabulary", "", "| level | records | raw spellings mapped |", "|---|---|---|"]
    for level in (*LEVELS, "unmapped"):
        spellings = ", ".join(f"`{s}` x{n}" for s, n in sorted(raw[level].items(), key=lambda x: (-x[1], x[0]))) or "none"
        lines.append(f"| {level} | {sum(raw[level].values())} | {spellings} |")
    lines += ["", "`unmapped` is a spelling this does not know (or a state such as `resolved`); it is listed, never guessed.", "",
              "## Recurrence by category", "", "| category | records | sources | high | medium | low | unmapped | recurs |", "|---|---|---|---|---|---|---|---|"]
    shown = [g for g in groups if len(g["sources"]) >= 2 or g["category"] == NO_CATEGORY]
    for group in shown:
        lv = group["levels"]
        lines.append(f"| {group['category']} | {len(group['records'])} | {len(group['sources'])} | {lv['high']} | {lv['medium']} | {lv['low']} | "
                     f"{lv['unmapped']} | {'yes' if group['recurs'] else 'no'} |")
    singles = [g["category"] for g in groups if g not in shown]
    if singles:
        lines += ["", f"{len(singles)} categor(y/ies) appear in a single source and are not tabled: " + ", ".join(f"`{c}`" for c in singles[:20])
                  + (f", and {len(singles) - 20} more" if len(singles) > 20 else "") + "."]
    merged = [(g["category"], g["spellings"]) for g in groups if len(g["spellings"]) > 1]
    if merged:
        lines += ["", "Category spellings merged (a severity word written into the category is stripped, nothing else):"]
        lines += [f"- `{key}`: " + ", ".join(f"`{raw}` x{n}" for raw, n in sorted(sp.items(), key=lambda x: (-x[1], x[0]))) for key, sp in merged[:15]]
    lines += ["", "## Signatures that recur (2+ sources)", ""]
    lines += ([f"- `{sig}`: {n} sources" for sig, n in recurring_sigs[:15]] if recurring_sigs else
              [f"None: {distinct_sigs} distinct signature(s)/rule(s), each in a single source."])
    recurring = [g for g in groups if g["recurs"]]
    lines += ["", "## Proposals", ""]
    if not recurring and not recurring_sigs:
        lines += [f"**Nothing recurs.** No category appears in {min_prs} or more sources and no signature in 2. Nothing is proposed."]
    else:
        if recurring and not any(g["mechanical"] for g in recurring):
            lines += ["**Nothing mechanical recurs:** every recurring group below is a judgement call.", ""]
        for group in recurring:
            members = group["records"]
            lines += [f"### {group['category']}: {len(members)} record(s) in {len(group['sources'])} sources", ""]
            if group["mechanical"]:
                lines += [f"- **mechanical candidate**: {group['mechanical']}.",
                          "- Propose a deterministic check, in order of preference: a rubocop cop, a repo lint, a spec helper, a hook. A person decides whether the pattern is fixed enough."]
                for sig in group["repeated"][:2]:
                    seen = [(s, text_of(r.get("issue"))[:110]) for s, r in members if (text_of(r.get("signature")) or text_of(r.get("rule"))) == sig][:3]
                    lines += [f"- Look before you trust `{sig}` (a signature is the reviewer's own label and can coincide, such as a numbered criterion in different PRs): "
                              + "; ".join(f"{s}: \"{issue}\"" for s, issue in seen)]
            else:
                lines += ["- **judgement**: no shared file pattern or repeated signature. Propose a line in the project's review doctrine, not a check."]
            lines += [f"- Findings behind it: {cite(members)}.", ""]
    nocat = [g for g in groups if g["category"] == NO_CATEGORY]
    if nocat:
        lines += ["", f"{len(nocat[0]['records'])} record(s) carry no category and are not proposed on: {cite(nocat[0]['records'], 4)}."]
    return "\n".join(lines).rstrip() + "\n"


def run(root, since, until, min_prs, day, out, stdout, git=git_date, emit=print):
    root = Path(root)
    if not root.is_dir():
        raise Unusable(f"no directory {root}: nothing to read")
    files = sorted(p for p in root.rglob("*findings.jsonl") if p.is_file())
    if not files:
        raise Unusable(f"no *findings.jsonl under {root}: nothing to read, so nothing to report")
    items, skipped, kept, excluded = [], [], [], 0
    for path in files:
        source = source_of(path, root)
        if since or until:
            when = dated_by_name(source) or git(path)
            if when is None:
                excluded += 1
                continue
            if (since and when < since) or (until and when > until):
                continue
        records, bad = read_file(path)
        kept.append(path)
        skipped += [(str(path.relative_to(root)), number, why) for number, why in bad]
        items += [(source, record) for record in records]
    if not items:
        raise Unusable(f"{len(kept)} file(s) read but no usable record: nothing to report")
    groups, recurring_sigs, distinct = analyse(items, min_prs)
    filters = ", ".join(f"{k} {v}" for k, v in (("since", since), ("until", until)) if v)
    text = render(day, root, min_prs, filters, kept, items, skipped, excluded, groups, recurring_sigs, distinct)
    if stdout:
        emit(text, end="")
    else:
        target = Path(out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
        emit(f"wrote {target} ({len(items)} record(s), {len([g for g in groups if g['recurs']])} recurring categor(y/ies))")
    return 0


def selftest() -> int:
    failures = []

    def check(label, ok, detail=""):
        if not ok:
            failures.append(f"{label}: {detail}")

    def rec(i, category="claims-vs-enforcement", file="app/models/a.rb", sig=None, severity="P2", **extra):
        record = {"id": i, "severity": severity, "category": category, "file": file, "issue": "x"}
        if sig:
            record["signature"] = sig
        record.update(extra)
        return record

    def write(root, rel, records, extra_lines=()):
        path = Path(root) / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join([json.dumps(r) for r in records] + list(extra_lines)) + "\n", encoding="utf-8")

    def go(root, **kw):
        out = []
        args = dict(since=None, until=None, min_prs=3, day="2026-10-10", out=str(Path(root) / "out.md"), stdout=True, git=lambda p: None)
        args.update(kw)
        code = run(root, emit=lambda text, end="\n": out.append(text), **args)
        return code, "".join(out)

    def unusable(root, **kw):
        try:
            go(root, **kw)
        except Unusable:
            return True
        return False

    with tempfile.TemporaryDirectory() as tmp:
        # 1. a category in 3 sources, all in app/models: a mechanical candidate by file pattern, citing its findings
        a = Path(tmp) / "a"
        for n in (1, 2, 3):
            write(a, f"prs/pr-{n}/pr-reviewer-findings.jsonl", [rec(f"F{n}", file=f"app/models/m{n}.rb:{n}0"), rec(f"G{n}", file=f"app/models/n{n}.rb")])
        _, text = go(a)
        check("a recurring category is reported", "### claims-vs-enforcement: 6 record(s) in 3 sources" in text, text)
        check("the file pattern makes it a mechanical candidate", "**mechanical candidate**: a file pattern app/models/**/*.rb" in text, text)
        check("the findings behind it are cited", "prs/pr-1:F1" in text and "prs/pr-3:G3" in text, text)
        check("a numeric id is cited, not '?'", cite([("prs/x", {"id": 7})]) == "prs/x:7" and cite([("prs/x", {})]) == "prs/x:?", cite([("prs/x", {"id": 7})]))
        check("the preference order is named", "a rubocop cop, a repo lint, a spec helper, a hook" in text, text)
        # 2. the same count with scattered files is judgement
        b = Path(tmp) / "b"
        for n, f in ((1, "app/models/a.rb"), (2, "docs/product/x.md"), (3, "qa/e2e/y.ts")):
            write(b, f"prs/pr-{n}/pr-reviewer-findings.jsonl", [rec(f"F{n}", file=f)])
        _, text = go(b)
        check("scattered files are judgement", "**judgement**" in text and "mechanical candidate" not in text, text)
        check("and the report says nothing mechanical recurs", "Nothing mechanical recurs" in text, text)
        # 2b. a pattern few of the group's records share is not mechanical, however many sources carry it
        lw = Path(tmp) / "lw"
        for n in (1, 2, 3):
            write(lw, f"prs/pr-{n}/pr-reviewer-findings.jsonl", [rec(f"F{n}", file="app/models/a.rb"), rec(f"G{n}", file="docs/x.md"), rec(f"H{n}", file="qa/y.ts"), rec(f"J{n}", file="lib/z.rb")])
        _, text = go(lw)
        check("a low-dominance pattern is not mechanical", "**judgement**" in text and "mechanical candidate" not in text, text)
        # 3. a repeated signature (2 sources) in a category that recurs is mechanical even with scattered files
        c = Path(tmp) / "c"
        for n, f in ((1, "app/a.rb"), (2, "docs/x.md"), (3, "qa/y.ts")):
            write(c, f"prs/pr-{n}/pr-reviewer-findings.jsonl", [rec(f"F{n}", file=f, sig="dead-flag:Foo" if n < 3 else "other")])
        _, text = go(c)
        check("a repeated signature is a mechanical candidate", "a signature that recurs in 2+ sources: dead-flag:Foo." in text, text)
        check("and is listed under recurring signatures", "- `dead-flag:Foo`: 2 sources" in text, text)
        check("a signature candidate shows the issue text so a person can see a coincidence", "Look before you trust `dead-flag:Foo`" in text and 'prs/pr-1: "x"' in text, text)
        # 4. all singletons: it says so
        d = Path(tmp) / "d"
        for n in (1, 2):
            write(d, f"prs/pr-{n}/pr-reviewer-findings.jsonl", [rec(f"F{n}", category=f"cat-{n}", sig=f"s{n}")])
        _, text = go(d)
        check("all singletons is 'Nothing recurs'", "**Nothing recurs.**" in text and "### " not in text, text)
        # 5. below the threshold, and the threshold is a parameter
        _, text = go(a, min_prs=4)
        check("min-prs is honoured", "**Nothing recurs.**" in text, text)
        # 6. one source counts once: two files in one PR directory are one source
        e = Path(tmp) / "e"
        write(e, "prs/pr-1/pr-reviewer-findings.jsonl", [rec("A1"), rec("A2")])
        write(e, "prs/pr-1/spec-reviewer-findings.jsonl", [rec("B1"), rec("B2")])
        write(e, "prs/pr-2/pr-reviewer-findings.jsonl", [rec("C1")])
        _, text = go(e)
        check("two files in one PR are one source, many records are not recurrence", "| claims-vs-enforcement | 5 | 2 |" in text and "**Nothing recurs.**" in text, text)
        # 7. severity: every known spelling mapped and listed, unknown and a state unmapped, case-insensitive
        f = Path(tmp) / "f"
        spellings = ["P1", "blocker", "BLOCKING", "P2", "major", "medium", "P3", "minor", "low", "SUGGESTION", "advisory", "info", "resolved", "weird", "p1"]
        write(f, "prs/pr-1/x-findings.jsonl", [rec(f"S{i}", severity=s) for i, s in enumerate(spellings)] + [{"id": "N", "category": "c", "file": "a/b.rb"}])
        _, text = go(f)
        check("high maps P1, blocker, BLOCKING (and lower-case p1)", "| high | 4 | `BLOCKING` x1, `P1` x1, `blocker` x1, `p1` x1 |" in text, text)
        check("medium maps P2, major, medium", "| medium | 3 | `P2` x1, `major` x1, `medium` x1 |" in text, text)
        check("low maps P3, minor, low, SUGGESTION, advisory, info", "| low | 6 |" in text and "`SUGGESTION` x1" in text, text)
        check("a state and an unknown spelling and a missing one are unmapped and listed", "| unmapped | 3 | `(none)` x1, `resolved` x1, `weird` x1 |" in text, text)
        # 7b. a severity word in the category does not split it: one class, merged, and the spellings listed
        m = Path(tmp) / "m"
        for n, c in ((1, "claims-vs-enforcement"), (2, "claims-vs-enforcement (BLOCKING)"), (3, "Suggestion claims-vs-enforcement")):
            write(m, f"prs/pr-{n}/x-findings.jsonl", [rec(f"M{n}", category=c)])
        _, text = go(m)
        check("severity-word spellings merge into one recurring category", "### claims-vs-enforcement: 3 record(s) in 3 sources" in text, text)
        check("the merged spellings are listed", "`claims-vs-enforcement`: `Suggestion claims-vs-enforcement` x1, `claims-vs-enforcement` x1, `claims-vs-enforcement (BLOCKING)` x1" in text, text)
        check("a different phrase is not merged", category_of({"category": "BLOCKING mock-up gate evidence"})[0] == "mock-up gate evidence" and category_of({"category": "d-109"})[0] != category_of({"category": "d-109 phone card"})[0])
        check("a category that is only a severity word keeps its own spelling", category_of({"category": "BLOCKING"})[0] == "blocking", category_of({"category": "BLOCKING"}))
        # 7c. single-source categories are summarised, not tabled
        sgl = Path(tmp) / "sgl"
        write(sgl, "prs/pr-1/x-findings.jsonl", [rec("A1", category="alpha"), rec("A2", category="beta")])
        write(sgl, "prs/pr-2/x-findings.jsonl", [rec("B1", category="alpha")])
        _, text = go(sgl)
        check("a single-source category is summarised", "1 categor(y/ies) appear in a single source and are not tabled: `beta`" in text and "| beta |" not in text and "| alpha | 2 | 2 |" in text, text)
        # 8. unreadable lines are counted and named, not dropped
        g = Path(tmp) / "g"
        write(g, "prs/pr-1/x-findings.jsonl", [rec("A1")], extra_lines=["not json", "[1, 2]", ""])
        _, text = go(g)
        check("an unreadable line is named", "**2 line(s) could not be read" in text and "`prs/pr-1/x-findings.jsonl:2`: not JSON" in text, text)
        check("a non-object line is named", "`prs/pr-1/x-findings.jsonl:3`: a list, not an object" in text, text)
        # 9. nothing to read is exit 2, never a clean report
        check("a missing directory is unusable", unusable(Path(tmp) / "nope"))
        empty = Path(tmp) / "empty"
        empty.mkdir()
        check("no findings files is unusable", unusable(empty))
        none = Path(tmp) / "none"
        write(none, "prs/pr-1/x-findings.jsonl", [], extra_lines=["garbage"])
        check("files with no usable record is unusable", unusable(none))
        # 10. records with no category are counted and never proposed on
        h = Path(tmp) / "h"
        for n in (1, 2, 3):
            write(h, f"prs/pr-{n}/x-findings.jsonl", [{"id": f"O{n}", "severity": "P1", "file": "app/a.rb"}])
        _, text = go(h)
        check("no-category records never recur into a proposal", "### " not in text and "3 record(s) carry no category" in text, text)
        # 11. dates: a dated directory by its name, others by git (None here), excluded and counted
        i = Path(tmp) / "i"
        write(i, "2026-09-01/findings.jsonl", [rec("D1")])
        write(i, "2026-10-05/findings.jsonl", [rec("D2")])
        write(i, "prs/pr-1/x-findings.jsonl", [rec("U1")])
        _, text = go(i, since="2026-10-01")
        check("a dated directory is filtered by its name", "Read 1 finding record(s) from 1 file(s)" in text, text)
        check("an undated file is excluded and counted", "Excluded 1 file(s) whose date could not be read" in text, text)
        _, text = go(i, since="2026-10-01", git=lambda p: "2026-10-09")
        check("git's date admits a PR file", "Read 2 finding record(s) from 2 file(s)" in text, text)
        # 12. writing: only the out file, created with its directory; --stdout writes nothing; the same input is the same report
        j = Path(tmp) / "j"
        write(j, "prs/pr-1/x-findings.jsonl", [rec("A1")])
        target = Path(tmp) / "brain" / "retro" / "2026-10-10.md"
        code, _ = go(j, stdout=False, out=str(target))
        first = target.read_text()
        check("the report is written to the out path", code == 0 and "# Retro, 2026-10-10" in first)
        go(j, stdout=False, out=str(target))
        check("the same input is the same report", target.read_text() == first)
        before = sorted(p.name for p in Path(tmp).rglob("*"))
        go(j, stdout=True, out=str(Path(tmp) / "should-not-exist.md"))
        check("--stdout writes nothing", sorted(p.name for p in Path(tmp).rglob("*")) == before and not (Path(tmp) / "should-not-exist.md").exists())
        check("the input is untouched", sorted(p.name for p in (j / "prs" / "pr-1").iterdir()) == ["x-findings.jsonl"])
        # 13. the file pattern helper
        check("a pattern keeps two directories and the suffix", file_pattern("app/models/user.rb:41") == "app/models/**/*.rb", file_pattern("app/models/user.rb:41"))
        check("a shallow path keeps one", file_pattern("app/user.rb") == "app/**/*.rb")
        check("no suffix, no pattern", file_pattern("Dockerfile") is None and file_pattern("app/Makefile") is None)
    if failures:
        print("retro selftest FAILED:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    print("retro selftest passed")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Group review findings, count what recurs, propose checks (#1339).")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--root", default="docs/evidence/reviews")
    parser.add_argument("--since")
    parser.add_argument("--until")
    parser.add_argument("--min-prs", type=int, default=MIN_PRS)
    parser.add_argument("--date", default=None, help="the report's date (default: today)")
    parser.add_argument("--out", default=None, help="default docs/brain/retro/<date>.md")
    parser.add_argument("--stdout", action="store_true", help="print the report; write nothing")
    ns = parser.parse_args(argv)
    if ns.selftest:
        return selftest()
    for name in ("since", "until", "date"):
        value = getattr(ns, name)
        if value and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            parser.error(f"--{name.replace('_', '-')} must be YYYY-MM-DD, got {value!r}")
    if ns.min_prs < 2:
        parser.error("--min-prs must be 2 or more: one source is not a recurrence")
    day = ns.date or date.today().isoformat()
    try:
        return run(ns.root, ns.since, ns.until, ns.min_prs, day, ns.out or f"docs/brain/retro/{day}.md", ns.stdout)
    except Unusable as error:
        print(f"retro: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
