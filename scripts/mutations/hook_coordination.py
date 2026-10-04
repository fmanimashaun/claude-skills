"""Mutation guard: hook_coordination. Declared here, run by scripts/mutation_check.py (#1581).

The record is the thing a fail-closed worktree guard trusts, so the mutations that matter are the ones
that let a non-coordinator write, lose a field another feature added, read a corrupt file as an empty
one, or let two worktrees of one clone see different records.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="hook_coordination",
    subject="plugins/rails-flow/hooks/scripts/lib/coordination.py",
    selftest="plugins/rails-flow/hooks/scripts/lib/coordination.py",
    mutations=(
        Mutation(
            "the coordinator check passes every caller, so a non-coordinator writes",
            '    if coord.get("session_id") == caller:\n        return None\n    holder',
            '    if True:\n        return None\n    holder',
            "a NON-coordinator write is refused and names the holder",
        ),
        Mutation(
            "an assign with no coordinator recorded is allowed without a claim",
            "return None if claiming else (",
            "return None if True else (",
            "assign with no coordinator recorded is refused",
        ),
        Mutation(
            "a second claim skips the holder check and takes the role",
            "claiming=True)\n    if err:\n        return err\n    coord",
            "claiming=True)\n    coord",
            "a second claim while a coordinator is recorded is refused",
        ),
        Mutation(
            "a write drops every top-level key it does not know (the workspace block)",
            '    data.setdefault("sessions", {})\n    return data',
            '    data.setdefault("sessions", {})\n    return {k: data[k] for k in ("version", "coordinator", "sessions")}',
            "unknown top-level keys survive a write",
        ),
        Mutation(
            "an assign replaces the whole row, dropping fields another feature added",
            '    row = row if isinstance(row, dict) else {}\n    row.update({"session_id": owner or caller',
            '    row = {}\n    row.update({"session_id": owner or caller',
            "unknown row fields survive a write",
        ),
        Mutation(
            "a corrupt record reads as an empty one",
            '        raise RecordError(f"{path}: {e}") from e',
            '        return {"version": VERSION, "coordinator": None, "sessions": {}}',
            "a corrupt record is an ERROR, not an empty record",
        ),
        Mutation(
            "a closed lane still counts as an open lane",
            'and r.get("state") != "closed"]',
            ']',
            "closing a lane removes it from the session's open lanes",
        ),
        Mutation(
            "lanes_for returns every session's lanes",
            'if isinstance(r, dict) and r.get("session_id") == session_id',
            'if isinstance(r, dict) and True',
            "a session sees only ITS open lanes",
        ),
        Mutation(
            "a row is keyed by the session's name, so a rename adds a second row",
            '        row["name"] = name       # an attribute: a renamed session updates ITS row, never adds a second\n    record["sessions"][path] = row',
            '        row["name"] = name       # an attribute: a renamed session updates ITS row, never adds a second\n    record["sessions"][name or path] = row',
            "a restart with a new name rewrites the SAME row",
        ),
        Mutation(
            "a check-in looks its row up by the session's name, so a renamed session starts a fresh row",
            '    row = record["sessions"].get(path)\n    row = row if isinstance(row, dict) else {"state": "waiting"}',
            '    row = record["sessions"].get(name)\n    row = row if isinstance(row, dict) else {"state": "waiting"}',
            "a check-in keeps what the lane already says",
        ),
        Mutation(
            "the record is read from --git-dir, so a linked worktree sees a different file",
            '["git", "rev-parse", "--git-common-dir"]',
            '["git", "rev-parse", "--git-dir"]',
            "a linked worktree resolves the SAME record file",
        ),
        Mutation(
            "the workspace block can be set by a non-coordinator",
            "    err = _refuse_unless_coordinator(record, caller, claiming=False)\n    if err:\n        return err\n    block =",
            "    block =",
            "a non-coordinator cannot set the workspace block",
        ),
        Mutation(
            "a workspace write drops the block's other keys",
            "    block = block if isinstance(block, dict) else {}\n    block[\"coordinator\"]",
            "    block = {}\n    block[\"coordinator\"]",
            "a workspace write keeps its other keys",
        ),
        Mutation(
            "a non-coordinator can close a lane",
            "    err = _refuse_unless_coordinator(record, caller, claiming=False)\n    if err:\n        return err\n    row = record[\"sessions\"].get(path)\n    if not isinstance(row, dict):\n        return f\"refused: no lane",
            "    row = record[\"sessions\"].get(path)\n    if not isinstance(row, dict):\n        return f\"refused: no lane",
            "a non-coordinator cannot close a lane",
        ),
        Mutation(
            "a refused write exits 1 instead of 2",
            "                print(err, file=sys.stderr)\n                return 2",
            "                print(err, file=sys.stderr)\n                return 1",
            "the CLI refuses a non-coordinator write with exit 2",
        ),
        Mutation(
            "an unreadable record exits 1 instead of 3",
            '            print(f"could not read the coordination record: {e}", file=sys.stderr)\n            return 3',
            '            print(f"could not read the coordination record: {e}", file=sys.stderr)\n            return 1',
            "the CLI exits 3 on a corrupt record",
        ),
        Mutation(
            "a write path exits 1 on an unreadable record",
            '                print(f"could not read the coordination record: {e}", file=sys.stderr)\n                return 3',
            '                print(f"could not read the coordination record: {e}", file=sys.stderr)\n                return 1',
            "a malformed record",
        ),
        Mutation(
            "the CLI swaps a sibling's path and remote",
            '[{"name": n, "path": pth, "remote": r} for n, pth, r in args.sibling]',
            '[{"name": n, "path": r, "remote": pth} for n, pth, r in args.sibling]',
            "the CLI records the workspace siblings as {name, path, remote}",
        ),
        Mutation(
            "the CLI close command does nothing",
            '                err = close(record, args.session_id, os.path.realpath(args.path))\n',
            '                err = None\n',
            "the CLI closes a lane, so it leaves the session's open lanes",
        ),
        Mutation(
            "the lock is never taken, so parallel commands race their read-modify-write",
            "                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)\n                break",
            "                break",
            "six parallel claims on an empty record: exactly one wins",
        ),
        Mutation(
            "a command that cannot get the lock proceeds without it",
            '                    raise LockError(f"{lock}: could not lock within {LOCK_TIMEOUT:g}s")',
            "                    break",
            "a command that cannot get the lock exits 3",
        ),
        Mutation(
            "a coordinator that is not an object is accepted, so the next command crashes",
            '\n            or not (data.get("coordinator") is None or isinstance(data["coordinator"], dict))):',
            "):",
            "a malformed record",
        ),
        Mutation(
            "a symlinked worktree path keeps its own row (abspath, not realpath)",
            "                err = assign(record, args.session_id, os.path.realpath(args.path),",
            "                err = assign(record, args.session_id, os.path.abspath(args.path),",
            "a symlinked worktree path and its target are ONE row",
        ),
        Mutation(
            "the lock file is created world-readable again (CodeQL py/overly-permissive-file)",
            "os.O_CREAT | os.O_RDWR, 0o600)",
            "os.O_CREAT | os.O_RDWR, 0o644)",
            "the lock file is created owner-only",
        ),
        Mutation(
            "a junk tuning value raises instead of being ignored",
            "    except ValueError:\n        return default",
            "    except ValueError:\n        raise",
            "a junk COORDINATION_LOCK_TIMEOUT is ignored",
        ),
        Mutation(
            "a coordinator object that names nobody makes the record unclaimable",
            '    if not coord or not coord.get("session_id"):      # none recorded, or an object that names nobody',
            "    if coord is None:",
            "a coordinator object with no session_id counts as no coordinator",
        ),
        Mutation(
            'a check-in is accepted from any caller',
            '    err = _refuse_unless_coordinator(record, caller, claiming=False)\n    if err:\n        return err\n    if not name.strip() or not owner.strip():',
            '    if not name.strip() or not owner.strip():',
            'a non-coordinator check-in is refused',
        ),
        Mutation(
            'a check-in replaces the whole row, dropping the branch and pull request',
            '    row = row if isinstance(row, dict) else {"state": "waiting"}',
            '    row = {"state": "waiting"}',
            'a check-in keeps what the lane already says',
        ),
        Mutation(
            'a check-in with no name is recorded',
            '    if not name.strip() or not owner.strip():',
            '    if False:',
            'a check-in with no name is refused',
        ),
        Mutation(
            'assign never records the pull request',
            '    if pr is not None:\n        row["pr"] = pr',
            '    if False:\n        row["pr"] = pr',
            'assign records the pull request',
        ),
        Mutation(
            'an ask is accepted from any caller',
            '    if err:\n        return None, err\n    if not title.strip():',
            '    if False:\n        return None, err\n    if not title.strip():',
            'a non-coordinator ask is refused',
        ),
        Mutation(
            'an ask with no title is recorded',
            '    if not title.strip():\n        return None,',
            '    if False:\n        return None,',
            'an ask with no title is refused',
        ),
        Mutation(
            'an ask changes state for any caller',
            '    err = _refuse_unless_coordinator(record, caller, claiming=False)\n    if err:\n        return err\n    row = next(',
            '    row = next(',
            'a non-coordinator cannot change an ask',
        ),
        Mutation(
            'an ask can jump to any state, so a draft reads as answered and an answer is re-opened',
            '    if order.get(state, -1) != order.get(row.get("state"), -2) + 1:',
            '    if False:',
            'an ask cannot be answered before it was asked',
        ),
        Mutation(
            'an event is accepted from any caller',
            '    err = _refuse_unless_coordinator(record, caller, claiming=False)\n    if err:\n        return err\n    if not text.strip():',
            '    if not text.strip():',
            'a non-coordinator event is refused',
        ),
        Mutation(
            'events grow without a bound',
            '    del record["events"][:-EVENT_CAP]',
            '    pass',
            'events are capped at EVENT_CAP',
        ),
    ),
)
