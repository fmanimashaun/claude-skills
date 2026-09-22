#!/usr/bin/env python3
"""Hold a project to the memory systems it chose to load at session start (#1181).

Run:  python3 check_memory_systems.py            # this project
      python3 check_memory_systems.py --root DIR
      python3 check_memory_systems.py --selftest

WHY THIS EXISTS. Three memory systems can inject into every session of one project, and none knows
about the others: Claude Code's auto-memory (the `MEMORY.md` index, "the first 200 lines or the first
25KB"), the `remember` plugin (a day's log and a handoff), and this plugin's own `docs/brain` lessons,
printed by `session-start.sh`. Measured on one repository on 2026-09-22 they were ~3,800, ~5,700 and
~520 tokens -- the largest being a handoff another session wrote, which the plugin itself marked
"already delivered 14 times... pending replacement, not news". Our own budget gate
(`check_hook_output_budget.py`) ratchets only the bytes WE print, so it measured the smallest of the
three and never saw the rest.

WHY A RECORDED CHOICE AND NOT A RULE. Running two memory systems is legitimate for some teams, so a
check refusing it would be wrong for them and switched off. What can be checked honestly is whether
what loads matches what the project chose. `/rails-flow:setup-flow` records the choice in
`.rails-flow/memory.json`:

    {"memory": ["auto-memory"]}          # any of: auto-memory, remember, rails-flow-brain

UNDECLARED IS NOT DECLARED-EMPTY. No file means nobody decided -- NOT APPLICABLE, exit 3, never a
pass. `{"memory": []}` is a decision: load none.

JUDGED ON WHAT THE PROJECT COMMITS, NEVER ON THIS MACHINE. Only `.claude/settings.json` and the
repository's own files are read. User settings (`~/.claude/settings.json`) and local settings
(`.claude/settings.local.json`) differ per person and do not exist in CI, so a verdict that read them
would change with whoever ran it. That is also why a choice must be held EXPLICITLY in the committed
settings: Claude Code applies "a key set at a higher level" over "the same key set lower down"
(managed > command line > project local > shared project > user; code.claude.com/docs/en/settings),
so a project that says nothing about `remember` gets whatever each user enabled globally.

TOKEN COST: NONE PER SESSION. This runs inside `project_gates` -- on demand and in CI -- and adds
nothing to any SessionStart hook. `scripts/check_hook_output_budget.py` holds that in bytes.

Exit 0 pass, 1 the loaded set differs from the choice, 2 bad usage or an unreadable choice, 3 n/a.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

CHOICE = Path(".rails-flow/memory.json")
SETTINGS = Path(".claude/settings.json")
BRAIN = Path("docs/brain/MEMORY.md")
SYSTEMS = ("auto-memory", "remember", "rails-flow-brain")


class Unusable(Exception):
    """The project's choice or settings cannot be read -- a finding about the input, exit 2."""


def load_choice(root: Path) -> set[str] | None:
    """The recorded choice, or None when nothing was recorded (not-applicable, never a pass)."""
    path = root / CHOICE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Unusable(f"{CHOICE} is not valid JSON: {exc}") from None
    chosen = data.get("memory") if isinstance(data, dict) else None
    if not isinstance(chosen, list) or not all(isinstance(x, str) for x in chosen):
        raise Unusable(f'{CHOICE} must be {{"memory": [...]}} naming any of: {", ".join(SYSTEMS)}')
    unknown = sorted(set(chosen) - set(SYSTEMS))
    if unknown:
        raise Unusable(f"{CHOICE} names unknown system(s) {unknown}; known: {', '.join(SYSTEMS)}")
    return set(chosen)


def load_settings(root: Path) -> dict:
    path = root / SETTINGS
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise Unusable(f"{SETTINGS} is not valid JSON: {exc}") from None
    return data if isinstance(data, dict) else {}


