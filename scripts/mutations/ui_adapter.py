"""Mutation guard: ui_adapter. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    # #2185. The resolver every dispatching command asks which UI adapter to run. Its signature failure is an ANSWER where there should be
    # a refusal: a detector that could not judge, or found nothing, read as a clean verdict, and the command then scaffolds or audits
    # against the wrong stack with nothing raised.
    name="ui_adapter",
    subject="plugins/design-flow/scripts/ui_adapter.py",
    selftest="plugins/design-flow/scripts/ui_adapter.py",   # --selftest lives in the module
    # a repo-root guard, not a plugin one: the selftest resolves a real project against the real rails-stack manifest through the mirrored detector,
    # so those files stage at their repo paths beside design-flow's.
    needs=("plugins/design-flow/ui/viewcomponent-erb/adapter.json", "plugins/design-flow/scripts/detect_stack.py",
           "plugins/design-flow/agents", "plugins/design-flow/.claude-plugin/plugin.json",
           # the detector refuses a descriptor naming an agent or a file that does not exist (agents, setup section, security checklist),
           # so the whole rails-stack plugin the real descriptor lives in stages with it
           "plugins/rails-stack"),
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
            "the adapter's token file is dropped, so design_prompt looks for a default that no stack names",
            '"tokens_file": spec.get("tokens_file")}',
            '"tokens_file": None}',
            "...and the token file the adapter names",
        ),
        Mutation(
            "the detected stack's descriptor is never consulted, so every project resolves nothing",
            "    impls = implementations(detected)\n    if not impls:",
            "    impls = set()\n    if not impls:",
            "a project the real manifest recognises resolves",
        ),
    ),
)
