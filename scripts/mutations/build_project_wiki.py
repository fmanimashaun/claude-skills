"""Mutation guard: build_project_wiki. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #887. A generated reference has two promises a clean build cannot show: --check notices a source that
# moved, and a count on a page is the source's own total (a parser that misses a table must FAIL, not
# print a shorter page). Plus the hand-written Home.md survives a rebuild, and n/a is never a pass.
GUARD = Guard(
    name="build_project_wiki",
    subject="plugins/rails-flow/scripts/build_project_wiki.py",
    selftest="plugins/rails-flow/scripts/build_project_wiki.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "drift is never reported, so a page that no longer matches its sources passes --check",
            '        drift = [n for n, text in pages.items() if not (wiki / n).is_file() or (wiki / n).read_text(encoding="utf-8") != text]',
            '        drift = []',
            "a source that moved makes --check report DRIFT",
        ),
        Mutation(
            "a table the parser missed is accepted, so the Data-Model page is quietly shorter than the schema",
            '    if s is not None and s["declared_tables"] != len(s["tables"]):',
            '    if False:',
            "a table the parser missed is a PROBLEM",
        ),
        Mutation(
            "the rebuild overwrites the hand-written Home.md",
            '        if not (wiki / n).is_file():\n            (wiki / n).write_text(HOME_SEED.format(name=root.resolve().name), encoding="utf-8")',
            '        if True:\n            (wiki / n).write_text(HOME_SEED.format(name=root.resolve().name), encoding="utf-8")',
            "never overwrites the hand-written Home.md",
        ),
        Mutation(
            "a missing graph.json reads as a pass instead of n/a",
            '    if not (root / GRAPH).is_file():\n        print(f"n/a: no {GRAPH.as_posix()} — run /rails-flow:graph first; the wiki is a join over that graph")\n        return 3',
            '    if False:\n        return 3',
            "no graph.json is n/a",
        ),
        Mutation(
            "--check with no wiki yet passes instead of saying build first",
            '        if not wiki.is_dir():\n            print(f"n/a: no {WIKI.as_posix()} yet — build it first (run without --check)")\n            return 3',
            '        if False:\n            return 3',
            "--check with no wiki yet is n/a",
        ),
        Mutation(
            "indexes are dropped from the data model, so a unique constraint is invisible on the page",
            "            i = re.match(r'\\s*t\\.index\\s+\\[([^\\]]*)\\](.*)', line)",
            "            i = None",
            "indexes, foreign keys and the version are parsed",
        ),
        Mutation(
            "association edges are not read, so the page shows tables with no relationships",
            '    assoc = [e for e in m["edges"] if e.get("kind") in ("belongs_to", "has_many", "has_one", "has_and_belongs_to_many")]',
            '    assoc = []',
            "associations from the models",
        ),
        Mutation(
            "the parser's own notes about unmodelled routes are dropped from the Routes page",
            '    unmodelled = [n for n in m["notes"] if "route" in n.lower()]',
            '    unmodelled = []',
            "unmodelled lines are on the page",
        ),
        Mutation(
            "commented-out examples in recurring.yml are read as real schedules",
            '        line = raw.split("#", 1)[0].rstrip() if not raw.lstrip().startswith("#") else ""',
            '        line = raw.rstrip()',
            "commented examples are ignored",
        ),
        Mutation(
            "the Gemfile.lock versions come from the constraint, not the resolved spec",
            '    return [(d, specs.get(d, "?")) for d in deps]',
            '    return [(d, "?") for d in deps]',
            "direct dependencies resolved to installed versions",
        ),
        Mutation(
            "a source problem no longer blocks --print, so a page renders from inputs the tool knows are wrong",
            '    if problems:\n        return 2',
            '    if False:\n        return 2',
            "a source PROBLEM blocks --print",
        ),
    ),
)
