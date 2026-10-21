"""Mutation guard: prove_neutral. Declared here, run by scripts/mutation_check.py (#2205)."""
from mutation_types import Guard, Mutation  # noqa: F401

# Every mutation here lets a component that assumes Rails read as PROVEN neutral, or lets the proven count fall unseen.
GUARD = Guard(
    name="prove_neutral",
    subject="scripts/prove_neutral.py",
    selftest="scripts/prove_neutral.py",   # --selftest lives in the module itself
    needs=("scripts/component_classes.py", "scripts/rails_assumptions.py", "scripts/hermetic_git.py", "plugins/rails-flow/scripts/fixture_git.py", "plugins/rails-flow/scripts/project_gates.py", "plugins/rails-flow/checks.json"),
    mutations=(
        Mutation(
            "a reset recorded for a different floor excuses a drop",
            '    if reset.get("from") == base.get("floor") and reset.get("to") == head.get("floor", 0) and',
            '    if reset.get("from") == base.get("floor") and',
            "a reset recorded for a different floor does not excuse the drop",
        ),
        Mutation(
            "a base proof file that is not JSON raises a traceback again",
            "        except ValueError as exc:\n            return None, f\"base proof file unreadable: {exc}\"",
            "        except KeyError as exc:\n            return None, f\"base proof file unreadable: {exc}\"",
            "a base proof file that is not valid JSON is a named finding, not a traceback",
        ),
        Mutation(
            "--record keeps a stale floor_reset",
            '            data = {"floor": len(proven) if a.reset_floor else max(proof.get("floor", 0), len(proven)), "proven": proven}',
            '            data = {"floor": len(proven) if a.reset_floor else max(proof.get("floor", 0), len(proven)), "proven": proven, **({"floor_reset": proof["floor_reset"]} if "floor_reset" in proof else {})}',
            "--record that does not lower the floor clears a stale floor_reset",
        ),
        Mutation(
            "a floor lower than the base branch's passes",
            '    if base is None or head.get("floor", 0) >= base.get("floor", 0):',
            "    if True:",
            "a floor that fell with no reason is a finding",
        ),
        Mutation(
            "a reset from any floor excuses a drop",
            '    if reset.get("from") == base.get("floor") and',
            "    if True and",
            "a reset from a different floor does not excuse the drop",
        ),
        Mutation(
            "an empty reason excuses a drop",
            '    if reset.get("from") == base.get("floor") and reset.get("to") == head.get("floor", 0) and str(reset.get("reason", "")).strip():',
            '    if reset.get("from") == base.get("floor") and reset.get("to") == head.get("floor", 0):',
            "an empty reason does not excuse the drop",
        ),
        Mutation(
            "--reset-floor is accepted with --check or alone",
            '    if a.reset_floor is not None and (not a.record or a.check or not a.reset_floor.strip()):',
            "    if False:",
            "--reset-floor with --check is refused",
        ),
        Mutation(
            "--check never compares the floor with the base branch",
            "        findings += floor_drop(base, proof)",
            "        pass",
            "--check fails a floor lower than the base branch's with no reason",
        ),
        Mutation(
            "an unreadable base branch is accepted",
            "        if unreadable:",
            "        if False:",
            "--check fails when the base branch cannot be read",
        ),
        Mutation(
            "exit 1 reads as clean again",
            "    if rc == 0:\n        return \"clean\", \"\"",
            "    if rc in (0, 1):\n        return \"clean\", \"\"",
            "a script that refuses the project with exit 1 is not proven",
        ),
        Mutation(
            "a gate that is not applicable counts as proven",
            "    if result.status == pg.NA:\n        return \"notproven\"",
            "    if result.status == pg.NA:\n        return \"clean\"",
            "a gate that is not applicable on the project proves nothing",
        ),
        Mutation(
            "a timed-out recorded component counts against the floor",
            "    if proven + unverified < proof.get(\"floor\", 0):",
            "    if proven < proof.get(\"floor\", 0):",
            "a recorded component that still times out is not a finding and counts for the floor",
        ),
        Mutation(
            "a timed-out component is not retried",
            "    slow = [c for c in todo if results[c[\"path\"]][\"state\"] == \"timeout\"]",
            "    slow = []",
            "a timed-out component is retried once, alone, with a longer timeout",
        ),
        Mutation(
            "a call to a Rails stub is no longer a finding",
            '    if calls:\n        return "finding", f"called a Rails tool: {calls[0][:80]}"\n    if "Traceback',
            '    if False:\n        return "finding", f"called a Rails tool: {calls[0][:80]}"\n    if "Traceback',
            "a hook that calls `bundle exec rspec` is a finding",
        ),
        Mutation(
            "the `bundle` stub is not installed, so bundle exec runs a real bundler or fails as a missing command",
            'STUBS = ("rails", "bundle", ',
            'STUBS = ("rails", ',
            "a hook that calls `bundle exec rspec` is a finding",
        ),
        Mutation(
            "a traceback is no longer a finding",
            '    if "Traceback (most recent call last)" in out:',
            "    if False:",
            "a script that crashes with a traceback is a finding",
        ),
        Mutation(
            "a stub called before a timeout hides as not proven",
            "    if calls:\n        return \"finding\", f\"called a Rails tool before timing out",
            "    if False:\n        return \"finding\", f\"called a Rails tool before timing out",
            "a hook that calls a stub and then hangs past the timeout is a finding",
        ),
        Mutation(
            "a recorded component that now fails is accepted",
            '        elif row["state"] != "proven":',
            "        elif False:",
            "a recorded component that now fails is a finding",
        ),
        Mutation(
            "the proven count may fall below the floor",
            '    if proven + unverified < proof.get("floor", 0):',
            "    if False:",
            "a proven count below the floor is a finding",
        ),
        Mutation(
            "a recorded component that vanished is accepted",
            "        if row is None:",
            "        if False:",
            "a recorded component that vanished is a finding",
        ),
    ),
)
