#!/usr/bin/env python3
"""The deterministic floor of the /gauntlet agents (#1563; B2 and B3 of the #1578 review).

Run:  python3 scripts/gauntlet_core.py guards [--base origin/dev]     # mutation-verifier, steps 1 and 2
      python3 scripts/gauntlet_core.py battery [--hook PATH]          # shell-adversary, the catalogue inputs
      python3 scripts/gauntlet_core.py --selftest

WHY THIS EXISTS. The two agents are prompts run by a model. A model's behaviour cannot be checked here: a live
run costs money and the repository's own benchmark rule is that one never gates a release (evals/README.md).
What CAN be checked is the part of each agent that is not judgement, once it is a script the agent is told to
run: which changed scripts have no guard, and whether the hostile inputs reviewers blocked on still get through
a hook. The selftest drives both on a known-bad and a known-good fixture diff, so each returns BLOCKED on one
and CLEAN on the other, and it fails when an agent's instructions stop naming the command (a reverted prompt).

WHAT THIS DOES NOT PROVE. That a model follows the instructions, or finds the defect that is not in the
battery. `docs/evidence/reviews/gauntlet-replay.md` is the record of the one model-run replay (2 of 3).

THE GUARD LOOKUP USES THE HARNESS'S OWN REGISTRY (`mutation_check.GUARDS`), not a file name and not a text search
of the guard files. A guard's name is not its script's name (`guard-bash.sh` is `hook_guard_bash`), and a regex
over the guard files finds 141 of 169 subjects because the quoting differs (review of #1578, B2).

Stdlib only. Exit 0 CLEAN, 1 BLOCKED, 2 could not run (nothing was examined, which is not CLEAN).
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

HOOK = "plugins/rails-flow/hooks/scripts/guard-bash.sh"
AGENTS = {
    "mutation-verifier": ".claude/agents/mutation-verifier.md",
    "shell-adversary": ".claude/agents/shell-adversary.md",
}
# The command each agent must be told to run. An agent whose instructions stop naming it has been reverted to
# prose a model can misread (the unguarded-hook-script false BLOCKED of review B2 came from exactly that).
AGENT_COMMANDS = {
    "mutation-verifier": "python3 scripts/gauntlet_core.py guards",
    "shell-adversary": "python3 scripts/gauntlet_core.py battery",
}
# EACH AGENT'S MODEL, PINNED (#1702). The owner's rule of 2026-10-08: Fable is the model for ADVERSARIAL ATTACK passes, the
# ones that try to break a change. `shell-adversary` is one; `mutation-verifier` is mechanical (it applies the declared
# mutants through the harness) and stays on `haiku`, `model-tiers.md`'s mechanical tier. `fable` is a documented subagent
# `model:` alias (https://code.claude.com/docs/en/sub-agents, "Choose a model": `sonnet`, `opus`, `haiku`, or `fable`). The
# selftest reads each agent's frontmatter, so a pin that drifts either way is red.
AGENT_MODELS = {
    "mutation-verifier": "haiku",
    "shell-adversary": "fable",
}
ADVERSARY_MODEL = AGENT_MODELS["shell-adversary"]

# What counts as a changed script that needs a guard (mutation-verifier step 1). A guard file is the check itself and
# is not guarded by another one; a changed SELFTEST is a changed check, so it reaches the guard of the script it tests.
SCRIPT_GLOBS = ("scripts/*.py", "plugins/*/scripts/*.py", "plugins/*/hooks/scripts/*.sh", "plugins/*/hooks/scripts/lib/*.sh")
NOT_A_SUBJECT = ("*/mutations/*", "*/__pycache__/*")

# One row per class a reviewer blocked on, as the real PreToolUse payload: (label, command, must the hook refuse).
# Every refusal here was measured on the real hook before it was written down; the legitimate commands are the
# positive controls, so a hook that refuses everything cannot pass.
BATTERY: tuple[tuple[str, str, bool], ...] = (
    ("control: the plain command", "git add -A", True),
    ("dequoting the raw-text pre-check does not see (#1498)", "e'v'al \"git add -A\"", True),
    ("a batch separator inside quotes (#1519)", "bash -c 'x\n\x02\ny'; bash -c 'git add -A'", True),
    ("an env prefix before the verb", "FOO=1 git add -A", True),
    ("a global option before the verb", "git -C . add -A", True),
    ("a ) inside a heredoc inside $( )", "echo $(cat <<'EOF'\n)\nEOF\n); git add -A", True),
    ("&> folded into >", "git add -A &> /dev/null", True),
    ("legitimate: a different git command", "git status", False),
    ("legitimate: the rule quoted in a grep (#906)", "grep -c \"git add -A\" GUARDRAILS.md", False),
    ("legitimate: the rule quoted in an echo (#906)", "echo \"never git add -A\"", False),
)


# --- mutation-verifier: steps 1 and 2 ---------------------------------------------------------------

def is_script(path: str) -> bool:
    return any(fnmatch.fnmatch(path, g) for g in SCRIPT_GLOBS) and not any(fnmatch.fnmatch(path, n) for n in NOT_A_SUBJECT)


def changed_scripts(paths: list[str]) -> list[str]:
    return sorted({p for p in paths if is_script(p)})


def guards_for(changed: list[str], guards: list[tuple[str, str, str]]) -> tuple[dict[str, str], list[str]]:
    """Map each changed script to its guard name, and list the ones with none. `guards` is (name, subject, selftest):
    a script is covered as the subject of a guard, or as the selftest that guard runs."""
    by_path: dict[str, str] = {}
    for name, subject, selftest in guards:
        by_path.setdefault(subject, name)
        by_path.setdefault(selftest, name)
    found = {p: by_path[p] for p in changed if p in by_path}
    return found, [p for p in changed if p not in by_path]


def guards_verdict(paths: list[str], guards: list[tuple[str, str, str]]) -> tuple[int, list[str]]:
    """(exit code, output lines). Nothing to examine is exit 2, never CLEAN: a gauntlet with nothing to attack is a
    pass nobody earned."""
    changed = changed_scripts(paths)
    if not changed:
        return 2, ["NOTHING TO ATTACK  0 scripts changed (scripts/*.py, plugins/*/scripts/*.py, hook scripts)"]
    found, missing = guards_for(changed, guards)
    run = sorted(set(found.values()))
    lines = [f"{'BLOCKED' if missing else 'CLEAN'}  {len(missing)} finding(s), {len(run)} guard(s) to run"]
    for n, path in enumerate(missing, 1):
        lines.append(f"  {n}. {path}: no guard declares this script as its subject or selftest")
    lines += [f"  run: python3 scripts/mutation_check.py --guard {name} --jobs 2" for name in run]
    return (1 if missing else 0), lines


def registry() -> list[tuple[str, str, str]]:
    import mutation_check as mc

    return [(g.name, g.subject, g.selftest) for g in mc.GUARDS]


# --- shell-adversary: the catalogue inputs ----------------------------------------------------------

def run_hook(hook: Path, command: str) -> int:
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}).encode()
    return subprocess.run(["bash", str(hook)], input=payload, capture_output=True, timeout=60).returncode


def battery_verdict(hook: Path) -> tuple[int, list[str]]:
    """Feed every battery row to `hook`. A refusal is exit 2. BLOCKED lists each input the hook got wrong."""
    if not hook.is_file():
        return 2, [f"COULD NOT RUN  {hook} does not exist"]
    wrong = []
    for label, command, must_refuse in BATTERY:
        got = run_hook(hook, command)
        if (got == 2) != must_refuse:
            wrong.append(f"{label}: {command!r} -> exit {got} (want {2 if must_refuse else 0})")
    lines = [f"{'BLOCKED' if wrong else 'CLEAN'}  {len(wrong)} finding(s), {len(BATTERY)} inputs run"]
    lines += [f"  {n}. {w}" for n, w in enumerate(wrong, 1)]
    return (1 if wrong else 0), lines


def frontmatter_model(text: str) -> str | None:
    """The `model:` value of an agent file's YAML frontmatter (the block between the first two `---` lines), or None."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for line in lines[1:]:
        if line.strip() == "---":
            return None
        if line.startswith("model:"):
            return line.split(":", 1)[1].strip().strip("\"'") or None
    return None


