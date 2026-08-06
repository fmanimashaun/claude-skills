#!/usr/bin/env python3
"""Render what this marketplace ships -- agents, commands, gates -- as one filterable page.

Run:  python3 scripts/build_inventory.py              # write the HTML
      python3 scripts/build_inventory.py --out P      # ...somewhere else
      python3 scripts/build_inventory.py --check      # fail if the committed copy is stale
      python3 scripts/build_inventory.py --selftest   # prove the guards fire and stay silent

WHY (#509). We ship 27 agents, 37 commands and four model-tier tables across four plugins, and
carry 60-odd gates on top of them, and there is no map of any of it. A maintainer arriving here --
or a user deciding which plugin does what -- has `CLAUDE.md` prose and four plugin trees. The one
question that gets asked ("which agent owns this, what gate covers it, which command drives it")
cuts ACROSS agent / command / gate, so answering it today means three separate reads and holding
the join in your head. One table plus filter chips is not a prettier `ls`; it is the same data in
a shape that can answer that question.

WHY THIS IS NOT A DASHBOARD. #509 was prompted by a read-only observability dashboard and rejects
adopting one: it makes no enforcement claim, and a surface with no guarantee is a maintenance cost
this repo has argued against repeatedly. This is the opposite shape and deliberately the same shape
as `build_coverage_artifact.py` -- a generated page, COMMITTED, with a `--check` drift gate, over
inputs every clone already has. No runtime, no server, no dependency.

WHERE THE DATA COMES FROM, AND WHY EACH SOURCE IS IMPORTED RATHER THAN RE-PARSED

  * gates       -- `maintainer_doctor.GATES`, imported. It is a literal tuple; re-deriving it by
                   regex would be a second reader of the registry that decides what runs.
  * tier tables -- `check_handoff.parse_tiers`, imported. That module is the arbiter of the
                   `<!-- <plugin>:tiers:begin -->` block for four shipped gates; a second parser
                   here would be a fifth opinion on one contract, which is the failure its own
                   comments warn about ("four sources of truth for one contract").
  * agents      -- frontmatter, read HERE because the page needs `description` and `tools`, which
                   `check_handoff.agent_models` does not return. So the two parsers are reconciled
                   instead: `verify_reconciled_agents` asserts this module and the shipped one
                   agree on every agent's name and `model:`. That is a cross-check against another
                   implementation of the same read, not an assertion against ourselves.
  * commands    -- frontmatter, plus the `<!-- topology: ... -->` marker
                   `lint_self_consistency`'s `undeclared-topology` rule already reads, plus which
                   of its plugin's agents the command's text names. That last one is deliberately
                   a WIDER read than that rule's dispatch detection, and it measures a different
                   thing on purpose -- `names_agent` says why, and why the column is called
                   "Agents named" rather than anything implying a call graph.

THE THREE TRAPS THIS INHERITS FROM `build_coverage_artifact.py`. Its history records all three, and
every one of them broke a committed generated page in production:

  1. THE RENDERED BYTES ARE A FUNCTION OF THE DATA AND NOTHING ELSE. That page once embedded its
     own short SHA and branch, which made the gate unpassable by construction -- committing the
     page advances HEAD, and a file inside a commit cannot name its own commit. Then the dirty
     caveat did it again, more sharply. So this module reads git in exactly ONE place,
     `committed_blob`, which is used only by `--check` and never by the render. The page stamps the
     release version and the per-plugin versions, all from tracked JSON, and nothing else. The
     selftest COUNTS git invocations during a build and requires zero, which is stronger than
     comparing two renders under stubbed state (that comparison passes vacuously).
  2. NO NON-CONTENT INPUT. That page once walked the licensed corpora, so a machine without them
     committed null counts and broke the gate for everyone who had them. Every input here is a
     tracked file in every clone: `plugins/**`, `.claude/**`, `scripts/maintainer_doctor.py`,
     `.claude-plugin/marketplace.json`. Nothing optional, nothing generated, no network.
  3. `--check` COMPARES THE BLOB AT `HEAD`, never the file on disk. Testing the working copy is how
     a page built and never `git add`ed passed the gate whose own message says "is not committed".

REGENERATE IT WHEN THE VERSION MOVES. The page stamps the release version, exactly as
`docs/coverage.html` does and for the same reason -- it is the only freshness signal a shared copy
carries. So the arm step invalidates it and `inventory artifact drift` fails until it is rebuilt.
That is the gate working; the failure message names the command.

Exit codes:  0 clean · 1 drift · 2 a guard tripped (nothing is written)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(Path(__file__).resolve().parent))
# APPENDED, not inserted at 0: this directory holds a dozen modules with ordinary names, and
# putting it ahead of the stdlib to reach one of them is a shadowing hazard for a future file.
sys.path.append(str(REPO / "plugins" / "rails-flow" / "scripts"))

import check_handoff as ch  # noqa: E402  — the arbiter of the tier tables, imported not re-parsed
import maintainer_doctor as md  # noqa: E402  — the gate registry, imported not re-parsed

MARKETPLACE = REPO / ".claude-plugin" / "marketplace.json"
PLUGINS = REPO / "plugins"
MAINTAINER = REPO / ".claude"
# COMMITTED, deliberately, beside `docs/coverage.html`. The first version of that page wrote to a
# gitignored path, so "the deliverable existed only on the machine that built it" -- no other
# maintainer could see the thing it was for. `docs/` and not `skills/`, because anything under
# `skills/` is packaged into a `.skill` and shipped to agents, which an HTML page is not.
DEFAULT_OUT = REPO / "docs" / "inventory.html"

PLACEHOLDER = "__DATA__"
KIND_AGENT, KIND_COMMAND, KIND_GATE = "agent", "command", "gate"
OWNER_MAINTAINER = "maintainer"
OWNER_REPO = "repo"

# Frontmatter: a key at column 0 only. Continuation lines of a folded scalar are indented, so
# anchoring here is what stops "  Use when: authoring UI" being read as a `Use when` field.
FIELD_RE = re.compile(r"^(?P<key>[a-z][\w-]*)\s*:\s*(?P<value>.*?)\s*$")
BLOCK_SCALARS = frozenset({">", "|", ">-", "|-", ">+", "|+"})
TOPOLOGY_RE = re.compile(r"<!--\s*topology:\s*(sequential|parallel|loop|agent-to-agent)\b", re.I)


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


class ArtifactError(Exception):
    """A guard tripped. Never write a file after one of these."""


# ---------------------------------------------------------------------------- text

def inline(md_text: str) -> str:
    """Markdown inline -> HTML fragment.

    Escapes FIRST and unconditionally. Agent descriptions carry `<turbo-frame>`, `->` arrows and
    bare `&`, and every string here reaches the DOM through `innerHTML`.
    """
    s = html.escape(md_text.strip())
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", s)
    return s


def searchable(*parts: str) -> str:
    s = " ".join(p for p in parts if p)
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)
    return re.sub(r"[`*]", "", s).lower()


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

def verify_unique_ids(rows: list[dict]) -> None:
    """Every row needs a distinct id.

    The id is what the page's expand/collapse wiring keys on, so a collision does not error: two
    rows share one detail panel and the second silently shows the first's contract. An inventory
    that quietly mislabels a row is worse than one that is missing it.
    """
    seen: dict[str, int] = {}
    problems: list[str] = []
    for row in rows:
        if row["id"] in seen:
            problems.append(
                f"{row['id']!r} appears twice ({row['kind']} in {row['owner']}) — two rows would "
                "share one detail panel, so the second silently shows the first's contract"
            )
        seen[row["id"]] = 1
    if problems:
        raise ArtifactError("\n".join(f"  - {p}" for p in problems))


def verify_summaries(rows: list[dict]) -> None:
    """No agent or command may render a blank summary.

    A gate row's summary is its command line and cannot be empty. An agent or command row's is its
    `description:`, and an empty cell in a map reads as "this has no description", not as "the
    frontmatter is malformed" -- which is the failure a reader cannot distinguish from data.

    Reads the RENDERED summary rather than a second raw copy of the same string. `inline()` only
    escapes and unwraps, so it is empty exactly when its input is, and carrying the raw text in the
    payload as well would be a third copy of every description for no reader.
    """
    problems = [
        f"{row['kind']} {row['name']!r} ({row['owner']}) resolves no description — an empty cell "
        "in an inventory reads as an answer"
        for row in rows
        if row["kind"] in (KIND_AGENT, KIND_COMMAND) and not row["summaryHtml"].strip()
    ]
    if problems:
        raise ArtifactError("\n".join(f"  - {p}" for p in problems))


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

def _git(*args: str, raw: bool = False) -> str | None:
    """Run git, or return None if it cannot run at all.

    THE ONLY GIT IN THIS MODULE, and it is reachable only from `committed_blob`, which only
    `--check` calls. Nothing on the render path may read git: `build_coverage_artifact.py` embedded
    its own SHA, branch and dirty flag, and each made the committed bytes a function of the
    checkout, so the gate could pass only at the one commit that did not yet contain the file.
    """
    try:
        r = subprocess.run(("git", *args), cwd=REPO, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout if raw else r.stdout.strip()


def committed_blob(rel: Path | str) -> str | None:
    """The file's content **as committed at HEAD**, or None if it is not tracked there.

    Deliberately not `Path.read_text`. The gate's claim is that the page is a deliverable other
    maintainers can see, and only the committed blob supports that claim: a page built locally and
    never added -- or rebuilt and never committed -- is invisible to every other clone while
    sitting right there on disk. An earlier version of the sibling gate tested `is_file()` and
    waved through exactly that.
    """
    # git pathspecs are forward-slashed everywhere, including on Windows, where `str(Path)` is not.
    return _git("show", f"HEAD:{Path(rel).as_posix()}", raw=True)


def stamp(plugins: list[str]) -> dict:
    """The only version information the page carries -- all of it from tracked JSON.

    Not a provenance block. `build_coverage_artifact.py` had one and lost it in two rounds, each
    after it broke the gate: first the commit/branch/released split, then the dirty caveat. The
    release version is the freshness signal a shared copy needs, it lives in a tracked file, and it
    is the whole allowed surface.
    """
    versions: dict[str, str] = {}
    try:
        data = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
        versions["release"] = str(data.get("metadata", {}).get("version", ""))
        for entry in data.get("plugins", []):
            if entry.get("name") == "rails-stack" and entry.get("version"):
                versions["rails-stack"] = str(entry["version"])
    except (OSError, ValueError):
        pass
    for name in plugins:
        version = plugin_version(name)
        if version:
            versions[name] = version
    return {"label": f"Inventory as of v{versions.get('release') or '?'}", "versions": versions}


# --------------------------------------------------------------------------- data

def collect() -> dict:
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

    tier_of = {(plugin, row.agent): row for plugin, rows in tables.items() for row in rows}
    callers: dict[tuple[str, str], list[str]] = {}
    for command in commands:
        for agent in command["names"]:
            callers.setdefault((command["owner"], agent), []).append(command["invocation"])

    rows: list[dict] = []
    for agent in agents:
        tier = tier_of.get((agent["owner"], agent["name"]))
        model = agent["model"] or "inherit (default)"
        drivers = callers.get((agent["owner"], agent["name"]), [])
        detail = [("Description", inline(agent["description"]))]
        if agent["tools"]:
            detail.append(("Tools", inline(agent["tools"])))
        detail.append(("Model", inline(f"`{model}`")))
        if tier:
            detail.append(("Tier", inline(f"`{tier.tier}`")))
            detail.append(("What proves its output",
                           inline(tier.proof) if tier.proof.strip(" -—–") else "—"))
        detail.append(("Named by", inline(", ".join(f"`{d}`" for d in drivers)) if drivers
                       else "no command of its own plugin names it"))
        # NOT "orphaned". A command is one way an agent is reached, not the only one -- another
        # agent may hand off to it, and a user may invoke it directly. The row states what was
        # measured (which command texts name it) and stops there.
        detail.append(("Defined in", inline(f"`{agent['path']}`")))
        rows.append({
            "id": f"agent:{agent['owner']}:{agent['name']}",
            "name": agent["name"], "nameHtml": html.escape(agent["name"]),
            "kind": KIND_AGENT, "owner": agent["owner"], "shipped": agent["shipped"],
            "badge": f"{tier.tier} · {model}" if tier else model,
            "badgeClass": (tier.tier if tier else "unranked"),
            "summaryHtml": inline(agent["description"]),
            "detail": detail,
            "q": searchable(agent["name"], KIND_AGENT, agent["owner"], agent["description"],
                            agent["tools"], model, tier.tier if tier else "",
                            tier.proof if tier else "", " ".join(drivers)),
        })

    for command in commands:
        detail = [("Description", inline(command["description"]))]
        if command["argumentHint"]:
            detail.append(("Arguments", inline(f"`{command['argumentHint']}`")))
        detail.append(("Topology", inline(f"`{command['topology']}`") if command["topology"]
                       else "not declared"))
        detail.append(("Agents named",
                       inline(", ".join(f"`{a}`" for a in command["names"]))
                       if command["names"] else "none of its own plugin's agents"))
        detail.append(("Defined in", inline(f"`{command['path']}`")))
        rows.append({
            "id": f"command:{command['owner']}:{command['name']}",
            "name": command["invocation"], "nameHtml": html.escape(command["invocation"]),
            "kind": KIND_COMMAND, "owner": command["owner"], "shipped": command["shipped"],
            "badge": command["topology"] or (f"{len(command['names'])} agents"
                                             if command["names"] else "no agent named"),
            "badgeClass": command["topology"] or "plain",
            "summaryHtml": inline(command["description"]),
            "detail": detail,
            "q": searchable(command["invocation"], command["name"], KIND_COMMAND, command["owner"],
                            command["description"], command["argumentHint"], command["topology"],
                            " ".join(command["names"])),
        })

    for gate in gates:
        detail = [("Runs", inline(f"`{gate['command']}`")),
                  ("Subject", inline(f"`{gate['script']}`"))]
        if gate["corporaExempt"]:
            detail.append(("Corpora", "SKIPs when the licensed corpora are not attached — the one "
                                      "gate that genuinely enumerates them"))
        if gate["timeout"]:
            detail.append(("Timeout", inline(f"`{gate['timeout']}s` — its cost grows with the "
                                             "repo's own thoroughness")))
        rows.append({
            "id": f"gate:{gate['name']}",
            "name": gate["name"], "nameHtml": html.escape(gate["name"]),
            "kind": KIND_GATE, "owner": gate["owner"], "shipped": False,
            "badge": "selftest" if gate["selftest"] else "live check",
            "badgeClass": "selftest" if gate["selftest"] else "live",
            "summaryHtml": inline(f"`{gate['command']}`"),
            "detail": detail,
            "q": searchable(gate["name"], KIND_GATE, gate["owner"], gate["command"]),
        })

    verify_unique_ids(rows)
    verify_summaries(rows)
    rows.sort(key=lambda r: (r["kind"], r["owner"], r["name"]))

    state, message = cross_check_manifest(plugins)
    if state == "fail":
        raise ArtifactError(f"  - {message}")

    shipped_agents = [a for a in agents if a["shipped"]]
    shipped_commands = [c for c in commands if c["shipped"]]
    totals = {
        "agents": len(shipped_agents),
        "commands": len(shipped_commands),
        "gates": len(gates),
        "tierTables": len(tables),
        "maintainerAgents": len(agents) - len(shipped_agents),
        "maintainerCommands": len(commands) - len(shipped_commands),
        "rows": len(rows),
    }

    return {
        "rows": rows,
        "totals": totals,
        "owners": [*plugins, OWNER_MAINTAINER, OWNER_REPO],
        "plugins": [{
            "name": plugin,
            "version": plugin_version(plugin),
            "agents": sum(1 for a in shipped_agents if a["owner"] == plugin),
            "commands": sum(1 for c in shipped_commands if c["owner"] == plugin),
            "tierRows": len(tables.get(plugin, [])),
            "gates": sum(1 for g in gates if g["owner"] == plugin),
        } for plugin in plugins],
        "crossCheck": {"state": state, "message": message},
        "stamp": stamp(plugins),
    }


def render(data: dict) -> str:
    """Substitute the data blob into the template.

    `json.dumps` escapes what JSON needs, which is NOT what an inline `<script>` needs: a literal
    `</script>` or `<!--` inside any string would end the script element early and the rest of the
    page would render as text. The corpus makes this concrete rather than theoretical -- five
    commands carry a literal `<!-- topology: ... -->` marker, and command bodies quote HTML. HTML
    escaping cannot help (the blob is parsed as JavaScript), so the two sequences are broken with
    `\\/` and `\\u002D`, both valid JSON escapes, leaving the parsed value unchanged.
    """
    # CHECKED BEFORE SUBSTITUTION, not after. `str.replace` replaces every occurrence, so a
    # placeholder can never "survive" -- testing for one afterwards is a guard that cannot fire,
    # and it would only ever trip on a description that legitimately contained the token. The real
    # failure is the template LOSING its placeholder (the page then ships with no data at all) or
    # gaining a second one (the whole blob is emitted twice). Both are visible only here.
    slots = TEMPLATE.count(PLACEHOLDER)
    if slots != 1:
        raise ArtifactError(
            f"  - the template holds {slots} `{PLACEHOLDER}` slots, need exactly 1 — none means "
            "the page ships with no data, two means the blob is emitted twice")
    blob = json.dumps(data, ensure_ascii=False)
    # `<!--` keeps the `!` — escaping to `<--` would decode to `<--`, silently changing the value.
    blob = blob.replace("</", "<\\/").replace("<!--", "<!\\u002D\\u002D")
    doc = TEMPLATE.replace(PLACEHOLDER, blob)
    # Check the emitted SCRIPT BODY, not the whole document: the template's own closing tag is
    # legitimate, so scanning `doc` would flag every successful build.
    body = doc[doc.index("const DATA = "):doc.rindex("</script>")]
    if "</script" in body or "<!--" in body:
        raise ArtifactError(
            "  - the data blob still contains a script-terminating sequence after escaping")
    return doc


# ----------------------------------------------------------------------- template

TEMPLATE = r"""<title>What this marketplace ships</title>
<style>
/* ---------------------------------------------------------------------- tokens
   The fidara kit's own values, from skills/fidara-design/references/foundations-tokens.md:
   fm-* primitives bound through the semantic role layer, exactly as docs/coverage.html
   does. A page about this marketplace has no business inventing a look. */
