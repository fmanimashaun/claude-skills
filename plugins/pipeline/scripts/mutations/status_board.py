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
            "            found = m                       # the LAST matching comment decides",
            "            found = found or m",
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
            "a call may wait past the time budget",
            "        left = max(1.0, min(CALL_TIMEOUT, self.deadline - time.monotonic()))",
            "        left = CALL_TIMEOUT",
            "every call is given a timeout no longer than the time left",
        ),
    ),
)