def remember_setting(settings: dict) -> bool | None:
    """The committed `enabledPlugins` value for `remember`, from any marketplace; None when unset."""
    plugins = settings.get("enabledPlugins")
    if not isinstance(plugins, dict):
        return None
    values = [v for k, v in plugins.items() if k.split("@", 1)[0] == "remember" and isinstance(v, bool)]
    return values[0] if values else None


def findings_for(root: Path, chosen: set[str]) -> list[str]:
    settings = load_settings(root)
    out: list[str] = []

    remember = remember_setting(settings)
    if "remember" in chosen and remember is not True:
        out.append("remember is chosen but not enabled in .claude/settings.json, so whether it loads "
                   "depends on each user's global setting -- set "
                   '"enabledPlugins": {"remember@claude-plugins-official": true}')
    if "remember" not in chosen and remember is not False:
        state = "enabled" if remember else "unset"
        out.append(f"remember is not chosen but {state} in .claude/settings.json -- a user who enabled it "
                   "globally still loads it here. Hold the choice explicitly: "
                   '"enabledPlugins": {"remember@claude-plugins-official": false}')

    auto = settings.get("autoMemoryEnabled")
    if "auto-memory" in chosen and auto is False:
        out.append('auto-memory is chosen but .claude/settings.json sets "autoMemoryEnabled": false')
    if "auto-memory" not in chosen and auto is not False:
        out.append("auto-memory is not chosen but is on -- it is ON BY DEFAULT, so leaving the key out "
                   'loads it. Set "autoMemoryEnabled": false in .claude/settings.json')

    brain = (root / BRAIN).is_file()
    if "rails-flow-brain" in chosen and not brain:
        out.append(f"rails-flow-brain is chosen but {BRAIN} does not exist -- there is nothing to load")
    if "rails-flow-brain" not in chosen and brain:
        out.append(f"rails-flow-brain is not chosen but {BRAIN} exists, and session-start.sh prints its "
                   "newest lessons at every session start and after every compaction")
    return out


