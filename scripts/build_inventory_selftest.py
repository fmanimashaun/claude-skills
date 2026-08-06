#!/usr/bin/env python3
"""Prove the inventory guards fire -- and stay silent on the real plugins.

Run:  python3 scripts/build_inventory.py --selftest   (or execute this file directly)

WHAT THIS IS DEFENDING. `docs/inventory.html` is a COMMITTED generated page, so it inherits the
three failures `build_coverage_artifact.py` recorded, and every one of them reads as success:

  1. A page whose bytes depend on the CHECKOUT makes its own gate unpassable -- a file inside a
     commit cannot name its own commit. Pinned two ways here, one structural and one direct:
     `test_no_git_on_the_render_path` counts every call to `_git` while building the page and
     requires ZERO, and then asserts HEAD's own short SHA does not appear in the output.
  2. A page whose bytes depend on something not every clone has breaks the gate for whoever has
     it. Every input here is tracked, so the corresponding fixture is `test_real_build`: it runs
     the whole pipeline over the real repo, which is the only place the claim can be falsified.
  3. `--check` reading the WORKING COPY passes a page nobody committed. Seven fixtures below vary
     the committed blob and leave the file on disk alone, precisely so a `Path.read_text`
     regression cannot pass them.

AND THE ONE FAILURE THAT IS SPECIFIC TO THIS PAGE. An inventory's whole claim is completeness, so
a row that silently DISAPPEARS is the worst outcome and looks identical to a row that never
existed. Three guards exist for that shape and all three are observed failing here:
`verify_reconciled_agents` (two frontmatter readers disagreeing), `verify_tier_join` (an agent with
no tier row, or a tier row with no agent) and `verify_unique_ids` (two rows sharing one detail
panel, so the second silently shows the first's contract).

THE CARVE-OUT GETS A NEGATIVE TEST. `verify_summaries` deliberately exempts gate rows, whose
summary is a command line rather than a description. An exemption with no fixture proving it stays
narrow is the `carve-out-without-negative-test` class from the shipped `code-review` skill, so
there is a fixture for the exempt side as well as the enforced one.

Costs nothing: no network, no licensed corpora, no interpreter beyond python3.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_inventory as bi  # noqa: E402
import check_handoff as ch  # noqa: E402

FAILURES: list[str] = []
SKIPPED: list[str] = []
CHECKS = 0
# The one real `collect()` of the run, built first by `run()` and read by most fixtures below.
REAL: dict = {}


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def expect_raises(label: str, fn, needle: str = "") -> None:
    """A guard must FIRE. A check never observed failing is not known to work."""
    _tick()
    try:
        fn()
    except bi.ArtifactError as exc:
        if needle and needle not in str(exc):
            FAILURES.append(f"{label}: fired, but message lacks {needle!r}:\n{exc}")
    else:
        FAILURES.append(f"{label}: expected ArtifactError, none raised")


def expect_clean(label: str, fn) -> None:
    """A guard must STAY SILENT on conforming input."""
    _tick()
    try:
        fn()
    except bi.ArtifactError as exc:
        FAILURES.append(f"{label}: expected clean, got ArtifactError:\n{exc}")


def check(label: str, condition: bool, detail: str = "") -> None:
    _tick()
    if not condition:
        FAILURES.append(f"{label}: {detail or 'assertion failed'}")


def row(kind: str, name: str, owner: str = "qa-flow", summary: str = "does a thing") -> dict:
    """A minimal row of the shape `collect()` emits, for the guards that take rows."""
    return {"id": f"{kind}:{owner}:{name}", "name": name, "kind": kind, "owner": owner,
            "summaryHtml": summary}


# ------------------------------------------------------------------- frontmatter

# The continuation lines are chosen to DISCRIMINATE, which the first draft's did not. `FIELD_RE` is
# anchored at column 0 so that an indented line cannot open a field; a fixture whose folded lines all
# begin with a capital letter passes under `^\s*` too, so it proves nothing about the anchor. The
# second folded line therefore begins with a lowercase word followed by a colon — the exact shape a
# relaxed anchor would steal.
FOLDED = """---
name: qa-lead
description: >
  Plans the risk-based test strategy. Use when: a release needs a plan.
  fallback: none, and this whole line belongs to the fold.
