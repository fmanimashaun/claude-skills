"""Mutation guard: audit_findings. Declared here, run by scripts/mutation_check.py (#2221).

The contract's whole value is that an audit cannot overclaim: authority comes from the rule's basis,
not from whoever found the defect, and what was not measured is said. Each mutation switches off one
refusal or one honesty line that keeps that true, and names the fixture that must notice.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="audit_findings",
    subject="scripts/audit_findings.py",
    selftest="scripts/audit_findings.py",
    selftest_args=("--selftest",),
    needs=("reference/architecture-rules.json",),
    mutations=(
        Mutation(
            'a finding naming no real rule stops being refused',
            '        if rule is None:',
            '        if False:',
            'an unknown rule is refused',
        ),
        Mutation(
            'a finding may write its own authority',
            '            if k in ("authority", "rank", "severity", "basis"):',
            '            if False:',
            'a written authority is refused',
        ),
        Mutation(
            'a finding may carry any key, so free text hides in it',
            '            elif k not in FINDING_KEYS:',
            '            elif False:',
            'an unknown key is refused',
        ),
        Mutation(
            'a screenshot path may point anywhere that is a file',
            '            if ev["kind"] == "screenshot" and not _under(root, str(ev["ref"])):',
            '            if ev["kind"] == "screenshot" and not (root / ev["ref"]).is_file():',
            'an absolute screenshot path is refused',
        ),
        Mutation(
            'ADA drops out of the standard-claiming words',
            '|ADA|EN\\s*301',
            '|EN\\s*301',
            "'ADA' in a house rule's text is refused",
        ),
        Mutation(
            'a forged registry is accepted',
            '        if r.get("authority") != want:',
            '        if False:',
            'a registry whose authority disagrees with its basis is refused',
        ),
        Mutation(
            'the CLI accepts a registry path again',
            '        p.add_argument("--root", default=".")',
            '        p.add_argument("--root", default=".")\n        p.add_argument("--registry")',
            'the CLI offers no --registry option',
        ),
        Mutation(
            'a finding for a rule the document did not audit passes',
            '        elif f["rule"] not in audited:',
            '        elif False:',
            'a rule the document did not say it audited is refused',
        ),
        Mutation(
            'a document that audited no rule passes',
            '    if not isinstance(audited, dict) or not audited:',
            '    if False:',
            'a document that audited no rule is refused',
        ),
        Mutation(
            'the report drops its Not audited section',
            '    lines += ["## Not audited", ""]',
            '    lines += []',
            'the report prints a Not audited section',
        ),
        Mutation(
            'Not audited lists the rules the run did audit',
            '        if rid in doc["audited"]:\n            continue',
            '        if False:\n            continue',
            'Not audited does not list a rule the run audited',
        ),
        Mutation(
            'a standard no longer outranks a house rule',
            '    out.sort(key=lambda d: (d["authority"] != "standard", -d["reach"]',
            '    out.sort(key=lambda d: (False, -d["reach"]',
            'a standard outranks a house rule whatever its reach and instance count',
        ),
        Mutation(
            'layout_fit findings are filed against the wrong rule',
            '"layout_fit": "A23"',
            '"layout_fit": "A24"',
            "a judge's finding maps to its framework rule",
        ),
        Mutation(
            "a judge's unverified and redirected routes are dropped",
            '        for k in ("unverified", "redirected"):',
            '        for k in ():',
            "a judge's unverified and redirected routes are carried, never clean",
        ),
        Mutation(
            'only the first example route of a judge finding is kept',
            '        for screen in examples:',
            '        for screen in examples[:1]:',
            'each example route becomes its own finding, so reach is the routes listed',
        ),
        Mutation(
            'a judge finding that is not an object is not refused',
            '        if not isinstance(it, dict):',
            '        if False:',
            'a judge finding that is not an object is unusable, not a crash',
        ),
        Mutation(
            'a merge keeps only the last screen count for a rule',
            '            audited[rid] = max(audited.get(rid, 0), n)',
            '            audited[rid] = n',
            "a merge keeps each rule's own screen count, not one overall number",
        ),
        Mutation(
            "a merge drops all but the first document's findings",
            '"findings": [f for d in docs for f in d.get("findings", [])]}',
            '"findings": list(docs[0].get("findings", []))}',
            'a merge keeps every finding',
        ),
        Mutation(
            'a merge drops the unverified screens',
            '"unverified": sorted({u for d in docs for u in d.get("unverified", [])}),',
            '"unverified": [],',
            'a merge unions the unverified screens',
        ),
        Mutation(
            'a house rule may claim a standard',
            '        if rule is not None and rule["authority"] == "house":',
            '        if False:',
            'a house rule that claims WCAG in its message is refused',
        ),
        Mutation(
            'only the message is scanned, not every string',
            '            claim = claim_in(every_string({k: v for k, v in f.items() if k not in ("rule", "screen")}),',
            '            claim = claim_in([str(f.get("message", ""))],',
            'a house rule that claims a standard in its evidence is refused',
        ),
        Mutation(
            'the walk skips strings nested in lists',
            '    elif isinstance(obj, (list, tuple)):',
            '    elif False:',
            'a claim nested inside a list in evidence.ref is refused',
        ),
        Mutation(
            'a screen may carry a sentence',
            '        if not isinstance(f.get("screen"), str) or not SCREEN_SHAPE.match(f["screen"]):',
            '        if not isinstance(f.get("screen"), str):',
            'a screen that carries a sentence is refused',
        ),
        Mutation(
            "a screen's separators are not read as spaces",
            're.sub(r"[-_/.]+", " ", screen)',
            'screen',
            'a screen that hides a claim behind separators is refused on a house rule',
        ),
        Mutation(
            'a screen is scanned for plain prose words too',
            '        m = CLAIM_ONLY.search(',
            '        m = STANDARD_WORDS.search(',
            'a plain route named /standards passes on a house rule (prose words are not read in a screen)',
        ),
        Mutation(
            'the document title is not scanned beside house rules',
            '    if has_house:',
            '    if False:',
            "the document's title claiming a standard beside a house finding is refused",
        ),
        Mutation(
            'an unverified entry may carry a sentence',
            'isinstance(u, str) and SCREEN_SHAPE.match(u) for u in unv',
            'isinstance(u, str) for u in unv',
            'an unverified entry that carries a sentence is refused',
        ),
        Mutation(
            'an unknown document key is accepted',
            '        if k not in DOC_KEYS:',
            '        if False:',
            'an unknown document key is refused',
        ),
    ),
)
