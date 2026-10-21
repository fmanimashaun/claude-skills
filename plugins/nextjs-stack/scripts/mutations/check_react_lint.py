"""Mutation guard: check_react_lint. Declared here, run by scripts/mutation_check.py (#2222)."""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="check_react_lint",
    subject="scripts/check_react_lint.py",
    selftest="scripts/check_react_lint.py",
    mutations=(
        Mutation(
            "every rule's message becomes a finding, not only our three",
            '            if m.get("ruleId") in RULES:',
            "            if True:",
            "only our three rules become findings",
        ),
        Mutation(
            "the preset's own rules are left on",
            'Object.keys(entry.rules).map((k) => [k, \\"off\\"])',
            'Object.keys(entry.rules).map((k) => [k, \\"warn\\"])',
            "switch the preset's own rules off",
        ),
        Mutation(
            "our three rules are only warnings",
            '''    rules = ", ".join(f'"{r}": "error"' for r in RULES)''',
            '''    rules = ", ".join(f'"{r}": "warn"' for r in RULES)''',
            "the config must turn",
        ),
        Mutation(
            "a not-applicable project exits 0, reading as a pass",
            '        print(f"check_react_lint: not applicable -- {exc}")\n        return 3',
            '        print(f"check_react_lint: not applicable -- {exc}")\n        return 0',
            "must exit 3, not applicable",
        ),
        Mutation(
            "a missing eslint binary escapes as a traceback",
            "        except FileNotFoundError as exc:   # #2243 review",
            "        except ZeroDivisionError as exc:   # #2243 review",
            "a missing eslint binary must be unjudgeable",
        ),
    ),
)
