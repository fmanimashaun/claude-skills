"""Mutation guard: check_manifest_paths. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_manifest_paths",
    subject="scripts/check_manifest_paths.py",
    selftest="scripts/check_manifest_paths.py",   # --selftest lives in the module itself
    # No `needs`: every fixture builds its own synthetic plugin in a tempdir. A fixture reaching
    # for the real `plugins/` tree would die here on a missing corpus and read as a caught
    # mutation, when a crash is not a verdict.
    mutations=(
        Mutation(
            "agreement becomes unconditional, so no manifest path is ever phantom",
            '    return named.startswith(entry + "/")   '
            "# the manifest waits on a directory written into",
            "    return True",
            "a phantom applies_when path is reported",
        ),
        Mutation(
            "prose leaks into the corpus, so a path mentioned in a sentence vouches for itself",
            '            out.append((path, [fenced(path.read_text(encoding="utf-8"))]))',
            '            out.append((path, [path.read_text(encoding="utf-8")]))',
            "a path named only in prose does not count as agreement",
        ),
        Mutation(
            "docstrings leak in, which is the exact shape that hid `qa/routes.json`",
            "            and id(n) not in docstrings]",
            "            ]",
            "a path named only in a docstring does not count as agreement",
        ),
        Mutation(
            "a bare `dir/*` writer starts vouching for every child name anyone invents",
            '                    while token.endswith("/*") or token.endswith("/**"):',
            "                    while False:",
            "a bare `dir/*` writer does not vouch for an invented child",
        ),
        # The two coverage counters. A rule reporting "no findings" over nothing examined is
        # the vacuous pass this repo keeps hitting, so each half is mutated separately —
        # one guard for both would let either go quiet behind the other.
        Mutation(
            "a manifest declaring no paths stops being reported",
            "    if not entries:",
            "    if False:",
            "a manifest declaring no paths is reported, not passed",
        ),
        Mutation(
            "an empty corpus stops being reported, so a broken scan reads as a clean manifest",
            "    if not corpus:",
            "    if False:",
            "a plugin whose surfaces name no paths is reported",
        ),
    ),
)