:root {
  --fm-navy:#0C1B33; --fm-ink:#1A2B45; --fm-midnight:#152238;
  --fm-cerulean:#0077CC; --fm-electric:#00A3FF;
  --fm-success:#22C55E; --fm-warning:#F59E0B;
  --s50:#F8F9FB; --s100:#F1F3F7; --s200:#E2E6ED; --s300:#C8CDD8; --s400:#8F96A3;
  --s500:#5E6775; --s800:#1C2531; --s900:#0F1520;

  --background:var(--s50); --foreground:var(--s900);
  --card:#FFFFFF; --muted:var(--s100); --muted-foreground:var(--s500);
  --border:var(--s200); --hairline:var(--s200);
  --primary:var(--fm-cerulean); --primary-foreground:#FFFFFF; --ring:var(--fm-cerulean);
  --chip:#FFFFFF; --chip-border:var(--s300);
  --tint:rgba(0,119,204,.06);
  --ok-fg:#166534; --ok-bg:rgba(34,197,94,.13); --ok-bd:rgba(34,197,94,.30);
  --info-fg:#075985; --info-bg:rgba(0,119,204,.12); --info-bd:rgba(0,119,204,.28);
  --warn-fg:#92400E; --warn-bg:rgba(245,158,11,.15); --warn-bd:rgba(245,158,11,.35);
  --bad-fg:#991B1B;

  --step--2:clamp(.72rem,.70rem + .10vw,.78rem);
  --step--1:clamp(.833rem,.80rem + .15vw,.9rem);
  --step-0:clamp(1rem,.95rem + .25vw,1.125rem);
  --step-1:clamp(1.2rem,1.12rem + .4vw,1.42rem);
  --step-2:clamp(1.44rem,1.31rem + .65vw,1.8rem);
  --step-3:clamp(1.73rem,1.54rem + .97vw,2.28rem);
  --space-2xs:clamp(.5rem,.46rem + .18vw,.625rem);
  --space-xs:clamp(.75rem,.70rem + .27vw,.9375rem);
  --space-s:clamp(1rem,.93rem + .36vw,1.25rem);
  --space-m:clamp(1.5rem,1.39rem + .54vw,1.875rem);
  --space-l:clamp(2rem,1.86rem + .71vw,2.5rem);
  --width-shell:80rem; --measure:65ch;
  --radius:.5rem; --radius-sm:calc(var(--radius) - 2px);
  --shadow-xs:0 1px 2px rgb(12 27 51 / .04);
  --ease-out:cubic-bezier(.16,1,.3,1); --duration-fast:120ms; --duration:180ms;

  /* Brand faces if the viewer has them, else the stacks the token file declares. No CDN
     <link>: a blocked font host is a silent fallback wearing a webfont's clothes. */
  --font-sans:"Bricolage Grotesque",ui-sans-serif,system-ui,sans-serif;
  --font-display:"Newsreader",ui-serif,Georgia,serif;
  --font-mono:"Overpass Mono",ui-monospace,SFMono-Regular,monospace;
}
/* dark re-points the ROLES only; component rules below never name a theme. */
@media (prefers-color-scheme:dark){:root{
  --background:var(--fm-navy); --foreground:var(--s50);
  --card:var(--fm-ink); --muted:var(--s800); --muted-foreground:var(--s400);
  --border:var(--s800); --hairline:#243349;
  --primary:var(--fm-electric); --primary-foreground:var(--fm-navy); --ring:var(--fm-electric);
  --chip:var(--fm-midnight); --chip-border:#2C3E58;
  --tint:rgba(0,163,255,.09);
  --ok-fg:#7EE2A8; --info-fg:#7CD4FF; --warn-fg:#FCD34D; --bad-fg:#FCA5A5;
}}
:root[data-theme="dark"]{
  --background:var(--fm-navy); --foreground:var(--s50);
  --card:var(--fm-ink); --muted:var(--s800); --muted-foreground:var(--s400);
  --border:var(--s800); --hairline:#243349;
  --primary:var(--fm-electric); --primary-foreground:var(--fm-navy); --ring:var(--fm-electric);
  --chip:var(--fm-midnight); --chip-border:#2C3E58;
  --tint:rgba(0,163,255,.09);
  --ok-fg:#7EE2A8; --info-fg:#7CD4FF; --warn-fg:#FCD34D; --bad-fg:#FCA5A5;
}
:root[data-theme="light"]{
  --background:var(--s50); --foreground:var(--s900);
  --card:#FFFFFF; --muted:var(--s100); --muted-foreground:var(--s500);
  --border:var(--s200); --hairline:var(--s200);
  --primary:var(--fm-cerulean); --primary-foreground:#FFFFFF; --ring:var(--fm-cerulean);
  --chip:#FFFFFF; --chip-border:var(--s300);
  --tint:rgba(0,119,204,.06);
  --ok-fg:#166534; --info-fg:#075985; --warn-fg:#92400E; --bad-fg:#991B1B;
}

