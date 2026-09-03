#!/usr/bin/env python3
"""Run every shipped check that applies to THIS project — one command, locally and in CI.

Run:  python3 project_gates.py            # run what applies; exit 1 on any failure
      python3 project_gates.py --list      # say what applies and what does not, run nothing
      python3 project_gates.py --json      # the same run, machine-readable, with the routing
      python3 project_gates.py --selftest  # prove the states, the applicability rules, the routing

WHY (#334). The plugins shipped eleven checks that ran against a *user's* repo, and no way to run
them together. (Past tense, and no current count: this said "ship eleven" while the manifests
declared fifteen. The manifests are the count; a number restated here only goes stale.)
A user had to know each script existed, know which applied, and invoke each by hand — which
in practice meant **an agent ran them when it remembered.** That is the claims-vs-enforcement defect
this toolchain warns about, in the toolchain itself.

It matters most at **`dev → main`**, because that is the branch a project deploys from. `setup-flow`
§8 already puts the hosted CI at exactly that trigger; what runs there is the project's own test
matrix, and nothing verified the doctrine we shipped them before the deploy branch moved.

THE STATE MODEL, WHICH IS THE WHOLE DESIGN. Four outcomes, not two:

    pass            the check ran and was clean
    FAIL            the check ran and found something, or its dependency is missing
    not applicable  this repo has nothing for it to read -- REPORTED, never counted as a pass
    ERROR           the check could not be run at all (bad manifest, missing script)

`not applicable` is the one that has to be loud. A project with no `qa/` directory genuinely has no
QA evidence to validate, and calling that "passed" would let a repo with zero evidence report the
same green as a repo with complete evidence. The summary always prints how many were skipped and
why, for the same reason `maintainer_doctor` does.

A MISSING DEPENDENCY IS A FAILURE, NOT A SKIP. In CI a skip is indistinguishable from a pass unless
something asserts the dependency is there, so `requires` is checked and its absence FAILS.

NO BROWSER CHECKS HERE, deliberately. `rendered_conformance.py` needs Playwright, which is the user's
dependency and not installable from a plugin. A gate that quietly skips when the browser is absent is
worse than no gate; those stay in the agent-driven browser pass, where absence is visible.

REGISTRATION IS THE MANIFEST. Each plugin ships `checks.json` declaring its own; this runner never
hardcodes a list, so adding a check is one manifest entry and a new plugin needs no change here.

AND THEN: WHOSE TRACKER (#485). The four states say what happened, not where the fix goes, and the
summary used to add ERRORs into the same "failed" total as real findings. An ERROR is a manifest of
OURS naming a script that does not exist — a user reading "2 failed" files two bugs against their
own app, one of which is ours. So every non-pass outcome is now routed:

    app          the detector ran against this project's content and found something -> their tracker
    doctrine     the check produced no verdict at all, which project content cannot cause -> ours,
                 reportable with /rails-flow:report
    environment  a required binary is absent -> neither their code nor our doctrine; install it
    unrouted     `not applicable` -- reported, and deliberately routed NOWHERE

WHAT THE ROUTING DOES NOT CLAIM, stated because the omission is the interesting part. A FAIL routes
to `app` because the detector ran and worked. That is correct for every check shipped today and it
is a **default, not a proof**: a check that catches the toolchain scaffolding half a pattern — its
own doctrine mandates a container, its own setup never emits one — is a FAIL that belongs upstream,
and no rule here can tell that apart from a defect in the project's code. Such detectors do not
exist yet, and `checks.json` therefore carries **no** destination field: a field with one
hypothetical consumer is indirection, not a seam. The check that needs it adds it, and until then
the default must not be widened to guess — a confidently wrong route is worse than no route.

`unrouted` is the routing layer's version of "not applicable is not a pass". One run cannot tell a
project that genuinely has no `qa/` from a check aimed at a path nothing writes — that second case
is a doctrine gap, and reconciling it needs the whole plugin, not one project. It has its own
maintainer-side gate upstream and is not re-derived here.

Exit codes:  0 all applicable checks passed · 1 at least one FAIL or ERROR · 2 nothing discovered

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PASS, FAIL, NA, ERROR = "pass", "FAIL", "n/a", "ERROR"

# Destinations. See the module docstring for why each outcome routes where it does.
APP, DOCTRINE, ENVIRONMENT, UNROUTED = "app", "doctrine", "environment", "unrouted"

# The headline printed once per destination, and the action it asks for. Kept beside the constants
# so a new destination cannot be added without saying where its findings are supposed to go.
DESTINATIONS: dict[str, tuple[str, str]] = {
    APP: ("this project's own tracker",
          "the detector ran against this project's content and found something"),
    DOCTRINE: ("upstream, via /rails-flow:report",
               "the check produced no verdict at all, and this project's content cannot cause that"),
    ENVIRONMENT: ("nobody's tracker — install the binary",
                  "a required dependency is absent, so neither this code nor our doctrine is at fault"),
}


@dataclass
class Check:
    plugin: str
    id: str
    why: str
    command: list[str]
    applies_when: list[str]
    requires: list[str]
    root: Path            # the plugin directory this came from


@dataclass
class Result:
    check: Check
    status: str
    detail: str = ""
    # Everything the check said AFTER its summary line (#812). The aggregate used to keep only the
    # summary, so `[FAIL] mandated-gems  1 finding(s):` was the whole report -- a trailing colon
    # promising a list, followed by nothing. The individual scripts carry the finding, the reason
    # AND the fix; a reader got "something is wrong" and never "what".
    findings: tuple[str, ...] = ()


def plugin_identity(root: Path) -> tuple[str, tuple[int, ...]]:
    """`(plugin name, version tuple)` from the root's own `plugin.json`.

    Authoritative rather than inferred: every installed plugin directory carries
    `.claude-plugin/plugin.json` with both fields, in the cache and in a source checkout alike. The
    directory NAME cannot serve -- in the installed layout it is a version number, and in a checkout
    it is the plugin name, so reading it means guessing which layout you are in.

    Falls back to the directory name at version `(0,)` when the manifest is unreadable. That keeps a
    hand-assembled tree working while still collapsing duplicates of the same name.
    """
    manifest = root / ".claude-plugin" / "plugin.json"
    name, raw = root.name, ""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        name = str(data.get("name") or root.name)
        raw = str(data.get("version") or "")
    except (OSError, ValueError, TypeError):
        pass
    parts = []
    for chunk in raw.split("."):
        digits = "".join(c for c in chunk if c.isdigit())
        parts.append(int(digits) if digits else 0)
    return name, tuple(parts) or (0,)


def plugin_roots(start: Path) -> list[Path]:
    """One directory per installed PLUGIN that ships a `checks.json` -- never one per version.

    Siblings are discovered rather than configured: plugins are installed independently, so a repo
    may have rails-flow and not design-flow. A plugin that is not installed contributes nothing --
    which is different from a check that is installed and does not apply, and the report says which.

    #706. THE OLD WALK ASSUMED A FLAT LAYOUT AND THE INSTALLED ONE IS NESTED. It took
    `start.parents[1]` as the plugin dir and scanned that dir's parent for siblings, which is right
    in a source checkout (`plugins/rails-flow/scripts/x.py` -> siblings are `plugins/*`) and wrong
    where the toolchain actually runs:

        ~/.claude/plugins/cache/claude-skills/<plugin>/<version>/checks.json

    There `parents[1]` is a VERSION dir, so "siblings" were other versions of the same plugin. Two
    consequences, both measured on a real machine:

      * every check ran once per cached version -- six for rails-flow, FOURTEEN for design-flow --
        inflating every count and, worse, grading one artifact `[ok]` by some versions and `[FAIL]`
        by others, because their check logic differs. A single artifact with contradictory verdicts
        in one run destroys the point of a single trustworthy gate.
      * the real sibling plugins live one level HIGHER and were never discovered at all, so
        qa-flow's 8 checks and design-flow's 2 silently never ran locally -- a coverage gap wearing
        an inflated count, which reads busier than the truth rather than quieter.

    A pinned CI checkout has exactly one version on disk and never sees either half, which is why
    this looked clean in CI while the documented "one command, locally and in CI" was wrong locally.

    So: gather candidates from BOTH shapes, then collapse by plugin identity keeping the highest
    version. Layout is discovered, not assumed.

    KNOWN LIMIT, stated rather than hidden: "highest cached" is a proxy for "active". For the plugin
    you invoked it is exact -- `own` wins its own name, because running a different version's checks
    than the script you launched would be surprising. For SIBLING plugins it can disagree: a
    downgraded plugin leaves the newer version in the cache and its checks would be the ones that
    run. The alternative is `installed_plugins.json`, which `toolchain_version.py` reads with some
    care -- and which does not exist in a source checkout or on a CI runner, so keying on it would
    make the same repo grade differently by environment. That is a worse failure than a stale
    sibling. `/rails-flow:toolchain-check` is the thing that surfaces version drift; this is not.
    """
    own = start.resolve().parents[1]          # <plugin>/scripts/x.py -> <plugin>, or <plugin>/<ver>
    candidates: set[Path] = set()
    if (own / "checks.json").is_file():
        candidates.add(own)

    def scan(directory: Path) -> None:
        try:
            children = sorted(directory.iterdir())
        except OSError:
            return
        for child in children:
            if child.is_dir() and (child / "checks.json").is_file():
                candidates.add(child)

    # One level up: sibling PLUGINS in a flat source checkout, sibling VERSIONS in the cache.
    scan(own.parent)
    # Two levels up, one level down: every plugin's every version in the cache. Harmless in a
    # checkout, where nothing at that depth ships a `checks.json`.
    #
    # `own.parent` is skipped here on purpose. Scanning it in both places made the line above
    # unprovable -- a mutation deleting it survived, because this loop covers `own.parent` as one of
    # grandparent's children. A line no fixture can distinguish is a line that does nothing, so the
    # two scans are now disjoint and a mutation to either one fails a named fixture.
    grandparent = own.parent.parent
    try:
        peers = sorted(grandparent.iterdir())
    except OSError:
        peers = []
    for peer in peers:
        if peer.is_dir() and peer != own.parent:
            scan(peer)

    # COLLAPSE BY IDENTITY. `own` wins ties on its own name, so the version you invoked is the one
    # that runs even if a higher one is cached -- an explicit invocation is a choice, not an accident.
    best: dict[str, Path] = {}
    own_name = plugin_identity(own)[0] if own in candidates else None
    for root in sorted(candidates):
        name, version = plugin_identity(root)
        if name == own_name and root == own:
            best[name] = root
            continue
        if name == own_name and best.get(name) == own:
            continue
        current = best.get(name)
        if current is None or plugin_identity(current)[1] < version:
            best[name] = root
    return sorted(best.values())


def load_checks(roots: list[Path]) -> tuple[list[Check], list[str]]:
    checks: list[Check] = []
    problems: list[str] = []
    for root in roots:
        path = root / "checks.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            problems.append(f"{path}: unreadable manifest ({exc})")
            continue
        for raw in data.get("checks", []):
            missing = [k for k in ("id", "why", "command") if k not in raw]
            if missing:
                problems.append(f"{path}: a check is missing {missing}")
                continue
            checks.append(Check(
                plugin=data.get("plugin", root.name), id=raw["id"], why=raw["why"],
                command=list(raw["command"]), applies_when=list(raw.get("applies_when", [])),
                requires=list(raw.get("requires", [])), root=root))
    return checks, problems


def expand(command: list[str], check: Check, project: Path) -> list[list[str]]:
    """Resolve `{plugin}` and `{match:glob}` into concrete argv lists.

    A `{match:...}` command runs ONCE PER MATCHING FILE, because the underlying scripts take a single
    path. Returning a list of argvs rather than one keeps that in the runner instead of asking every
    script to grow multi-path handling it does not need.
    """
    argvs: list[list[str]] = [[]]
    for token in command:
        if token.startswith("{match:") and token.endswith("}"):
            pattern = token[len("{match:"):-1]
            hits = sorted(str(p) for p in project.glob(pattern))
            if not hits:
                return []          # applicability is decided by the caller; no files means nothing to run
            argvs = [a + [h] for a in argvs for h in hits]
        else:
            argvs = [a + [token.replace("{plugin}", str(check.root))] for a in argvs]
    return argvs


def applicability(check: Check, project: Path) -> str | None:
    """None if the check applies; otherwise the reason it does not."""
    absent = [p for p in check.applies_when if not (project / p).exists()]
    if absent:
        return f"no {', '.join(absent)} in this project"
    for token in check.command:
        if token.startswith("{match:") and token.endswith("}"):
            if not list(project.glob(token[len("{match:"):-1])):
                return f"nothing matches {token[len('{match:'):-1]}"
    return None


def required_subcommand(help_text: str) -> set[str]:
    """The subparser choices a script REQUIRES, or an empty set if it takes none.

    Two signals together, because either alone is wrong: the group must sit in the `usage:` block,
    and argparse follows a subparser group with ` ...`. Matching `{a,b}` anywhere in the help fired a
    false positive on a `--format {json,md}` choice list in the options body.

    Extracted from its caller so a fixture can exercise it directly. Inline, a mutation that neutered
    it deleted the only assertion that would have noticed -- a check that cannot fail.
    """
    usage = help_text.split("\n\n", 1)[0]
    found = re.search(r"\{([a-z,]+)\}\s*\.\.\.", usage)
    return set(found.group(1).split(",")) if found else set()


def missing_dependencies(check: Check) -> list[str]:
    """Required binaries absent from PATH.

    A named query so the router asks the same question `run_check` asks, rather than recognising a
    dependency failure by the wording of its message. Recognising it by text is how a message edit
    silently re-routes findings to the wrong tracker.

    `run_check` asks it inline rather than calling this, so the two must be held in agreement by
    test rather than by construction — the selftest pins both directions.
    """
    return [b for b in check.requires if shutil.which(b) is None]


def route_of(result: Result) -> tuple[str, str]:
    """Whose tracker this outcome belongs to, and why. `("", "")` when there is nothing to route.

    Derived from the outcome, never declared per check -- see the module docstring for the one case
    this deliberately cannot decide and does not pretend to.
    """
    if result.status == PASS:
        return "", ""
    if result.status == NA:
        return UNROUTED, ("not applicable verified nothing, so it is nobody's finding yet — but it "
                          "is also not a pass")
    if result.status == ERROR:
        return DOCTRINE, DESTINATIONS[DOCTRINE][1]
    if missing_dependencies(result.check):
        return ENVIRONMENT, DESTINATIONS[ENVIRONMENT][1]
    return APP, DESTINATIONS[APP][1]


# CSI colour/style runs, plus OSC-8 hyperlinks (`ESC ] 8 ; ; url ESC \\ text ESC ] 8 ; ; ESC \\`).
# Both appear in real checker output the moment a tool decides it is talking to a human.
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x1b\x07]*(?:\x07|\x1b\\)")
# PREFER A POSITIVE SIGNAL, not a denylist of banners. The first version of this skipped known
# preamble lines (`Herb`, `Node.js:`, `Running:`) and was immediately beaten by
# `No .herb.yml found, using defaults` -- because a denylist of every way a tool can clear its
# throat is a treadmill, and the one line it misses is the one a user sees.
#
# A finding names a severity or a location. Anything else is preamble by default.
_FINDING = re.compile(r"\b(error|errors|warning|warnings|fail(ed|ure)?)\b|⚠|:\d+:\d+")


# A check that prints hundreds of lines is a check whose output belongs in its own run, not inlined
# in an aggregate. Truncating SILENTLY would be the same defect this fixes one step along, so the
# marker names what was dropped and where to get it.
MAX_FINDING_LINES = 40


def summarise(output: str, returncode: int) -> tuple[str, tuple[str, ...]]:
    """`(summary, the lines after it)` — the aggregate needs both (#812).

    A one-line status row answers "what is the one line worth printing", which is right and was
    never the whole job: our own checks emit `N finding(s):` and then the findings, so the summary
    is precisely the LEAST informative line in the output -- a trailing colon promising a list, and
    nothing after it. Everything before the summary is the tool clearing its throat (a version
    banner, a config notice) and is dropped; everything after it is the report.

    It absorbed `first_meaningful_line` (#715/#716), which it had re-implemented line for line --
    two functions doing one job, and only the dead one was mutation-guarded. That history is why
    the escape-stripping and banner-skipping below look defensive:

      * `herb analyze` opens with `Herb 🌿 v0.10.3` and then `No .herb.yml found, using defaults`,
        so a FAIL read `[FAIL] erb-parse-safety  Herb 🌿 v0.10.3` -- a version banner where the
        finding belongs.
      * `herb lint` colours its output, so the detail arrived as
        `[[1m[91merror[0m[0m] Avoid ...`, with a hyperlink escape inside it. In a CI log that
        is worse than the banner: unreadable AND it looks like corruption.

    A summary nobody can read is a summary nobody reads, and then the routing that says WHOSE
    tracker a failure belongs to stops being consulted at all. Hence the fallback to the first
    line rather than to nothing: a check that failed with only a banner still has to say so.
    """
    lines = [_ANSI.sub("", ln).rstrip() for ln in output.splitlines()]
    idx = next((i for i, ln in enumerate(lines) if ln.strip() and _FINDING.search(ln)), None)
    if idx is None:
        idx = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if idx is None:
        return f"exit {returncode}", ()
    rest = [ln for ln in lines[idx + 1:] if ln.strip()]
    if len(rest) > MAX_FINDING_LINES:
        dropped = len(rest) - MAX_FINDING_LINES
        rest = rest[:MAX_FINDING_LINES] + [
            f"… {dropped} more line(s) — run the check directly for the rest"]
    return lines[idx].strip()[:160], tuple(rest)


def tree_state(project: Path) -> dict[str, str] | None:
    """`{path: status}` from `git status --porcelain -uall`, or None outside a git repo (then unasserted).

    `-uall` because plain `--porcelain` collapses a new untracked directory to one row, so a check
    that wrote `docs/architecture/graph.json` into a new folder would show as `docs/` -- still a
    change, but not the path the reader needs.
    """
    try:
        done = subprocess.run(["git", "status", "--porcelain", "-uall"], cwd=project,
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    if done.returncode != 0:
        return None
    state: dict[str, str] = {}
    for line in done.stdout.splitlines():
        if len(line) > 3:
            state[line[3:].split(" -> ")[-1]] = line[:2]
    return state


def tree_delta(before: dict[str, str] | None, after: dict[str, str] | None) -> list[str]:
    """Paths whose status changed between two snapshots; empty when either side could not be read."""
    if before is None or after is None:
        return []
    return sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))


def run_check(check: Check, project: Path) -> Result:
    why_not = applicability(check, project)
    if why_not:
        return Result(check, NA, why_not)
    for binary in check.requires:
        if shutil.which(binary) is None:
            # NOT a skip. See the module docstring: in CI a skip reads as a pass.
            return Result(check, FAIL, f"`{binary}` is not on PATH, so this check could not run")
    argvs = expand(check.command, check, project)
    if not argvs:
        return Result(check, ERROR, "command expanded to nothing")
    for argv in argvs:
        script = Path(argv[1]) if len(argv) > 1 else None
        if script is not None and script.suffix == ".py" and not script.is_file():
            return Result(check, ERROR, f"{script} does not exist — manifest and plugin disagree")
        before = tree_state(project)
        try:
            done = subprocess.run(argv, cwd=project, capture_output=True, text=True, timeout=300)
        except (OSError, subprocess.SubprocessError) as exc:
            return Result(check, ERROR, f"{type(exc).__name__}: {exc}")
        # A DIAGNOSTIC NEVER MUTATES THE PROJECT (#849). The maintainer doctor snapshots `dist/` and
        # restores it byte-for-byte so that reading the tree cannot change it; this is the same
        # contract for the shipped audit, asserted rather than assumed. A check that wrote files
        # while being asked a question is a defect in the check -- ours, routed to doctrine -- and
        # the user is told exactly which paths moved so nothing is committed by accident.
        changed = tree_delta(before, tree_state(project))
        if changed:
            return Result(check, ERROR,
                          f"this check MODIFIED the project during an audit — a diagnostic must never write: "
                          f"{', '.join(changed[:6])}{' …' if len(changed) > 6 else ''}",
                          tuple(f"  - {c}" for c in changed))
        if done.returncode != 0:
            summary, findings = summarise(done.stdout + done.stderr, done.returncode)
            # THE CHECK'S OWN VERDICT, not "non-zero means FAIL" (#828). `applicability()` above
            # decides n/a from the manifest's `applies_when`; a check that has to READ the project
            # to know -- i18n with no `config.x.locales`, a coverage ratchet with no simplecov --
            # says so itself with exit 3, and this loop graded every one of those as FAIL, counted
            # it in `N failed`, and routed it to the project's own tracker. A line reading
            # `[FAIL] i18n-wired  not applicable — …` is the SKIP-as-FAIL inversion of the
            # SKIP-as-PASS defect this runner's docstring exists to refuse.
            #
            # Exit 2 is "could not run/compare" -- a brand pack that cannot be determined, an
            # unreadable input -- which is ours to explain, not the project's to fix: ERROR, routed
            # to doctrine, carrying the check's reason.
            if done.returncode == 3:
                return Result(check, NA, summary, findings)
            if done.returncode == 2:
                return Result(check, ERROR, summary, findings)
            return Result(check, FAIL, summary, findings)
    return Result(check, PASS, f"{len(argvs)} invocation(s)")


def routing_detail(r: Result) -> str:
    """One line for the routing view — the first FINDING when the summary is only a count (#812).

    `1 finding(s):` in a routing block is the trailing-colon problem in miniature: a promise of a
    list, in a view that is deliberately one line per check. The routing view answers "whose tracker
    does this belong to", so it stays one line -- but that line may as well be the finding rather
    than its cardinality.
    """
    if r.findings and r.detail.rstrip().endswith(":"):
        return r.findings[0].lstrip("- ").strip()[:160]
    return r.detail


def routed(results: list[Result], problems: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Non-pass outcomes grouped by destination, as (what, detail) pairs.

    `unrouted` is absent by design: the not-applicable block already lists those, and printing one
    list twice trains people to skim both.
    """
    groups: dict[str, list[tuple[str, str]]] = {d: [] for d in DESTINATIONS}
    for r in sorted(results, key=lambda r: (r.check.plugin, r.check.id)):
        destination = route_of(r)[0]
        if destination in groups:
            groups[destination].append((f"{r.check.plugin}/{r.check.id}", routing_detail(r)))
    # A manifest that will not parse is ours by the same argument an ERROR is: the project did not
    # write it. It never reaches `run_check`, so it has no Result to route.
    groups[DOCTRINE].extend(("checks.json", p) for p in problems)
    return groups


def report(results: list[Result], problems: list[str]) -> int:
    for r in sorted(results, key=lambda r: (r.check.plugin, r.check.id)):
        mark = {PASS: "ok  ", FAIL: "FAIL", NA: "n/a ", ERROR: "ERR "}[r.status]
        line = f"  [{mark}] {r.check.plugin}/{r.check.id}"
        print(f"{line:44} {r.detail}" if r.detail else line)
        # THE FINDINGS, not just their count (#812). `1 finding(s):` with nothing under it is a
        # trailing colon promising a list -- and the individual scripts carry the finding, the
        # reason AND the fix, all of which the aggregate discarded. This is the run people are told
        # to make, so it has to be the one that says what to do.
        for detail_line in r.findings:
            print(f"      {detail_line}")
    for p in problems:
        print(f"  [ERR ] {p}", file=sys.stderr)
    fails = [r for r in results if r.status == FAIL]
    errors = [r for r in results if r.status == ERROR]
    na = [r for r in results if r.status == NA]
    # ERRORs are counted SEPARATELY from failures, not folded into one "failed" total. An ERROR is
    # this toolchain's manifest disagreeing with this toolchain's own scripts; adding it to the
    # number a user reads as "defects in my app" is how our bug becomes their bug report (#485).
    print(f"\n{len(results) - len(fails) - len(errors) - len(na)} passed, {len(fails)} failed, "
          f"{len(errors)} errored, {len(na)} not applicable, {len(problems)} manifest problem(s).")
    if na:
        # Said every run, not only when it is convenient: a not-applicable check did NOT verify
        # anything, and a summary that lets it read as a pass is the defect this tool exists to stop.
        print("Not applicable is NOT a pass — those checks verified nothing, and they are routed "
              "to no tracker:")
        for r in na:
            print(f"  - {r.check.plugin}/{r.check.id}: {r.detail}")
    groups = routed(results, problems)
    if any(groups.values()):
        print("\nWhere each finding goes — a gap this toolchain caused is not a gap in your app:")
        for destination, entries in groups.items():
            where, why = DESTINATIONS[destination]
            print(f"  {destination.upper()} ({len(entries)}) → {where} — {why}")
            for what, detail in entries:
                print(f"    - {what}: {detail}")
        if groups[DOCTRINE]:
            print("  Hand the DOCTRINE list to /rails-flow:report — one observation per report.")
    return exit_code(results, problems)


def as_json(results: list[Result], problems: list[str]) -> str:
    """The same run as `report`, for an agent that has to act on it rather than read it.

    Routing exists so a finding reaches the right tracker without a human re-deciding each time; a
    destination an agent must recover by parsing prose is the same defect one step later.
    """
    rows = []
    for r in sorted(results, key=lambda r: (r.check.plugin, r.check.id)):
        destination, why = route_of(r)
        rows.append({"plugin": r.check.plugin, "id": r.check.id, "why": r.check.why,
                     "status": r.status, "detail": r.detail,
                     "findings": list(r.findings),
                     "destination": destination or None, "routed_because": why or None})
    return json.dumps({
        "results": rows,
        "manifest_problems": problems,
        "summary": {status: sum(1 for r in results if r.status == status)
                    for status in (PASS, FAIL, NA, ERROR)},
    }, indent=2, sort_keys=False)


def exit_code(results: list[Result], problems: list[str]) -> int:
    """0 all applicable checks passed, 1 at least one FAIL or ERROR. Shared so the text and JSON
    paths cannot drift into disagreeing about whether the same run failed."""
    return 1 if problems or any(r.status in (FAIL, ERROR) for r in results) else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run every shipped check that applies to this project.")
    ap.add_argument("--project", type=Path, default=Path.cwd(), help="repo to check (default: cwd)")
    ap.add_argument("--list", action="store_true", help="report applicability, run nothing")
    ap.add_argument("--json", action="store_true", help="machine-readable results, with the routing")
    ap.add_argument("--selftest", action="store_true",
                    help="prove the states, the applicability rules and the routing")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    checks, problems = load_checks(plugin_roots(Path(__file__)))
    if not checks and not problems:
        print("No plugin shipped a checks.json — nothing to run, and that is not a pass.",
              file=sys.stderr)
        return 2
    project = args.project.resolve()
    if args.list:
        for c in sorted(checks, key=lambda c: (c.plugin, c.id)):
            why_not = applicability(c, project)
            print(f"  [{'n/a ' if why_not else 'runs'}] {c.plugin}/{c.id:24} "
                  f"{why_not or c.why}")
        return 0
    results = [run_check(c, project) for c in checks]
    if args.json:
        print(as_json(results, problems))
        return exit_code(results, problems)
    return report(results, problems)


def selftest() -> int:
    import tempfile
    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "plug"
        (root / "scripts").mkdir(parents=True)
        (root / "scripts" / "ok.py").write_text("import sys; sys.exit(0)\n", encoding="utf-8")
        (root / "scripts" / "bad.py").write_text(
            "import sys; print('a finding'); sys.exit(1)\n", encoding="utf-8")
        project = Path(tmp) / "proj"
        (project / "docs").mkdir(parents=True)
        (project / "docs" / "a.md").write_text("x\n", encoding="utf-8")

        def mk(**kw):
            base = dict(plugin="p", id="c", why="w", command=["python3", str(root / "scripts/ok.py")],
                        applies_when=[], requires=[], root=root)
            base.update(kw)
            return Check(**base)

        check("a passing check reports pass", run_check(mk(), project).status == PASS)
        r = run_check(mk(command=["python3", str(root / "scripts/bad.py")]), project)
        check("a failing check reports FAIL", r.status == FAIL, f"got {r.status}")
        check("a failure carries the finding's first line", "a finding" in r.detail, r.detail)
        # NOT APPLICABLE, and the two ways it arises.
        r = run_check(mk(applies_when=["qa"]), project)
        check("a missing directory is n/a, not pass", r.status == NA, f"got {r.status}")
        check("n/a says WHY", "qa" in r.detail, f"got {r.detail!r}")
        r = run_check(mk(command=["python3", str(root / "scripts/ok.py"), "{match:qa/*.csv}"]), project)
        check("an empty glob is n/a, not pass", r.status == NA, f"got {r.status}")
        # THE THIRD WAY N/A ARISES (#828): the check itself, after reading the project. Exit 3 is
        # its verdict, and every such verdict used to be graded FAIL and routed to the app.
        (root / "scripts" / "na.py").write_text(
            "import sys; print('not applicable — no config.x.locales declared (NOT a pass)'); sys.exit(3)\n",
            encoding="utf-8")
        r = run_check(mk(command=["python3", str(root / "scripts/na.py")]), project)
        check("a check that exits 3 is n/a, not FAIL", r.status == NA, f"got {r.status}")
        check("...carrying the check's own reason", "config.x.locales" in r.detail, f"got {r.detail!r}")
        check("...and routed nowhere, like every other n/a", route_of(r)[0] == UNROUTED, route_of(r)[0])
        # EXIT 2 IS OURS. "cannot compare" / "cannot run" is the toolchain failing to reach a verdict,
        # which is doctrine's to explain and not the project's to fix.
        (root / "scripts" / "cannot.py").write_text(
            "import sys; print('cannot compare: no brand pack declared'); sys.exit(2)\n", encoding="utf-8")
        r = run_check(mk(command=["python3", str(root / "scripts/cannot.py")]), project)
        check("a check that exits 2 is ERROR, not FAIL", r.status == ERROR, f"got {r.status}")
        check("...routed to doctrine, not the app", route_of(r)[0] == DOCTRINE, route_of(r)[0])
        check("...carrying the check's reason", "brand pack" in r.detail, f"got {r.detail!r}")
        # A DIAGNOSTIC NEVER MUTATES (#849). A check that writes into the project during an audit is
        # ERROR and ours -- the user is told which path moved. Needs a git repo to assert; the
        # project fixture becomes one here.
        for cmd in (["git", "init", "-q"], ["git", "add", "-A"],
                    ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"]):
            subprocess.run(cmd, cwd=project, check=True, capture_output=True)
        (root / "scripts" / "writer.py").write_text(
            "import pathlib, sys; pathlib.Path('docs/generated.md').write_text('x'); sys.exit(0)\n", encoding="utf-8")
        r = run_check(mk(command=["python3", str(root / "scripts/writer.py")]), project)
        check("a check that WRITES during the audit is ERROR, even though it exited 0", r.status == ERROR, f"got {r.status}")
        check("...naming the path it wrote", "docs/generated.md" in r.detail, f"got {r.detail!r}")
        check("...and routed to doctrine: a check that mutates is ours to fix", route_of(r)[0] == DOCTRINE, route_of(r)[0])
        (project / "docs" / "generated.md").unlink()
        r = run_check(mk(), project)
        check("a check that writes nothing is unaffected by the assertion", r.status == PASS, f"got {r.status}")
        check("outside a git repo the assertion is unasserted, not a false ERROR",
              tree_delta(None, {"a": "??"}) == [] and tree_state(Path(tmp) / "nowhere") is None)

        # A MISSING DEPENDENCY FAILS. This is the one that would otherwise read as a pass in CI.
        r = run_check(mk(requires=["definitely-not-a-real-binary-xyz"]), project)
        check("a missing dependency FAILS rather than skipping", r.status == FAIL, f"got {r.status}")
        check("and says which binary", "definitely-not-a-real-binary-xyz" in r.detail, r.detail)
        # A manifest naming a script that does not exist is an ERROR, never a quiet pass.
        r = run_check(mk(command=["python3", str(root / "scripts/gone.py")]), project)
        check("a missing script is ERROR", r.status == ERROR, f"got {r.status}")
        # {match:} runs once per file.
        (project / "docs" / "b.md").write_text("y\n", encoding="utf-8")
        r = run_check(mk(command=["python3", str(root / "scripts/ok.py"), "{match:docs/*.md}"]), project)
        check("a match runs once per file", r.status == PASS and "2 invocation" in r.detail, r.detail)
        # THE SUMMARY MUST NOT COUNT n/a AS PASSED. The near-miss that matters: a repo where
        # everything is inapplicable must not exit 0 looking like a repo where everything passed.
        import io, contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = report([Result(mk(), NA, "no qa in this project")], [])
        out = buf.getvalue()
        check("an all-n/a run says so loudly", "NOT a pass" in out, out[:120])
        check("an all-n/a run reports 0 passed", "0 passed" in out, out[:120])
        check("an all-n/a run still exits 0 (nothing failed)", code == 0, f"got {code}")

        # ROUTING (#485). Every assertion below is paired with its negative, because the value of a
        # destination is entirely in what it REFUSES to send to the app's tracker. A router that
        # answers `app` to everything is indistinguishable from no router at all, and it is the
        # shape this would naturally decay into.
        passing = run_check(mk(), project)
        check("a pass routes nowhere", route_of(passing) == ("", ""), f"got {route_of(passing)}")

        found = run_check(mk(command=["python3", str(root / "scripts/bad.py")]), project)
        check("a check that ran and found something routes to the app",
              route_of(found)[0] == APP, f"got {route_of(found)}")

        errored = run_check(mk(command=["python3", str(root / "scripts/gone.py")]), project)
        check("an ERROR routes to DOCTRINE, not the app",
              route_of(errored)[0] == DOCTRINE,
              "a manifest naming a script we do not ship is our bug; routing it to the project's "
              f"tracker files our defect against their code (got {route_of(errored)})")

        absent = run_check(mk(requires=["definitely-not-a-real-binary-xyz"]), project)
        check("a missing dependency routes to ENVIRONMENT, not the app",
              route_of(absent)[0] == ENVIRONMENT,
              f"it FAILS (correctly) but no code is at fault (got {route_of(absent)})")
        # THE NEAR MISS, which is the whole value of the carve-out. `environment` is an exemption
        # from `app`, and an exemption keyed on "the check declares requires" instead of "a required
        # binary is actually absent" would divert every real finding from every check that declares
        # a dependency -- which is all of them.
        declared = run_check(mk(command=["python3", str(root / "scripts/bad.py")],
                                requires=["python3"]), project)
        check("a real finding from a check whose dependencies are PRESENT still routes to the app",
              route_of(declared)[0] == APP,
              f"declaring `requires` must not exempt a check from its own findings "
              f"(got {route_of(declared)})")
        # `run_check` asks `shutil.which` inline and the router asks `missing_dependencies`. Nothing
        # makes them the same code, so pin that they answer alike -- in both directions.
        check("missing_dependencies agrees with run_check on an absent binary",
              missing_dependencies(absent.check) == ["definitely-not-a-real-binary-xyz"] and
              absent.status == FAIL, f"{missing_dependencies(absent.check)}, {absent.status}")
        check("missing_dependencies agrees with run_check on a present binary",
              missing_dependencies(declared.check) == [] and "not on PATH" not in declared.detail,
              f"{missing_dependencies(declared.check)}, {declared.detail!r}")

        skipped = run_check(mk(applies_when=["qa"]), project)
        check("not applicable routes NOWHERE, and specifically not to the app",
              route_of(skipped)[0] == UNROUTED, f"got {route_of(skipped)}")
        check("unrouted is not a destination anything is filed against",
              UNROUTED not in DESTINATIONS,
              "a headline for `unrouted` would print a tracker to send non-findings to")
        check("a not-applicable check appears in NO destination group",
              not any(routed([skipped], []).values()), f"{routed([skipped], [])}")
        check("every destination declares where its findings go and why",
              all(len(v) == 2 and all(v) for v in DESTINATIONS.values()), f"{DESTINATIONS}")

        # THE SUMMARY MUST NOT ADD ERRORS INTO THE FAILURE COUNT. This is the defect the routing
        # was written for: before #485 an ERROR was folded into "N failed", so a user read our
        # broken manifest as a defect in their own app and had no way to tell.
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = report([found, errored], [])
        out = buf.getvalue()
        check("an ERROR is counted apart from a failure", "1 failed, 1 errored" in out, out[:200])
        check("the report says where each finding goes", "Where each finding goes" in out, out[:200])
        check("a doctrine gap names the upstream route", "/rails-flow:report" in out, out[:400])
        check("a mixed run still exits 1", code == 1, f"got {code}")

        # A manifest that will not parse has no Result, and must still reach the doctrine list.
        check("a manifest problem routes to DOCTRINE",
              routed([], ["checks.json: unreadable manifest"])[DOCTRINE] ==
              [("checks.json", "checks.json: unreadable manifest")],
              f"{routed([], ['checks.json: unreadable manifest'])}")
        check("a manifest problem alone still exits 1", exit_code([], ["boom"]) == 1)

        # THE MACHINE PATH MUST CARRY THE ROUTING, or an agent re-derives it by parsing prose.
        payload = json.loads(as_json([passing, found, errored, skipped], ["boom"]))
        destinations = [row["destination"] for row in payload["results"]]
        check("--json routes every non-pass row",
              destinations.count(None) == 1 and set(destinations) ==
              {None, APP, DOCTRINE, UNROUTED}, f"got {destinations}")
        check("--json states why each row was routed",
              all(row["routed_because"] for row in payload["results"] if row["destination"]),
              "a destination with no reason cannot be argued with")
        check("--json carries the manifest problems", payload["manifest_problems"] == ["boom"])
        check("--json counts every state", payload["summary"] == {PASS: 1, FAIL: 1, NA: 1, ERROR: 1},
              f"{payload['summary']}")

    # The SHIPPED manifests must be loadable and name scripts that exist -- otherwise this runner
    # reports ERROR on a user's first run, which is the worst possible first impression.
    checks, problems = load_checks(plugin_roots(Path(__file__)))
    # The subparser detector, fixtured directly. Both directions, because the false positive is what
    # would get this rule deleted and the true positive is what it exists for.
    check("a subparser group is detected",
          required_subcommand("usage: p [-h] {completed,derive,validate} ...\n\noptions:\n") ==
          {"completed", "derive", "validate"})
    check("a --format choice list is NOT a subcommand",
          required_subcommand("usage: p [-h] [--out OUT]\n\noptions:\n  --format {json,md}\n") == set(),
          "a choice list in the options body must not read as a required subcommand")
    check("a script with no subparsers reports none",
          required_subcommand("usage: p [-h] [--selftest] [path]\n\noptions:\n") == set())

    check("shipped manifests parse", not problems, f"{problems}")
    check("shipped manifests declare checks", len(checks) >= 5, f"got {len(checks)}")

    # EVERY SHIPPED COMMAND MUST SUPPLY A REQUIRED SUBCOMMAND. I declared `evidence_manifest.py`
    # bare; it requires one of {completed,derive,validate,index,prune}, so it exited on a usage error
    # and the runner reported FAIL. The runner was right and the MANIFEST was wrong, and nothing
    # would have caught it before a user's first run.
    #
    # An earlier version of this assertion ran `<prefix> --help` and was VACUOUS: argparse prints the
    # top-level help and exits 0 whether or not a subcommand is required, so re-introducing the bug
    # sailed through. Caught by mutating the manifest and watching the check stay silent. It now
    # reads the usage line for a `{a,b,c}` group and requires the manifest to have chosen one.
    for c in checks:
        argv = [tok.replace("{plugin}", str(c.root)) for tok in c.command
                if not tok.startswith("{match:")]
        script = argv[1] if len(argv) > 1 else None
        if not script or not script.endswith(".py"):
            continue
        try:
            helped = subprocess.run([argv[0], script, "--help"], capture_output=True,
                                    text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as exc:
            check(f"{c.plugin}/{c.id} help runs", False, str(exc)[:90])
            continue
        check(f"{c.plugin}/{c.id} help runs", helped.returncode == 0, f"exit {helped.returncode}")
        # Only a SUBPARSER group counts, and it is identified by two things together: it sits in the
        # `usage:` block, and argparse follows it with ` ...`. Matching `{a,b}` anywhere in the help
        # produced a false positive on `architecture_graph.py`, whose `{json,md}` is a --format
        # choice list in the options body -- a rule that fires on a correct manifest gets deleted,
        # so the pattern is narrowed rather than the finding excused.
        options = required_subcommand(helped.stdout)
        if not options:
            continue                       # no subcommands: a bare invocation is legitimate
        supplied = [tok for tok in argv[2:] if not tok.startswith("-")]
        check(f"{c.plugin}/{c.id} supplies a required subcommand",
              bool(supplied) and supplied[0] in options,
              f"needs one of {sorted(options)}, manifest supplies {supplied[:1] or 'nothing'}")
    for c in checks:
        target = Path(c.command[1].replace("{plugin}", str(c.root))) if len(c.command) > 1 else None
        if target and target.suffix == ".py":
            check(f"{c.plugin}/{c.id} names a real script", target.is_file(), f"{target} missing")

    # ---- #715/#716: a FAIL's detail must be readable ------------------------------------
    # Registering the first checks whose tool writes for a human broke the summary line twice.
    # Each clause gets a fixture that trips only it, so a mutation to either is provable.
    #
    # ANSI ONLY -- no severity word, no location -- so this proves the stripping, not the ranking.
    _t = "\x1b[1m\x1b[91mbg-#{status}\x1b[0m interpolated"
    check("ANSI escapes are stripped from the detail",
          summarise(_t, 1)[0] == "bg-#{status} interpolated",
          f"got {summarise(_t, 1)[0]!r}")
    # An OSC-8 hyperlink, which is what made the real output look corrupted rather than merely ugly.
    _t = "\x1b]8;;https://x/rule\x1b\\erb-no-unsafe-raw\x1b]8;;\x1b\\ tail"
    check("OSC-8 hyperlinks are stripped too",
          "\x1b" not in summarise(_t, 1)[0], f"got {summarise(_t, 1)[0]!r}")
    # RANKING, with no escapes at all: the finding is the THIRD line, behind two preamble lines.
    # `herb analyze` really does open with its banner and then a config notice.
    _t = "Herb v0.10.3\nNo .herb.yml found, using defaults\nValidation errors:"
    check("a banner and a config notice lose to a line naming a severity",
          summarise(_t, 1)[0] == "Validation errors:",
          f"got {summarise(_t, 1)[0]!r}")
    # ---- THE FINDINGS, not just their count (#812) --------------------------------------------
    # `[FAIL] mandated-gems  1 finding(s):` was the whole report -- a trailing colon promising a
    # list, followed by nothing. The individual scripts carry the finding, the reason AND the fix.
    OURS = ("1 finding(s):\n"
            "  - the prescribed testing stack is incomplete — missing `vcr`.\n"
            "    testing.md declares the full block; that file is doctrine, not a menu.\n"
            "    Install:  bundle add vcr --group test\n")
    summary, findings = summarise(OURS, 1)
    check("the summary is still the summary", summary == "1 finding(s):", f"got {summary!r}")
    check("...and the findings are CARRIED, not dropped", len(findings) == 3, f"{findings}")
    check("...including the fix, which is the only actionable line",
          any("bundle add vcr" in f for f in findings), f"{findings}")
    # Guarded: with the carry removed, `findings` is empty and `findings[0]` raises. A crash aborts
    # the run before any labelled assertion reports, and a crash is not a verdict.
    check("...with indentation preserved, so the shape survives",
          bool(findings) and findings[0].startswith("  - "), f"{findings!r}")

    # ---- THE TWO CONSUMERS, driven directly ---------------------------------------------------
    # Everything above proves `summarise` carries the lines. Neither proves that `report` PRINTS
    # them or that `as_json` EMITS them -- and emptying either survived every fixture above. Proving
    # the helper is not proving the caller; this repo has paid for that lesson twice already.
    _r = Result(Check("p", "i", "why", [], [], [], Path(".")), FAIL, "1 finding(s):",
                ("  - the actual problem", "    Install:  bundle add vcr"))
    import contextlib as _ctx, io as _io
    _buf = _io.StringIO()
    with _ctx.redirect_stdout(_buf):
        report([_r], [])
    _out = _buf.getvalue()
    check("report() PRINTS the findings, not only the count",
          "the actual problem" in _out and "bundle add vcr" in _out, f"{_out[:200]!r}")
    check("...indented under their check, so the association is visible",
          "      - the actual problem" in _out, f"{_out[:200]!r}")

    _rec = json.loads(as_json([_r], []))["results"][0]
    check("as_json() EMITS a findings key", "findings" in _rec, f"{sorted(_rec)}")
    check("...carrying every line", _rec.get("findings") == list(_r.findings), f"{_rec.get('findings')}")

    # A PRE-SUMMARY BANNER is still dropped: everything before the summary is the tool clearing its
    # throat, and carrying it would put a version string where a finding belongs.
    summary, findings = summarise("Herb v0.10.3\nNo .herb.yml found\nValidation errors:\n  a.erb:2 bad", 1)
    check("a banner before the summary is not carried", not any("v0.10.3" in f for f in findings),
          f"{findings}")
    check("...while what follows the summary is", any("a.erb:2" in f for f in findings), f"{findings}")

    # VOLUME IS CAPPED, and the cap SAYS SO. Silently truncating would be this same defect one step
    # along -- a reader who cannot tell whether they saw everything.
    many = "3 finding(s):\n" + "".join(f"  - finding {i}\n" for i in range(MAX_FINDING_LINES + 12))
    summary, findings = summarise(many, 1)
    check("a very long output is capped", len(findings) == MAX_FINDING_LINES + 1, f"{len(findings)}")
    check("...and the last line names what was dropped",
          bool(findings) and "more line(s)" in findings[-1] and "12" in findings[-1],
          f"{findings[-1:]!r}")

    # THE ROUTING VIEW stays one line, but that line is the finding rather than its cardinality.
    r_count = Result(Check("p", "i", "why", [], [], [], Path(".")), FAIL, "1 finding(s):",
                     ("  - the actual problem", "    and its fix"))
    check("the routing view shows the finding, not the count",
          routing_detail(r_count) == "the actual problem", f"{routing_detail(r_count)!r}")
    # ...and a detail that is ALREADY a finding is left alone -- no colon, nothing to substitute.
    r_plain = Result(Check("p", "i", "why", [], [], [], Path(".")), FAIL, "a.erb:2 unquoted attr", ())
    check("a real one-line detail is left alone",
          routing_detail(r_plain) == "a.erb:2 unquoted attr", f"{routing_detail(r_plain)!r}")

    # A LOCATION counts as a finding even with no severity word -- `path:line:col`.
    _t = "Running: npx thing\napp/views/a.html.erb:2:6 unquoted attribute"
    check("a path:line:col line counts as a finding",
          summarise(_t, 1)[0].startswith("app/views/a.html.erb:2:6"),
          f"got {summarise(_t, 1)[0]!r}")
    # FALLBACK. Nothing names a severity or a location, and a failing check still has to say
    # something -- returning "" would be a FAIL with no detail at all.
    _t = "something opaque happened\nand then more of it"
    check("falls back to the first line when nothing looks like a finding",
          summarise(_t, 3)[0] == "something opaque happened",
          f"got {summarise(_t, 3)[0]!r}")
    check("empty output falls back to the exit code",
          summarise("   \n\n", 2)[0] == "exit 2",
          f"got {summarise('   \n\n', 2)[0]!r}")
    check("the detail is capped at 160 chars",
          len(summarise("error " + "x" * 500, 1)[0]) == 160,
          f"got {len(summarise('error ' + 'x' * 500, 1)[0])}")

    # ---- #706: one root per PLUGIN, never one per cached version -------------------------
    # The fixture is the installed layout, because that is the one the old walk got wrong and the
    # one every local run uses:  <cache>/<plugin>/<version>/checks.json
    with tempfile.TemporaryDirectory() as tmp:
        cache = (Path(tmp) / "cache").resolve()
        cache.mkdir(parents=True, exist_ok=True)

        def plug(name: str, version: str) -> Path:
            d = cache / name / version
            (d / "scripts").mkdir(parents=True)
            (d / ".claude-plugin").mkdir(parents=True)
            (d / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": name, "version": version}), encoding="utf-8")
            (d / "checks.json").write_text(json.dumps({"checks": []}), encoding="utf-8")
            (d / "scripts" / "project_gates.py").write_text("x\n", encoding="utf-8")
            return d

        for v in ("1.18.2", "1.19.0", "1.20.0", "1.22.2", "1.23.0"):
            plug("rails-flow", v)
        plug("qa-flow", "1.24.1")
        plug("qa-flow", "1.25.0")
        plug("design-flow", "1.29.0")
        invoked = cache / "rails-flow" / "1.23.0" / "scripts" / "project_gates.py"

        roots = plugin_roots(invoked)
        names = [plugin_identity(r)[0] for r in roots]
        # THE DEFECT: five cached rails-flow versions produced five roots and every check ran 5x,
        # with one artifact graded ok by some versions and FAIL by others.
        check("one root per plugin, not one per cached version", len(roots) == 3,
              f"got {len(roots)}: {[f'{r.parent.name}/{r.name}' for r in roots]}")
        check("no plugin appears twice", len(names) == len(set(names)), f"{names}")
        # THE OTHER HALF, and the quieter one: sibling PLUGINS live a level higher than the old walk
        # looked, so their checks silently never ran while the counts read busy.
        check("sibling plugins are discovered", set(names) == {"rails-flow", "qa-flow", "design-flow"},
              f"{sorted(names)}")
        # A sibling with several cached versions collapses to the highest.
        qa = [r for r in roots if plugin_identity(r)[0] == "qa-flow"]
        check("a sibling collapses to its highest cached version",
              len(qa) == 1 and qa[0].name == "1.25.0", f"{[r.name for r in qa]}")
        # The version you INVOKED wins its own name, even though 1.23.0 is not the highest string
        # sorted lexically and even if a higher one were cached: launching a script and running a
        # different version's checks would be surprising.
        mine = [r for r in roots if plugin_identity(r)[0] == "rails-flow"]
        check("the invoked version wins for its own plugin",
              len(mine) == 1 and mine[0].name == "1.23.0", f"{[r.name for r in mine]}")
        plug("rails-flow", "1.24.0")
        mine = [r for r in plugin_roots(invoked) if plugin_identity(r)[0] == "rails-flow"]
        check("...even when a higher version is cached alongside",
              len(mine) == 1 and mine[0].name == "1.23.0", f"{[r.name for r in mine]}")

        # A FLAT layout still works -- that is the source-checkout shape, and breaking it would trade
        # one wrong environment for another.
        flat = (Path(tmp) / "plugins").resolve()
        for name in ("rails-flow", "design-flow"):
            d = flat / name
            (d / "scripts").mkdir(parents=True)
            (d / ".claude-plugin").mkdir(parents=True)
            (d / ".claude-plugin" / "plugin.json").write_text(
                json.dumps({"name": name, "version": "9.9.9"}), encoding="utf-8")
            (d / "checks.json").write_text(json.dumps({"checks": []}), encoding="utf-8")
        flat_roots = plugin_roots(flat / "rails-flow" / "scripts" / "project_gates.py")
        check("a flat source-checkout layout still finds both plugins", len(flat_roots) == 2,
              f"got {len(flat_roots)}")

        # Identity comes from the MANIFEST, not the directory name -- the name is a version number in
        # one layout and a plugin name in the other, so reading it means guessing the layout.
        check("identity is read from plugin.json",
              plugin_identity(cache / "rails-flow" / "1.23.0") == ("rails-flow", (1, 23, 0)),
              f"{plugin_identity(cache / 'rails-flow' / '1.23.0')}")
        # An unreadable manifest degrades to the directory name rather than crashing the whole run.
        orphan = cache / "orphan" / "0.0.1"
        (orphan / "scripts").mkdir(parents=True)
        (orphan / "checks.json").write_text("{}", encoding="utf-8")
        check("a missing manifest degrades to the directory name",
              plugin_identity(orphan) == ("0.0.1", (0,)), f"{plugin_identity(orphan)}")

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"project_gates selftest: {n} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
