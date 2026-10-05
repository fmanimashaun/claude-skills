"""Mutation guard: status_board. Declared here, run by scripts/mutation_check.py (#866).

#1585, PR 1. The board exists to show the truth about a repository, so the breaks below are the ones that
make it show something else: an unreadable source drawn as 0, a count that hit its limit drawn as exact,
a stale review drawn as clean, a drafted question shown to the owner, a corrupt record drawn as no
sessions, a page that loads a font from the network. Each must be caught by the fixture its `expects`
names, and by nothing coincidental.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="status_board",
    subject="scripts/status_board.py",
    selftest="scripts/status_board_selftest.py",
    needs=("scripts/status_board_verdicts.json", "hooks/scripts/board-refresh.sh", "hooks/hooks.json"),     # the selftest runs the Stop hook
    mutations=(
        Mutation(
            "a pull request list gh cannot read is drawn as an empty, measured list -- unknown becomes 0",
            "        return unknown(why)\n    by_pr",
            "        return panel(\"ok\", \"\", items=[], count=0)\n    by_pr",
            "with gh unavailable the pull request panel is UNKNOWN",
        ),
        Mutation(
            "a list that reached its limit is drawn as an exact count",
            "    if len(data) >= PR_LIMIT:",
            "    if False:",
            "a pull request list that hit its limit says 'or more'",
        ),
        Mutation(
            "the FIRST matching review comment decides, so a later CLEAN never replaces an old BLOCKED",
            "            found = v                       # the LAST matching comment decides",
            "            found = found or v",
            "the LAST matching review comment decides",
        ),
        Mutation(
            "a review of an older commit is drawn as the verdict on the head",
            "    if not head.startswith(sha) and not sha.startswith(head[: len(sha)]):",
            "    if False:",
            "a review of an OLDER commit reads stale",
        ),
        Mutation(
            "a run from any event counts as the dispatched full run",
            "    runs = [r for r in data if not ev or r.get(\"event\") == ev]",
            "    runs = list(data)",
            "a run from another event does not count",
        ),
        Mutation(
            "a worktree counts as finished when it is merged OR clean",
            "\"finished\": bool(merged is True and clean is True)})",
            "\"finished\": bool(merged is True or clean is True)})",
            "a worktree is finished only when merged AND clean",
        ),
        Mutation(
            "any stopped process counts as an orphan",
            "        stopped += parts[1].startswith(\"T\") and parts[2] == \"1\"",
            "        stopped += parts[1].startswith(\"T\")",
            "a stopped process counts as an orphan only when its parent is init",
        ),
        Mutation(
            "every user's processes are counted against this user's limit",
            "        if len(parts) < 3 or parts[0] != me:",
            "        if len(parts) < 3:",
            "processes are counted for this user only",
        ),
        Mutation(
            "a coordination record of the wrong shape is drawn as no record",
            "        return \"unreadable\", f\"{path} is not a coordination record\"",
            "        return \"none\", \"\"",
            "a wrong-shaped record",
        ),
        Mutation(
            "a drafted question reaches the owner",
            "        if a.get(\"state\") == \"asked\":",
            "        if a.get(\"state\") in (\"asked\", \"drafted\"):",
            "drafted, answered and stateless asks do not reach the owner",
        ),
        Mutation(
            "a silent coordinator is never stale",
            "            stale = mins > int(cfg[\"stale_minutes\"])",
            "            stale = False",
            "a coordinator silent for 240 minutes shows as STALE",
        ),
        Mutation(
            "a closed lane still counts as a session",
            "    open_sessions = [s for s in sessions if s[\"state\"] != \"closed\"]",
            "    open_sessions = list(sessions)",
            "a closed lane does not count as a session",
        ),
        Mutation(
            "a coordinator object that names nobody counts as a coordinator",
            "    if not isinstance(c, dict) or not c.get(\"session_id\"):",
            "    if not isinstance(c, dict):",
            "a coordinator object that names nobody is no coordinator",
        ),
        Mutation(
            "one session with no coordinator is drawn as orchestration",
            "    mode = \"orchestrated\" if coord or len(open_sessions) > 1 else \"single\"",
            "    mode = \"orchestrated\"",
            "one session and no coordinator is single-session mode",
        ),
        Mutation(
            "one sibling whose gh fails blanks the whole pull request panel",
            "    if prs_reasons and len(prs_reasons) == len(repos):",
            "    if prs_reasons:",
            "a sibling whose gh fails is named unavailable",
        ),
        Mutation(
            "a collector that raises ends the run instead of becoming an unknown panel",
            "    except Exception as e:                       # noqa: BLE001 -- converted to a visible unknown, never a silent 0",
            "    except ZeroDivisionError as e:               # noqa: BLE001",
            "a collector that raises becomes an UNKNOWN panel",
        ),
        Mutation(
            "per-pull-request lookups are no longer capped",
            "        if i < PR_DETAIL_CAP:",
            "        if True:",
            "per-pull-request lookups are capped",
        ),
        Mutation(
            "the page escapes nothing",
            "_e = html.escape",
            "_e = lambda s, quote=True: str(s)",
            "page data is escaped",
        ),
        Mutation(
            "the page loads a font from the network",
            "f'<style>{CSS}</style>\\n</head>",
            "f'<link rel=\"stylesheet\" href=\"https://fonts.googleapis.com/css2?family=IBM+Plex+Mono\"><style>{CSS}</style>\\n</head>",
            "no network",
        ),
        Mutation(
            "the passive voice is no longer flagged in an instruction",
            "    if kind == \"instruction\":\n        for m in _PASSIVE.finditer(text):",
            "    if False:\n        for m in _PASSIVE.finditer(text):",
            "an instruction in the passive voice is flagged",
        ),
        Mutation(
            "the word limits are loosened",
            "LIMITS = {\"instruction\": 20, \"description\": 25}",
            "LIMITS = {\"instruction\": 30, \"description\": 40}",
            "an instruction of 21 words is flagged",
        ),
        Mutation(
            "a file the command cannot write is reported as success",
            "        print(f\"could not write the board: {e}\", file=sys.stderr)\n        return 3",
            "        print(f\"could not write the board: {e}\", file=sys.stderr)\n        return 0",
            "when the files cannot be written it exits 3",
        ),
        Mutation(
            "outside a git repository the command carries on and exits 0",
            "        return 2\n    board = collect(env, root)",
            "        return 0\n    board = collect(env, root)",
            "outside a git repository it exits 2",
        ),
        Mutation(
            "the board files are written world-readable",
            "        os.replace(tmp, path)",
            "        os.chmod(tmp, 0o644)\n        os.replace(tmp, path)",
            "the file mode is owner-only",
        ),
        Mutation(
            "the board fetches from the remote",
            "    rc, head = env.sh([\"git\", \"rev-parse\", \"--short\", \"HEAD\"], root)",
            "    rc, head = env.sh([\"git\", \"fetch\", \"-q\", \"origin\"], root)",
            "the board runs only read verbs",
        ),
        Mutation(
            "gh for a sibling repository runs in this repository's directory",
            "        return env.sh(argv, self.root)",
            "        return env.sh(argv, self.root if self.is_self else None)",
            "a sibling with no parseable remote is read from its own directory",
        ),
        Mutation(
            "a merge state git cannot answer is drawn as 'not merged'",
            "        merged = True if mrc == 0 else False if mrc == 1 else None",
            "        merged = mrc == 0",
            "a merge state git cannot answer",
        ),
        Mutation(
            "an unreadable coordination record leaves the asks panel measured and empty",
            "    if status == \"unreadable\":\n        asks_panel = unknown(",
            "    if False:\n        asks_panel = unknown(",
            "an unreadable record makes the ASKS panel UNKNOWN",
        ),
        Mutation(
            "an unreadable record leaves Today looking complete",
            "    if events_panel[\"state\"] == \"ok\" and status == \"unreadable\":",
            "    if False:",
            "an unreadable record makes TODAY partial",
        ),
        Mutation(
            "a worktree with no HEAD reads as not merged",
            "[0] if head else None",
            "[0] if head else 1",
            "a worktree row with no HEAD reads merged UNKNOWN",
        ),
        Mutation(
            "a pull request with no head commit gets a current-looking review",
            "    if not head:\n        return {\"state\": \"unknown\"}",
            "    if False:\n        return {\"state\": \"unknown\"}",
            "a pull request with no head commit has an UNKNOWN review",
        ),
        Mutation(
            "a full window of other runs reads as 'not dispatched'",
            "if len(data) >= RUN_LIMIT else {\"state\": \"not dispatched\"}",
            "if False else {\"state\": \"not dispatched\"}",
            "20 runs of other events",
        ),
        Mutation(
            "every merge state says 'Merge.' for a green run and a clean review",
            "        if ms in (\"CLEAN\", \"HAS_HOOKS\"):",
            "        if True:",
            "does NOT say 'Merge.'",
        ),
        Mutation(
            "a merged-today list that hit its limit looks complete",
            "    return sorted(ev, key=lambda e: e[\"time\"]), len(data) >= MERGED_LIMIT",
            "    return sorted(ev, key=lambda e: e[\"time\"]), False",
            "a merged-today list that hit its limit marks Today partial",
        ),
        Mutation(
            "the last call gets a one-second floor and can overrun the budget",
            "min(CALL_TIMEOUT, left))",
            "max(1.0, min(CALL_TIMEOUT, left)))",
            "a call is given exactly the time left",
        ),
        Mutation(
            "a call still runs after the budget is spent",
            "        if left <= 0:\n            return 124, \"\"",
            "        if False:\n            return 124, \"\"",
            "once the budget is spent a call does not run at all",
        ),
        Mutation(
            "a relative sibling path resolves against the process directory",
            "            sroot = (root / sroot).resolve()",
            "            sroot = sroot.resolve()",
            "a relative sibling path resolves against the repository root",
        ),
        Mutation(
            "integration_branch is read but never declared, so a configured value is dropped",
            '    "integration_branch": None,         # None: `integration_branch_of` finds it (dev when origin/dev exists)\n',
            "",
            "integration_branch is declared in DEFAULTS",
        ),
        Mutation(
            "a repository whose origin/HEAD is main and whose work lands on dev is measured against main",
            '    if env.sh(["git", "rev-parse", "--verify", "-q", "refs/remotes/origin/dev"], root)[0] == 0:',
            "    if False:",
            "origin/HEAD is main, origin/dev exists",
        ),
        Mutation(
            "the first verdict word of a delta review decides, so a quoted CLEAN beats the real verdict",
            "    return (m.group(1) if m else \"\"), words[-1]",
            "    return (m.group(1) if m else \"\"), words[0]",
            "since my CLEAN at 0fdb8eb",
        ),
        Mutation(
            "any hex word is read as the reviewed commit, so a run id becomes one",
            '_VERDICT_SHA = re.compile(r"\\b(?:at|of|head|commit)\\s+([0-9a-f]{7,40})\\b")',
            '_VERDICT_SHA = re.compile(r"\\b([0-9a-f]{7,40})\\b")',
            "a run id is never read as the commit",
        ),
        Mutation(
            "a verdict that names no commit is drawn as no review",
            '        return {"state": "unknown", "head": ""}        # a verdict that names no commit: not "none", not a match',
            '        return {"state": "none"}',
            "names no commit is UNKNOWN",
        ),
        Mutation(
            "a re-check is no longer a verdict",
            '(?:review|re-?check)',
            '(?:review)',
            "every real verdict comment is read",
        ),
        Mutation(
            "the built-in reader is the old single-shape regex",
            '    "review_pattern": None,             # None: `verdict_of` reads the shapes in use. A regex here replaces it',
            '    "review_pattern": r"Independent review at ([0-9a-f]{7,40})\\W[^\\n]{0,80}?\\b(CLEAN|BLOCKED)\\b",  # replaces it',
            "a re-review is a verdict on the head",
        ),
        Mutation(
            "an f-string reuses its own quote (a SyntaxError on the stock python3 3.9)",
            "\"<ul>\" + \"\".join(_step_li(s) for s in l[\"steps\"]) + \"</ul>\"",
            "f\"<ul>{\"\".join(_step_li(s) for s in l[\"steps\"])}</ul>\"",
            "no f-string in status_board.py reuses its own quote",
        ),
        Mutation(
            "a run lookup is made for a pull request with no head commit, and returns another commit's run",
            '    if not wf or not head:',
            '    if not wf:',
            'a pull request with no head commit has an UNKNOWN run',
        ),
        Mutation(
            'a sibling whose directory has another origin is read as the record declares',
            '    if own.lower() != declared.lower():',
            '    if False:',
            'has a different origin than the record declares',
        ),
        Mutation(
            "a sibling whose origin cannot be read is trusted on the record's word",
            '    own = slug_of(out.strip()) if rc == 0 else None',
            '    own = slug_of(out.strip()) if rc == 0 else declared',
            'whose origin cannot be read is unavailable',
        ),
        Mutation(
            'the origin match is case-sensitive',
            '    if own.lower() != declared.lower():',
            '    if own != declared:',
            'ignores case and the https form',
        ),
        Mutation(
            'a sibling that declares no remote is held to the origin rule',
            '    if not declared:\n        return ""',
            '    if False:\n        return ""',
            'a sibling with no parseable remote is read from its own directory',
        ),
    ),
)
