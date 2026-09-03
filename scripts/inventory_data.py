#!/usr/bin/env python3
"""inventory_data.py -- what this marketplace ships (agents, commands, gates, tier tables) as DATA, read from
the structured sources and verified, for the generated wiki page `Agents-And-Gates.md` (#892).

HISTORY. This was the data layer of `build_inventory.py`, which rendered `docs/architecture/inventory.html`
(#509): a filterable page, committed, drift-gated. The wiki's reference pages are generated from the same
inputs, so the repo kept two generated views of one input set, each with its own generator, drift gate and
selftest. The page is retired; the readers and their verifications live on here, and `build_wiki.py`
renders them as one more reference page, under the wiki's existing drift gate. `coverage.html` stays: it
is the only browsable view of the design-system matrix.

WHY EACH SOURCE IS IMPORTED RATHER THAN RE-PARSED (unchanged from #509):
  * gates       -- `maintainer_doctor.GATES`, imported. A literal tuple; re-deriving it by regex would be
                   a second reader of the registry that decides what runs.
  * tier tables -- `check_handoff.parse_tiers`, imported. That module is the arbiter of the
                   `<!-- <plugin>:tiers:begin -->` block for four shipped gates.
  * agents      -- frontmatter, read HERE because the page needs `description` and `tools`, which
                   `check_handoff.agent_models` does not return -- and reconciled against it, both ways.

Run:  python3 scripts/inventory_data.py --selftest     (the `inventory data selftest` gate)
      python3 scripts/inventory_data.py --json         (the model the wiki page renders)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.append(str(REPO / "plugins" / "rails-flow" / "scripts"))

import check_handoff as ch  # noqa: E402  — the arbiter of the tier tables, imported not re-parsed
import maintainer_doctor as md  # noqa: E402  — the gate registry, imported not re-parsed

MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
PLUGINS = REPO / "plugins"
MAINTAINER = REPO / ".claude"
OWNER_MAINTAINER = "maintainer"
OWNER_REPO = "repo"

FIELD_RE = re.compile(r"^(?P<key>[a-z][\w-]*)\s*:\s*(?P<value>.*?)\s*$")
BLOCK_SCALARS = frozenset({">", "|", ">-", "|-", ">+", "|+"})
TOPOLOGY_RE = re.compile(r"<!--\s*topology:\s*(sequential|parallel|loop|agent-to-agent)\b", re.I)


class ArtifactError(Exception):
    """The data cannot be built honestly; the page must not be."""


def names_agent(body: str, agent: str) -> bool:
    """Does this command's text name that agent anywhere -- in any markup, or none?

    THE COLUMN SAYS "NAMED", SO THE MEASUREMENT HAS TO BE "NAMED". This started as a borrowed copy
    of the DISPATCH detection in `lint_self_consistency.check_undeclared_topology`, which is right
    for ITS job -- deciding whether a command owes a topology declaration, where over-counting
    invents findings -- and wrong for a map, in both directions:

      * FALSE NEGATIVES BY MARKUP. Five commands name their agent only in **bold** --
        `/design-flow:audit` writes `**design-auditor**` -- so a backticks-only read printed "no
        agent" beside four of design-flow's seven commands.
      * FALSE NEGATIVES BY PLAIN PROSE, which is the worse half and was nearly shipped as a claim.
        `/rails-flow:issues` names seven of its plugin's agents in running prose and genuinely
        dispatches them ("code-reviewer -> `VERDICT: CLEAN`", "else the pr-reviewer agent"). A
        draft of this page said it dispatched none of them. Emphasis is a typographic choice, not
        a semantic one, and reading it as one manufactures a negative the corpus contradicts.

    So the match is word-bounded and markup-blind. `(?<![\\w-])`/`(?![\\w-])` keeps backticks,
    asterisks and full stops adjacent (all of which still name the agent) while refusing
    `design-auditors` and `meta-design-auditor` -- a longer token is a different name.

    WHAT THIS DELIBERATELY DOES NOT CLAIM: that a named agent is dispatched. Naming is what can be
    measured from the text; dispatch is a judgement about intent, and a map that guessed at it
    would be asserting a call graph it cannot see. The page uses the word "named" throughout and
    says so in its footer, so an empty list means "this command's text names none of its plugin's
    agents" -- a negative that WAS verified over the whole body.
    """
    return bool(re.search(rf"(?<![\w-]){re.escape(agent)}(?![\w-])", body))


# ---------------------------------------------------------------------------- text

def read_frontmatter(text: str) -> dict[str, str]:
    """The `---` frontmatter block as flat strings, folded scalars joined.

    Deliberately not YAML: the stdlib has no parser, adding a dependency would make this gate pass
    or fail by machine, and the corpus uses exactly two shapes -- `key: value` and `key: >` with an
    indented block. Anything richer would be a finding about the frontmatter, not about this reader.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    key: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        nonlocal key, buffer
        if key is not None:
            fields[key] = " ".join(buffer).strip()
        key, buffer = None, []

    for line in lines[1:]:
        if line.strip() == "---":
            break
        match = FIELD_RE.match(line)
        if match:
            flush()
            value = match.group("value")
            if value in BLOCK_SCALARS:
                key, buffer = match.group("key"), []
            else:
                fields[match.group("key")] = value.strip("\"'")
        elif key is not None and line.strip():
            buffer.append(line.strip())
    flush()
    return fields