/* ------------------------------------------------------------------------ base */
*{box-sizing:border-box}
body{margin:0; background:var(--background); color:var(--foreground);
  font-family:var(--font-sans); font-size:var(--step-0); line-height:1.55;
  -webkit-font-smoothing:antialiased}
.shell{max-inline-size:var(--width-shell); margin-inline:auto; padding-inline:var(--space-s)}
code{font-family:var(--font-mono); font-size:.92em; background:var(--muted);
  padding:.1em .35em; border-radius:var(--radius-sm); overflow-wrap:anywhere}
:where(a,button,input):focus-visible{outline:2px solid var(--ring); outline-offset:2px}
.sr{position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden;
  clip-path:inset(50%); white-space:nowrap; border:0}
@media (prefers-reduced-motion:reduce){*{transition-duration:0ms !important}}

/* -------------------------------------------------------------------- masthead */
.masthead{padding-block:var(--space-l) var(--space-s)}
.eyebrow{font-size:var(--step--2); text-transform:uppercase; letter-spacing:.09em;
  font-weight:600; color:var(--muted-foreground); margin:0 0 var(--space-2xs)}
h1{font-size:var(--step-3); line-height:1.1; margin:0; font-weight:640;
  text-wrap:balance; letter-spacing:-.015em}
.tagline{font-family:var(--font-display); font-style:italic; font-size:var(--step-1);
  color:var(--muted-foreground); margin:var(--space-2xs) 0 0;
  max-inline-size:var(--measure); text-wrap:balance}
