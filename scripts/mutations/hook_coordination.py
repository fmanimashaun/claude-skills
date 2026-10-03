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
            '    record["sessions"][path] = row',
            '    record["sessions"][name or path] = row',
            "a restart with a new name rewrites the SAME row",
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
            "        print(err, file=sys.stderr)\n        return 2",
            "        print(err, file=sys.stderr)\n        return 1",
            "the CLI refuses a non-coordinator write with exit 2",
        ),
        Mutation(
            "an unreadable record exits 1 instead of 3",
            '        print(f"could not read the coordination record: {e}", file=sys.stderr)\n        return 3',
            '        print(f"could not read the coordination record: {e}", file=sys.stderr)\n        return 1',
            "the CLI exits 3 on a corrupt record",
        ),
        Mutation(
            "the CLI swaps a sibling's path and remote",
            '[{"name": n, "path": pth, "remote": r} for n, pth, r in args.sibling]',
            '[{"name": n, "path": r, "remote": pth} for n, pth, r in args.sibling]',
            "the CLI records the workspace siblings as {name, path, remote}",
        ),
        Mutation(
            "the CLI close command does nothing",
            '        err = close(record, args.session_id, os.path.abspath(args.path))\n',
            '        err = None\n',
            "the CLI closes a lane, so it leaves the session's open lanes",
        ),
    ),
)
