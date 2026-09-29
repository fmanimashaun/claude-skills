"""Mutation guard: check_tenancy_cop. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #1361. Review of #1403 BLOCKED three times: a checker that re-derived RuboCop's config, one that
    # probed a single stand-in path, and one blind to a controller's own directives. It now asks RuboCop
    # per real controller, the app for its tables, and Ruby (Prism, File.fnmatch) for comments and globs;
    # each mutation removes one refusal, and the fixture named in `expects` must be the one that notices.
    name="check_tenancy_cop",
    subject="scripts/check_tenancy_cop.py",
    selftest="scripts/check_tenancy_cop.py",
    needs=("scaffold/tenancy/scoped_lookup.rb",),
    mutations=(
        Mutation(
            'a controller where the cop is off is no longer refused, so one stand-in path speaks for all',
            '    off = [(p, v["unflagged"]) for p, v in verdicts.items() if v["unflagged"] and not excused(p)]',
            '    off = []',
            'a controller where the cop is off (nested config / non-recursive Include) is refused BY PATH',
        ),
        Mutation(
            'a controller where `-a` would rewrite is no longer refused (nested SafeAutoCorrect: true)',
            '    fixed = [(p, v["autocorrected"]) for p, v in verdicts.items() if v["autocorrected"]]',
            '    fixed = []',
            'a controller where `-a` would rewrite (nested SafeAutoCorrect: true) is refused BY PATH',
        ),
        Mutation(
            'the output is no longer capped, so a misconfigured Include prints without bound',
            '    for p, keys in off[:SHOW_AT_MOST]:',
            '    for p, keys in off:',
            'many unchecked controllers are capped, not printed without bound',
        ),
        Mutation(
            "the probe counts every cop's offenses, so an unrelated one masks a missing tenancy offense",
            '    offenses = [o for f in report.get("files", []) for o in f.get("offenses", []) if o.get("cop_name") == COP_NAME]',
            '    offenses = [o for f in report.get("files", []) for o in f.get("offenses", [])]',
            'a probe report: only THIS cop counts; line 3 is unflagged, line 2 was autocorrected',
        ),
        Mutation(
            'the probe ignores the corrected flag, so an autocorrect never shows',
            '    corrected = {o["location"]["line"] for o in offenses if o.get("corrected")}',
            '    corrected = set()',
            'a probe report: only THIS cop counts; line 3 is unflagged, line 2 was autocorrected',
        ),
        Mutation(
            "a key that is no loadable model passes (the reviewer's `Invocie`)",
            '        if "missing" in v:',
            '        if False:',
            'a misspelt model KEY is refused as no model the app loads',
        ),
        Mutation(
            'a key whose table does not carry the tenant key passes',
            '        elif v.get("table") not in tables:',
            '        elif False:',
            'a key whose table does not carry the tenant key is refused',
        ),
        Mutation(
            'a tenant-FK table no key uses passes, so a stale model list cannot fail',
            '        if table not in unscoped and table not in reached:',
            '        if False:',
            'a tenant-FK table no key uses is refused',
        ),
        Mutation(
            'a foreign key no table carries passes, so the coverage check reads nothing',
            '    if not tables:',
            '    if False:',
            'a foreign key no table carries is refused -- zero tables is not a pass',
        ),
        Mutation(
            'a hand-edited cop passes as the shipped one',
            '    if installed.read_text(encoding="utf-8") != shipped:',
            '    if False:',
            'a hand-edited cop is refused',
        ),
        Mutation(
            'an unknown key under the cop is no longer reported, so a typo configures nothing silently',
            '    for key in sorted(set(section) - KNOWN_KEYS):',
            '    for key in []:',
            "an unknown (typo'd) key is refused by name",
        ),
        Mutation(
            'a blank association passes, and the cop autocorrects to broken Ruby',
            '            if not (isinstance(assoc, str) and IDENTIFIER.match(assoc)):',
            '            if False:',
            'a blank association is refused (it would autocorrect to broken Ruby)',
        ),
        Mutation(
            'a RuboCop or app that will not run is swallowed, so a broken project reads as clean',
            '        out.append(f"cannot run the project\'s RuboCop/app: {exc}")',
            '        pass',
            'a RuboCop that will not run is a FINDING, not a silent pass',
        ),
        Mutation(
            'a declared single-tenant app reads as a pass instead of not-applicable',
            '            return 3',
            '            return 0',
            'a declared single-tenant app is not applicable (exit 3)',
        ),
        Mutation(
            'an excused table or controller no longer needs a reason',
            '    if not isinstance(value, dict) or not all(isinstance(r, str) and r.strip() for r in value.values()):',
            '    if not isinstance(value, dict):',
            '...but WITHOUT a reason it is refused',
        ),
        Mutation(
            'the structure.sql body ends at `);` again, so a partitioned table swallows the next',
            '    r\'^CREATE\\s+(?:UNLOGGED\\s+)?TABLE\\s+(?:IF\\s+NOT\\s+EXISTS\\s+)?(?P<table>[\\w."]+)\\s*\\((?P<body>.*?)^\\)\',',
            '    r\'^CREATE\\s+(?:UNLOGGED\\s+)?TABLE\\s+(?:IF\\s+NOT\\s+EXISTS\\s+)?(?P<table>[\\w."]+)\\s*\\((?P<body>.*?)^\\);\',',
            'structure.sql: partitioned, UNLOGGED and IF NOT EXISTS tables are each read, and none swallows the next',
        ),
        Mutation(
            'an excuse that matches no controller is no longer reported',
            '        if not hits:',
            '        if False:',
            'a dead excuse (matches no controller) is reported',
        ),
        Mutation(
            'an excuse for controllers the cop does check is no longer reported',
            '        elif all(not verdicts[p]["unflagged"] for p in hits):',
            '        elif False:',
            'an excuse for controllers the cop DOES check is reported',
        ),
        Mutation(
            'every path counts as declared, so an unchecked controller needs no reason',
            '        return any(path in matches[g] for g in unchecked)',
            '        return True',
            'a controller where the cop is off (nested config / non-recursive Include) is refused BY PATH',
        ),
        Mutation(
            'a line silenced by a directive is no longer refused, so a file-wide disable passes (round 3)',
            '    bare = [(p, n) for p, n in silenced if not excused(p) and not sanctioned(comments.get(f"{p}:{n}", []))]',
            '    bare = []',
            'a file-wide `rubocop:disable` (no reason) is refused at the silenced line',
        ),
        Mutation(
            '`all` in the cop list is accepted, silencing every cop on the line (round 4)',
            '            if COP_NAME in cops and "all" not in cops:',
            '            if COP_NAME in cops:',
            'NEAR MISS: a list that includes `all` is not the sanctioned per-cop form',
        ),
        Mutation(
            'any text after `--` counts as a reason, even `# x` (round 4)',
            '(?P<reason>[^\\s#].*)',
            '(?P<reason>.*)',
            'a `--` followed only by `#` is no reason',
        ),
        Mutation(
            "the comment is taken from the line's first `#`, which may sit inside a string, so a fake reason passes (round 4)",
            'cs.select { |c| c.location.start_line == line }.map { |c| c.location.slice }',
            '[File.readlines(path)[line - 1].to_s[/#.*/].to_s]',
            'directive text inside a STRING is not a comment, so a file-wide disable is still refused',
        ),
        Mutation(
            "globs lose RuboCop's flags, so `*` crosses `/` and braces stop expanding (round 4)",
            'f = File::FNM_PATHNAME | File::FNM_EXTGLOB;',
            'f = 0;',
            'NEAR MISS: `*` does not cross `/`',
        ),
    ),
)
