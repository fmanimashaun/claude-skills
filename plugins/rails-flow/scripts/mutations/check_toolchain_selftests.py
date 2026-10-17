"""Mutation guard: check_toolchain_selftests. Run by scripts/mutation_check.py (#1109)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_toolchain_selftests",
    subject="scripts/check_toolchain_selftests.py",
    selftest="scripts/check_toolchain_selftests.py",
    mutations=(
        Mutation(
            # The whole point. A shipped gate that has rotted against the project's framework or
            # Python version must be reported, or the project reads its silence as health.
            "a failing selftest stops being reported",
            "        if not ok:",
            "        if False:",
            "a FAILING selftest is reported",
        ),
        Mutation(
            # THE DISTINCTION THAT KEEPS IT USABLE. "The gate is broken here" is not "your code is
            # wrong"; collapsing them makes a team chase their own code, or ignore the gate. Same
            # defect as #1097's timeout-reported-as-FAIL, one level out.
            "the finding stops saying the GATE is broken rather than the project's code",
            '                f"this project, which is not the same as your code being wrong: it may have rotted "',
            '                f"this project. "',
            "says the gate is broken here, not that the project's code is wrong",
        ),
        Mutation(
            # A check nobody proved must be counted, not silently accepted -- that is the vacuous
            # pass this whole file exists to refuse.
            "a shipped check with no selftest is silently accepted",
            "        if not supports_selftest(path):",
            "        if False:",
            "a check with no selftest is counted as unproven, not as a pass",
        ),
        Mutation(
            # A manifest naming a script that is not there means the gate never ran at all, and
            # "0 findings" over a gate that never ran is the flattering reading.
            "a manifest naming a missing script stops being a finding",
            "        if not path.is_file():",
            "        if False:",
            "a manifest naming a missing script is a finding",
        ),
        Mutation(  # #1873: the n/a row reaches its site
            'zero selftests run is a pass instead of n/a',
            'this proved nothing.")\n        return 3',
            'this proved nothing.")\n        return 0',
            'no shipped selftest found is not applicable (exit 3)',
        ),
        # #2111: the selftest's environment names the project when the caller has none. Without it the shim's fixture exemption fails closed and every selftest that stages a fixture fails.
        Mutation(
            "the project is never named, so a session without CLAUDE_SESSION_PROJECT_TOP runs the selftests without it",
            "        env[SESSION_TOP] = top\n",
            "        pass\n",
            "an environment without the session's project gets the git toplevel of the cwd",
        ),
        Mutation(
            "a value the caller set is overridden by the project's toplevel",
            "    if env.get(SESSION_TOP):\n        return env\n",
            "    if False:\n        return env\n",
            "a value the caller set is never overridden",
        ),
        Mutation(
            "an empty value counts as set, so it is left empty",
            "    if env.get(SESSION_TOP):\n        return env\n",
            "    if SESSION_TOP in env:\n        return env\n",
            "an EMPTY value counts as not set",
        ),
        Mutation(
            "run() does not hand the child the environment selftest_env built",
            "timeout=timeout, cwd=cwd,\n                              env=selftest_env(cwd=cwd))",
            "timeout=timeout, cwd=cwd)",
            "a selftest run by the check SEES the project it runs in",
        ),
        Mutation(
            # #2137: the walk that ran every cached VERSION of a plugin and none of its siblings. An older cached docs_layout.py (no fixture marker) failed `git add -A` under the
            # current git shim, which blocked every Retask `gh pr ready`.
            "the walk is the flat one again: every cached version of the plugin, none of the sibling plugins",
            "    return project_gates.plugin_roots((start or HERE).resolve())",
            "    return sorted(p.parent for p in (start or HERE).resolve().parents[1].parent.glob(\"*/checks.json\"))",
            "ONE directory per plugin",
        ),
    ),
)