.stamp{display:flex; flex-wrap:wrap; gap:var(--space-2xs) var(--space-s); align-items:baseline;
  margin-top:var(--space-s); padding:var(--space-2xs) var(--space-xs);
  border:1px solid var(--border); border-left:3px solid var(--fm-success);
  border-radius:var(--radius-sm); background:var(--card); font-size:var(--step--1)}
.stamp .badge{font-size:var(--step--2); font-weight:700; text-transform:uppercase;
  letter-spacing:.06em; padding:.15rem .5rem; border-radius:99px;
  color:var(--ok-fg); background:var(--ok-bg); border:1px solid var(--ok-bd)}
.stamp .meta{color:var(--muted-foreground)}
.stamp .meta b{color:var(--foreground); font-family:var(--font-mono); font-weight:400}
.provenance{margin:var(--space-s) 0 0; font-size:var(--step--1);
  color:var(--muted-foreground); max-inline-size:var(--measure)}
.provenance code{background:transparent; padding:0; color:var(--foreground)}

/* ----------------------------------------------------------------- stat tiles */
.tiles{display:grid; gap:var(--space-xs); grid-template-columns:repeat(auto-fit,minmax(10rem,1fr));
  margin-block:var(--space-m)}
.tile{background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:var(--shadow-xs); padding:var(--space-xs) var(--space-s)}
.tile .k{font-size:var(--step--2); text-transform:uppercase; letter-spacing:.07em;
  font-weight:600; color:var(--muted-foreground)}
