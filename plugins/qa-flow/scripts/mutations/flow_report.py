"""Mutation guard: flow_report. Declared here, run by scripts/mutation_check.py (#2250).

A flow judge fails in two opposite directions, and both are mutated: a measurement that stops firing reports a clean journey over a dead end or a
wall, and one that fires too freely (a reload read as a back-track, the journey's own end read as a dead end, a limit nobody declared) trains a
team to ignore it. The budget is a declaration, so the guard also breaks every way of reading one that would let a made-up limit through.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="flow_report",
    subject="scripts/flow_report.py",
    selftest="scripts/flow_report.py",
    mutations=(
        Mutation(
            'steps over the declared budget stops being a finding',
            '    elif steps > budget.steps:',
            '    elif False:',
            'steps over budget is a finding naming the overrun',
        ),
        Mutation(
            'a journey that never completed is read as complete',
            '    if not journey["complete"]:',
            '    if False:',
            'a journey that never completed is a finding',
        ),
        Mutation(
            'a modal or tab opened stops counting as a context switch',
            '        if moved or row["action"] in SWITCHES:',
            '        if moved:',
            'switches are counted (two section changes and a modal)',
        ),
        Mutation(
            'a declared switches limit is never applied',
            '    limit = budget.switches\n    if limit is not None and switches > limit:',
            '    if False:',
            'switches over a declared limit are a finding',
        ),
        Mutation(
            'an undeclared switches limit is invented as zero',
            '    limit = budget.switches\n    if limit is not None and switches > limit:',
            '    limit = budget.switches or 0\n    if limit is not None and switches > limit:',
            'switches with no declared limit are measured, not a finding',
        ),
        Mutation(
            'a wait over the budget stops being a finding',
            '        if ms > budget.wait_ms:',
            '        if False:',
            'every wait over the budget is a finding',
        ),
        Mutation(
            'a wait that was not measured is skipped without a trace',
            '        if ms is None:\n            unverified.append(',
            '        if ms is None:\n            continue\n            unverified.append(',
            'a wait that was not measured is unverified',
        ),
        Mutation(
            "the journey's declared end counts as a dead end",
            '    dead = [r for r in rows if not r["terminal"] and r["forward_actions"] == 0]',
            '    dead = [r for r in rows if r["forward_actions"] == 0]',
            'the declared end with no forward action is not a dead end',
        ),
        Mutation(
            'a dead end is never reported',
            '    dead = [r for r in rows if not r["terminal"] and r["forward_actions"] == 0]',
            '    dead = []',
            'a page with no forward action that is not the end is a dead end',
        ),
        Mutation(
            'a reload counts as a back-track',
            '        if key in visited and row["action"] not in NOT_A_BACKTRACK:',
            '        if key in visited:',
            'a reload is not a back-track',
        ),
        Mutation(
            'a trailing slash makes a new page',
            '    path = path.rstrip("/") or "/"',
            '    path = path or "/"',
            'a trailing slash and a fragment do not make a new page',
        ),
        Mutation(
            'a different query is the same page',
            '    return path + ("?" + query if query else "")',
            '    return path',
            'a different query is a different page',
        ),
        Mutation(
            'a form submitted twice but never returned counts as re-entered',
            '        if earlier is not None and earlier["form"]["outcome"] == "returned":',
            '        if earlier is not None:',
            'the same form submitted twice but never returned is not re-entry',
        ),
        Mutation(
            'every form is the same form, whatever its fields',
            '    return (_norm(form["url"]).split("?", 1)[0], tuple(sorted(form["fields"])))',
            '    return (_norm(form["url"]).split("?", 1)[0], ())',
            'a different field set is a different form',
        ),
        Mutation(
            'field order makes a different form',
            'tuple(sorted(form["fields"]))',
            'tuple(form["fields"])',
            'field order does not make a different form',
        ),
        Mutation(
            'a wall at step 1 is a late wall',
            '    late = [r for r in walls if r["step"] >= 2]',
            '    late = [r for r in walls if r["step"] >= 1]',
            'a wall at step 1 is not late',
        ),
        Mutation(
            'a late wall is never reported',
            '    late = [r for r in walls if r["step"] >= 2]',
            '    late = []',
            'a wall at step 3 is a late wall',
        ),
        Mutation(
            'findings are ranked by step, not by class',
            '    return sorted(findings, key=lambda f: (RANK.index(f.measurement), amount(f), f.step or 0, f.journey))',
            '    return sorted(findings, key=lambda f: (f.step or 0,))',
            'findings rank walls, then dead ends',
        ),
        Mutation(
            'a journey with no Budget line is given a default',
            '        return None, "declares no `Budget:` line',
            '        return Budget(8, 3000), None  # "declares no `Budget:` line',
            'no Budget line is refused',
        ),
        Mutation(
            "another journey's Budget line is read",
            '                if n and len(n.group(1)) <= level:',
            '                if False:',
            'the budget of ANOTHER journey is refused',
        ),
        Mutation(
            'two Budget lines are both accepted',
            '    if len(marked) > 1:',
            '    if False:',
            'two Budget lines is refused',
        ),
        Mutation(
            'a wait with no unit is read as seconds',
            'if unit else float("nan")',
            'if unit else float(value) * 1000',
            'wait with no unit is refused',
        ),
        Mutation(
            'a step out of order is accepted',
            '            if row.get("step") != i + 1 or not _is_int(row.get("step")):',
            '            if False:',
            'a step out of order is refused',
        ),
        Mutation(
            'an unknown action is accepted',
            '            if row.get("action") not in ACTIONS:',
            '            if False:',
            'an unknown action is refused',
        ),
        Mutation(
            'a complete journey whose last row is not the end is accepted',
            '        if isinstance(rows[-1], dict) and journey.get("complete") is True and rows[-1].get("terminal") is not True:',
            '        if False:',
            'a complete journey whose last row is not the end is refused',
        ),
        Mutation(
            'a journey document outside the project root is read',
            '        if not str(path).startswith(str(root.resolve())):',
            '        if False:',
            'a document outside the project root is refused',
        ),
        Mutation(
            'an unmeasured wait stops failing the run',
            '    return 1 if (result.findings or result.unverified) else 0',
            '    return 1 if result.findings else 0',
            'an unmeasured wait fails the run (exit 1)',
        ),
        Mutation(
            'an unusable document exits 1, not 2',
            '        return 2\n    if a.json:',
            '        return 1\n    if a.json:',
            'a journey with no budget exits 2',
        ),
    ),
)
