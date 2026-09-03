"""Mutation guard: check_guide. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_guide",
    subject="plugins/rails-flow/scripts/check_guide.py",
    selftest="plugins/rails-flow/scripts/check_guide_selftest.py",
    mutations=(
        Mutation(
            "subgraph depth stops deciding whether a bare `end` is legal",
            "            if depth == 0:",
            "            if False:",
            "a bare lowercase `end` closing no subgraph",
        ),
        Mutation(
            "a correctly quoted label is read as unquoted (the false-positive direction)",
            "            if text.startswith('\"') and text.endswith('\"') and len(text) >= 2:",
            "            if False:",
            "a quoted label containing parentheses",
        ),
        Mutation(
            "an unclosed managed section stops being unusable",
            "    if open_section is not None:\n        raise Unusable(",
            "    if False:\n        raise Unusable(",
            "an unclosed section would swallow everything after it",
        ),
        Mutation(
            "the ASCII-art rule loses its arrow carve-out and eats directory trees",
            "                if len(drawn) >= 3 and any(ARROW_RE.search(b) for b in diagram.body):",
            "                if len(drawn) >= 3:",
            "a directory tree is box-drawing WITHOUT arrows and must pass",
        ),
        Mutation(
            "the diagram-type allowlist stops rejecting unverified types",
            "                if declared not in KNOWN_DIAGRAM_TYPES:",
            "                if False:",
            "a diagram type with no evidence GitHub renders it",
        ),
        Mutation(
            "the image rule widens from diagrams to every picture, eating screenshots",
            "                if any(w in haystack for w in DIAGRAM_WORDS):",
            "                if True:",
            "a screenshot is legitimate",
        ),
    ),
)
