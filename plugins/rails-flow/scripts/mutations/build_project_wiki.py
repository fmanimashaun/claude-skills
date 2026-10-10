"""Mutation guard: build_project_wiki. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #887. A generated reference has two promises a clean build cannot show: --check notices a source that
# moved, and a count on a page is the source's own total (a parser that misses a table must FAIL, not
# print a shorter page). Plus the hand-written Home.md survives a rebuild, and n/a is never a pass.
GUARD = Guard(
    name="build_project_wiki",
    subject="scripts/build_project_wiki.py",
    selftest="scripts/build_project_wiki.py",   # --selftest lives in the module itself
    needs=("scripts/fixture_git.py",),   # its selftest's git goes through fixture_git (#1588)
    deps=("scripts/generated_docs.py",),   # #1230: imported for the opt-in branch policy
    mutations=(
        # Constraints read as columns again: the data-model page lists `(code)::text ~ ...` as a column.
        Mutation(
            "a check constraint is read as a column again",
            'NON_COLUMN_CALLS = frozenset({"index", "check_constraint", "exclusion_constraint", "unique_constraint"})',
            'NON_COLUMN_CALLS = frozenset({"index"})',
            "schema.rb: a check constraint is not read as a column",
        ),
        # Every `#` a comment again, so `rate#893` is cut to `rate`.
        Mutation(
            "a `#` anywhere starts a comment again",
            '        elif ch == "#" and (i == 0 or raw[i - 1].isspace()):',
            '        elif ch == "#":',
            "yaml: a `#` with no space before it is part of the value",
        ),
        Mutation(
            "drift is never reported, so a page that no longer matches its sources passes --check",
            '        drift = [n for n, text in pages.items() if not (wiki / n).is_file() or (wiki / n).read_text(encoding="utf-8") != text]',
            '        drift = []',
            "a source that moved makes --check report DRIFT",
        ),
        Mutation(
            "a table the parser missed is accepted, so the Data-Model page is quietly shorter than the schema",
            '    if s is not None and s["declared_tables"] != len(s["tables"]) + repeats:',
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
            "            return raw[:i].rstrip()",
            "            return raw.rstrip()",
            "commented examples are ignored",
        ),
        Mutation(
            "the Gemfile.lock versions come from the constraint, not the resolved spec",
            '    return [(d, specs.get(d, "?")) for d in deps]',
            '    return [(d, "?") for d in deps]',
            "direct dependencies resolved to installed versions",
        ),
        # #1157. The expression-index branch and the refusal to drop what it cannot classify.
        Mutation(
            "an expression index is skipped again, so a unique constraint vanishes from the page",
            "            e = None if i else re.match(r'\\s*t\\.index\\s+(\"(?:[^\"\\\\]|\\\\.)*\")(.*)', line)",
            "            e = None",
            "an EXPRESSION index is parsed, not skipped",
        ),
        Mutation(
            "an index line the parser cannot classify is dropped in silence again",
            "                unparsed.append(line.strip())",
            "                pass",
            "an index line it CANNOT classify is recorded rather than dropped",
        ),
        # THE CONTROL'S OWN MUTATION. Without it, "parses expression indexes" is satisfied by a
        # parser that treats the bracketed form as an expression too -- the same defect inverted.
        Mutation(
            "the bracketed form is parsed as a single expression instead of a column list",
            "                    cols_in = [x.strip().strip('\"') for x in i.group(1).split(\",\") if x.strip()]",
            "                    cols_in = [i.group(1)]",
            "the bracketed form still parses as columns, not as an expression",
        ),
        Mutation(
            "a source problem no longer blocks --print, so a page renders from inputs the tool knows are wrong",
            '    if problems:\n        return 2',
            '    if False:\n        return 2',
            "a source PROBLEM blocks --print",
        ),
        Mutation(
            # #1233: the dirty-source NOTE is dropped, so a local db:migrate reads as upstream drift again.
            "a locally dirty source is no longer named",
            "        for path in dirty_sources(root):\n",
            "        for path in []:\n",
            "a locally dirty db/schema.rb is named in a NOTE",
        ),
        Mutation(
            "dirty_sources reports nothing, so the NOTE can never fire",
            "    return sorted({ln[3:].strip() for ln in done.stdout.splitlines() if len(ln) > 3})",
            "    return []",
            "dirty_sources names exactly the dirty source",
        ),
        Mutation(
            "wiki drift fails a feature branch that the policy makes advisory",
            "        advisory = drift_is_advisory(root) if drift else None\n",
            "        advisory = None\n",
            "with a policy, wiki drift on fix/1 exits 0",
        ),
        # #1732: a table keyed on another column has no implicit id.
        Mutation(
            "a table keyed on another column still has an implicit id",
            "(pk is None or pk.group(1) == '\"id\"')}",
            "True}",
            "schema.rb: a table has an implicit id unless `id: false` or another primary key is named",
        ),
        Mutation(
            "`id: false` still has an implicit id",
            '"implicit_id": not re.search(r"\\bid:\\s*false\\b", opts) and',
            '"implicit_id":',
            "schema.rb: a table has an implicit id unless `id: false` or another primary key is named",
        ),
        # #1698: which schema files the Data-Model page reads. The rule is decided here once; check_privacy_inventory.py imports it.
        Mutation(
            'a second db/*_schema.rb is never read',
            '    return [root / SCHEMA_RB, *sorted((root / "db").glob("*_schema.rb"))]',
            '    return [root / SCHEMA_RB]',
            "#1698 a second database's table is on the Data-Model page, with the schema file it is in",
        ),
        Mutation(
            'the Solid trio is read as well',
            '    return path.name in FRAMEWORK_SCHEMAS and _solid_only(path)',
            '    return False',
            "#1698 the Solid trio, holding only solid_* tables, is the framework's and is NOT on the page",
        ),
        Mutation(
            'a trio-named file is skipped by its name alone',
            '    return path.name in FRAMEWORK_SCHEMAS and _solid_only(path)',
            '    return path.name in FRAMEWORK_SCHEMAS',
            "#1698 a cache_schema.rb holding a table of the PROJECT's own is the project's",
        ),
        Mutation(
            'a table in two schema files is picked silently',
            '            if name in merged["tables"]:',
            '            if False:',
            '#1698 a table name in two schema files is a problem, never silently one of them',
        ),
        Mutation(
            "dirty_sources ignores a second database's dump",
            '    extra = [p.relative_to(root).as_posix() for p in app_schema_files(root) if p.relative_to(root).as_posix() != SCHEMA_RB]',
            '    extra = []',
            "dirty_sources names a second database's schema file",
        ),
        Mutation(
            'the Solid prefix loses its underscore',
            '    return all(table.startswith("solid_") for table in parse_schema(path.read_text(encoding="utf-8"))["tables"])',
            '    return all(table.startswith("solid") for table in parse_schema(path.read_text(encoding="utf-8"))["tables"])',
            "#1698 a project table that merely BEGINS `solid` (solidarity_votes) keeps its cache_schema.rb the project's",
        ),
    ),
)
