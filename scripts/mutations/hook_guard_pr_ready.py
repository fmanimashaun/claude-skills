"""Mutation guard: hook_guard_pr_ready. Declared here, run by scripts/mutation_check.py (#1565).

`gh pr ready` only on a GREEN sweep record with zero skips for HEAD. The wrapper decides whether a command is a
`gh pr ready`; `lib/pr_ready_guard.py` judges the record. Each mutation is caught by the fixture its `expects` names.
"""
from mutation_types import Guard, Mutation  # noqa: F401

_NEEDS = ("plugins/rails-flow/scripts/advisory_scope.py", "plugins/rails-flow/scripts/security_scope.py", "plugins/rails-flow/scripts/check_threat_model.py", "plugins/rails-flow/scripts/detect_stack.py",  # stop-gate.sh runs advisory_scope.py (#2262)
           "plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/scripts/test_preflight.py", "plugins/rails-flow/scripts/wip_commit.py",
          'plugins/qa-flow/scripts/remote_evidence.py',
          'plugins/rails-flow/scripts/assign_lanes.py', 'plugins/rails-flow/scripts/brain_local_sync.py', 'plugins/rails-flow/scripts/check_memory_index.py',
          "plugins/rails-flow/hooks/hooks.json",
          'plugins/rails-flow/hooks/scripts', 'plugins/qa-flow/hooks/scripts', 'plugins/qa-flow/scripts',
          'plugins/rails-flow/scripts/check_criteria.py',
          'plugins/rails-flow/scripts/check_handoff.py',
          'plugins/qa-flow/scripts/read_certification.py',
          'plugins/qa-flow/scripts/push_targets.py',
          'plugins/qa-flow/scripts/release_evidence.py',
          'plugins/rails-flow/scripts/self_consistency.py',
          'plugins/rails-flow/scripts/extract_claims.py',
          'plugins/rails-flow/scripts/ci_verdict_hint.py', 'plugins/rails-flow/scripts/session_reaper.py',
          'plugins/rails-flow/scripts/process_containment.py')

