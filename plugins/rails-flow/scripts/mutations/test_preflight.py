"""Mutation guard: test_preflight. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #1561, #1566. An ADVISORY that must speak on a suite run when the environment is wrong, be silent on everything else, and never block. Each
# mutation removes one half of one of those and names the selftest check that exists for it, so a coincidental catch cannot hide a fixture
# that went quiet.
GUARD = Guard(
    name="test_preflight",
    subject="scripts/test_preflight.py",
    selftest="scripts/test_preflight.py",
    mutations=(
        # ---- Postgres
        Mutation(
            "a Postgres outage is never reported",
            "    if probe is None or probe.returncode == 0:\n",
            "    if True:\n",
            "a Postgres outage before an rspec run is named, with its exit status",
        ),
        Mutation(
            # DORMANT WITHOUT A DATABASE (plugin-boundaries): a sqlite or API-only project must not be probed for Postgres at all.
            "a project that has no Postgres is probed for it anyway",
            "    if not database_detected(root, env):\n",
            "    if False:\n",
            "a project whose adapter is sqlite3 is not probed at all",
        ),
        Mutation(
            "DATABASE_URL naming Postgres stops counting as a detected database",
            '    if str(env.get("DATABASE_URL", "")).startswith(("postgres://", "postgresql://", "postgis://")):\n        return True\n',
            '    if False:\n        return True\n',
            "DATABASE_URL naming Postgres counts as detected",
        ),
        Mutation(
            # A password on a command line is visible in `ps`.
            "pg_isready is handed the whole DATABASE_URL, password included",
            '    args = ["-h", match.group(1).strip("[]")]\n',
            '    args = ["-d", url]\n',
            "...and pg_isready got -h/-p, never the URL with its password",
        ),
        Mutation(
            # A hung probe must be cut off. An unanswered pg_isready is silence, not an accusation.
            "a hung command is waited for without a deadline",
            "                              timeout=PROBE_SECONDS if timeout is None else timeout, check=False)\n",
            "                              timeout=None, check=False)\n",
            "a `pg_isready` that hangs is cut off at the deadline, and the hook is silent",
        ),
        # ---- the held bundler.lock
        Mutation(
            "a lock held by another process reads as free",
            "                return True\n            fcntl.flock(handle, fcntl.LOCK_UN)\n",
            "                return False\n            fcntl.flock(handle, fcntl.LOCK_UN)\n",
            "a bundler.lock held by another process is named, with its holder",
        ),
        # ---- load
        Mutation(
            "a load above the threshold is never reported",
            "    if load <= limit:\n",
            "    if True:\n",
            "a load above the threshold advises foreground or smaller shards",
        ),
        Mutation(
            "the load threshold ignores RAILS_FLOW_PREFLIGHT_LOAD_MAX",
            '        limit = float(env.get("RAILS_FLOW_PREFLIGHT_LOAD_MAX") or 2 * count)\n',
            "        limit = 2.0 * count\n",
            "RAILS_FLOW_PREFLIGHT_LOAD_MAX moves the threshold both ways",
        ),
        # ---- spec paths
        Mutation(
            "a spec path that does not exist is never reported",
            "    missing = [p for p in spec_paths(args) if not os.path.exists(p if os.path.isabs(p) else os.path.join(cwd, p))]\n",
            "    missing = []\n",
            "a spec path that does not exist is named, and one that does is not",
        ),
        Mutation(
            "`file.rb:12` and `file.rb[1:2]` are checked as file names, so a good path reads as missing",
            '        path = re.sub(r"\\[[\\d:, ]+\\]$", "", re.sub(r"(?::\\d+)+$", "", token))\n',
            "        path = token\n",
            "CONTROL: a path with :line and an [example id] that exists is silent",
        ),
        Mutation(
            "an option's value that looks like a path is checked as a spec path",
            "            skip = token in VALUE_OPTIONS\n",
            "            skip = False\n",
            "an option's value that looks like a path is not a spec path",
        ),
        Mutation(
            "a glob is checked as a file name",
            '        if any(c in token for c in "*?{}$`"):\n',
            "        if False:\n",
            "a glob is not checked",
        ),
        Mutation(
            # A Playwright path is relative to a directory this script cannot know; checking it from the project root accuses good commands.
            "a Playwright path is checked against the project root",
            '    if kind not in ("rspec", "rails-test"):\n',
            "    if False:\n",
            "a Playwright path is NOT checked (it is relative to a directory this cannot know)",
        ),
        # ---- what counts as a suite run
        Mutation(
            # COMMAND POSITION. The word `rspec` inside a commit message or a grep is not a suite run.
            "any segment that contains the word rspec is read as a suite run",
            "    program, args = os.path.basename(tokens[0]), tokens[1:]\n",
            '    program, args = ("rspec", tokens[1:]) if "rspec" in tokens else (os.path.basename(tokens[0]), tokens[1:])\n',
            "grep for rspec is silent",
        ),
        Mutation(
            "`bundle exec` in front of rspec hides the suite run",
            '        elif head == "bundle" and tokens[1:2] == ["exec"]:\n',
            "        elif False:\n",
            "a compound command is still read as a suite run",
        ),
        Mutation(
            "environment assignments in front of rspec hide the suite run",
            "        if ENV_ASSIGNMENT.match(head) or head in WRAPPERS:\n",
            "        if head in WRAPPERS:\n",
            "env assignments first is still read as a suite run",
        ),
        Mutation(
            "an unbalanced quote raises instead of reading as no command",
            "    except ValueError:\n        return []\n    out: list[list[str]] = []\n",
            "    except ZeroDivisionError:\n        return []\n    out: list[list[str]] = []\n",
            "an unbalanced quote reads as no command at all, not as an error",
        ),
        Mutation(
            # A `pg_isready` shipped in the checkout is repository code run before the user is asked about the command.
            "a program is looked up inside the project's own tree",
            "        if real == base or real.startswith(base + os.sep):\n            continue\n",
            "        if False:\n            continue\n",
            "a pg_isready the repository ships inside its own tree is never run, even FIRST on PATH",
        ),
        Mutation(
            "a relative PATH entry is searched, so it resolves against wherever the process happens to be",
            "        if not entry or not os.path.isabs(entry):\n            continue\n",
            "        if not entry:\n            continue\n",
            "a RELATIVE PATH entry is never searched, wherever the process happens to be",
        ),
        # ---- the advisory contract: speak on one channel, decide nothing, never fail
        Mutation(
            "the context is attributed to the wrong event",
            '    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": render(findings)}})\n',
            '    return json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": render(findings)}})\n',
            "...as PreToolUse additionalContext, the channel documented as reaching the model",
        ),
        Mutation(
            # AN ADVISORY MUST NEVER BLOCK OR ALLOW. A permission decision turns it into a gate nobody classified.
            "the advisory starts deciding permissions",
            '    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": render(findings)}})\n',
            '    return json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": render(findings), "permissionDecision": "allow"}})\n',
            "...and it never decides a permission",
        ),
        Mutation(
            # FAILS OPEN. An advisory that raises takes the tool call down with it.
            "an error inside a check raises instead of staying silent",
            "    except Exception:  # noqa: BLE001 - an advisory that raises takes the tool call down with it\n        return \"\"\n",
            "    except (ValueError, TypeError):\n        return \"\"\n",
            "an exception inside a check is silence, not a crash",
        ),
        Mutation(
            "input that is not even text takes the process down",
            '    sys.stdout.write(run(sys.stdin.buffer.read().decode("utf-8", "replace")))\n',
            '    sys.stdout.write(run(sys.stdin.buffer.read().decode("utf-8")))\n',
            "the entry point exits 0 on garbage that is not even text, and prints nothing",
        ),
        Mutation(
            "the context has no character cap",
            '    return text if len(text) <= MAX_CHARS else text[: MAX_CHARS - 1] + "…"\n',
            "    return text\n",
            "the context is capped in lines and characters",
        ),
        Mutation(
            "the context has no line cap",
            "    lines = findings[:MAX_LINES]\n",
            "    lines = findings\n",
            "the context is capped in lines and characters",
        ),
    ),
)