.tile .v{font-size:var(--step-2); font-weight:650; font-variant-numeric:tabular-nums;
  line-height:1.15; margin-top:.15em; letter-spacing:-.02em}
.tile .sub{font-size:var(--step--2); color:var(--muted-foreground); margin-top:.2em}

/* ------------------------------------------------------------------- controls */
.controls{position:sticky; top:0; z-index:5; background:var(--background);
  border-block:1px solid var(--hairline); padding-block:var(--space-xs)}
.controls .row{display:flex; flex-wrap:wrap; gap:var(--space-xs); align-items:center}
.controls .row + .row{margin-top:.5rem}
.search{flex:1 1 16rem; min-inline-size:0; display:flex}
.search input{inline-size:100%; font:inherit; font-size:var(--step--1);
  font-family:var(--font-sans); padding:.5rem .75rem; height:2.25rem;
  color:var(--foreground); background:var(--card); border:1px solid var(--chip-border);
  border-radius:var(--radius-sm)}
.search input::placeholder{color:var(--muted-foreground)}
.group{display:flex; flex-wrap:wrap; gap:.35rem; align-items:center}
.group > .lbl{font-size:var(--step--2); text-transform:uppercase; letter-spacing:.07em;
  font-weight:600; color:var(--muted-foreground); margin-inline-end:.15rem}
.chip{font:inherit; font-size:var(--step--1); font-family:var(--font-sans); line-height:1;
  padding:.4rem .7rem; min-height:2rem; cursor:pointer; color:var(--foreground);
  background:var(--chip); border:1px solid var(--chip-border); border-radius:99px;
  display:inline-flex; align-items:center; gap:.4em;
  transition:background var(--duration-fast) var(--ease-out),
             border-color var(--duration-fast) var(--ease-out)}
.chip:hover{background:var(--muted)}
.chip[aria-pressed="true"]{background:var(--primary); border-color:var(--primary);
  color:var(--primary-foreground)}
.chip[aria-pressed="true"] .dot{box-shadow:0 0 0 1px var(--primary-foreground)}
.dot{width:.5rem; height:.5rem; border-radius:99px; flex:none}
.dot.agent{background:var(--fm-success)}
.dot.command{background:var(--primary)}
.dot.gate{background:var(--fm-warning)}
.reset{margin-inline-start:auto; font:inherit; font-size:var(--step--1);
  font-family:var(--font-sans); background:none; border:0; color:var(--primary);
  cursor:pointer; padding:.4rem .25rem; text-decoration:underline; text-underline-offset:3px}
.count{font-size:var(--step--1); color:var(--muted-foreground);
  padding-block:var(--space-2xs); margin:0; font-variant-numeric:tabular-nums}
.count b{color:var(--foreground)}

/* ---------------------------------------------------------------------- table */
.tablewrap{overflow-x:auto; border:1px solid var(--border); border-radius:var(--radius);
  background:var(--card); margin-block:var(--space-m) var(--space-l)}
