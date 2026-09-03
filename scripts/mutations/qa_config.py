"""Mutation guard: qa_config. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #792. The ONE reader for qa.config.yml, extracted from two separately-written copies that
    # carried the SAME defect. Neither had a fixture: `route_coverage --selftest` passed 70
    # checks while `load_config` was referenced only at its definition and its one call site.
    name="qa_config",
    subject="plugins/qa-flow/scripts/qa_config.py",
    selftest="plugins/qa-flow/scripts/qa_config.py",
    mutations=(
        Mutation(
            # THE REPORTED DEFECT. A trailing comment on every key is what setup-qa scaffolds,
            # so both loaders returned {} on the block the scaffolder writes.
            "trailing comments stop being stripped, so every scaffolded key is dropped again",
            '        elif ch == "#":\n            break',
            '        elif ch == "#":\n            pass',
            "the scaffolded coverage block is READ, not discarded",
        ),
        Mutation(
            # THE SECOND DEFECT, which the report did not separate: only an EMPTY inline list
            # was accepted, so `exclude: ["/up"]` was lost with no comment in sight.
            "only an EMPTY inline list is accepted, so a populated one is dropped",
            "(?P<inline>\\[.*\\])?",
            "(?P<inline>\\[\\s*\\])?",
            "a POPULATED inline list is read",
        ),
        Mutation(
            # A `#` inside quotes is DATA. Stripping unconditionally is the false positive this
            # repo shipped in a CI checker hours earlier.
            "quote tracking goes, so a # inside a value truncates it",
            "        if quote:\n            out.append(ch)\n            if ch == quote:\n                quote = None",
            "        if False:\n            out.append(ch)\n            if ch == quote:\n                quote = None",
            "a quoted # is data, not a comment",
        ),
        Mutation(
            # The early break and the `inside` reassignment agree on a well-formed file, so this
            # survived every fixture until one existed for a DUPLICATE top-level key.
            "the section stops ending early, so a duplicate key merges into the first",
            "                # grow. Without the break the second block merges into the first, silently.\n                break",
            "                # grow. Without the break the second block merges into the first, silently.\n                pass",
            "a duplicate section does not merge into the first",
        ),
    ),
)