GUARD = Guard(
    name="hook_guard_pr_ready",
    subject="plugins/rails-flow/hooks/scripts/lib/pr_ready_guard.py",
    selftest="plugins/rails-flow/scripts/check_hook_gates.py",
    selftest_args=("--only", "guard_pr_ready"),
    narrow_with="--match",
    needs=_NEEDS,
    mutations=(
        Mutation(
            "a target it cannot tell is guessed as the session's directory (fail open)",
            "        root = git(start, \"rev-parse\", \"--show-toplevel\")\n        if root and in_force(root):\n            return refuse(f\"which repository",
            "        where = start\n        root = None\n        if root and in_force(root):\n            return refuse(f\"which repository",
            "a command whose directory cannot be told refuses, it does not guess the session's: HOME=/x gh pr ready 5",
        ),
        Mutation(
            "the allowlist accepts any word",
            "        if not seen_ready or not plain_word(w):\n",
            "        if False:\n",
            "a word that is not a plain number or branch is refused: gh pr ready 5 --rep o/r",
        ),
        Mutation(
            "a scheme-less PR URL is not an explicit target",
            '    return any("/pull/" in w for w in words)    # a PR URL, with or without a scheme\n',
            '    return any(w.startswith("http") and "/pull/" in w for w in words)\n',
            "a scheme-less PR URL is an explicit target",
        ),
        Mutation(
            "a PR argument built by the shell is judged against the local HEAD",
            "    if dynamic_target(raw):\n",
            "    if False:\n",
            "a PR argument built by the shell cannot be judged: gh pr ready $PR",
        ),
        Mutation(
            "an explicit remote target is judged against the local HEAD",
            '    if explicit_target(segment, str(payload.get("tool_input", {}).get("command", ""))):\n',
            "    if False:\n",
            "an explicit remote target is refused even with a green record: gh pr ready 5 -R o/r",
        ),
        Mutation(
            "any record in the sweep directory is accepted, whatever HEAD it names",
            '    record = d / f"{head}.json"\n',
            '    record = next(iter(sorted(d.glob("*.json"))), d / f"{head}.json")\n'
            '    head = json.loads(record.read_text()).get("head", head) if record.is_file() else head\n',
            "a green record for ANOTHER HEAD is stale and refused",
        ),
        Mutation(
            "skips are ignored",
            "    if skips != 0:\n",
            "    if False:\n",
            "a green record with skips > 0 is refused",
        ),
        Mutation(
            "a malformed record fails OPEN",
            '        return refuse(f"the sweep record {record} is unreadable or malformed ({type(exc).__name__}: {exc}).", args)\n',
            "        return 0\n",
            "a MALFORMED record fails closed",
        ),
        Mutation(
            "a red verdict is let through",
            '    if verdict != "green":\n',
            "    if False:\n",
            "a RED record is refused",
        ),
        Mutation(
            "a repository that does not run project_gates is judged anyway",
            "    if not root or not in_force(root):\n",
            "    if not root:\n",
            "NOT in force (no marker, no workflow, no record dir)",
        ),
        Mutation(
            'the refusal never names the worktree with a green record',
            '(looked for {record}).{elsewhere_hint(root, args)}"',
            '(looked for {record})."',
            'the refusal names the worktree with a green record',
        ),
        Mutation(
            'a RED record elsewhere is offered',
            'data.get("verdict") == "green" and',
            'data.get("verdict") in ("green", "red") and',
            'a RED record elsewhere is not offered',
        ),
        Mutation(
            'a record with skips elsewhere is offered',
            'and type(data.get("skips")) is int and data["skips"] == 0:',
            ':',
            'a record with a skip elsewhere is not offered',
        ),
        Mutation(
            'a record naming another head elsewhere is offered',
            'data.get("head") == head and data.get("verdict")',
            'data.get("verdict")',
            'a record naming another head elsewhere is not offered',
        ),
        Mutation(
            'a skips that is not a number elsewhere is offered',
            'type(data.get("skips")) is int and data["skips"] == 0',
            'data.get("skips") in (0, "0")',
            'a record whose skips is not a number elsewhere is not offered',
        ),
        Mutation(
            'the cd form is suggested for a path the exception cannot accept',
            'plain = CD_WORD.match(path) is not None',
            'plain = True',
            'named WITHOUT the cd form',
        ),
        Mutation(
            'the worktree list is split on newlines, so a path holding one is cut in two',
            'for field in done.stdout.split("\\0"):',
            'for field in done.stdout.replace("\\0", "\\n").split("\\n"):',
            'a worktree path holding a NEWLINE is one path',
        ),
        Mutation(
            'a path with a newline or quote is shown raw in the refusal',
            'shown = path if plain else repr(path)',
            'shown = path',
            'a worktree path holding a NEWLINE is one path, shown escaped',
        ),
        Mutation(
            'the hint reads every worktree, whatever the cap',
            'if scanned >= HINT_MAX_WORKTREES:',
            'if False:',
            'the hint reads at most RAILS_FLOW_HINT_MAX_WORKTREES worktrees',
        ),
        Mutation(
            'a hint git call may outlast what is left of the time budget',
            'timeout=max(0.05, min(GIT_TIMEOUT, left))',
            'timeout=GIT_TIMEOUT',
            'the hint has a TIME budget',
        ),
        Mutation(
            'a git that does not answer in time reads as "not a repository" again',
            'raise GitTimeout(f"`git {\' \'.join(args[:3])}` in {where} did not answer within {limit:g} s") from exc',
            'return None',
            'a git that does not answer in time is a NAMED refusal',
        ),
        Mutation(
            'the hook entry does not catch a GitTimeout',
            '    except GitTimeout as exc:\n        return refuse(f"{exc}, so whether',
            '    except ZeroDivisionError as exc:\n        return refuse(f"{exc}, so whether',
            'a git that does not answer in time is a NAMED refusal',
        ),
    ),
)
