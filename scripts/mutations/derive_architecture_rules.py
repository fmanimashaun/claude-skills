"""Mutation guard: derive_architecture_rules. Declared here, run by scripts/mutation_check.py (#2221).

The registry is derived from the framework page and committed in design-flow. The audit takes a
finding's authority from it, so the mutations below turn off each thing that keeps that authority
honest: the computation (a house rule must not become a standard), the refusal of an empty or
duplicated table, and the drift comparison itself.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="derive_architecture_rules",
    subject="scripts/derive_architecture_rules.py",
    selftest="scripts/derive_architecture_rules.py",
    selftest_args=("--selftest",),
    needs=(
        "scripts/check_architecture_rules.py",
        "plugins/rails-stack/skills/design-system/references/architecture.md",
        "plugins/design-flow/reference/architecture-rules.json",
    ),
    mutations=(
        Mutation(
            "every rule derives as a standard, so a house rule can be reported as one",
            '"authority": "standard" if kind == "claim" else "house"',
            '"authority": "standard"',
            "a decision basis derives as a house rule",
        ),
        Mutation(
            "a page with no rule rows stops being refused",
            "    if not rules:",
            "    if False:",
            "a page with no rule rows is refused",
        ),
        Mutation(
            "a duplicate rule id stops being refused",
            "    if len(set(ids)) != len(ids):",
            "    if False:",
            "a duplicate id is refused",
        ),
        Mutation(
            "the drift comparison always agrees",
            "    return on_disk != derived",
            "    return False",
            "an artifact that differs from the page is a disagreement",
        ),
    ),
)