# ------------------------------------------------------------------------- sources

def rel(path: Path) -> str:
    """Repo-relative and forward-slashed, falling back to the absolute path outside the repo.

    Never a bare `relative_to`, which RAISES on a path outside REPO — the selftest points these
    readers at a temp directory on purpose, and a guard that cannot be exercised on a fixture is
    the one that is wrong when it finally runs.
    """
    return (path.relative_to(REPO) if path.is_relative_to(REPO) else path).as_posix()


def plugin_names() -> list[str]:
    """Every shipped plugin, as a directory name. The directory is the unit a plugin installs as."""
    if not PLUGINS.is_dir():
        return []
    return sorted(p.name for p in PLUGINS.iterdir()
                  if p.is_dir() and (p / ".claude-plugin" / "plugin.json").is_file())


def plugin_version(name: str) -> str:
    try:
        data = json.loads((PLUGINS / name / ".claude-plugin" / "plugin.json")
                          .read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ""
    return str(data.get("version", ""))


def read_agents(directory: Path, owner: str, shipped: bool) -> list[dict]:
    """Every agent definition under `directory`, by its frontmatter identity.

    Identity is the `name` field, not the filename: Claude Code's docs are explicit that "identity
    comes only from the `name` frontmatter field" and "The filename doesn't have to match". Same
    rule `check_handoff.agent_models` follows, and `verify_reconciled_agents` holds the two to it.

    A FILE WITH NO `name:` IS REFUSED, NOT SKIPPED. `agent_models` skips it, which is right for a
    reconciler -- there is nothing to reconcile. It is wrong here, and wrong in a way this page
    cannot survive: both readers would skip it identically, so the reconciliation stays clean, no
    tier gate notices (the table has nothing to match), and an agent simply is not on the map. A
    completeness matrix silently missing a row is indistinguishable from a row that never existed.
    """
    out: list[dict] = []
    if not directory.is_dir():
        return out
    nameless: list[str] = []
    for path in sorted(directory.glob("*.md")):
        fields = read_frontmatter(path.read_text(encoding="utf-8"))
        name = fields.get("name", "")
        if not name:
            nameless.append(rel(path))
            continue
        out.append({
            "name": name,
            "owner": owner,
            "shipped": shipped,
            "description": fields.get("description", ""),
            "tools": fields.get("tools", ""),
            "model": fields.get("model", ""),
            "path": rel(path),
        })
    if nameless:
        raise ArtifactError("\n".join(
            f"  - {p} declares no `name:` — Claude Code takes an agent's identity only from that "
            "field, so it has none, and it would vanish from this page with no error"
            for p in nameless))
    return out


def read_commands(directory: Path, owner: str, shipped: bool,
                  agent_names: set[str]) -> list[dict]:
    """Every command under `directory`, with the agents it names and its declared topology.

    A command has no `name:` field -- the filename IS the invocation (`/<plugin>:<stem>`), which is
    why this one keys on the stem while `read_agents` keys on frontmatter.

    "Names" rather than "dispatches", and the page uses that word too: see `names_agent` for what
    is and is not counted, and why the difference is worth being precise about on a map.
    """
    out: list[dict] = []
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.md")):
        body = path.read_text(encoding="utf-8")
        fields = read_frontmatter(body)
        topology = TOPOLOGY_RE.search(body)
        named = sorted(n for n in agent_names if names_agent(body, n))
        out.append({
            "name": path.stem,
            "owner": owner,
            "shipped": shipped,
            "invocation": f"/{owner}:{path.stem}" if shipped else f"/{path.stem}",
            "description": fields.get("description", ""),
            "argumentHint": fields.get("argument-hint", ""),
            "topology": topology.group(1).lower() if topology else "",
            "names": named,
            "path": rel(path),
        })
    return out


def read_tiers() -> dict[str, list[ch.TierRow]]:
    """Each plugin's model-tier table, parsed by the module four shipped gates already trust."""
    tables: dict[str, list[ch.TierRow]] = {}
    for name in plugin_names():
        path = PLUGINS / name / "reference" / "model-tiers.md"
        if not path.is_file():
            continue
        try:
            tables[name] = ch.parse_tiers(path)
        except ch.Unusable as exc:
            raise ArtifactError(
                f"  - {rel(path)} cannot be read as a tier table ({exc}) "
                "— the page would render every one of that plugin's agents with an empty tier"
            ) from exc
    return tables


def read_gates() -> list[dict]:
    """`maintainer_doctor.GATES`, as rows -- who owns each gate and what it actually runs."""
    out: list[dict] = []
    for name, cmd in md.GATES:
        script = cmd[1]
        parts = Path(script).parts
        owner = parts[1] if parts[0] == "plugins" and len(parts) > 1 else OWNER_REPO
        out.append({
            "name": name,
            "owner": owner,
            "script": script,
            "command": " ".join(cmd),
            "selftest": "--selftest" in cmd,
            "corporaExempt": name in md.CORPORA_GATES,
            "timeout": md.SLOW_GATES.get(name, 0),
        })
    return out


# ------------------------------------------------------------------------- guards

def verify_reconciled_agents(parsed: list[dict], plugin: str,
                             shipped: dict[str, tuple[Path, str | None]]) -> None:
    """This module's frontmatter reader must agree with the shipped one, agent for agent.

    NOT a tautology, and this is the whole reason the page does not simply call
    `check_handoff.agent_models`: that function returns name and `model:` only, so the page has to
    read the frontmatter itself for `description` and `tools`. Two readers of one file will
    eventually disagree -- over a quoted value, a folded scalar, a stray indent -- and the one that
    is wrong here is silent, because a page rendering 26 of 27 agents looks exactly like a page
    over 26 agents. So they are reconciled against each other, in both directions.
    """
    mine = {row["name"]: (row["model"] or None) for row in parsed}
    theirs = {name: model for name, (_path, model) in shipped.items()}
    problems: list[str] = []
    for name in sorted(set(mine) - set(theirs)):
        problems.append(f"{plugin}: this module reads an agent `{name}` that check_handoff does not")
    for name in sorted(set(theirs) - set(mine)):
        problems.append(f"{plugin}: check_handoff reads an agent `{name}` that this module does not")
    for name in sorted(set(mine) & set(theirs)):
        if mine[name] != theirs[name]:
            problems.append(
                f"{plugin}: agent `{name}` reads as model {mine[name]!r} here and {theirs[name]!r} "
                "in check_handoff — one of the two frontmatter readers is wrong"
            )
    if problems:
        raise ArtifactError("\n".join(f"  - {p}" for p in problems))


def verify_tier_join(agents: list[dict], tables: dict[str, list[ch.TierRow]]) -> None:
    """Every shipped agent resolves exactly one tier row, and every tier row a shipped agent.

    The four `<plugin> tiers` gates already assert this, and asserting it again is deliberate for
    the reason `build_coverage_artifact.verify_prose` re-asserts what its builder enforces: THIS
    renderer would emit a visibly empty tier cell rather than failing, and an empty tier on a page
    whose whole claim is "here is what runs on what" is the one cell that must never be blank.
    """
    problems: list[str] = []
    for row in agents:
        if not row["shipped"]:
            continue
        rows = [t for t in tables.get(row["owner"], []) if t.agent == row["name"]]
        if len(rows) != 1:
            problems.append(
                f"{row['owner']}: agent `{row['name']}` matches {len(rows)} tier rows, need exactly "
                "1 — the page would render its tier cell empty or ambiguous"
            )
    known = {(row["owner"], row["name"]) for row in agents if row["shipped"]}
    for plugin, rows in tables.items():
        for tier_row in rows:
            if (plugin, tier_row.agent) not in known:
                problems.append(
                    f"{plugin}: tier table line {tier_row.line} names `{tier_row.agent}`, which no "
                    "agent definition declares — a stale row would render as a shipped agent"
                )
    if problems:
        raise ArtifactError("\n".join(f"  - {p}" for p in problems))


def verify_gate_scripts(gates: list[dict]) -> None:
    """Every registered gate must name a script that exists.

    `maintainer_doctor.check_gates` SKIPs a missing script on purpose ("this checkout predates the
    gate"), which is right for a partial checkout and wrong for this page: rendering a row for a
    gate whose script is not there states coverage that does not exist. Here the whole repo is
    present by construction, so absence is a stale registry entry, not an old clone.
    """
    problems = [
        f"gate {gate['name']!r} runs {gate['script']}, which does not exist — the page would list "
        "a gate nothing can run"
        for gate in gates if not (REPO / gate["script"]).exists()
    ]
    if problems:
        raise ArtifactError("\n".join(f"  - {p}" for p in problems))


def cross_check_manifest(plugins: list[str]) -> tuple[str, str]:
    """Compare the plugin directories walked here against the ones `marketplace.json` declares.

    THE SECOND CHECK IS AGAINST DATA, NOT AGAINST OURSELVES. Counting our own rows twice would be
    the same expression written twice; the manifest is an independently maintained statement about
    the same subject, so agreement means two records of what ships agree. It is also the exact
    defect #203 recorded -- `design-flow` existed as a plugin and was named in no manifest list --
    which is a plugin this page would have inventoried while the marketplace did not install it.

    Three states, never two. `skip` means the check did not run, and it is not a pass.
    """
    try:
        data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return "skip", f"{MARKETPLACE.name} could not be read ({exc}) — cross-check did not run"
    declared: set[str] = set()
    for entry in data.get("plugins", []):
        source = str(entry.get("source", "")).strip().rstrip("/")
        while source.startswith("./"):
            source = source[2:]
        if source.startswith("plugins/"):
            declared.add(source[len("plugins/"):])
    if not declared:
        return "skip", (f"{MARKETPLACE.name} declares no `plugins/<name>` source — cross-check did "
                        "not run")
    walked = set(plugins)
    if walked == declared:
        return "ok", (f"the {len(walked)} plugin directories inventoried are exactly the ones "
                      f"{MARKETPLACE.name} installs")
    missing = sorted(walked - declared)
    extra = sorted(declared - walked)
    parts = []
    if missing:
        parts.append(f"on disk but not installed by the manifest: {', '.join(missing)}")
    if extra:
        parts.append(f"installed by the manifest but not on disk: {', '.join(extra)}")
    return "fail", ("the plugin directories and the marketplace manifest disagree — "
                    + "; ".join(parts))


# ---------------------------------------------------------------- version stamp



# ------------------------------------------------------------------------- the model

def collect_data() -> dict:
    """Agents (with tier, model, the commands that name them), commands, gates, tier tables, totals."""
    plugins = plugin_names()
    agents: list[dict] = []
    commands: list[dict] = []
    for plugin in plugins:
        found = read_agents(PLUGINS / plugin / "agents", plugin, shipped=True)
        agent_dir = PLUGINS / plugin / "agents"
        if agent_dir.is_dir():
            try:
                verify_reconciled_agents(found, plugin, ch.agent_models(agent_dir))
            except ch.Unusable as exc:
                raise ArtifactError(f"  - {plugin}: {exc}") from exc
        agents += found
        commands += read_commands(PLUGINS / plugin / "commands", plugin, shipped=True,
                                  agent_names={row["name"] for row in found})
    maintainer_agents = read_agents(MAINTAINER / "agents", OWNER_MAINTAINER, shipped=False)
    agents += maintainer_agents
    commands += read_commands(MAINTAINER / "commands", OWNER_MAINTAINER, shipped=False,
                              agent_names={row["name"] for row in maintainer_agents})
    tables = read_tiers()
    verify_tier_join(agents, tables)
    gates = read_gates()
    verify_gate_scripts(gates)
    state, message = cross_check_manifest(plugins)
    if state == "fail":
        raise ArtifactError(f"  - {message}")
    tier_of = {(plugin, row.agent): row for plugin, rows in tables.items() for row in rows}
    callers: dict[tuple[str, str], list[str]] = {}
    for command in commands:
        for agent in command["names"]:
            callers.setdefault((command["owner"], agent), []).append(command["invocation"])
    for agent in agents:
        tier = tier_of.get((agent["owner"], agent["name"]))
        agent["tier"] = tier.tier if tier else ""
        agent["proof"] = (tier.proof if tier and tier.proof.strip(" -—–") else "")
        agent["model_shown"] = agent["model"] or "inherit (default)"
        agent["named_by"] = callers.get((agent["owner"], agent["name"]), [])
    blank = [f"{k} {r['name']!r} ({r['owner']}) has no description -- an empty cell reads as an answer"
             for k, rows in (("agent", agents), ("command", commands)) for r in rows if not r["description"].strip()]
    if blank:
        raise ArtifactError("\n".join(f"  - {p}" for p in blank))
    shipped_agents = [a for a in agents if a["shipped"]]
    shipped_commands = [c for c in commands if c["shipped"]]
    return {
        "agents": agents, "commands": commands, "gates": gates,
        "tables": {p: [{"agent": r.agent, "tier": r.tier, "proof": r.proof} for r in rows] for p, rows in tables.items()},
        "totals": {"agents": len(shipped_agents), "commands": len(shipped_commands), "gates": len(gates),
                   "tierTables": len(tables), "maintainerAgents": len(agents) - len(shipped_agents),
                   "maintainerCommands": len(commands) - len(shipped_commands)},
        "plugins": [{"name": p, "version": plugin_version(p),
                     "agents": sum(1 for a in shipped_agents if a["owner"] == p),
                     "commands": sum(1 for c in shipped_commands if c["owner"] == p),
                     "tierRows": len(tables.get(p, [])),
                     "gates": sum(1 for g in gates if g["owner"] == p)} for p in plugins],
        "crossCheck": {"state": state, "message": message},
    }


# ------------------------------------------------------------------------- selftest

def selftest() -> int:
    import tempfile
    n, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    def raises(fn, needle: str) -> bool:
        try:
            fn()
        except ArtifactError as exc:
            return needle in str(exc)
        return False

    got = read_frontmatter("---\nname: a\ndescription: >-\n  first line\n  second: colon\n  Use when: x\ntools: Read, Grep\nmodel: inherit\n---\nmodel: haiku\n")
    check("frontmatter: a folded scalar joins onto one line and a colon inside it is not a new key",
          got.get("description") == "first line second: colon Use when: x" and "Use when" not in got, str(got))
    check("frontmatter: plain fields parse, the body is not frontmatter", got.get("tools") == "Read, Grep" and got.get("model") == "inherit")
    check("names_agent: markup-blind and word-bounded -- backticks, bold, prose and a path all name it; a longer token does not",
          names_agent("run the `issue-triager` agent", "issue-triager") and names_agent("**issue-triager**", "issue-triager")
          and names_agent("see .claude/agents/issue-triager.md", "issue-triager")
          and not names_agent("issue-triagerx", "issue-triager") and not names_agent("meta-issue-triager", "issue-triager"))
    with tempfile.TemporaryDirectory() as td:
        d = Path(td) / "agents"; d.mkdir()
        (d / "ok.md").write_text("---\nname: ok-agent\ndescription: does x\ntools: Read\n---\nbody\n", encoding="utf-8")
        check("read_agents keys on frontmatter `name`, not the filename", [a["name"] for a in read_agents(d, "p", True)] == ["ok-agent"])
        (d / "nameless.md").write_text("---\ndescription: no name\n---\n", encoding="utf-8")
        check("an agent file with no `name:` is REFUSED, not skipped", raises(lambda: read_agents(d, "p", True), "declares no `name:`"))
        (d / "nameless.md").unlink()
        c = Path(td) / "commands"; c.mkdir()
        (c / "go.md").write_text("---\ndescription: runs\nargument-hint: <n>\n---\n<!-- topology: sequential -->\nuse `ok-agent`\n", encoding="utf-8")
        cmd = read_commands(c, "p", True, {"ok-agent"})[0]
        check("read_commands: invocation, topology, the agents it names", cmd["invocation"] == "/p:go" and cmd["topology"] == "sequential" and cmd["names"] == ["ok-agent"])
    agents = [{"name": "a", "owner": "p", "shipped": True, "model": "", "description": "d"}]
    check("verify_reconciled_agents: a model that differs between the two readers is refused",
          raises(lambda: verify_reconciled_agents(agents, "p", {"a": (Path("x"), "haiku")}), "one of the two frontmatter readers is wrong"))
    check("...and an agent one reader sees and the other does not", raises(lambda: verify_reconciled_agents(agents, "p", {}), "check_handoff does not"))
    import dataclasses
    fields = {f.name for f in dataclasses.fields(ch.TierRow)}
    def row(agent, tier="fast", proof="tests", line=1):
        kw = {"agent": agent, "tier": tier, "proof": proof, "line": line}
        if "model" in fields:
            kw["model"] = "haiku"
        return ch.TierRow(**kw)
    ok_rows = {"p": [row("a")]}
    check("verify_tier_join: one row per shipped agent is clean", verify_tier_join(agents, ok_rows) is None)
    check("...and a tier row naming no agent is refused", raises(lambda: verify_tier_join(agents, {"p": ok_rows["p"] + [row("ghost", proof="", line=9)]}), "no agent definition declares"))
    check("...and an agent with no tier row is refused", raises(lambda: verify_tier_join(agents, {"p": []}), "matches 0 tier rows"))
    check("verify_gate_scripts: a gate naming a script that does not exist is refused",
          raises(lambda: verify_gate_scripts([{"name": "g", "script": "scripts/nope.py"}]), "does not exist"))
    state, msg = cross_check_manifest(plugin_names())
    check("cross_check_manifest on the real repo is ok, and says how many", state == "ok" and str(len(plugin_names())) in msg, msg)
    check("...and it FAILS when a directory the manifest does not install is walked", cross_check_manifest(plugin_names() + ["phantom"])[0] == "fail")
    try:
        data = collect_data()
        check("the real repo builds: every gate in the registry is a row", data["totals"]["gates"] == len(md.GATES))
        check("every shipped agent carries exactly one tier", all(a["tier"] for a in data["agents"] if a["shipped"]))
        check("a shipped agent named by a command lists it", any(a["named_by"] for a in data["agents"] if a["shipped"]))
    except ArtifactError as exc:
        check("collect_data() refused to build the real repo", False, str(exc)[:200])
    for f in failures:
        print(f"FAIL {f}")
    print(f"inventory_data selftest: {n} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        data = collect_data()
    except ArtifactError as exc:
        print(f"cannot build the inventory:\n{exc}", file=sys.stderr)
        return 1
    print(json.dumps(data, indent=2) if a.json else f"{data['totals']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
