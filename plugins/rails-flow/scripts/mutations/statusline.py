"""Mutation guard: statusline. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1829. The status line a project vendors. Each mutation breaks ONE rule (a boundary, a field, the stale-window rule of #1854, an exit, or a hostile-payload defence found in
# review of #1869), and the script's own selftest must notice it.
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
            'a bool is read as a number',
            '    if isinstance(value, bool) or not isinstance(value, (int, float)):\n        return False',
            '    if not isinstance(value, (int, float)):\n        return False',
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
            'where = f"{where} ({clean(tree)})" if where else f"({clean(tree)})"',
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
            'the catch-all is dropped, so a payload that exhausts the stack crashes',
            '    except Exception:\n        return 0',
            '    except ValueError:\n        return 0',
            'an unexpected RecursionError anywhere in main prints nothing and exits 0',
        ),
        Mutation(
            'NO_COLOR is ignored',
            'color="NO_COLOR" not in os.environ',
            'color=True',
            'NO_COLOR turns the colour off',
        ),
        Mutation(
            'NaN and Infinity are real numbers',
            '        return math.isfinite(value)',
            '        return True',
            'a NaN percentage is not a percent',
        ),
        Mutation(
            'an integer too large for a float raises',
            '    except OverflowError:\n        return False',
            '    except OverflowError:\n        raise',
            'an integer too large for a float is not a percent',
        ),
        Mutation(
            'a cost of NaN or Infinity is printed',
            '    if finite(cost):',
            '    if isinstance(cost, (int, float)) and not isinstance(cost, bool):',
            'a NaN cost is left out',
        ),
        Mutation(
            'control characters in a value reach the footer',
            '    return "".join(c for c in text if ord(c) >= 32 and ord(c) != 127 and not 0xD800 <= ord(c) <= 0xDFFF)',
            '    return text',
            'C0 control characters and DEL in a printed value are stripped',
        ),
        Mutation(
            'DEL is kept',
            ' and ord(c) != 127 and not 0xD800',
            ' and not 0xD800',
            'C0 control characters and DEL in a printed value are stripped',
        ),
        Mutation(
            'a lone surrogate is kept',
            ' and not 0xD800 <= ord(c) <= 0xDFFF)',
            ')',
            'a lone surrogate in a printed value is dropped',
        ),
        Mutation(
            'a NUL in the working directory is not caught in the branch lookup',
            '    except (OSError, ValueError, subprocess.SubprocessError):',
            '    except (OSError, subprocess.SubprocessError):',
            'a NUL in the working directory does not take the line down',
        ),
        Mutation(
            'effort is printed uncleaned',
            '        parts.append(clean(effort))',
            '        parts.append(effort)',
            'C0 control characters and DEL in a printed value are stripped',
        ),
        Mutation(
            'the branch is printed uncleaned',
            '    where = clean(git_branch or "")',
            '    where = git_branch or ""',
            'a branch name with an escape sequence is cleaned before it is printed',
        ),
    ),
)
