"""Mutation guard: breaker. Declared here, run by scripts/mutation_check.py (#866)."""
from mutation_types import Guard, Mutation  # noqa: F401

# #128, the pipeline half. Two of these break a fixture whose job is to stay SILENT -- a
# breaker that refuses a run which was progressing does not get tuned, it gets bypassed, and
# then nothing is bounded at all. The last one breaks neither: it drifts the CODE away from the
# shipped DOCTRINE, which only the real-file checks can see.
GUARD = Guard(
    name="breaker",
    subject="scripts/breaker.py",
    selftest="scripts/breaker_selftest.py",
    # Read, not imported. The selftest's last checks run against the SHIPPED doctrine and the
    # SHIPPED surfaces, and FAIL rather than skip when absent -- so the mutant needs them, or
    # every mutation reports as "caught by the wrong fixture" and the real signal is buried.
    needs=(
        "reference/stop-conditions.md",
        "commands/ack.md",
        "commands/deploy-cloud.md",
        "commands/install-hooks.md",
        "commands/pipeline.md",
        "commands/release.md",
        "commands/setup-cloud.md",
        "commands/setup-pipeline.md",
        "commands/status.md",
        "agents/kamal-configurator.md",
        "agents/pipeline-coordinator.md",
    ),
    mutations=(
        Mutation(
            "the attempt cap stops firing",
            "    if len(failures) >= cap:",
            "    if False:",
            "three failures against a cap of three",
        ),
        Mutation(
            "the no-progress detector stops firing",
            "        if len(set(recent)) == 1:",
            "        if False:",
            "two identical failure signatures",
        ),
        Mutation(
            "the signature normaliser strips digits, so a converging run reads as stuck",
            '    return _WS.sub(" ", text).strip().lower()',
            '    return _WS.sub(" ", re.sub(r"\\d+", "", text)).strip().lower()',
            "a changing failure count is progress, not a stall",
        ),
        Mutation(
            "the ordering rule stops firing, and gate-skipping returns",
            "        if not _passed(records, earlier):",
            "        if False:",
            "release reached before certify passed",
        ),
        Mutation(
            "the budget breaker stops firing",
            "    if spent >= budget:",
            "    if False:",
            "the wall-clock budget is spent",
        ),
        Mutation(
            "a passed stage may be re-attempted",
            '    if _passed(records, stage):\n        return "already-passed", (',
            '    if False:\n        return "already-passed", (',
            "a passed stage is not re-attempted",
        ),
        Mutation(
            "an override outside its bounds is accepted, so a cap becomes unbounded",
            "        if not low <= value <= high:",
            "        if False:",
            "an attempt cap of 99",
        ),
        Mutation(
            "a failure is recorded with no signature, making no-progress unfalsifiable",
            '    if args.outcome == "fail" and not (args.signature or "").strip():',
            "    if False:",
            "a fail recorded with no signature",
        ),
        Mutation(
            "`report` exits 0 on a partial run -- partial presented as complete",
            '    if state == "complete":\n        return 0',
            "    if True:\n        return 0",
            "reporting an unfinished run",
        ),
        Mutation(
            "exceeding the cap stops spoiling the verdict, so the breaker becomes advisory",
            '        if len(failures) > limits["attempts"]:',
            "        if False:",
            "a cap exceeded then passed is still stopped",
        ),
        Mutation(
            "a second `start` silently resets every attempt counter",
            '            if state != "complete":',
            "            if False:",
            "restarting over an unfinished run",
        ),
        Mutation(
            "an undiagnosed stop stops being named in the report",
            '        if not str(stop.get("diagnosis", "")).strip():',
            "        if False:",
            "a stop with no diagnosis is named in the report",
        ),
        Mutation(
            "a missing `started` disables the budget rule instead of being unusable",
            '        raise Unusable(\n            "the `run` record carries no `started` '
            "timestamp, so the budget cannot be measured. \"\n            \"That is unusable "
            'input, not an unlimited budget."\n        )',
            "        return float(0)",
            "a run record with no started timestamp",
        ),
        Mutation(
            "the bound widens in the code while the doctrine still states the old one",
            '    "attempts": (1, 10),',
            '    "attempts": (1, 99),',
            "allowed range 1..99",
        ),
    ),
)
