"""Mutation guard: remote_evidence (#1591). Declared here, run by scripts/mutation_check.py.

`remote_evidence.py` judges another repository's release-only layers from a scratch snapshot, inside the time the release
gate has left (a hook that outlives its 15 s timeout does not deny). Its own selftest is the harness: each mutation below
breaks one guarantee and a named check in that selftest must go red.
"""
from mutation_types import Guard, Mutation  # noqa: F401

GUARD = Guard(
    name="remote_evidence",
    subject="scripts/remote_evidence.py",
    selftest="scripts/remote_evidence.py",
    needs=("scripts/fixture_git.py",),   # its selftest's git goes through fixture_git (#1588)
    selftest_args=("--selftest",),
    mutations=(
        Mutation(
            "a short commit is accepted, so an abbreviation reaches git fetch",
            'SHA = re.compile(r"^[0-9a-f]{40}$")',
            'SHA = re.compile(r"^[0-9a-f]{7,40}$")',
            "a short commit is unusable",
        ),
        Mutation(
            "an upper-case commit is accepted",
            'SHA = re.compile(r"^[0-9a-f]{40}$")',
            'SHA = re.compile(r"^[0-9a-fA-F]{40}$")',
            "an upper-case commit is unusable",
        ),
        Mutation(
            "any text is a repository, so a URL or an option reaches the remote url",
            'REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")',
            'REPO = re.compile(r"^.+$")',
            "a repository that is a URL is unusable",
        ),
        Mutation(
            "a step may start with no time left, so the hook's budget is only advice",
            "    if left <= 0:\n        raise Unusable(\"the time budget ran out before the evidence could be read\")",
            "    if False:\n        raise Unusable(\"the time budget ran out before the evidence could be read\")",
            "a step started with no time left is refused",
        ),
        Mutation(
            "the evidence judge may run past the budget, so a slow judge outlives the hook",
            "                             scratch, left)\n        except subprocess.TimeoutExpired as exc:\n            raise Unusable(\"the evidence was not judged",
            "                             scratch, 600)\n        except subprocess.TimeoutExpired as exc:\n            raise Unusable(\"the evidence was not judged",
            "a judge that outlives the budget is unusable",
        ),
        Mutation(
            "the judge's findings are not passed through: every verdict reads as clean",
            "        sys.stderr.write(done.stderr)\n        return done.returncode\n    finally:",
            "        sys.stderr.write(done.stderr)\n        return 0\n    finally:",
            "a finding is passed through as exit 1",
        ),
        Mutation(
            "the scratch repository is left behind",
            "        sys.stderr.write(done.stderr)\n        return done.returncode\n    finally:\n        shutil.rmtree(scratch, ignore_errors=True)",
            "        sys.stderr.write(done.stderr)\n        return done.returncode\n    finally:\n        pass",
            "no scratch repository is left behind",
        ),
        Mutation(
            "the recording's scratch repository is left behind",
            '        return done.returncode\n    finally:\n        shutil.rmtree(scratch, ignore_errors=True)\n\n\nclass Unusable(',
            '        return done.returncode\n    finally:\n        pass\n\n\nclass Unusable(',
            "no scratch repository is left behind",
        ),
        Mutation(
            "a timeout kills only the step's own process, so git's remote helper and a credential helper run on",
            "            os.killpg(proc.pid, signal.SIGKILL)",
            "            proc.kill()",
            "leaves no child running",
        ),
        # ---- the recorded verdict (#1686) -------------------------------------------------------------------------------
        Mutation(
            "a verdict never expires, so a stale judgement still permits a promotion",
            "    if (time.time() if now is None else now) - at > VERDICT_TTL:",
            "    if False:",
            "a verdict 31 minutes old is stale",
        ),
        Mutation(
            "the evidence tree id is not compared, so a verdict for other evidence permits",
            '    if not tree or v["tree"] != tree:',
            "    if False:",
            "a verdict for another evidence tree is a mismatch",
        ),
        Mutation(
            "the verdict's own repo and sha fields are not compared, so a copied file permits",
            '    if v["repo"] != repo or v["sha"] != sha:',
            "    if False:",
            "names another is a mismatch",
        ),
        Mutation(
            "a FAIL verdict reads as a pass",
            '    if v["verdict"] != "PASS":',
            "    if False:",
            "a FAIL is recorded as a FAIL",
        ),
        Mutation(
            "a FAIL is recorded as a PASS",
            '"verdict": "PASS" if done.returncode == EXIT_OK else "FAIL"',
            '"verdict": "PASS"',
            "a FAIL is recorded as a FAIL",
        ),
        Mutation(
            "an unusable judgement still records a verdict",
            "        if done.returncode not in (EXIT_OK, EXIT_FINDINGS):",
            "        if False:",
            "an unusable judgement records NO verdict",
        ),
        Mutation(
            "the verdict file is world-readable and writable",
            "os.O_TRUNC, 0o600)",
            "os.O_TRUNC, 0o666)",
            "owner-only",
        ),
    ),
)
