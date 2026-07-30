#!/usr/bin/env python3
"""Prove every selftest CAN fail — by breaking its subject and requiring it to notice.

Run:  python3 scripts/mutation_check.py            # all guards
      python3 scripts/mutation_check.py --guard lint_self_consistency
      python3 scripts/mutation_check.py --selftest  # prove this checker itself can fail

WHY THIS EXISTS (#233). The repo has six selftests and fourteen gates, and until now **nothing
checked that a selftest fails when the thing it guards breaks**. Two fixtures written in one
session were vacuous and passed for the wrong reason:

  * a `hasattr` on a function that never existed, so it compared `[] == []`
  * a cross-contamination scenario whose two classes shared one fenced block, leaving the second
    unregistered — the scenario never ran

Both looked right. One survived until a maintainer asked whether the fix was real. CLAUDE.md
already says to make every new check fail on purpose once; the failure mode is not ignorance of
that rule, it is skipping it under momentum. So it becomes a gate.

WHAT IT IS NOT. Not a general mutation framework — no AST rewriting, no operator taxonomy, no
survivor analysis. Each guard declares a short list of **named, hand-chosen mutations** to its own
subject, each with the fixture it is expected to trip. A declared list is auditable and cheap; a
generated one produces survivors nobody triages, and an untriaged mutation report is
indistinguishable from a passing one.

HOW A MUTATION IS APPLIED. The subject is copied to a temp directory with one exact string
replaced, its selftest is copied beside it, and the selftest runs against the mutant. Nothing in
the working tree is touched — earlier hand-runs of this edited real files and relied on a `finally`
to restore them, which is one interrupted process away from leaving a mutated repo.

THE ASSERTION THAT MATTERS. A mutation must be *verified applied* before its result counts. An
anchor that no longer matches produces a mutant identical to the original, the selftest passes, and
that reads exactly like a caught mutation. So a stale anchor is a hard error, never a pass.

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Mutation:
    """One hand-chosen break, and the fixture that must notice it."""

    name: str
    old: str
    new: str
    # Substring expected in the selftest's failure output. Proves the RIGHT fixture tripped, not
    # merely that something did -- a mutation caught by an unrelated assertion is a coincidence,
    # and would mask the guard it was written for going quiet.
    #
    # Use the FIXTURE'S LABEL, not the finding's message text. Most mutations here make a finding
    # DISAPPEAR, so its message is absent from the output by definition -- expecting it fails for
    # the wrong reason. (Learned on this checker's first run: three of sixteen expectations were
    # written as finding text and reported spurious "wrong fixture" results.) Empty string means
    # any failure counts, for mutations that break the module hard enough to raise.
    expects: str


@dataclass(frozen=True)
class Guard:
    name: str
    subject: str          # the module whose behaviour is guarded
    selftest: str         # the script that must notice a break
    # Extra modules the selftest imports; copied alongside so the mutant is self-contained.
    deps: tuple[str, ...] = ()
    # Repo files the selftest READS (not imports). Copied at their repo-relative path, because
    # a selftest resolving `Path(__file__).parents[1] / ".gitignore"` must still find it. Found
    # when maintainer_doctor's mutant died on a missing .gitignore -- an environmental failure the
    # `expects` check correctly refused to count as a caught mutation.
    needs: tuple[str, ...] = ()
    mutations: tuple[Mutation, ...] = field(default_factory=tuple)


GUARDS: tuple[Guard, ...] = (
    Guard(
        name="lint_self_consistency",
        subject="scripts/lint_self_consistency.py",
        selftest="scripts/lint_self_consistency.py",   # --selftest lives in the module itself
        mutations=(
            Mutation(
                "render rules require a paren again (the #142 blind spot)",
                r'_RENDER_CALL = re.compile(r"render\(?\s*',
                r'_RENDER_CALL = re.compile(r"render\(\s*',
                "paren-less render",
            ),
            Mutation(
                "slot window scans to end-of-document (the false-positive generator)",
                "stop = blocks[position + 1].start() if position + 1 < len(blocks) else len(body)",
                "stop = len(body)",
                "bleed into each other",
            ),
            Mutation(
                "corpora no longer pruned from the walk",
                ', "design-corpora"}',
                "}",
                "not ours to enforce",
            ),
            Mutation(
                "unbounded gh queries stop being flagged",
                "if not _GH_LIST.search(line) or not _INVOCATION.search(line):",
                "if True:",
                "unbounded",
            ),
            Mutation(
                "the renders_many singular setter is flagged as a mismatch again",
                'if used in declared or f"{used}s" in declared:',
                "if used in declared:",
                "singular setter is correct",
            ),
            Mutation(
                "a declared plugin missing from the docs stops being flagged",
                "if name in blob:\n                continue",
                "if True:\n                continue",
                "undocumented-plugin",
            ),
        ),
    ),
    Guard(
        name="build_coverage",
        subject="scripts/build_coverage.py",
        selftest="scripts/build_coverage_selftest.py",
        mutations=(
            Mutation(
                "the totality guard stops naming unclassified corpus entries",
                "def verify_totality(",
                "def _disabled_verify_totality(",
                "",   # any failure counts: removing the entry point breaks many fixtures
            ),
        ),
    ),
    Guard(
        name="validate_evidence",
        subject="plugins/qa-flow/scripts/validate_evidence.py",
        selftest="plugins/qa-flow/scripts/validate_evidence_selftest.py",
        mutations=(
            Mutation(
                "a Pass on a non-2xx/3xx page is accepted (the #106 defect)",
                "elif not _http_ok(row[\"HTTP\"]):",
                "elif False:",
                "not the page under test",
            ),
            Mutation(
                "duplicate finding signatures stop being rejected (#118's dedupe)",
                "        if sig in seen:",
                "        if False:",
                "repeated signature",
            ),
            Mutation(
                "runtime severity is trusted instead of recomputed",
                "    elif required == S1 and severity != S1:",
                "    elif False:",
                "downgraded to S2",
            ),
        ),
    ),
    Guard(
        name="route_coverage",
        subject="plugins/qa-flow/scripts/route_coverage.py",
        selftest="plugins/qa-flow/scripts/route_coverage_selftest.py",
        deps=("plugins/qa-flow/scripts/validate_evidence.py",),
        mutations=(
            Mutation(
                ":id matches greedily, over-crediting coverage",
                'out.append(r"[^/]+")',
                'out.append(r".+")',
                "swallow a deeper path",
            ),
            Mutation(
                "a findings rollup is credited as real visits",
                "columns = ROUTE_SOURCES.get(profile.name)",
                'columns = ROUTE_SOURCES.get(profile.name) or ("Example Routes",)',
                "contributes no coverage",
            ),
        ),
    ),
    Guard(
        name="evidence_manifest",
        subject="plugins/qa-flow/scripts/evidence_manifest.py",
        selftest="plugins/qa-flow/scripts/evidence_manifest_selftest.py",
        mutations=(
            Mutation(
                "a truncated final line crashes the parse (#111's own defect)",
                "        except json.JSONDecodeError:\n            truncated += 1\n            continue",
                "        except json.JSONDecodeError:\n            raise",
                "",   # the killed-run fixtures raise Unusable; any failure counts
            ),
            Mutation(
                "unreached units stop being distinguished from a complete run",
                '        "unreached": unreached,\n        "aborted": bool(unreached) or truncated > 0,',
                '        "unreached": [],\n        "aborted": False,',
                "unreached",
            ),
            Mutation(
                "full-page evidence accepted for a component purpose",
                'elif purpose in CLIPPED_PURPOSES and capture != "clipped":',
                "elif False:",
                "full-page",
            ),
        ),
    ),
    Guard(
        name="maintainer_doctor",
        subject="scripts/maintainer_doctor.py",
        selftest="scripts/maintainer_doctor_selftest.py",
        needs=(".gitignore",),
        mutations=(
            Mutation(
                "an unignored corpora path stops being reported",
                "                if not verdict:",
                "                if False:",
                "slashed ignore",
            ),
            Mutation(
                "a SKIP is allowed to render as a PASS",
                'if not missing:\n            self.add(PASS, "design corpora present"',
                'if True:\n            self.add(PASS, "design corpora present"',
                "corpora",
            ),
        ),
    ),
)


def apply_mutation(guard: Guard, mutation: Mutation, workdir: Path) -> Path:
    """Copy subject + selftest + deps into `workdir`, with the mutation applied.

    Raises if the anchor is absent or non-unique: a mutation that did not apply produces a mutant
    identical to the original, which passes and reads exactly like a caught mutation.
    """
    subject = REPO / guard.subject
    source = subject.read_text(encoding="utf-8")
    hits = source.count(mutation.old)
    if hits != 1:
        raise RuntimeError(
            f"{guard.name} / {mutation.name}: anchor matches {hits} time(s), need exactly 1 — "
            "the mutation list has drifted from the code it mutates"
        )
    mutated = source.replace(mutation.old, mutation.new)
    if mutated == source:
        raise RuntimeError(f"{guard.name} / {mutation.name}: replacement changed nothing")

    # Mirror the repo layout rather than flattening, so `parents[1]`-relative reads still work.
    for relative in {guard.subject, guard.selftest, *guard.deps}:
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text((REPO / relative).read_text(encoding="utf-8"), encoding="utf-8")
    for relative in guard.needs:
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(REPO / relative, target)
    (workdir / guard.subject).write_text(mutated, encoding="utf-8")
    return workdir / guard.selftest


def run_guard(guard: Guard) -> list[str]:
    """Failures for one guard. Empty list = every mutation was caught by the right fixture."""
    problems: list[str] = []
    for mutation in guard.mutations:
        workdir = Path(tempfile.mkdtemp(prefix=f"mutcheck-{guard.name}-"))
        try:
            entry = apply_mutation(guard, mutation, workdir)
            argv = [sys.executable, str(entry)]
            if guard.selftest == guard.subject:
                argv.append("--selftest")   # the selftest is a flag on the module itself
            result = subprocess.run(argv, cwd=workdir, capture_output=True, text=True, timeout=300)
            output = result.stdout + result.stderr

            if result.returncode == 0:
                problems.append(
                    f"{guard.name}: SURVIVED — {mutation.name}. The selftest passed with this "
                    "broken, so nothing guards it."
                )
                continue
            if mutation.expects and mutation.expects.lower() not in output.lower():
                problems.append(
                    f"{guard.name}: caught {mutation.name!r} but not by the expected fixture "
                    f"(no mention of {mutation.expects!r}) — a coincidental catch would hide that "
                    "fixture going quiet"
                )
        except subprocess.TimeoutExpired:
            problems.append(f"{guard.name}: {mutation.name} timed out")
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prove each selftest fails when the thing it guards breaks."
    )
    parser.add_argument("--guard", help="run one guard by name")
    parser.add_argument("--selftest", action="store_true",
                        help="prove this checker itself detects a survivor and a stale anchor")
    args = parser.parse_args(argv)

    if args.selftest:
        import mutation_check_selftest as st

        return st.run()

    guards = [g for g in GUARDS if not args.guard or g.name == args.guard]
    if args.guard and not guards:
        print(f"no guard named {args.guard!r}; known: {[g.name for g in GUARDS]}", file=sys.stderr)
        return 2

    problems: list[str] = []
    total = 0
    for guard in guards:
        total += len(guard.mutations)
        found = run_guard(guard)
        status = "ok" if not found else "FAIL"
        print(f"  [{status:4}] {guard.name}: {len(guard.mutations)} mutation(s)")
        problems.extend(found)

    if problems:
        print(f"\nMUTATION CHECK FAILED — {len(problems)} of {total}:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"\nmutation check: {total} mutation(s) across {len(guards)} guard(s), all caught")
    return 0


if __name__ == "__main__":
    sys.exit(main())