def run(root: Path) -> tuple[int, str]:
    try:
        chosen = load_choice(root)
        if chosen is None:
            return 3, (f"not applicable — no {CHOICE}, so nobody has decided which memory systems this "
                       "project loads (NOT a pass). /rails-flow:setup-flow records the choice.")
        found = findings_for(root, chosen)
    except Unusable as exc:
        return 2, str(exc)
    label = ", ".join(sorted(chosen)) or "none"
    if found:
        return 1, (f"chosen: {label} — but what loads at session start differs:\n  - "
                   + "\n  - ".join(found))
    return 0, f"chosen: {label} — and exactly that is held in the committed settings"


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    def verdict(files: dict[str, str]) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body, encoding="utf-8")
            return run(root)

    def choice(*systems: str) -> str:
        return json.dumps({"memory": list(systems)})

    def settings(remember: bool | None = None, auto: bool | None = None) -> str:
        s: dict = {}
        if remember is not None:
            s["enabledPlugins"] = {"remember@claude-plugins-official": remember, "other@x": True}
        if auto is not None:
            s["autoMemoryEnabled"] = auto
        return json.dumps(s)

    BRAIN_FILE = {str(BRAIN): "- [a](a.md) — lesson\n"}

    # 1. UNDECLARED is not-applicable, never a pass.
    code, msg = verdict({})
    check("no recorded choice is not-applicable", code == 3, f"exit {code}")
    check("...and says it is NOT a pass", "NOT a pass" in msg, msg)

    # 2. The common choice, held correctly: auto-memory only, remember explicitly off, no brain.
    code, msg = verdict({str(CHOICE): choice("auto-memory"), str(SETTINGS): settings(remember=False)})
    check("auto-memory only, with remember explicitly off, passes", code == 0, f"exit {code}: {msg}")

    # 3. THE CASE THIS EXISTS FOR: remember not chosen and not held off. The committed settings say
    #    nothing, so a user who enabled it globally loads it anyway -- which is what happened.
    code, msg = verdict({str(CHOICE): choice("auto-memory"), str(SETTINGS): settings()})
    check("remember unset when not chosen fails", code == 1, f"exit {code}: {msg}")
    check("...naming the global setting as the reason", "global" in msg, msg)
    code, msg = verdict({str(CHOICE): choice("auto-memory"), str(SETTINGS): settings(remember=True)})
    check("remember enabled when not chosen fails", code == 1, f"exit {code}: {msg}")

    # 4. remember chosen must be held ON, for the same reason in the other direction.
    code, msg = verdict({str(CHOICE): choice("remember"), str(SETTINGS): settings(remember=True, auto=False)})
    check("remember chosen and on, auto-memory off, passes", code == 0, f"exit {code}: {msg}")
    code, msg = verdict({str(CHOICE): choice("remember"), str(SETTINGS): settings(auto=False)})
    check("remember chosen but unset fails", code == 1, f"exit {code}: {msg}")

    # 5. AUTO-MEMORY IS ON BY DEFAULT: leaving the key out loads it.
    code, msg = verdict({str(CHOICE): choice("remember"), str(SETTINGS): settings(remember=True)})
    check("auto-memory unset when not chosen fails, because it is on by default", code == 1,
          f"exit {code}: {msg}")
    check("...saying so", "ON BY DEFAULT" in msg, msg)
    code, msg = verdict({str(CHOICE): choice("auto-memory"),
                         str(SETTINGS): settings(remember=False, auto=False)})
    check("auto-memory chosen but disabled fails", code == 1, f"exit {code}: {msg}")

    # 6. The brain is present exactly when docs/brain/MEMORY.md exists -- that is when session-start.sh
    #    prints it.
    code, msg = verdict({str(CHOICE): choice("auto-memory"), str(SETTINGS): settings(remember=False),
                         **BRAIN_FILE})
    check("a brain present but not chosen fails", code == 1, f"exit {code}: {msg}")
    code, msg = verdict({str(CHOICE): choice("auto-memory", "rails-flow-brain"),
                         str(SETTINGS): settings(remember=False), **BRAIN_FILE})
    check("a brain chosen and present passes", code == 0, f"exit {code}: {msg}")
    code, msg = verdict({str(CHOICE): choice("rails-flow-brain"),
                         str(SETTINGS): settings(remember=False, auto=False)})
    check("a brain chosen but absent fails", code == 1, f"exit {code}: {msg}")

    # 7. DECLARED-EMPTY is a decision, not undeclared: none may load.
    code, msg = verdict({str(CHOICE): choice(), str(SETTINGS): settings(remember=False, auto=False)})
    check("an empty choice with everything off passes", code == 0, f"exit {code}: {msg}")
    code, msg = verdict({str(CHOICE): choice(), str(SETTINGS): settings(remember=False)})
    check("an empty choice with auto-memory left on fails -- not treated as undeclared", code == 1,
          f"exit {code}: {msg}")

    # 8. The plugin key is matched by NAME, whatever marketplace it came from; another plugin that
    #    merely contains the word is not it.
    code, msg = verdict({str(CHOICE): choice("auto-memory"),
                         str(SETTINGS): json.dumps({"enabledPlugins": {"remember@my-fork": False}})})
    check("remember from another marketplace is recognised", code == 0, f"exit {code}: {msg}")
    code, msg = verdict({str(CHOICE): choice("auto-memory"),
                         str(SETTINGS): json.dumps({"enabledPlugins": {"remember-me@x": False}})})
    check("a different plugin named remember-me is not remember", code == 1, f"exit {code}: {msg}")

    # 9. An unreadable or invalid choice is bad input, never a pass or a silent n/a.
    for label, body in (("not JSON", "{"), ("wrong shape", '{"memory": "auto-memory"}'),
                        ("unknown system", choice("mem0"))):
        code, _ = verdict({str(CHOICE): body})
        check(f"a choice that is {label} is exit 2", code == 2, f"exit {code}")

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} memory-systems assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=Path("."), help="project root (default: .)")
    ap.add_argument("--selftest", action="store_true", help="run the fixtures and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, msg = run(a.root)
    print(msg)
    return code


if __name__ == "__main__":
    sys.exit(main())
