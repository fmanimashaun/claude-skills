"""Mutation guard: check_slices. Declared here, run by scripts/mutation_check.py (#1369)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1369. A slice plan is filed as issues and worked in order, so each refusal below is a way a plan
# that cannot be worked would be filed anyway: no first slice, a blocker nobody closes, a slice with
# nothing to prove, or an edge dropped on the way into the issue.
GUARD = Guard(
    name="check_slices",
    subject="scripts/check_slices.py",
    selftest="scripts/check_slices.py",
    # It imports the criteria reader, the Mock-up reader and (in the selftest) check_issue_ready.
    needs=(
        "scripts/check_criteria.py",
        "scripts/check_issue_mockup.py",
        "scripts/check_issue_ready.py",
        # check_issue_mockup imports its approval rule from check_mockup_gate, which reads the diff
        # through classify_door (#1424). Unstaged, the unmutated selftest failed in the tempdir and
        # every mutation read as caught: INERT, found only by the full local run at 49ea846.
        "scripts/check_mockup_gate.py",
        "scripts/classify_door.py",
    ),
    mutations=(
        # #1435: CommonMark fences, as check_issue_ready.py reads them.
        Mutation(
            "only ``` opens a fence, so a depends-on inside ~~~ becomes an edge",
            '        f = re.match(r"^[ \\t]*(`{3,}|~{3,})[ \\t]*(\\w*)", raw)',
            '        f = re.match(r"^[ \\t]*(`{3,})[ \\t]*(\\w*)", raw)',
            "a depends-on inside a ~~~ fence is not an edge",
        ),
        Mutation(
            "any fence line closes, so a ``` inside a ```` fence ends it early",
            "            elif f.group(1).startswith(run):",
            "            else:",
            "a ``` inside a ```` fence does not close it",
        ),
        Mutation(
            "a cycle is no longer found",
            "            if state.get(w) == 1:\n                return stack[stack.index(w):] + [w]",
            "            if False:\n                return stack[stack.index(w):] + [w]",
            "a cycle is refused",
        ),
        Mutation(
            "an edge to an undefined slice is accepted",
            "            elif d not in seen:",
            "            elif False:",
            "a dangling edge is refused",
        ),
        Mutation(
            "a slice with no criteria is accepted",
            "        if s.sid not in covered:",
            "        if False:",
            "a slice with no criteria is refused",
        ),
        Mutation(
            "every slice reads as uncovered, so the refusal names slices that have criteria",
            "    covered = {m.group(1) for unit in by_unit if (m := SLICE_RE.match(f\"## {unit}\"))}",
            "    covered = set()",
            "a well-formed plan has no findings",
        ),
        Mutation(
            "a loose depends-on line is silently dropped instead of refused",
            "                current.malformed.append(no)\n",
            "",
            "a loose `depends-on:` line is refused",
        ),
        Mutation(
            "the Mock-up declaration is no longer required",
            "        if not ok:\n            findings.append(f\"{s.sid}: Mock-up — {why}\")",
            "        if False:\n            findings.append(f\"{s.sid}: Mock-up — {why}\")",
            "a slice with no Mock-up declaration is refused",
        ),
        Mutation(
            "check_criteria's refusal is swallowed, so the author is told only 'no criteria'",
            '            findings.append(f"criteria: {err}")',
            "            pass",
            "a criteria file check_criteria refuses says why",
        ),
        Mutation(
            "check_criteria's rules stop reaching the slices",
            "    for problem in check_criteria.check(criteria) if criteria else []:",
            "    for problem in []:",
            "check_criteria's error-path rule applies to each slice",
        ),
        Mutation(
            "the order ignores the edges and follows the numbering",
            "        ready = sorted((sid for sid, d in deps.items() if sid not in done and d <= set(done)),",
            "        ready = sorted((sid for sid, d in deps.items() if sid not in done),",
            "a slice numbered first but blocked by a later one is filed after it",
        ),
        Mutation(
            "a slice is written before its blocker has a number",
            "    if unfiled:\n        raise Unusable(",
            "    if False:\n        raise Unusable(",
            "a slice whose blocker is not filed yet is refused",
        ),
        Mutation(
            "filed edges keep their slice ids, which check_issue_ready cannot read",
            '            refs = [f"#{filed[t]}" if t in filed else t for t in TOKEN.findall(raw)]',
            "            refs = TOKEN.findall(raw)",
            "a filed slice's edges are rewritten to issue numbers",
        ),
        # Pre-release review of #1397: a fenced sample counted as an edge the filed issue drops.
        Mutation(
            "a depends-on inside a plain fence counts as an edge again",
            '        if fence not in (None, "deps"):\n            continue\n',
            "",
            "a depends-on inside a plain fence is not an edge",
        ),
    ),
)