table{border-collapse:collapse; inline-size:100%; min-inline-size:46rem}
thead th{position:sticky; top:0; background:var(--card); text-align:left;
  font-size:var(--step--2); text-transform:uppercase; letter-spacing:.07em; font-weight:600;
  color:var(--muted-foreground); padding:.7rem var(--space-xs);
  border-bottom:1px solid var(--border); white-space:nowrap}
tbody td{font-size:var(--step--1); padding:.55rem var(--space-xs); vertical-align:top;
  border-bottom:1px solid var(--hairline)}
tbody tr.entry:hover td,tbody tr.entry.open td{background:var(--tint)}
td.stripe{padding:0; width:3px}
td.stripe i{display:block; inline-size:3px; block-size:100%; min-block-size:2.2rem}
tr.agent td.stripe i{background:var(--fm-success)}
tr.command td.stripe i{background:var(--primary)}
tr.gate td.stripe i{background:var(--fm-warning)}
.namebtn{font:inherit; font-size:var(--step--1); font-family:var(--font-mono);
  font-weight:500; text-align:left; background:none; border:0; padding:0;
  color:var(--foreground); cursor:pointer; display:flex; gap:.5em; align-items:baseline;
  inline-size:100%}
.namebtn:hover{color:var(--primary)}
.namebtn .caret{flex:none; font-size:.7em; font-family:var(--font-sans);
  color:var(--muted-foreground); display:inline-block;
  transition:transform var(--duration) var(--ease-out); translate:0 -.1em}
.namebtn[aria-expanded="true"] .caret{transform:rotate(90deg); color:var(--primary)}
.owner{font-size:var(--step--2); color:var(--muted-foreground); white-space:nowrap}
.owner .ship{display:block; font-size:.9em; opacity:.8}
.pill{display:inline-block; font-size:var(--step--2); font-weight:600; white-space:nowrap;
  padding:.15rem .5rem; border-radius:99px; border:1px solid transparent;
  color:var(--info-fg); background:var(--info-bg); border-color:var(--info-bd)}
.pill.judgement{color:var(--ok-fg); background:var(--ok-bg); border-color:var(--ok-bd)}
.pill.mechanical{color:var(--warn-fg); background:var(--warn-bg); border-color:var(--warn-bd)}
.pill.selftest{color:var(--ok-fg); background:var(--ok-bg); border-color:var(--ok-bd)}
.pill.parallel,.pill.loop{color:var(--warn-fg); background:var(--warn-bg);
  border-color:var(--warn-bd)}
.summary{color:var(--muted-foreground)}
.summary .clamp{display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;
  overflow:hidden; max-inline-size:52ch}
tr.detail > td{padding:0 var(--space-xs) var(--space-s); background:var(--tint);
  border-bottom:1px solid var(--hairline)}
tr.detail dl{margin:0; display:grid; gap:var(--space-2xs) var(--space-s);
  grid-template-columns:max-content minmax(0,var(--measure))}
tr.detail dt{font-size:var(--step--2); text-transform:uppercase; letter-spacing:.07em;
  font-weight:600; color:var(--muted-foreground); padding-top:.15em}
tr.detail dd{margin:0; font-size:var(--step--1); min-inline-size:0; overflow-wrap:anywhere}
@media (max-width:44rem){
  tr.detail dl{grid-template-columns:1fr}
  tr.detail dt{padding-top:var(--space-2xs)}
}
.empty{padding:var(--space-l); text-align:center; color:var(--muted-foreground);
  font-size:var(--step--1); margin:0}

/* --------------------------------------------------------------------- panels */
h2{font-size:var(--step-2); font-weight:620; margin:0 0 var(--space-2xs); letter-spacing:-.01em}
.lede{color:var(--muted-foreground); font-size:var(--step-0);
  max-inline-size:var(--measure); margin:0 0 var(--space-s)}
.panels{display:grid; gap:var(--space-s);
  grid-template-columns:repeat(auto-fit,minmax(15rem,1fr)); margin-bottom:var(--space-l)}
.panel{background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
  box-shadow:var(--shadow-xs); padding:var(--space-s)}
.panel h3{font-size:var(--step-1); font-weight:620; margin:0 0 .1em;
  font-family:var(--font-mono)}
.panel .ver{font-size:var(--step--2); color:var(--muted-foreground);
  font-family:var(--font-mono); margin:0 0 var(--space-xs)}
.panel dl{margin:0; display:grid; grid-template-columns:1fr max-content; gap:.3rem .5rem;
  font-size:var(--step--1)}
.panel dt{color:var(--muted-foreground)}
.panel dd{margin:0; font-variant-numeric:tabular-nums; font-weight:600}

footer{border-top:1px solid var(--hairline); padding-block:var(--space-m) var(--space-l);
  font-size:var(--step--2); color:var(--muted-foreground); max-inline-size:var(--measure)}
footer p{margin:0 0 var(--space-2xs)}
footer .xc.fail{color:var(--bad-fg)} footer .xc.skip{color:var(--warn-fg)}
</style>

