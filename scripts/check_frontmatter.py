#!/usr/bin/env python3
"""Every command, agent and skill frontmatter we ship must be valid YAML.

Run:  python3 scripts/check_frontmatter.py            # every shipped and maintainer frontmatter
      python3 scripts/check_frontmatter.py --selftest # prove the rule fires AND stays silent

WHY (#1344). `yaml.safe_load` over all 97 frontmatters found two that fail, with "mapping values
are not allowed here": `plugins/rails-flow/commands/report.md` and `escalate.md`. Their one-line
`description:` held an unquoted `: `. A YAML reader either refuses the block or reads a different
value, so the description the picker shows, and the model routes on, is not the one we wrote.

THE RULE, stated as YAML states it, because CI has no PyYAML and a stdlib check must not guess:
a PLAIN scalar (one not opened by a quote, `|`, `>`, `[` or `{`) cannot contain `": "`, which is a
mapping indicator, and cannot contain `" #"`, which starts a comment and silently truncates the
value. Only single-line top-level `key: value` pairs are read, which is the shape every
frontmatter here uses. A value that needs either sequence is quoted.

TWO AGENT RULES, for the same reason: a frontmatter that says less than the body assumes.
  * agent-undeclared-tools (#1343): a shipped agent with neither `tools:` nor `disallowedTools:`
    inherits EVERY tool. `functional-tester` did, so an agent told "never modify code" held Edit
    and could spawn nested agents. Declaring one of the two is the decision; which is the agent's.
  * agent-unloadable-skill (#1345): Claude Code: "To prevent a subagent from invoking skills
    entirely, omit `Skill` from the `tools` list". Eleven agents told the model to consult one of
    our skills, or to read `skills/<name>/...` (a path that does not exist in a user's project,
    since the skill lives in the plugin cache), with an allowlist that omitted Skill and no
    `skills:` preload, so the instruction did nothing.

Exit codes:  0 clean · 1 a finding · 2 nothing found to check (never reported clean)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOBS = ("plugins/*/commands/*.md", "plugins/*/agents/*.md", "skills/*/SKILL.md",
         ".claude/commands/*.md", ".claude/agents/*.md", ".claude/skills/*/SKILL.md")
TOP_LEVEL = re.compile(r"^(?P<key>[A-Za-z_][\w-]*):[ \t]+(?P<value>\S.*)$")
OPENERS = ('"', "'", "|", ">", "[", "{")


def frontmatter(text: str) -> list[tuple[int, str]] | None:
    """(line number, line) for each frontmatter line, or None when the file has none."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    out = []
    for i, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return out
        out.append((i, line))
    return None  # an unterminated block is itself unreadable


def problems(text: str) -> list[tuple[int, str]]:
    fm = frontmatter(text)
    if fm is None:
        return [(1, "frontmatter opened with --- but never closed")] if text.startswith("---") else []
    found = []
    for lineno, line in fm:
        m = TOP_LEVEL.match(line)
        if not m or m.group("value").startswith(OPENERS):
            continue
        value = m.group("value")
        if ": " in value:
            found.append((lineno, f"`{m.group('key')}` is a plain scalar containing ': ', a YAML mapping "
                                  "indicator -- quote the value"))
        elif " #" in value:
            found.append((lineno, f"`{m.group('key')}` is a plain scalar containing ' #', which YAML reads "
                                  "as a comment and truncates -- quote the value"))
    return found


OUR_SKILLS = ("rails-8", "hotwire", "design-system", "code-review", "quality-pass", "derived-artifacts",
              "parallel-session-lane")
NAMES_SKILL = re.compile(r"\b(" + "|".join(map(re.escape, OUR_SKILLS)) + r")`?\*{0,2}(?:/[a-z-]+)?\s+skill\b"
                         r"|skills/(" + "|".join(map(re.escape, OUR_SKILLS)) + r")/", re.I)


def fields(text: str) -> dict[str, str]:
    fm = frontmatter(text) or []
    out = {}
    for _, line in fm:
        m = re.match(r"^([A-Za-z_][\w-]*):[ \t]*(.*)$", line)
        if m:
            out[m.group(1)] = m.group(2).strip()
    return out


def agent_problems(text: str) -> list[str]:
    f = fields(text)
    found = []
    if "tools" not in f and "disallowedTools" not in f:
        found.append("[agent-undeclared-tools] declares neither `tools:` nor `disallowedTools:`, so it "
                     "inherits every tool, including Edit and nested agents")
    body = text.split("---", 2)[2] if text.count("---") >= 2 else ""
    named = sorted({(m.group(1) or m.group(2)).lower() for m in NAMES_SKILL.finditer(body)})
    tools = [t.strip() for t in f.get("tools", "").split(",") if t.strip()]
    blocked = "Skill" in [t.strip() for t in f.get("disallowedTools", "").split(",")]
    can_invoke = ("tools" not in f and not blocked) or "Skill" in tools
    if named and not can_invoke and "skills" not in f:
        found.append(f"[agent-unloadable-skill] tells the agent to use {', '.join(named)} but can neither "
                     "invoke skills (no `Skill` in its tools) nor has them preloaded (`skills:`)")
    return found