def prompt_names_command(agent: str, text: str) -> bool:
    """True when the agent's instructions still tell it to run its command."""
    return AGENT_COMMANDS[agent] in text


# --- selftest ---------------------------------------------------------------------------------------

# The hook's guard declares a selftest that is NOT the hook itself, as the real ones do: a lookup that read only the
# selftest would find nothing for the hook script.
FIXTURE_GUARDS = [("hook_guard", "plugins/p/hooks/scripts/guard.sh", "plugins/p/scripts/guard_selftest.py"),
                  ("tool", "scripts/tool.py", "scripts/tool_selftest.py")]

# Three hook fixtures that read the same payload. GOOD strips quoting before it looks for the verb; BAD checks the
# raw text for a command that STARTS with it (the shape of a pre-check that runs before dequoting); EVERYTHING
# refuses all, which the legitimate rows must catch.
_READ = 'cmd="$(python3 -c \'import json,sys;print(json.load(sys.stdin)["tool_input"]["command"])\')"\n'
HOOK_FIXTURES = {
    "good": _READ + 'flat="$(printf "%s" "$cmd" | tr -d "\'\\"\\n")"\n'
                    'case "$cmd" in grep\\ *|echo\\ \\"*) exit 0;; esac\n'
                    'case "$flat" in *"git add -A"*|*"git -C . add -A"*) exit 2;; esac\nexit 0\n',
    "bad": _READ + 'case "$cmd" in "git add -A"*) exit 2;; esac\nexit 0\n',
    "everything": "exit 2\n",
}