<div class="shell">
  <header class="masthead">
    <p class="eyebrow">claude-skills · marketplace inventory</p>
    <h1>What this marketplace ships</h1>
    <p class="tagline">Every agent, command and gate in one table — so "which agent owns this,
      what gate covers it, which command drives it" is one search, not four plugin trees.</p>
    <div class="stamp" id="stamp"></div>
    <p class="provenance">Generated from the plugins themselves — agent and command frontmatter,
      the <code>&lt;plugin&gt;:tiers</code> tables parsed by
      <code>plugins/rails-flow/scripts/check_handoff.py</code>, and the gate registry in
      <code>scripts/maintainer_doctor.py</code> — imported rather than re-parsed. Rebuild with
      <code>python3 scripts/build_inventory.py</code>.</p>
  </header>

  <section class="tiles" aria-label="Totals">
    <div class="tile"><div class="k">Shipped agents</div><div class="v" id="t-agents">—</div>
      <div class="sub" id="t-agents-sub"></div></div>
    <div class="tile"><div class="k">Shipped commands</div><div class="v" id="t-commands">—</div>
      <div class="sub" id="t-commands-sub"></div></div>
    <div class="tile"><div class="k">Model-tier tables</div><div class="v" id="t-tiers">—</div>
      <div class="sub">one per plugin, each reconciled by a gate</div></div>
    <div class="tile"><div class="k">Gates</div><div class="v" id="t-gates">—</div>
      <div class="sub" id="t-gates-sub"></div></div>
  </section>

  <div class="controls">
    <div class="row">
      <div class="search">
        <label class="sr" for="q">Search the inventory</label>
        <input id="q" type="search" placeholder="Search name, description, tool, tier or command…"
               autocomplete="off">
      </div>
      <div class="group" id="f-kind" role="group" aria-label="Filter by kind"></div>
      <button class="reset" type="button" id="reset">Clear filters</button>
    </div>
    <div class="row">
      <div class="group" id="f-owner" role="group" aria-label="Filter by owner"></div>
      <div class="group" id="f-ship" role="group" aria-label="Filter by distribution"></div>
    </div>
    <p class="count" id="count" aria-live="polite"></p>
  </div>

  <div class="tablewrap">
    <table>
      <thead>
        <tr>
          <th><span class="sr">Kind colour</span></th>
          <th scope="col">Name</th>
          <th scope="col">Kind</th>
          <th scope="col">Owner</th>
          <th scope="col">Runs as</th>
          <th scope="col">Summary</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
    <p class="empty" id="empty" hidden>Nothing matches those filters.</p>
  </div>

  <h2>Per plugin</h2>
  <p class="lede">Each plugin installs from its own <code>source:</code> in the marketplace
    manifest and versions independently, so these are four separate install surfaces rather than
    four folders.</p>
  <div class="panels" id="panels"></div>

  <footer>
    <p id="xc"></p>
    <p><b>“Agents named” means named, not proven to be dispatched.</b> It is a word-bounded,
      markup-blind search of the command's text for the agents of its own plugin — backticked,
      bold and plain prose all count, because emphasis is a typographic choice and reading it as a
      semantic one invents distinctions the corpus does not draw. Dispatch is intent, which no
      search can see. So read this as <i>where to look</i>, not as a call graph — and an empty
      list means the text names none of them, which is a search over the whole body.</p>
    <p>Rows marked <b>maintainer</b> or <b>repo</b> live under <code>.claude/</code> and
      <code>scripts/</code>. They are <b>not</b> part of the marketplace and
      <code>/plugin marketplace add</code> never installs them — anyone who clones the repo gets
      them, which is the point.</p>
    <p>Brand faces (Bricolage Grotesque · Newsreader · Overpass Mono) render if installed locally;
      otherwise this falls back to the stacks the fidara token file itself declares.</p>
  </footer>
</div>

<script>
const DATA = __DATA__;
const E = DATA.rows;

const KINDS = [['agent','Agents'],['command','Commands'],['gate','Gates']];
const SHIP = [['shipped','Shipped to users'],['internal','Maintainer-only']];
const state = {q:'', kind:new Set(), owner:new Set(), ship:new Set()};

/* ---- version stamp: the ONLY thing this page says about its own vintage ----
   Deliberately nothing about the checkout — no commit, no branch, no dirty flag. Every one of
   those makes the committed bytes a function of git state, so the --check gate cannot pass. */
{
  const s = DATA.stamp, v = s.versions, bits = [];
  for (const [k, val] of Object.entries(v)) {
    if (k !== 'release') bits.push(`${k} <b>${val}</b>`);
  }
  document.getElementById('stamp').innerHTML =
    `<span class="badge">${s.label}</span><span class="meta">${bits.join(' · ')}</span>`;
}

/* ---- totals ---- */
const T = DATA.totals;
document.getElementById('t-agents').textContent = T.agents;
document.getElementById('t-agents-sub').textContent =
  `+ ${T.maintainerAgents} maintainer-only`;
document.getElementById('t-commands').textContent = T.commands;
document.getElementById('t-commands-sub').textContent =
  `+ ${T.maintainerCommands} maintainer-only`;
document.getElementById('t-tiers').textContent = T.tierTables;
document.getElementById('t-gates').textContent = T.gates;
document.getElementById('t-gates-sub').textContent =
  `run by maintainer_doctor.py --gates-only`;

/* ---- filter chips ---- */
function chips(host, items, group, withDot) {
  for (const [val,label] of items) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'chip';
    b.setAttribute('aria-pressed','false');
    b.innerHTML = (withDot ? `<span class="dot ${val}"></span>` : '') + label;
    b.addEventListener('click', () => {
      const on = b.getAttribute('aria-pressed') === 'true';
      b.setAttribute('aria-pressed', String(!on));
      if (on) state[group].delete(val); else state[group].add(val);
      render();
    });
    host.append(b);
  }
}
for (const [id, items, group, dot, label] of [
  ['f-kind', KINDS, 'kind', true, 'Kind'],
  ['f-owner', DATA.owners.map(o => [o,o]), 'owner', false, 'Owner'],
  ['f-ship', SHIP, 'ship', false, 'Ships'],
]) {
  const host = document.getElementById(id);
  const lbl = document.createElement('span');
  lbl.className = 'lbl'; lbl.textContent = label;
  host.append(lbl);
  chips(host, items, group, dot);
}
document.getElementById('q').addEventListener('input', e => {
  state.q = e.target.value.trim().toLowerCase(); render();
});
document.getElementById('reset').addEventListener('click', () => {
  state.q = ''; state.kind.clear(); state.owner.clear(); state.ship.clear();
  document.getElementById('q').value = '';
  document.querySelectorAll('.chip').forEach(c => c.setAttribute('aria-pressed','false'));
  render();
});

