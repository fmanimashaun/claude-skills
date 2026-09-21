"""Mutation guard: check_agent_output_contract. Run by scripts/mutation_check.py (#1086)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_agent_output_contract",
    subject="scripts/check_agent_output_contract.py",
    selftest="scripts/check_agent_output_contract.py",   # --selftest lives in the module
    mutations=(
        Mutation(
            # The rule itself. 27 of 29 shipped agents were in exactly this state, and an agent
            # whose return is undeclared costs the parent on every later request, forever.
            # A forgiving default, which is how this really goes quiet: `or ""` looks harmless,
            # and an empty body is under the bounded limit, so every agent silently passes. It
            # REPORTS rather than crashing, so the fixture notices instead of a traceback.
            "a missing Output section defaults to empty and silently passes the bounded test",
            "        body = section_body(path.read_text(encoding=\"utf-8\", errors=\"replace\"))",
            "        body = section_body(path.read_text(encoding=\"utf-8\", errors=\"replace\")) or \"\"",
            "an agent with no Output section is reported",
        ),
        Mutation(
            # THE ANCHORING BUG, reintroduced. A heading that merely CONTAINS "output" -- like
            # `## Ranking /design-flow:variants output`, which is about someone else's output --
            # would count as a contract. It made the first baseline read 3 when it was 2.
            "any heading containing the word 'output' counts as a contract",
            'OUTPUT_HEADING = re.compile(r"^##+\\s+Output\\b.*$", re.M)',
            'OUTPUT_HEADING = re.compile(r"^##+.*[Oo]utput.*$", re.M)',
            "a heading merely CONTAINING 'output' is not a contract",
        ),
        Mutation(
            # The MUST-PASS half. Refusing contract 2 would fail the agents that already do the
            # right thing -- writing the detail to a file and returning a path -- and a gate that
            # is red on correct code is one somebody switches off.
            "writing an artifact and returning its path stops satisfying the contract",
            "        if ARTIFACT.search(body):",
            "        if False:",
            "an agent that writes an artifact and returns a path is accepted",
        ),
        Mutation(
            # The other MUST-PASS half: a bounded verdict is a contract too. Without this the
            # check would demand a file from every reviewer, which is the wrong shape for a
            # two-finding review.
            "a bounded shape stops counting, so only file-writing agents pass",
            "        if len(body) <= BOUNDED_CHARS:",
            "        if False:",
            "a bounded verdict is accepted",
        ),
        Mutation(
            # An Output section that WANDERS is the quiet failure: it looks like a contract and
            # bounds nothing. Removing the length test lets any prose pass.
            "an unbounded, wandering Output section passes",
            "        if len(body) <= BOUNDED_CHARS:",
            "        if True:",
            "an Output section that wanders and names no file is reported",
        ),
    ),
)
