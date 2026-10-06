"""Mutation guard: sweep_proof. Declared here, run by scripts/mutation_check.py (#1635).

A proof that matches too loosely lets the release skip the one sweep that would have caught
the change; one that matches too strictly only costs a re-run. Every mutation loosens it.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="sweep_proof",
    subject="scripts/sweep_proof.py",
    selftest="scripts/sweep_proof.py",
    needs=(".github", "scripts"),
    mutations=(
        Mutation(
            "a same-second tie goes to the success",
            '''            if newest is None or (stamp, state != "success") > (newest[0], newest[2] != "success"):''',
            "            if newest is None or stamp > newest[0]:",
            "a same-second tie goes to the failure",
        ),
        Mutation(
            "a failed sweep posts a success",
            '''"-f", "state=failure", "-f", f"context={CONTEXT}",''',
            '''"-f", "state=success", "-f", f"context={CONTEXT}",''',
            "record_failure posts a failure",
        ),
        Mutation(
            "the wiring check stops requiring that a skipped gates needs a found proof",
            '''    if "needs.gates.result == 'skipped' && needs.proof.outputs.found == 'true'" not in release_job:''',
            "    if False:",
            "release publishes after ANY skipped gates",
        ),
        Mutation(
            "the wiring check stops requiring a fast dev push",
            '''    if "github.ref == 'refs/heads/dev'" not in gates_yml or "'--fast'" not in gates_yml:''',
            "    if False:",
            "dev push runs the full sweep",
        ),
        Mutation(
            "the wiring check stops requiring a timeout on the proof, release and gates jobs",
            '''        if "timeout-minutes:" not in text:''',
            "        if False:",
            "loses its timeout",
        ),
        Mutation(
            "a status on a commit with a different tree counts",
            "        if commit_tree != tree:\n            continue\n",
            "",
            "a status on a commit with a DIFFERENT tree is ignored",
        ),
        Mutation(
            "a failing status counts as the newest verdict's success",
            "    return newest[1] if newest and newest[2] == \"success\" else None",
            "    return newest[1] if newest else None",
            "a newer failure beats an older success",
        ),
        Mutation(
            "an old success beats a newer failure (first success wins)",
            '''            if newest is None or (stamp, state != "success") > (newest[0], newest[2] != "success"):''',
            "            if newest is None:",
            "a newer failure beats an older success",
        ),
        Mutation(
            "a failure with no timestamp is read as the oldest",
            '''            stamp = str(s.get("created_at") or ("9999" if state != "success" else ""))''',
            '''            stamp = str(s.get("created_at") or "")''',
            "a failure with no timestamp is treated as newest",
        ),
        Mutation(
            "any status context counts",
            '''            if not (s.get("context") == CONTEXT and s.get("description") == description(tree)''',
            '''            if not (s.get("description") == description(tree)''',
            "a status for another context is no proof",
        ),
        Mutation(
            "the description need not name this tree",
            '''            if not (s.get("context") == CONTEXT and s.get("description") == description(tree)''',
            '''            if not (s.get("context") == CONTEXT''',
            "description names another tree",
        ),
        Mutation(
            "any creator's status counts, so a collaborator can forge a proof",
            '''
                    and (s.get("creator") or {}).get("login") == TRUSTED_CREATOR):''',
            "):",
            "created by someone else is ignored",
        ),
        Mutation(
            "an odd lookup answer crashes instead of running the full sweep",
            "    except Exception as e:                                # any odd answer fails SAFE, and says so readably",
            "    except RuntimeError as e:",
            "",   # the selftest itself crashes on the traceback, which is a catch
        ),
        Mutation(
            "record posts from a dirty worktree",
            '''    if run("git", "status", "--porcelain").strip():
        return None''',
            "    if False:\n        return None",
            "snapshot is None on a dirty worktree",
        ),
        Mutation(
            "record posts whatever HEAD is now, not the snapshot",
            "    if now != before:",
            "    if False:",
            "record refuses a commit during the sweep",
        ),
    ),
)
