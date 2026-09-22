"""Mutation guard: ci_verdict_hint. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1173. An advisory that must speak on exactly one condition -- a CI-reading command whose output
# shows a failing conclusion -- and on no other. Each mutation removes one half of that, and names
# the fixture that exists for it, so a coincidental catch cannot hide that fixture going quiet.
GUARD = Guard(
    name="ci_verdict_hint",
    subject="scripts/ci_verdict_hint.py",
    selftest="scripts/ci_verdict_hint.py",
    mutations=(
        Mutation(
            # THE ONE THAT MATTERS. Plain `gh pr checks` exits 1 on a failing check, so it arrives as
            # PostToolUseFailure with its text in `error`. Reading only `tool_response` is the design
            # the documentation implies, and it is silent in exactly the case this exists for.
            "the PostToolUseFailure `error` text is ignored, so plain `gh pr checks` never speaks",
            '    error = payload.get("error")\n',
            "    error = None\n",
            "plain `gh pr checks` with a failing check, via PostToolUseFailure, adds the hint",
        ),
        Mutation(
            "it speaks on any CI output, failing or not -- paid for on every `gh` call, then ignored",
            "    if STEP_COUNT.search(text) or not FAILING.search(text):\n",
            "    if STEP_COUNT.search(text):\n",
            "all-passing `plain` output is silent",
        ),
        Mutation(
            "it speaks on any command whose output says `fail` -- rspec, a log line",
            "    if not CI_READ.search(command) or ALREADY.search(command):\n",
            "    if ALREADY.search(command):\n",
            "a non-CI command whose output says `fail` is silent",
        ),
        Mutation(
            "it nags the session that is already running ci_verdict",
            "    if not CI_READ.search(command) or ALREADY.search(command):\n",
            "    if not CI_READ.search(command):\n",
            "a command that already runs ci_verdict is silent",
        ),
        Mutation(
            "it nags output that already carries a step count",
            "    if STEP_COUNT.search(text) or not FAILING.search(text):\n",
            "    if not FAILING.search(text):\n",
            "output that already carries a step count is silent",
        ),
        Mutation(
            # The field boundary is what stops a check NAMED `failover-drill` reading as a failure.
            "the plain-rows pattern loses its field boundary",
            '    r"(?:^|\\t)fail(?:\\t|$)"',
            '    r"fail"',
            "a passing check whose NAME contains `fail` is silent",
        ),
        Mutation(
            "every hint is attributed to PostToolUse, whichever event delivered it",
            '    event = payload.get("hook_event_name") or "PostToolUse"\n',
            '    event = "PostToolUse"\n',
            "...under the event it arrived on, so the harness attributes it correctly",
        ),
        Mutation(
            "the suggestion drops the repository the reader asked about",
            '    flag = f" -R {repo.group(1)}" if repo else ""\n',
            '    flag = ""\n',
            "`-R owner/repo` is carried into the suggested command",
        ),
        Mutation(
            # FAILS OPEN. An advisory that raises on odd input takes the tool call down with it.
            "an unreadable payload raises instead of staying silent",
            "    except (ValueError, TypeError):\n",
            "    except ZeroDivisionError:\n",
            "not JSON payload is silent, not an exception",
        ),
    ),
)
