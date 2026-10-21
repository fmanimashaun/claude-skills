#!/usr/bin/env python3
"""A ratchet on what each shipped plugin costs EVERY session before anything is invoked (#1881, slice 1 of #1683).

    python3 scripts/check_always_on_cost.py            # gate: fail on growth past the recorded baseline
    python3 scripts/check_always_on_cost.py --write    # record today's measurement as the baseline (after a drop, or a growth you justify)
    python3 scripts/check_always_on_cost.py --selftest

What is always on: the listing Claude Code puts in context at session start — each command/skill's name with its `description`
and `when_to_use`, and each agent's name with its `description`. The skills page: "Every skill in the skill listing adds to your
context on every turn"; the two fields are "truncated at 1,536 characters in the skill listing"; and `disable-model-invocation:
true` means "Description not in context" (https://code.claude.com/docs/en/skills.md, read 2026-10-11). Bodies load only when
invoked, so they are not counted. Hooks cost no model context. Agents: sub-agents.md says their descriptions "take up context"
and that Claude Code "still loads every subagent" past a 15,000-token warning -- no cap, no disable flag. One limit this does not
model: the skill listing has a budget (1% of the context window) past which Claude Code drops descriptions; a ratchet on growth is
still right below that budget.

The ratchet counts CHARACTERS, which are exact and need no CLI (CI has none). Tokens are reported as an estimate: calibrated against
`claude plugin details` 2.1.296 on 2026-10-11, the CLI charges about one token per 2.9-3.1 characters of name + description per
component. The CLI's own totals are recorded beside the baseline as a cross-check; note that the CLI still counts a command with
`disable-model-invocation: true` (pipeline's deploy-cloud), which the docs say is not in context, so it overcounts by those.
Exit: 0 at or under baseline, 1 grown (or a plugin with no baseline), 2 baseline unreadable.
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "scripts" / "always_on_baseline.json"
LISTING_CAP = 1536
CHARS_PER_TOKEN = 3.0


def frontmatter(text: str) -> dict[str, str]:
    """The scalar fields of a YAML frontmatter block: plain, quoted, and `>`/`|` block scalars. Enough for name/description."""
    m = re.match(r"---\r?\n(.*?)\r?\n---", text, re.S)
    if not m:
        return {}
    out: dict[str, str] = {}
    lines = m.group(1).splitlines()
    i = 0
    while i < len(lines):
        km = re.match(r"([A-Za-z_][\w-]*):\s*(.*)$", lines[i])
        i += 1
        if not km:
            continue
        key, val = km.group(1), km.group(2).strip()
        if val in (">", "|", ">-", "|-", ">+", "|+"):
            block = []
            while i < len(lines) and (lines[i].startswith((" ", "\t")) or not lines[i].strip()):
                block.append(lines[i].strip())
                i += 1
            val = (" " if val.startswith(">") else "\n").join(b for b in block).strip()
        elif len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        out[key] = val
    return out


def component_chars(path: Path, name: str, agent: bool = False) -> int:
    """A command/skill: name + description + when_to_use, capped at the listing's 1,536, 0 when model invocation is disabled.
    An agent: name + description, uncapped -- sub-agents.md gives agents no cap and no disable flag, only a startup warning past
    15,000 tokens of combined descriptions, and "still loads every subagent"."""
    fm = frontmatter(path.read_text(encoding="utf-8"))
    if agent:
        return len(name) + len(fm.get("description", ""))
    if fm.get("disable-model-invocation", "").lower() == "true":
        return 0
    listed = (fm.get("description", "") + (" " + fm["when_to_use"] if fm.get("when_to_use") else ""))[:LISTING_CAP]
    return len(name) + len(listed)


def plugin_sources(root: Path) -> dict[str, list[tuple[str, Path, bool]]]:
    """name -> [(component name, file)] for every plugin in the marketplace manifest."""
    manifest = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    out: dict[str, list[tuple[str, Path]]] = {}
    for p in manifest["plugins"]:
        base = (root / p.get("source", "./")).resolve()
        comps: list[tuple[str, Path, bool]] = []
        comps += [(f.stem, f, False) for f in sorted((base / "commands").glob("*.md"))]
        comps += [(f.stem, f, True) for f in sorted((base / "agents").glob("*.md"))]
        for s in p.get("skills", []) or []:
            skill = (base / s / "SKILL.md")      # a manifest skill path is relative to the plugin's own source, not to the repo root (#2231)
            if skill.is_file():
                comps.append((Path(s).name, skill, False))
        comps += [(f.parent.name, f, False) for f in sorted((base / "skills").glob("*/SKILL.md"))] if (base / "skills").is_dir() and not p.get("skills") else []
        out[p["name"]] = comps
    return out


def unmeasured(root: Path = ROOT) -> list[str]:
    """What the measurement cannot see. A plugin whose skills exist on disk under its source but are not in what `measure` counted, and a manifest
    skill path that names no SKILL.md, are both a number that reads low for no reason: rails-stack measured 0 chars for its skills when they moved
    under `plugins/rails-stack/`, and the gate passed (#2231)."""
    findings: list[str] = []
    manifest = json.loads((root / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    counted = plugin_sources(root)
    for p in manifest["plugins"]:
        base = (root / p.get("source", "./")).resolve()
        seen = {f.resolve() for _, f, agent in counted[p["name"]] if not agent}
        on_disk = sorted((base / "skills").glob("*/SKILL.md")) if (base / "skills").is_dir() else []
        for f in on_disk:
            if f.resolve() not in seen:
                findings.append(f"{p['name']}: skill {f.parent.name} exists on disk ({f.resolve().relative_to(root.resolve())}) but is not measured: its always-on cost is unguarded")
        for s in p.get("skills", []) or []:
            if not (base / s / "SKILL.md").is_file():
                findings.append(f"{p['name']}: the manifest lists skill {s}, which has no SKILL.md under {base.relative_to(root.resolve()) if base != root.resolve() else '.'}")
    return findings


def measure(root: Path = ROOT) -> dict[str, int]:
    return {name: sum(component_chars(f, n, a) for n, f, a in comps) for name, comps in plugin_sources(root).items()}


def gate(measured: dict[str, int], baseline: dict) -> list[str]:
    findings = []
    recorded = baseline.get("plugins", {})
    for name, chars in sorted(measured.items()):
        if name not in recorded:
            findings.append(f"{name}: no baseline (measured {chars} chars, ~{round(chars / CHARS_PER_TOKEN)} tok) -- record it with --write")
            continue
        was = recorded[name]["chars"]
        if chars > was:
            findings.append(f"{name}: always-on listing grew {was} -> {chars} chars (+{chars - was}, ~+{round((chars - was) / CHARS_PER_TOKEN)} tok "
                            f"every session). Shorten the description, set disable-model-invocation on a slash-only command, or justify and --write")
    return findings


def selftest() -> int:
    bad: list[str] = []

    def check(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            bad.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory() as td:
        r = Path(td)
        (r / ".claude-plugin").mkdir()
        (r / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [
            {"name": "alpha", "source": "./plugins/alpha"},
            {"name": "stack", "source": "./", "skills": ["./skills/one"]},
            {"name": "nested", "source": "./plugins/nested", "skills": ["./skills/two"]}]}))
        cmd = r / "plugins" / "alpha" / "commands"; cmd.mkdir(parents=True)
        agent = r / "plugins" / "alpha" / "agents"; agent.mkdir(parents=True)
        (cmd / "go.md").write_text("---\ndescription: Do the thing\n---\nbody that is never counted\n")
        (cmd / "quiet.md").write_text("---\ndescription: Hidden from the listing\ndisable-model-invocation: true\n---\n")
        (cmd / "folded.md").write_text("---\ndescription: >\n  first line\n  second line\nwhen_to_use: \"when asked\"\n---\n")
        (cmd / "huge.md").write_text("---\ndescription: " + "x" * 3000 + "\n---\n")
        (agent / "helper.md").write_text("---\nname: helper\ndescription: 'Helps'\n---\n")
        (agent / "big.md").write_text("---\nname: big\ndescription: " + "y" * 2000 + "\n---\n")
        (r / "skills" / "one").mkdir(parents=True)
        (r / "skills" / "one" / "SKILL.md").write_text("---\nname: one\ndescription: A skill\n---\n")
        (r / "plugins" / "nested" / "skills" / "two").mkdir(parents=True)
        (r / "plugins" / "nested" / "skills" / "two" / "SKILL.md").write_text("---\nname: two\ndescription: A nested skill\n---\n")
        m = measure(r)
        check("measure: a skill under a plugin whose source is NOT the repo root is counted (#2231: it measured 0)",
              m["nested"] == len("two") + len("A nested skill"), m)
        check("unmeasured: nothing is hidden from the measurement in a clean fixture", unmeasured(r) == [], unmeasured(r))
        check("measure: name + description, body never counted", component_chars(cmd / "go.md", "go") == len("go") + len("Do the thing"),
              component_chars(cmd / "go.md", "go"))
        check("measure: disable-model-invocation: true is not in context (0)", component_chars(cmd / "quiet.md", "quiet") == 0)
        check("measure: a folded description and when_to_use are both counted",
              component_chars(cmd / "folded.md", "folded") == len("folded") + len("first line second line when asked"),
              component_chars(cmd / "folded.md", "folded"))
        check("measure: the listing truncates at 1,536 characters", component_chars(cmd / "huge.md", "huge") == len("huge") + 1536)
        check("measure: agents and a manifest-listed skill are counted",
              m["alpha"] == sum(component_chars(f, f.stem) for f in [cmd / "go.md", cmd / "folded.md", cmd / "huge.md"])
              + sum(component_chars(f, f.stem, agent=True) for f in [agent / "helper.md", agent / "big.md"])
              and m["stack"] == len("one") + len("A skill"), m)
        check("measure: an agent's description is NOT capped at 1,536 (no cap for agents in sub-agents.md)",
              component_chars(agent / "big.md", "big", agent=True) == len("big") + 2000)
        # A declared plugin that measures 0 while its skills exist on disk is a vacuous gate: the check must name it.
        (r / ".claude-plugin" / "marketplace.json").write_text(json.dumps({"plugins": [
            {"name": "ghost", "source": "./plugins/nested", "skills": ["./skills/moved-away"]}]}))
        ghost = measure(r)
        check("unmeasured: a plugin measuring 0 while its skill exists on disk is a finding",
              ghost["ghost"] == 0 and any("two exists on disk" in f and "not measured" in f for f in unmeasured(r)), (ghost, unmeasured(r)))
        check("unmeasured: a manifest skill path naming no SKILL.md is a finding", any("moved-away" in f and "no SKILL.md" in f for f in unmeasured(r)), unmeasured(r))
        base = {"plugins": {k: {"chars": v} for k, v in m.items()}}
        check("gate: at the baseline passes", gate(m, base) == [], gate(m, base))
        check("gate: one character of growth fails, naming the plugin",
              any(f.startswith("alpha: always-on listing grew") for f in gate({**m, "alpha": m["alpha"] + 1}, base)), "")
        check("gate: a drop passes (lower the baseline with --write)", gate({**m, "alpha": m["alpha"] - 5}, base) == [])
        check("gate: a plugin with no baseline fails", any("no baseline" in f for f in gate({**m, "new": 10}, base)), "")
    for b in bad:
        print(f"FAIL {b}")
    print(f"check_always_on_cost selftest: {'FAILED ' + str(len(bad)) if bad else 'ok'}")
    return 1 if bad else 0


def main() -> int:
    args = sys.argv[1:]
    if args == ["--selftest"]:
        return selftest()
    measured = measure()
    if args == ["--write"]:
        old = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.is_file() else {}
        old["plugins"] = {k: {"chars": v, "est_tokens": round(v / CHARS_PER_TOKEN)} for k, v in sorted(measured.items())}
        BASELINE.write_text(json.dumps(old, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"always-on baseline written: {BASELINE.relative_to(ROOT)}")
        return 0
    try:
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"check_always_on_cost: cannot read {BASELINE}: {exc}", file=sys.stderr)
        return 2
    findings = gate(measured, baseline) + unmeasured()
    for f in findings:
        print(f)
    total = sum(measured.values())
    print(f"always-on listing: {len(measured)} plugins, {total} chars (~{round(total / CHARS_PER_TOKEN)} tok), "
          f"{'within' if not findings else 'OVER'} the recorded baseline")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
