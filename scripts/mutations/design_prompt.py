"""Mutation guard: design_prompt. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #745. The prompt is only worth generating if it carries the PROJECT's system. Each mutation
    # removes one thing that makes it carry it.
    name="design_prompt",
    subject="plugins/design-flow/scripts/design_prompt.py",
    selftest="plugins/design-flow/scripts/design_prompt.py",
    needs=("plugins/design-flow/scripts", "skills"),
    mutations=(
        Mutation(
            # A primitive in the prompt invites the canvas to bind to a private name.
            "private primitives leak into the prompt alongside the roles",
            "    kept = {k: v for k, v in roles.items() if k.startswith(ROLE_PREFIXES)}",
            "    kept = dict(roles)",
            "omits a private primitive",
        ),
        Mutation(
            "a missing theme stops being reported, so the prompt ships with no tokens and "
            "still looks like a prompt",
            "    if not theme_css.is_file():",
            "    if False:",
            "a missing theme is reported, not silent",
        ),
        Mutation(
            "the catalog stops excluding metadata keys, so `_comment` reads as a component",
            '    return sorted(k for k in data if not k.startswith("_")), None',
            "    return sorted(data), None",
            "metadata keys are not components",
        ),
        Mutation(
            # A gap buried under sixty lines of tokens is a gap nobody acts on.
            "the incompleteness warning stops leading the document",
            "    if problems:",
            "    if False:",
            "a gap is stated before anything else",
        ),
    ),
)
