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
            "a status on a commit with a different tree counts",
            "        if commit_tree != tree:\n            continue\n",
            "",
            "a status on a commit with a DIFFERENT tree is ignored",
        ),
        Mutation(
            "a failing status counts",
            's.get("state") == "success"',
            's.get("state") in ("success", "failure")',
            "a failing status is no proof",
        ),
        Mutation(
            "any status context counts",
            's.get("context") == CONTEXT and ',
            "",
            "a status for another context is no proof",
        ),
        Mutation(
            "the description need not name this tree",
            ' and s.get("description") == description(tree)',
            "",
            "description names another tree",
        ),
        Mutation(
            "a failed lookup crashes instead of running the full sweep",
            "    except (RuntimeError, ValueError) as e:",
            "    except KeyError as e:",
            "verify exits 1 (not a crash) when gh fails",
        ),
        Mutation(
            "record posts from a dirty worktree",
            '    if run("git", "status", "--porcelain").strip():',
            "    if False:",
            "record refuses a dirty worktree",
        ),
    ),
)
