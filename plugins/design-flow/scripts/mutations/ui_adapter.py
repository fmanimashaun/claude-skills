"""Mutation guard: ui_adapter. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #2185. The resolver every dispatching command asks which UI adapter to run. Its signature failure is an ANSWER where there should be
    # a refusal: a detector that could not judge, or found nothing, read as a clean verdict, and the command then scaffolds or audits
    # against the wrong stack with nothing raised.
    name="ui_adapter",
    subject="scripts/ui_adapter.py",
    selftest="scripts/ui_adapter.py",   # --selftest lives in the module
    needs=("ui/viewcomponent-erb/adapter.json",),   # the selftest resolves every adapter the plugin ships
    mutations=(
        Mutation(
            "a detector that cannot judge the project (exit 2 or problems) is read as an answer",
            '    if run.returncode == 2 or out.get("problems"):',
            "    if False:",
            "problems beside stacks are refused",
        ),
        Mutation(
            "a project no stack plugin recognises is read as an answer",
            '    if run.returncode == 1 or not out.get("stacks"):',
            "    if False:",
            "exit 1 (no stack) is refused",
        ),
        Mutation(
            "the descriptor's ui block is ignored, so no implementation is ever found",
            '    if isinstance(ui, dict) and ui.get("implementation"):',
            "    if False:",
            "a ui block names its implementation",
        ),
        Mutation(
            "the adapter's agents are dropped from the answer, so a command dispatches to nothing",
            '"agents": spec.get("agents", {})',
            '"agents": {}',
            "...with its agents and checks",
        ),
        Mutation(
            "an adapter.json that does not exist is no longer refused up front",
            "    if not spec_file.is_file():",
            "    if False:",
            "an implementation with no adapter is refused, not defaulted to another stack",
        ),
        Mutation(
            "the descriptor's token file is dropped, so design_prompt looks for a default that no stack names",
            '"stack": stack, "tokens_file": tokens_file}',
            '"stack": stack, "tokens_file": None}',
            "...and the token file the descriptor named",
        ),
    ),
)