def selftest() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label}{': ' + detail if detail else ''}")

    # mutation-verifier, steps 1 and 2: the known-bad diff and the known-good diff.
    bad_diff = ["plugins/p/hooks/scripts/guard.sh", "scripts/brand_new.py", "docs/readme.md"]
    good_diff = ["plugins/p/hooks/scripts/guard.sh", "scripts/tool_selftest.py", "docs/readme.md"]
    code, out = guards_verdict(bad_diff, FIXTURE_GUARDS)
    check("a changed script with no guard BLOCKS",
          code == 1 and out[0].startswith("BLOCKED") and "scripts/brand_new.py" in "\n".join(out), str(out))
    check("...naming ONLY the unguarded script", not any("guard.sh: no guard" in x for x in out), str(out))
    code, out = guards_verdict(good_diff, FIXTURE_GUARDS)
    check("a diff whose scripts all have a guard is CLEAN", code == 0 and out[0].startswith("CLEAN"), str(out))
    check("...and lists the guard to run, by the guard's NAME (not the script's)",
          "--guard hook_guard " in "\n".join(out) and "--guard tool " in "\n".join(out), str(out))
    check("B2: a hook script found by its declared subject, whatever the guard is called",
          guards_for(["plugins/p/hooks/scripts/guard.sh"], FIXTURE_GUARDS)[0] == {"plugins/p/hooks/scripts/guard.sh": "hook_guard"})
    check("a selftest file's change reaches its subject's guard", guards_for(["scripts/tool_selftest.py"], FIXTURE_GUARDS)[1] == [])
    check("nothing to attack is exit 2, never CLEAN", guards_verdict(["docs/a.md", "scripts/mutations/x.py"], FIXTURE_GUARDS)[0] == 2)
    check("a guard file is not itself a script that needs a guard", changed_scripts(["scripts/mutations/x.py"]) == [])

    # shell-adversary, the catalogue inputs: bad hook BLOCKS, good hook CLEAN, refuse-everything BLOCKS.
    with tempfile.TemporaryDirectory() as tmp:
        hooks = {}
        for name, body in HOOK_FIXTURES.items():
            hooks[name] = Path(tmp) / f"{name}.sh"
            hooks[name].write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8")
        code, out = battery_verdict(hooks["bad"])
        check("a hook that checks raw text before dequoting BLOCKS on the dequoting row",
              code == 1 and any("dequoting" in x for x in out), str(out))
        code, out = battery_verdict(hooks["good"])
        check("a hook that refuses what it should and allows the rest is CLEAN", code == 0, str(out))
        code, out = battery_verdict(hooks["everything"])
        check("a hook that refuses everything BLOCKS on the legitimate rows (the positive control)",
              code == 1 and any("legitimate" in x for x in out), str(out))
        check("a hook that is not there is exit 2, not CLEAN", battery_verdict(Path(tmp) / "absent.sh")[0] == 2)

    # The real tree: the battery's expectations hold on the shipped hook, and the real registry finds it.
    code, out = battery_verdict(ROOT / HOOK)
    check("the battery is CLEAN on the shipped guard-bash.sh (its expectations are measured, not guessed)", code == 0, str(out))
    found, missing = guards_for([HOOK], registry())
    check("the real registry finds guard-bash.sh's guard by subject", found.get(HOOK) == "hook_guard_bash", str(found))

    # A reverted prompt: each agent must still be told to run its command, and the check must be able to fail. The
    # reverted text is the prose step the review of #1578 (B2) measured giving a false BLOCKED on every hook diff.
    reverted = {"mutation-verifier": "2. Find each one's guard: `scripts/mutations/<name>.py` or `plugins/<plugin>/scripts/mutations/<name>.py`.",
                "shell-adversary": "3. **Run, do not reason.** Feed the real entry point each hostile input from the catalogue."}
    for agent, rel in AGENTS.items():
        text = (ROOT / rel).read_text(encoding="utf-8") if (ROOT / rel).is_file() else ""
        check(f"{agent}'s instructions name `{AGENT_COMMANDS[agent]}`", prompt_names_command(agent, text), rel)
        check(f"{agent}'s instructions, reverted to the prose step, no longer do (the check can go red)",
              not prompt_names_command(agent, reverted[agent]))
        check(f"{agent} pins `model: {AGENT_MODELS[agent]}` (#1702)", frontmatter_model(text) == AGENT_MODELS[agent], f"{rel}: model {frontmatter_model(text)!r}")

    # The pin check can go red: the model the agents had before #1702, a `model:` line in the BODY only, and no frontmatter.
    check("a frontmatter `model: sonnet` is not the adversary model", frontmatter_model("---\nname: x\nmodel: sonnet\n---\n") != ADVERSARY_MODEL)
    check("`model: fable` after the frontmatter does not count", frontmatter_model("---\nname: x\n---\nmodel: fable\n") is None)
    check("a file with no frontmatter has no model", frontmatter_model("model: fable\n") is None)

    for f in failures:
        print("SELFTEST FAIL", f)
    print(f"gauntlet_core selftest: {'FAILED' if failures else 'ok'}")
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--selftest", action="store_true")
    sub = parser.add_subparsers(dest="cmd")
    g = sub.add_parser("guards", help="changed scripts and the guards that cover them")
    g.add_argument("--base", default="origin/dev")
    b = sub.add_parser("battery", help="run the catalogue inputs against a hook")
    b.add_argument("--hook", type=Path, default=ROOT / HOOK)
    args = parser.parse_args()
    if args.selftest:
        return selftest()
    if args.cmd == "guards":
        diff = subprocess.run(["git", "diff", "--name-only", f"{args.base}...HEAD"], cwd=ROOT, capture_output=True, text=True)
        if diff.returncode != 0:
            print(f"COULD NOT RUN  git diff {args.base}...HEAD failed: {diff.stderr.strip()}", file=sys.stderr)
            return 2
        code, lines = guards_verdict(diff.stdout.split(), registry())
    elif args.cmd == "battery":
        code, lines = battery_verdict(args.hook)
    else:
        parser.print_help()
        return 2
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main())