def check(root: Path) -> tuple[int, list[str]]:
    files = sorted({p for g in GLOBS for p in root.glob(g)})
    if not files:
        return 2, ["UNUSABLE: no frontmatter files found to check"]
    findings = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        for lineno, why in problems(text):
            findings.append(f"  [frontmatter-invalid-yaml] {path.relative_to(root)}:{lineno} {why}")
        if path.parent.name == "agents" and path.parts[-3] != ".claude":
            for why in agent_problems(text):
                findings.append(f"  {path.relative_to(root)} {why}")
    if findings:
        return 1, [f"{len(findings)} finding(s) across {len(files)} frontmatter file(s):", *findings]
    return 0, [f"all {len(files)} frontmatter blocks are valid YAML; every shipped agent declares its tools "
               "and can load the skills it names"]


def selftest() -> int:
    import tempfile

    failures: list[str] = []

    def expect(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    def block(desc_line: str) -> str:
        return f"---\n{desc_line}\nargument-hint: \"<x>\"\n---\n\n# body: with a colon\n"

    expect("an unquoted ': ' in a plain scalar is a finding",
           bool(problems(block("description: Report friction upstream. Add MODE: FILE to file."))))
    expect("an unquoted ' #' in a plain scalar is a finding",
           bool(problems(block("description: Fix issue #12 fast, then close #13"))))
    expect("CONTROL: the same text double-quoted is valid",
           not problems(block('description: "Report friction upstream. Add MODE: FILE to file."')))
    expect("CONTROL: a colon with no space after it is valid in a plain scalar",
           not problems(block("description: Ship v1.2 at 10:30 via rails-flow:report")))
    expect("CONTROL: a '#' with no space before it is valid", not problems(block("description: see issue#12")))
    expect("CONTROL: a block scalar is not read as plain", not problems(block("description: >-")))
    expect("CONTROL: a colon in the body after the frontmatter is not read", not problems(block("description: ok")))
    expect("an unterminated frontmatter is a finding", bool(problems("---\ndescription: x\n")))
    try:
        import yaml  # optional: cross-check the stdlib rule against a real parser where one exists
        for good in ('description: "a: b"', "description: a:b", "description: see #12"):
            yaml.safe_load(good)
        for bad in ("description: a: b",):
            try:
                yaml.safe_load(bad)
                failures.append(f"PyYAML accepted {bad!r}, so the rule is stricter than YAML")
            except yaml.YAMLError:
                pass
    except ImportError:
        pass

    def agent(fm: str, body: str) -> str:
        return f"---\nname: a\ndescription: x\n{fm}---\n\n{body}\n"

    expect("an agent with no tools or disallowedTools is a finding",
           any("agent-undeclared-tools" in p for p in agent_problems(agent("", "Do things."))))
    expect("CONTROL: disallowedTools alone is a declaration",
           not agent_problems(agent("disallowedTools: Edit, Agent\n", "Do things.")))
    expect("an agent told to consult a skill it cannot load is a finding",
           any("agent-unloadable-skill" in p for p in
               agent_problems(agent("tools: Read, Bash\n", "Consult the rails-8 skill for doctrine."))))
    expect("...including a path-style mention",
           any("agent-unloadable-skill" in p for p in
               agent_problems(agent("tools: Read\n", "Follow `skills/design-system/SKILL.md`."))))
    expect("...and a Skill in disallowedTools blocks it",
           any("agent-unloadable-skill" in p for p in
               agent_problems(agent("disallowedTools: Skill\n", "Apply the `code-review` skill."))))
    expect("CONTROL: Skill in the tools list can load it",
           not agent_problems(agent("tools: Read, Skill\n", "Consult the rails-8 skill.")))
    expect("CONTROL: a skills: preload can load it",
           not agent_problems(agent("tools: Read\nskills: rails-8\n", "Consult the rails-8 skill.")))
    expect("CONTROL: a body naming no skill of ours is silent",
           not agent_problems(agent("tools: Read\n", "Run its review-pr skill if installed.")))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "plugins/p/commands").mkdir(parents=True)
        cmd = root / "plugins/p/commands/x.md"
        cmd.write_text(block('description: "fine"'), encoding="utf-8")
        expect("CONTROL: a clean tree passes", check(root)[0] == 0, str(check(root)))
        cmd.write_text(block("description: Add MODE: FILE"), encoding="utf-8")
        code, out = check(root)
        expect("a bad file is named with its line", code == 1 and any("x.md:2" in l for l in out), str(out))
        cmd.write_text(block('description: "fine"'), encoding="utf-8")
        (root / "plugins/p/agents").mkdir()
        (root / "plugins/p/agents/a.md").write_text(agent("", "Do things."), encoding="utf-8")
        expect("a shipped agent with no tools declaration is named",
               any("plugins/p/agents/a.md [agent-undeclared-tools]" in l for l in check(root)[1]), str(check(root)))
        (root / "plugins/p/agents/a.md").unlink()
        cmd.unlink()
        expect("no files at all is UNUSABLE, never clean", check(root)[0] == 2)

    for f in failures:
        print(f"FAIL: {f}")
    print(f"check_frontmatter selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    code, lines = check(ROOT)
    print("\n".join(lines))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
