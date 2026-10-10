"""Mutation guard: check_guide. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_guide",
    subject="scripts/check_guide.py",
    selftest="scripts/check_guide_selftest.py",
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
        Mutation(
            'a short sha is accepted as a pin commit',
            'SHA_RE = re.compile(r"^[0-9a-f]{40}$")',
            'SHA_RE = re.compile(r"^[0-9a-f]+$")',
            'a short sha is refused',
        ),
        Mutation(
            'a pin naming no commit in the repository passes',
            'if _git(repo, "cat-file", "-t", f"{sha}^{{commit}}").returncode != 0:',
            'if False:',
            'a commit that does not exist is a finding',
        ),
        Mutation(
            'a line past the end of the file passes',
            '            if end > total:',
            '            if False:',
            'a range past the end is a finding',
        ),
        Mutation(
            'a path with .. is accepted',
            'if path.startswith("/") or ".." in path.split("/"):',
            'if path.startswith("/"):',
            'a path with .. is refused',
        ),
        Mutation(
            'a file deleted at HEAD passes',
            'if _blob_lines(repo, "HEAD", path) is None:',
            'if False:',
            'a file deleted at HEAD is a finding',
        ),
        Mutation(
            'one pinned diagram no longer obliges the others',
            '    if not any_pin and not require:',
            '    if not require:',
            'one pinned diagram makes an unpinned one a finding',
        ),
        Mutation(
            '--require-pins is ignored',
            '    if not any_pin and not require:',
            '    if not any_pin:',
            '--require-pins refuses a guide with no pins',
        ),
        Mutation(
            'an orphan pin comment is ignored',
            '            if PIN_RE.search(line) and line_no not in pinned_lines:',
            '            if False:',
            'a pin above no mermaid block pins nothing',
        ),
        Mutation(
            'line 0 is accepted',
            '            if start < 1 or end < start:',
            '            if end < start:',
            'line 0 is not a line',
        ),
        Mutation(
            'a backwards range is accepted',
            '            if start < 1 or end < start:',
            '            if start < 1:',
            'a backwards range is refused',
        ),
        Mutation(
            'outside a git work tree the pins pass unverified',
            '    if inside.returncode != 0:',
            '    if False:',
            'outside a git work tree the pins cannot be verified',
        ),
        Mutation(
            'a file edited since the pin stops being noted',
            '            elif _git(repo, "diff", "--quiet", sha, "HEAD", "--", path).returncode != 0:',
            '            elif False:',
            'a file edited since the pin is a note',
        ),
        Mutation(
            'the entry point drops the pin findings',
            '    findings += pin_findings\n',
            '',
            'main() with a pin past the end of its file exited',
        ),
    ),
)
