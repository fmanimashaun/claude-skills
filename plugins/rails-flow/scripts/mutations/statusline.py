"""Mutation guard: statusline. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1829. The status line a project vendors. Each mutation breaks ONE rule (a boundary, a field, the stale-window rule of #1854, an exit), and the script's own selftest must notice it.
GUARD = Guard(
    name='statusline',
    subject='scripts/statusline.py',
    selftest='scripts/statusline.py',
    mutations=(
        Mutation(
            'amber starts at 81%',
            'AMBER_AT = 80',
            'AMBER_AT = 81',
            'a window at 80% is amber, and 79% is not',
        ),
        Mutation(
            'amber needs more than 80%',
            'value >= AMBER_AT',
            'value > AMBER_AT',
            'a window at 80% is amber, and 79% is not',
        ),
        Mutation(
            'colour is drawn even when off',
            'if color and value is not None',
            'if value is not None',
            'with colour off nothing is tinted',
        ),
        Mutation(
            'a window is expired only after resets_at',
            'and resets <= now:',
            'and resets < now:',
            'a window is expired at exactly resets_at',
        ),
        Mutation(
            'a window that has reset is still a reading',
            'and resets <= now:',
            'and False:',
            'a window whose resets_at has passed is left out',
        ),
        Mutation(
            'a fractional percentage is truncated',
            'return int(value + 0.5)',
            'return int(value)',
            'a fractional percentage rounds half up',
        ),
        Mutation(
            'a bool is read as a percent',
            'if isinstance(value, bool) or not isinstance(value, (int, float)):',
            'if not isinstance(value, (int, float)):',
            'a percentage that is a string or a bool is not a percent',
        ),
        Mutation(
            'cost is not two decimals',
            'parts.append(f"${cost:.2f}")',
            'parts.append(f"${cost}")',
            'cost is two decimals',
        ),
        Mutation(
            'the worktree is not named',
            'where = f"{where} ({tree})" if where else f"({tree})"',
            'where = where',
            'a linked worktree is named beside the branch',
        ),
        Mutation(
            'cwd is preferred over workspace.current_dir',
            'for value in ((ws.get("current_dir") if isinstance(ws, dict) else None), data.get("cwd")):',
            'for value in (data.get("cwd"), (ws.get("current_dir") if isinstance(ws, dict) else None)):',
            'the working directory is workspace.current_dir',
        ),
        Mutation(
            'a payload that is not JSON raises',
            '    except (ValueError, OSError):\n        return 0',
            '    except OSError:\n        return 0',
            'prints nothing and exits 0',
        ),
        Mutation(
            'NO_COLOR is ignored',
            'color="NO_COLOR" not in os.environ',
            'color=True',
            'NO_COLOR turns the colour off',
        ),
    ),
)
