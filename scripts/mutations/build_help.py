"""Mutation guard: build_help. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #934. Help is a join over the repo; each mutation makes the join lenient -- a screen may ship without its guide,
# a procedure without its citation, a build may drift, a dropped page may print a shorter file, n/a may read as a pass.
GUARD = Guard(
    name="build_help",
    subject="plugins/rails-flow/scripts/build_help.py",
    selftest="plugins/rails-flow/scripts/build_help.py",   # --selftest lives in the module itself
    mutations=(
        Mutation(
            "a screen with no guide is accepted, so a screen ships with no Help behind its Help link",
            "        if s.get(\"key\") not in guides:",
            "        if False:",
            "a screen with no guide is a PROBLEM",
        ),
        Mutation(
            "a procedure or rule with no spec citation is accepted -- opinion published as doctrine",
            '        if pg["kind"] in CITED and not pg["meta"].get("spec"):',
            "        if False:",
            "a procedure with no spec citation is a PROBLEM",
        ),
        Mutation(
            "a guide for a screen the app does not have is accepted",
            "        if k not in known:",
            "        if False:",
            "a guide for a screen the registry does not know is a PROBLEM",
        ),
        Mutation(
            "a setting with no description is accepted",
            '        if not s.get("what"):',
            "        if False:",
            "a setting with no description is a PROBLEM",
        ),
        Mutation(
            "drift is never reported, so a Help that no longer matches its sources passes --check",
            '        if out.read_text(encoding="utf-8") != text:',
            "        if False:",
            "a source that moved makes --check report DRIFT",
        ),
        Mutation(
            "a page the renderer dropped prints a shorter file instead of failing",
            '    if len(built["pages"]) != m["totals"]["pages"]:',
            "    if False:",
            "a page the renderer dropped is a PROBLEM",
        ),
        Mutation(
            "a missing registry reads as a pass instead of n/a",
            "    if not (root / REGISTRY).is_file():",
            "    if False:",
            "no registry is n/a",
        ),
        Mutation(
            "--check with no build yet passes instead of saying build first",
            "        if not out.is_file():\n            print(f\"n/a: no {OUT.as_posix()} yet — build it first (run without --check)\")\n            return 3",
            "        if False:\n            return 3",
            "--check before the first build is n/a",
        ),
        Mutation(
            "a page's roles are dropped from the build, so the app cannot scope Help to the signed-in role",
            '            "roles": split_list(meta.get("roles", "")),',
            '            "roles": [],',
            "a page carries its roles as a list",
        ),
        Mutation(
            "ordered steps are dropped from the rendered procedure",
            '        ol = re.match(r"^\\s*\\d+[.)]\\s+(.*)$", line)',
            "        ol = None",
            "markdown renders headings, ordered steps",
        ),
    ),
)