tools: Read, Grep
model: inherit
---

Body text, which must not be read as frontmatter.
model: haiku
"""


def test_frontmatter() -> None:
    got = bi.read_frontmatter(FOLDED)
    check("frontmatter: a folded scalar joins onto one line",
          got.get("description") == "Plans the risk-based test strategy. Use when: a release "
                                    "needs a plan. fallback: none, and this whole line belongs "
                                    "to the fold.",
          f"got {got.get('description')!r}")
    # Two near-misses the column-0 anchor exists for. A colon MID-line ("Use when: ...") must not
    # split, and a colon after the FIRST word of an indented line must not open a field either --
    # that second one is what an `^\s*` anchor gets wrong, silently truncating the description.
    check("frontmatter: a colon inside a folded line is not a new key",
          "Use when" not in got, f"got keys {sorted(got)}")
    check("frontmatter: an indented `word:` line is folded, not read as a field",
          "fallback" not in got, f"got keys {sorted(got)}")
    check("frontmatter: plain fields parse", got.get("tools") == "Read, Grep", f"got {got}")
    check("frontmatter: the model is read", got.get("model") == "inherit", f"got {got}")
    # The body is beyond the closing `---`, so a `model:` line down there must not win.
    check("frontmatter: the body is not read as frontmatter", got.get("model") != "haiku",
          "a body line overwrote a frontmatter field")

    check("frontmatter: quotes are stripped",
          bi.read_frontmatter('---\nargument-hint: "[all]"\n---\n')["argument-hint"] == "[all]",
          "the quotes survived")
    check("frontmatter: a file with no frontmatter yields nothing",
          bi.read_frontmatter("# Just a heading\n") == {}, "expected {}")


# ------------------------------------------------------------------ agent naming

def test_names_agent() -> None:
    """The `unverified-negative` fixture: what counts as naming an agent, and what does not.

    Both false-negative shapes that a markup-sensitive match produced are pinned as POSITIVES
    here, because each was a real wrong answer on the real corpus before it was widened.
    """
    check("names: a backticked name counts",
          bi.names_agent("delegate to `design-auditor` now", "design-auditor"), "missed backticks")
    # Five commands name their agent only in bold; a backtick-only read printed "no agent" beside
    # four of design-flow's seven commands.
    check("names: a bold name counts",
          bi.names_agent("Delegate to the **design-auditor** agent.", "design-auditor"),
          "missed bold, which is how design-flow writes every one of them")
    # The worse half. `/rails-flow:issues` names seven of its agents in plain prose and dispatches
    # them; a draft of this page claimed it dispatched none.
    check("names: a plain prose mention counts too",
          bi.names_agent("Gates: code-reviewer -> CLEAN; then the pr-reviewer agent.",
                         "code-reviewer"),
          "emphasis is typographic, not semantic — a plain mention still names the agent")
    check("names: a name at the very start of the body counts",
          bi.names_agent("design-auditor runs first", "design-auditor"),
          "the lookbehind must not require a preceding character")
    # The near-misses. A longer token is a DIFFERENT name, in both directions.
    check("names: a plural is not the agent",
          not bi.names_agent("the design-auditors disagree", "design-auditor"),
          "matched inside a longer token")
    check("names: a longer prefixed name is not the agent",
          not bi.names_agent("run the meta-design-auditor", "design-auditor"),
          "matched inside a longer token")
    check("names: an unrelated body matches nothing",
          not bi.names_agent("no agents here at all", "design-auditor"), "false positive")


# ------------------------------------------------------------------------ guards

def test_unique_ids() -> None:
    expect_clean("ids: distinct rows are accepted",
                 lambda: bi.verify_unique_ids([row("agent", "a"), row("command", "a")]))
    expect_raises("ids: a duplicate id is refused",
                  lambda: bi.verify_unique_ids([row("agent", "a"), row("agent", "a")]),
                  "appears twice")
    expect_clean("ids: the whole real inventory", lambda: bi.verify_unique_ids(REAL["rows"]))


def test_summaries() -> None:
    expect_clean("summaries: a described agent is accepted",
                 lambda: bi.verify_summaries([row("agent", "a")]))
    expect_raises("summaries: an agent with no description is refused",
                  lambda: bi.verify_summaries([row("agent", "a", summary="  ")]),
                  "resolves no description")
    expect_raises("summaries: a command with no description is refused",
                  lambda: bi.verify_summaries([row("command", "a", summary="")]),
                  "resolves no description")
    # THE CARVE-OUT'S NEGATIVE TEST. Gate rows are exempt because their summary is a command line,
    # not prose; an exemption nothing tests is an exemption that silently widens.
    expect_clean("summaries: a gate row is exempt, deliberately",
                 lambda: bi.verify_summaries([row("gate", "a", summary="")]))
    expect_clean("summaries: the whole real inventory",
                 lambda: bi.verify_summaries(REAL["rows"]))


def test_nameless_agent_is_refused() -> None:
    """An agent file with no `name:` must fail the build, not disappear from it.

    The failure this closes is invisible everywhere else: `check_handoff.agent_models` skips such a
    file too, so the reconciliation below stays clean, the tier table has nothing to match, and the
    agent is simply absent from a page whose whole claim is completeness.
    """
    tmp = Path(tempfile.mkdtemp(prefix="inventory-nameless-"))
    try:
        (tmp / "good.md").write_text("---\nname: fine\ndescription: ok\n---\n", encoding="utf-8")
        expect_clean("nameless: a named agent is accepted",
                     lambda: bi.read_agents(tmp, "x", shipped=False))
        (tmp / "bad.md").write_text("---\ndescription: no name here\n---\n", encoding="utf-8")
        expect_raises("nameless: an agent file with no `name:` is refused",
                      lambda: bi.read_agents(tmp, "x", shipped=False), "declares no `name:`")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


def test_reconciled_agents() -> None:
    """Two readers of one frontmatter file must not disagree in silence."""
    directory = bi.PLUGINS / "pipeline" / "agents"
    parsed = bi.read_agents(directory, "pipeline", shipped=True)
    shipped = ch.agent_models(directory)
    expect_clean("reconcile: the real pipeline agents agree",
                 lambda: bi.verify_reconciled_agents(parsed, "pipeline", shipped))

    expect_raises("reconcile: an agent this module invents is caught",
                  lambda: bi.verify_reconciled_agents(
                      [*parsed, {"name": "ghost", "model": "inherit"}], "pipeline", shipped),
                  "check_handoff does not")
    expect_raises("reconcile: an agent this module MISSES is caught",
                  lambda: bi.verify_reconciled_agents(parsed[:-1], "pipeline", shipped),
                  "this module does not")
    drifted = {**shipped, parsed[0]["name"]: (Path("x.md"), "haiku-but-wrong")}
    expect_raises("reconcile: a disagreeing model is caught",
                  lambda: bi.verify_reconciled_agents(parsed, "pipeline", drifted),
                  "one of the two frontmatter readers is wrong")


def test_tier_join() -> None:
    agents = [{"name": "qa-lead", "owner": "qa-flow", "shipped": True}]
    tables = {"qa-flow": [ch.TierRow("qa-lead", "judgement", "inherit", "—", 3)]}
    expect_clean("tiers: a joined agent is accepted",
                 lambda: bi.verify_tier_join(agents, tables))
    expect_raises("tiers: an agent with no tier row is refused",
                  lambda: bi.verify_tier_join(agents, {"qa-flow": []}), "matches 0 tier rows")
    expect_raises("tiers: an agent with TWO tier rows is refused",
                  lambda: bi.verify_tier_join(
                      agents, {"qa-flow": [*tables["qa-flow"], *tables["qa-flow"]]}),
                  "matches 2 tier rows")
    expect_raises("tiers: a stale tier row is refused",
                  lambda: bi.verify_tier_join(
                      agents,
                      {"qa-flow": [*tables["qa-flow"],
                                   ch.TierRow("retired", "judgement", "inherit", "—", 9)]}),
                  "no agent definition declares")
    # A MAINTAINER agent has no tier table and must not be demanded one -- the second carve-out,
    # and the reason `verify_tier_join` tests `shipped` at all.
    expect_clean("tiers: a maintainer agent is exempt, deliberately",
                 lambda: bi.verify_tier_join(
                     [*agents, {"name": "issue-triager", "owner": "maintainer", "shipped": False}],
                     tables))


def test_gate_scripts() -> None:
    expect_clean("gates: the real registry names real scripts",
                 lambda: bi.verify_gate_scripts(bi.read_gates()))
    expect_raises("gates: a registry entry naming no script is refused",
                  lambda: bi.verify_gate_scripts(
                      [{"name": "ghost", "script": "scripts/nope_does_not_exist.py"}]),
                  "does not exist")


MANIFEST_OK = json.dumps({"metadata": {"version": "9.9.9"}, "plugins": [
    {"name": "rails-stack", "source": "./"},
    {"name": "only-one", "source": "./plugins/only-one"},
]})


def test_cross_check_manifest() -> None:
    """Three states, and `skip` must never be reported as `ok`."""
    real = bi.MARKETPLACE
    tmp = Path(tempfile.mkdtemp(prefix="inventory-manifest-"))
    try:
        bi.MARKETPLACE = tmp / "marketplace.json"
        state, _ = bi.cross_check_manifest(["only-one"])
        check("manifest: an absent file reports skip", state == "skip", f"got {state!r}")

        bi.MARKETPLACE.write_text(MANIFEST_OK, encoding="utf-8")
        state, _ = bi.cross_check_manifest(["only-one"])
        check("manifest: agreeing plugin sets report ok", state == "ok", f"got {state!r}")

        state, msg = bi.cross_check_manifest(["only-one", "undeclared"])
        check("manifest: a plugin the manifest does not install reports fail",
              state == "fail", f"got {state!r}")
        check("manifest: the failure names the offending plugin", "undeclared" in msg,
              f"got {msg!r}")

        state, msg = bi.cross_check_manifest([])
        check("manifest: a plugin the manifest installs but is absent reports fail",
              state == "fail" and "only-one" in msg, f"got {state!r} / {msg!r}")

        bi.MARKETPLACE.write_text(json.dumps({"plugins": [{"source": "./"}]}), encoding="utf-8")
        state, _ = bi.cross_check_manifest(["only-one"])
        check("manifest: a manifest declaring no plugin source reports skip",
              state == "skip", f"got {state!r}")

        bi.MARKETPLACE.write_text("{ not json", encoding="utf-8")
        state, _ = bi.cross_check_manifest(["only-one"])
        check("manifest: unparseable JSON reports skip, never ok", state == "skip", f"got {state!r}")

        # ...and `collect()` must REFUSE to build on a fail, not warn and carry on.
        bi.MARKETPLACE.write_text(
            json.dumps({"plugins": [{"source": "./plugins/never-existed"}]}), encoding="utf-8")
        expect_raises("manifest: a fail aborts the build", bi.collect, "disagree")
    finally:
        bi.MARKETPLACE = real


# --------------------------------------------------------- escaping / injection

def test_escaping() -> None:
    """Every string here reaches the DOM through `innerHTML`, so escaping is load-bearing."""
    got = bi.inline("wraps `<turbo-frame>` in <div> & keeps **bold**")
    check("escape: literal tags become entities",
          "<div>" not in got and "&lt;div&gt;" in got, f"got {got!r}")
    check("escape: a tag inside backticks is escaped before it becomes <code>",
          "&lt;turbo-frame&gt;" in got and "<code>" in got, f"got {got!r}")
    check("escape: ampersand is escaped exactly once",
          got.count("&amp;") == 1 and "&amp;amp;" not in got, f"got {got!r}")
    check("escape: bold survives as markup", "<strong>bold</strong>" in got, f"got {got!r}")
    check("escape: markdown links keep their text, drop the target",
          bi.inline("see [the doctrine](CLAUDE.md)") == "see the doctrine",
          f"got {bi.inline('see [x](y.md)')!r}")


def test_script_terminator() -> None:
    """`json.dumps` does not protect an inline <script> from `</script>` inside a string.

    NOT theoretical for this page: five shipped commands carry a literal `<!-- topology: ... -->`
    marker, and command bodies quote HTML, so both hostile sequences are in the corpus already.
    """
    hostile = {"note": "close it with </script> and comment with <!-- this"}
    check("terminator: json.dumps alone does NOT neutralise it",
          "</script>" in json.dumps(hostile, ensure_ascii=False),
          "json.dumps escaped it after all — re-check whether the guard is still needed")

    # CAUGHT, not allowed to propagate. `render` keeps a backstop that raises if a terminator
    # survives escaping, and with the escaping removed that backstop fires -- correct behaviour,
    # but as an uncaught exception it would abort the run in a traceback. A crash is not a verdict:
    # it reads like a caught defect while telling you nothing about which fixture noticed.
    _tick()
    doc = ""
    try:
        doc = bi.render({**REAL, "hostile": hostile["note"]})
    except bi.ArtifactError as exc:
        FAILURES.append(
            "terminator: render REFUSED to build hostile data — the escaping step is gone and only "
            f"its backstop noticed ({exc}). Restore the escaping; the backstop is a net, not a fix")
    if doc:
        body = doc[doc.index("const DATA = "):doc.rindex("</script>")]
        check("terminator: the rendered script body carries no terminator",
              "</script" not in body and "<!--" not in body, "found one in the emitted body")

        # Line-anchored, NOT re.S: `json.dumps` emits no newlines, so the blob is one line.
        raw = re.search(r"^const DATA = (\{.*\});$", doc, re.M)
        check("terminator: the blob still parses", raw is not None, "could not locate the blob")
        if raw:
            check("terminator: escaping is value-preserving",
                  json.loads(raw.group(1))["hostile"] == hostile["note"],
                  "the escaped blob decoded to a different string")

    # The placeholder guard, in both directions. It is checked BEFORE substitution because
    # `str.replace` replaces every occurrence — a post-substitution test could never fire, which
    # is the `gate-that-cannot-fail` class, and the first draft of this file had exactly that.
    original = bi.TEMPLATE
    try:
        bi.TEMPLATE = "<script>const DATA = {};</script>"
        expect_raises("placeholder: a template that lost its slot is refused",
                      lambda: bi.render({"ok": 1}), "0 `__DATA__` slots")
        bi.TEMPLATE = "<script>const DATA = __DATA__; const AGAIN = __DATA__;</script>"
        expect_raises("placeholder: a template with two slots is refused",
                      lambda: bi.render({"ok": 1}), "2 `__DATA__` slots")
        bi.TEMPLATE = "<script>const DATA = __DATA__;</script>"
        expect_clean("placeholder: exactly one slot is accepted",
                     lambda: bi.render({"ok": 1}))
    finally:
        bi.TEMPLATE = original
    check("placeholder: the real template holds exactly one slot",
          bi.TEMPLATE.count(bi.PLACEHOLDER) == 1,
          f"got {bi.TEMPLATE.count(bi.PLACEHOLDER)}")


# ------------------------------------------ the invariant the whole gate rests on

def test_no_git_on_the_render_path() -> None:
    """The rendered bytes are a function of the DATA. Not of the checkout. At all.

    Asserted by COUNTING calls rather than by comparing two renders under stubbed git state: a
    comparison passes vacuously the moment nobody reads git, and would go on passing if someone
    later added a read whose value happened to be stable on the machine running it. Zero calls is
    the property that actually holds, so zero calls is what is pinned.
    """
    real_git = bi._git
    calls: list[tuple[str, ...]] = []

    def counting(*args: str, raw: bool = False) -> str | None:
        calls.append(args)
        return real_git(*args, raw=raw)

    try:
        bi._git = counting
        doc = bi.render(bi.collect())
    finally:
        bi._git = real_git
    check("determinism: building the page never invokes git",
          not calls, f"the render path ran git: {calls}")

    # A second angle, cheap: HEAD's own short SHA must not appear in the bytes. This is the exact
    # field `build_coverage_artifact.py` embedded, which made its gate unpassable by construction —
    # committing the page advances HEAD, and a file inside a commit cannot name its own commit.
    sha = real_git("rev-parse", "--short=12", "HEAD")
    if sha:
        check("determinism: HEAD's own SHA is nowhere in the page", sha not in doc,
              f"found {sha!r} in the rendered bytes")
    else:
        _tick()
        SKIPPED.append("HEAD SHA absence — git could not resolve HEAD here")

    stamp = REAL["stamp"]
    check("determinism: the stamp carries no field about the checkout",
          set(stamp) == {"label", "versions"}, f"got keys {sorted(stamp)}")
    check("determinism: the label is the release version, not a checkout description",
          stamp["label"].startswith("Inventory as of v"), f"got {stamp['label']!r}")
    check("determinism: every stamped version is a plain version string",
          all(re.fullmatch(r"[\w.\-+]+", v) for v in stamp["versions"].values()),
          f"got {stamp['versions']}")


# ------------------------------------------------------ the real end-to-end pass

def test_real_build() -> None:
    """The whole thing, over the real plugins — the SILENCE fixture that matters most."""
    data = REAL
    totals, rows = data["totals"], data["rows"]
    kinds = {k: sum(1 for r in rows if r["kind"] == k)
             for k in (bi.KIND_AGENT, bi.KIND_COMMAND, bi.KIND_GATE)}

    check("real: the three kinds partition the rows exactly",
          sum(kinds.values()) == totals["rows"] == len(rows),
          f"{kinds} against {totals['rows']} rows")
    check("real: shipped + maintainer agents account for every agent row",
          totals["agents"] + totals["maintainerAgents"] == kinds[bi.KIND_AGENT],
          f"{totals['agents']}+{totals['maintainerAgents']} != {kinds[bi.KIND_AGENT]}")
    check("real: shipped + maintainer commands account for every command row",
          totals["commands"] + totals["maintainerCommands"] == kinds[bi.KIND_COMMAND],
          f"{totals['commands']}+{totals['maintainerCommands']} != {kinds[bi.KIND_COMMAND]}")
    check("real: the gate count is the registry's own length",
          totals["gates"] == len(bi.md.GATES) == kinds[bi.KIND_GATE],
          f"{totals['gates']} vs {len(bi.md.GATES)} registered")
    check("real: every plugin with agents carries a tier table",
          totals["tierTables"] == sum(1 for p in data["plugins"] if p["agents"]),
          f"{totals['tierTables']} tables for {sum(1 for p in data['plugins'] if p['agents'])} "
          "plugins with agents")
    check("real: every plugin's tier rows equal its agent count",
          all(p["tierRows"] == p["agents"] for p in data["plugins"]),
          f"got {[(p['name'], p['agents'], p['tierRows']) for p in data['plugins']]}")
    check("real: the per-plugin panels account for every shipped agent",
          sum(p["agents"] for p in data["plugins"]) == totals["agents"], "panel totals disagree")
    check("real: the per-plugin panels account for every shipped command",
          sum(p["commands"] for p in data["plugins"]) == totals["commands"],
          "panel totals disagree")
    check("real: the manifest cross-check ran and agreed",
          data["crossCheck"]["state"] == "ok", f"got {data['crossCheck']}")
    check("real: every row carries a detail panel",
          all(r["detail"] for r in rows), "a row would expand to nothing")
    check("real: every row is searchable",
          all(r["q"].strip() for r in rows), "a row has an empty search key")
    check("real: nothing shipped is filed under maintainer or repo",
          all(not r["shipped"] for r in rows
              if r["owner"] in (bi.OWNER_MAINTAINER, bi.OWNER_REPO)),
          "a maintainer-only row is labelled as shipped")

    doc = bi.render(data)
    missing = [r["name"] for r in rows if r["nameHtml"] not in doc and r["name"] not in doc]
    check("real: every row name appears in the rendered document",
          not missing, f"absent: {missing[:5]}")
    check("real: the document declares a title", "<title>" in doc, "no <title>")
    check("real: both theme signals are present",
          "prefers-color-scheme:dark" in doc and 'data-theme="dark"' in doc,
          "a theme override is missing, so the viewer's toggle cannot win")
    check("real: no absolute filesystem path leaks into the page",
          str(bi.REPO) not in doc, "an absolute path from this machine is in the bytes")


# ------------------------------------------------------------ the --check gate

def test_committed_blob_reads_git() -> None:
    """`committed_blob` must read the COMMIT, against a real repository.

    THE GAP THIS CLOSES, found by mutating the subject rather than by reading it. Every `--check`
    fixture below stubs `committed_blob`, which exercises the gate's three verdicts and NONE of its
    plumbing -- so rewriting the function to `Path.read_text` survived the whole selftest. That is
    the precise defect the gate exists to prevent (a page on disk but not committed, waved
    through), sitting inside its own test. The sibling artifact's selftest leans on "the real
    `--check` run exercises the plumbing", which cannot discriminate: in a clean checkout the
    working copy and the commit hold the same bytes, so both implementations agree.

    So this builds a throwaway repo where they DISAGREE. Isolated from global git config, because a
    maintainer's `commit.gpgsign` or hook config must not decide whether this fixture can run.
    """
    import os
    import shutil
    import subprocess

    if shutil.which("git") is None:
        _tick()
        SKIPPED.append("committed_blob against a real repo — git is not on PATH")
        return

    tmp = Path(tempfile.mkdtemp(prefix="inventory-blob-"))
    env = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull,
           "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t"}

    def git(*args: str) -> int:
        return subprocess.run(("git", *args), cwd=tmp, env=env,
                              capture_output=True, text=True, timeout=60).returncode

    real_repo = bi.REPO
    try:
        if git("init", "-q") != 0:
            _tick()
            SKIPPED.append("committed_blob against a real repo — `git init` failed here")
            return
        (tmp / "page.html").write_text("COMMITTED BYTES\n", encoding="utf-8")
        (tmp / "untracked.html").write_text("never added\n", encoding="utf-8")
        git("add", "page.html")
        if git("commit", "-q", "-m", "seed") != 0:
            _tick()
            SKIPPED.append("committed_blob against a real repo — `git commit` failed here")
            return
        # The two now DISAGREE. Only an implementation that reads git can tell them apart.
        (tmp / "page.html").write_text("WORKING COPY BYTES\n", encoding="utf-8")

        bi.REPO = tmp
        got = bi.committed_blob("page.html")
        check("blob: returns the COMMITTED bytes, not the working copy",
              got is not None and got.strip() == "COMMITTED BYTES",
              f"got {got!r} — reading the working copy is the defect the gate exists to prevent")
        check("blob: an untracked file returns None, not its contents",
              bi.committed_blob("untracked.html") is None,
              "an untracked page must be drift, however perfect its bytes")
        check("blob: a path that does not exist at all returns None",
              bi.committed_blob("nowhere/at/all.html") is None, "expected None")
    finally:
        bi.REPO = real_repo
        shutil.rmtree(tmp, ignore_errors=True)


def test_check_gate() -> None:
    """All three verdicts, plus the two near-misses. The COMMITTED blob decides, never the disk."""
    real_blob = bi.committed_blob
    with tempfile.TemporaryDirectory() as directory:
        out = Path(directory) / "inventory.html"
        check("--check: generating to a temp path succeeds",
              bi.main(["--out", str(out)]) == 0, "the writer failed")
        fresh = out.read_text(encoding="utf-8")

        try:
            bi.committed_blob = lambda _rel: fresh
            check("--check passes when the COMMITTED blob is the clean build",
                  bi.main(["--check", "--out", str(out)]) == 0,
                  "a committed clean build must satisfy --check")

            # STALE: one appended byte must fail. The case that actually happens — an agent is
            # added and nobody regenerates.
            bi.committed_blob = lambda _rel: fresh + "<!-- drift -->"
            check("--check FAILS on a stale artifact",
                  bi.main(["--check", "--out", str(out)]) == 1,
                  "an edited artifact must be reported as drift, or the gate is decorative")

            # NOT TRACKED, but sitting on disk as a perfect clean build. THE defect this gate
            # exists to close, and the one an `is_file()` check waved through.
            bi.committed_blob = lambda _rel: None
            check("a built-but-untracked page is DRIFT, not a pass",
                  out.is_file() and bi.main(["--check", "--out", str(out)]) == 1,
                  "the gate must read git, not the working copy — that was the whole point")

            # THE OTHER DIRECTION: a scribbled working copy over a clean COMMIT is not drift.
            out.write_text("locally scribbled over", encoding="utf-8")
            bi.committed_blob = lambda _rel: fresh
            check("a dirty working copy over a clean COMMIT is not drift",
                  bi.main(["--check", "--out", str(out)]) == 0, "only the committed blob decides")

            # ABSENT from disk as well: still a real verdict, and no crash reaching for a file.
            out.unlink()
            bi.committed_blob = lambda _rel: None
            check("--check FAILS when the artifact is nowhere at all",
                  bi.main(["--check", "--out", str(out)]) == 1,
                  "a missing artifact must fail, not pass by absence")

            # NEAR MISS: differing only by line endings must NOT be drift — git hands back CRLF on
            # a Windows checkout, and calling that stale would make the gate unusable there.
            bi.committed_blob = lambda _rel: fresh.replace("\n", "\r\n")
            check("--check tolerates CRLF-normalised checkouts",
                  bi.main(["--check", "--out", str(out)]) == 0,
                  "line-ending normalisation is not drift")
        finally:
            bi.committed_blob = real_blob


def run() -> int:
    global REAL
    # FIRST, and it returns immediately on failure: every fixture below reads `REAL`, so a broken
    # `collect()` would otherwise surface as a traceback from whichever test happens to run first.
    # A traceback is not a verdict — it is how a real defect gets "caught" by accident.
    _tick()
    try:
        REAL = bi.collect()
    except bi.ArtifactError as exc:
        FAILURES.append(f"collect() refused to build the real inventory:\n{exc}")
    except Exception as exc:  # noqa: BLE001 — reported as a verdict, never as a traceback
        FAILURES.append(f"collect() raised {type(exc).__name__} on the real repo: {exc}")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    test_frontmatter()
    test_names_agent()
    test_unique_ids()
    test_summaries()
    test_nameless_agent_is_refused()
    test_reconciled_agents()
    test_tier_join()
    test_gate_scripts()
    test_cross_check_manifest()
    test_escaping()
    test_script_terminator()
    test_no_git_on_the_render_path()
    test_real_build()
    test_committed_blob_reads_git()
    test_check_gate()

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    passed = CHECKS - len(SKIPPED)
    if SKIPPED:
        print(f"build_inventory selftest: {passed} passed, {len(SKIPPED)} SKIPPED")
        for skip in SKIPPED:
            print(f"  - skipped: {skip}")
        print("A skipped check did NOT run — it is not a pass.")
    else:
        print(f"build_inventory selftest: {passed} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