/* ---- rows ---- */
const tbody = document.getElementById('tbody');
E.forEach((e, i) => {
  const tr = document.createElement('tr');
  tr.className = 'entry ' + e.kind;
  tr.dataset.i = String(i);
  tr.innerHTML = `
    <td class="stripe"><i></i></td>
    <td>
      <button class="namebtn" type="button" aria-expanded="false" aria-controls="d${i}">
        <span class="caret" aria-hidden="true">&#9654;</span>
        <span>${e.nameHtml}</span>
      </button>
    </td>
    <td class="owner">${e.kind}</td>
    <td class="owner">${e.owner}<span class="ship">${e.shipped ? 'shipped' : 'internal'}</span></td>
    <td><span class="pill ${e.badgeClass}">${e.badge}</span></td>
    <td class="summary"><span class="clamp">${e.summaryHtml}</span></td>`;

  const detail = document.createElement('tr');
  detail.className = 'detail ' + e.kind;
  detail.id = 'd' + i;
  detail.hidden = true;
  detail.innerHTML = '<td></td><td colspan="5"><dl>' +
    e.detail.map(([k,v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('') + '</dl></td>';

  const btn = tr.querySelector('.namebtn');
  btn.addEventListener('click', () => {
    const open = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', String(!open));
    detail.hidden = open;
    tr.classList.toggle('open', !open);
  });
  tbody.append(tr, detail);
});

function matches(e) {
  if (state.q && !e.q.includes(state.q)) return false;
  if (state.kind.size && !state.kind.has(e.kind)) return false;
  if (state.owner.size && !state.owner.has(e.owner)) return false;
  if (state.ship.size && !state.ship.has(e.shipped ? 'shipped' : 'internal')) return false;
  return true;
}

const countEl = document.getElementById('count'), emptyEl = document.getElementById('empty');
function render() {
  let shown = 0;
  tbody.querySelectorAll('tr.entry').forEach(tr => {
    const ok = matches(E[+tr.dataset.i]);
    tr.hidden = !ok;
    const detail = document.getElementById('d' + tr.dataset.i);
    if (!ok) {
      detail.hidden = true;
      tr.classList.remove('open');
      tr.querySelector('.namebtn').setAttribute('aria-expanded','false');
    } else shown++;
  });
  const filtered = state.q || state.kind.size || state.owner.size || state.ship.size;
  countEl.innerHTML = filtered
    ? `Showing <b>${shown}</b> of ${E.length} entries`
    : `<b>${E.length}</b> entries — click any row for its full contract`;
  emptyEl.hidden = shown > 0;
}
render();

/* ---- per-plugin panels ---- */
for (const p of DATA.plugins) {
  const el = document.createElement('section');
  el.className = 'panel';
  el.innerHTML = `<h3>${p.name}</h3><p class="ver">v${p.version || '?'}</p>` +
    `<dl><dt>agents</dt><dd>${p.agents}</dd>` +
    `<dt>commands</dt><dd>${p.commands}</dd>` +
    `<dt>tier rows</dt><dd>${p.tierRows}</dd>` +
    `<dt>gates over it</dt><dd>${p.gates}</dd></dl>`;
  document.getElementById('panels').append(el);
}

/* ---- footer: report the cross-check honestly, including when it did not run ---- */
{
  const xc = DATA.crossCheck, el = document.getElementById('xc');
  el.className = 'xc ' + xc.state;
  el.textContent = `Manifest cross-check: ${xc.state} — ${xc.message}.`;
}
</script>
"""


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render the marketplace's agent / command / gate inventory as an HTML page.")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT,
                        help=f"where to write (default {DEFAULT_OUT.relative_to(REPO)})")
    parser.add_argument("--selftest", action="store_true",
                        help="prove the guards fire and stay silent")
    parser.add_argument("--check", action="store_true",
                        help="fail if the committed artifact is not a clean build (drift gate)")
    args = parser.parse_args(argv)

    if args.selftest:
        import build_inventory_selftest as st
        return st.run()

    try:
        data = collect()
        doc = render(data)
    except ArtifactError as exc:
        print(f"INVENTORY BUILD FAILED:\n{exc}", file=sys.stderr)
        return 2

    rel_out = args.out.relative_to(REPO) if args.out.is_relative_to(REPO) else args.out

    if args.check:
        # NO DIRTY-TREE SKIP, for the reason its sibling gate removed one: a gate that skips during
        # normal work barely runs, and mid-edit the honest answer is a real verdict ("the committed
        # page does not match your data, regenerate it"), not "cannot tell". Compared as TEXT, not
        # bytes, so a checkout that normalised line endings is not reported as drift.
        remedy = "  -> python3 scripts/build_inventory.py && git add docs/"
        committed = committed_blob(rel_out)
        if committed is None:
            print(f"DRIFT: {rel_out} is not committed — the artifact is a deliverable other "
                  f"machines must be able to see, not a local build.\n{remedy}", file=sys.stderr)
            return 1
        if committed.replace("\r\n", "\n") != doc.replace("\r\n", "\n"):
            print(f"DRIFT: committed {rel_out} is not a clean build — an agent, command, gate or "
                  f"version moved and the page was not regenerated.\n{remedy}", file=sys.stderr)
            return 1
        print(f"{rel_out} matches a clean build.")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(doc, encoding="utf-8")

    t, xc = data["totals"], data["crossCheck"]
    print(f"wrote {rel_out} — {t['rows']} rows "
          f"({t['agents']} shipped agents / {t['commands']} shipped commands / {t['gates']} gates; "
          f"+{t['maintainerAgents']} maintainer agents, +{t['maintainerCommands']} maintainer "
          f"commands)")
    print(f"  tier tables: {t['tierTables']}")
    print(f"  cross-check: {xc['state']} — {xc['message']}")
    print(f"  {data['stamp']['label']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
