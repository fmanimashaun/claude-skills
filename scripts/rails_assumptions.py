#!/usr/bin/env python3
"""Inventory the Rails assumptions in the flows, and the decision for each (#2164, slice 2 of #2162).

Run:  python3 scripts/rails_assumptions.py                # rebuild docs/architecture/rails-assumptions.{md,json}
      python3 scripts/rails_assumptions.py --check        # drift gate: the policy resolves every file, the page matches a clean build (compares the blob at HEAD)
      python3 scripts/rails_assumptions.py --status       # the counts, from a fresh scan, one line each
      python3 scripts/rails_assumptions.py --selftest     # prove each rule fires AND stays silent

WHY THIS EXISTS. `nextjs-stack` (EPIC #2162) will be a second stack beside `rails-stack`, and `plugin-boundaries` rule 1 forbids a per-stack
fork of any flow. So before anything is built, every place a flow assumes Rails has to be named and given ONE of four decisions:

  rails-stack  the file exists only for Rails projects (an agent, a gate, a hook): it moves to `rails-stack`, whose manifest registers it
  detector     the file is flow logic that hardwires a Rails command or path: it stays, and asks the stack detector (#2163) what to run
  reword       prose or metadata that says "Rails" and drives no behaviour: reworded in whichever slice touches the file
  neutral      the hits are incidental (an example, a fixture, a name inside another word): nothing to change

THE COUNTS COME FROM THIS SCRIPT. A number in the page, an issue or a PR is `--status` output, never recalled. The scan is a fixed table of
patterns (`PATTERNS`) over every tracked text file of the four flows; the DECISIONS are the committed policy
(`docs/architecture/rails-assumptions.policy.json`), a table of path globs with the reason each decision was made, and the script refuses:

  * a file with hits that no rule resolves (a new Rails FILE cannot arrive undecided);
  * a file decided `neutral` whose hit-line count differs from the count the policy records for it (`lines`): a neutral file must STAY at its
    recorded references, so a new Rails line in it needs a decision. This is the only line-level ratchet: a new Rails line in a `rails-stack`,
    `detector` or `reword` file passes once the page is rebuilt, because those already say the file assumes Rails;
  * a rule that matches no file with hits (a rule left behind after the file moved or was cleaned);
  * a decision outside the four, or a `rails-stack` rule with no move group, or a move group with no issue filed under #2162;
  * a mutation or selftest file whose script has no decision (those files follow the script they test).

WHAT IT IS HONESTLY NOT. A regex scan finds the lines that NAME a Rails thing; it cannot tell a line that assumes Rails from a line that
explains why it does not. The decision is a person's, made by reading the file, and the policy says why. The scan is a floor: a flow that
assumes Rails without ever naming it (a path convention in prose, say) is not found here.

Stdlib only. Exit codes: 0 clean · 1 findings · 2 not this repo.
"""
from __future__ import annotations

import argparse
import io
import fnmatch
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "plugins" / "rails-flow" / "scripts"))
import fixture_git  # noqa: E402  (#1588: a selftest fixture's git touches only its own temp repo)
import hermetic_git  # noqa: E402  (git that starts nothing in the background, for the real repository read)
FLOWS = ("rails-flow", "qa-flow", "pipeline", "design-flow")
POLICY = "docs/architecture/rails-assumptions.policy.json"
JSON_OUT = "docs/architecture/rails-assumptions.json"
MD_OUT = "docs/architecture/rails-assumptions.md"
DECISIONS = ("rails-stack", "detector", "reword", "neutral")
CATEGORIES = ("tool", "gem", "path", "concept", "hotwire")
# Where a scan reads from, relative to the repo root. A flow's own `checks.json` and manifests are in scope: they are where a stack registers.
SCOPE = tuple(f"plugins/{flow}" for flow in FLOWS)


class Pattern:
    __slots__ = ("id", "category", "rx", "what")

    def __init__(self, ident: str, category: str, regex: str, what: str, flags: int = 0) -> None:
        self.id, self.category, self.what = ident, category, what
        self.rx = re.compile(regex, flags)


# A line can match several patterns; each match is one hit. `Rails` (capitalised, not followed by a hyphen) is the framework's name: the lowercase
# `rails-flow` / `rails-stack` / `/rails-flow:` are this marketplace's own plugin names and are deliberately not hits.
PATTERNS: tuple[Pattern, ...] = (
    Pattern("bin-rails", "tool", r"\bbin/rails\b|\brails (?:db:\w+|runner|console|server|generate|routes|credentials|assets:\w+|tailwindcss:\w+|new)\b",
            "the Rails CLI"),
    Pattern("bundler", "tool", r"\bbundle (?:exec|install|add|update|check|lock|show|config)\b|\bbundler\b(?!-audit)", "Bundler and the Ruby toolchain", re.I),
    Pattern("rspec", "tool", r"\brspec\b(?!-)", "the RSpec runner", re.I),
    Pattern("rubocop", "tool", r"\brubocop\b", "RuboCop", re.I),
    Pattern("brakeman", "tool", r"\bbrakeman\b", "Brakeman", re.I),
    Pattern("bundler-audit", "tool", r"\bbundler-audit\b", "bundler-audit", re.I),
    Pattern("erb-lint", "tool", r"\bherb\b|\berb[_-]lint\b", "the ERB linters", re.I),
    Pattern("rake", "tool", r"\brake\b", "Rake", re.I),
    Pattern("ruby", "tool", r"\bruby\b(?! on)|\.ruby-version", "the Ruby interpreter", re.I),
    Pattern("binstub", "tool", r"\bbin/(?:ci|setup|dev|brakeman|rubocop|jobs|thrust)\b", "a Rails binstub"),
    Pattern("gem", "gem", r"\b(?:simple_form|factory_bot(?:_rails)?|capybara|simplecov|rspec-rails|shoulda-matchers|pundit|devise|solid_queue|solid_cache|"
                          r"solid_cable|turbo-rails|stimulus-rails|importmap-rails|view_component|propshaft|tailwindcss-rails|rack-attack|webmock)\b",
            "a named Ruby gem", re.I),
    Pattern("gemfile", "path", r"\bGemfile(?:\.lock)?\b", "the Gemfile"),
    Pattern("routes", "path", r"\bconfig/routes\.rb\b", "config/routes.rb"),
    Pattern("rails-config", "path", r"\bconfig/(?:application\.rb|environments/|initializers/|credentials|database\.yml|ci\.rb|puma\.rb|storage\.yml)",
            "a Rails config file"),
    Pattern("db", "path", r"\bdb/(?:migrate|schema\.rb|[a-z_]*_schema\.rb|seeds|queue_migrate)", "Active Record's db/ layout"),
    Pattern("app-layers", "path", r"\bapp/(?:models|controllers|views|components|jobs|helpers|mailers|javascript|assets|policies|services|channels)\b",
            "Rails' app/ layout"),
    Pattern("spec-dir", "path", r"(?<![\w.-])spec/|\.rspec\b", "the spec/ directory"),
    Pattern("rubocop-yml", "path", r"\.rubocop(?:\.yml|_todo\.yml)", "the RuboCop config"),
    Pattern("rails-word", "concept", r"\bRails\b(?![-_:])|(?<![-\w])rails (?:apps?|applications?|projects?|gems?|models?|migrations?|controllers?|engines?|generators?)\b",
            "the framework by name (capitalised, or lowercase before a Rails noun: `off-rails` and `the rails` are not hits)"),
    Pattern("active-framework", "concept",
            r"\bActive(?:Record|Storage|Job|Model)\b|\bAction(?:Mailer|Cable|Controller|View)\b", "a Rails framework component"),
    Pattern("erb", "concept", r"\.erb\b|\bERB\b|\bViewComponent\b", "ERB or ViewComponent templates", re.I),
    Pattern("ruby-file", "concept", r"\.rb\b", "a Ruby source file"),
    Pattern("hotwire", "hotwire", r"\bHotwire\b|\bTurbo\b|\bStimulus\b|\bturbo[_-]frame\b|\bturbo[_-]stream\b", "Hotwire (Turbo, Stimulus)"),
)
PATTERN_IDS = tuple(p.id for p in PATTERNS)


# ---------------------------------------------------------------------------------------------
# The scan
# ---------------------------------------------------------------------------------------------

def tracked_files(root: Path) -> list[str]:
    """Every tracked file under the four flows, repo-relative, sorted. `git ls-files`, so an untracked scratch file is never inventoried."""
    out = subprocess.run(["git", "ls-files", "-z", "--", *SCOPE], cwd=root, capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.split("\0") if p)


def kind_of(path: str) -> str:
    """What sort of file this is, from its path alone: the unit the dispositions are reasoned about."""
    p = path.split("/", 2)[-1]
    if "/mutations/" in f"/{p}":
        return "mutation"
    if p.endswith(("_selftest.py", ".test.ts", ".unit.mjs")) or p.startswith("tests/"):
        return "selftest"
    for prefix, kind in (("commands/", "command"), ("agents/", "agent"), ("hooks/", "hook"), ("scaffold/", "scaffold"), ("templates/", "template"),
                         ("reference/", "reference"), ("git-hooks/", "hook"), (".claude-plugin/", "manifest")):
        if p.startswith(prefix):
            return kind
    if p.startswith("scripts/"):
        return "script"
    if p in ("checks.json", "mandated_gems.json") or p.endswith(".json"):
        return "data"
    return "doc"


def scan(root: Path, files: list[str] | None = None) -> dict[str, dict]:
    """`{path: {"kind", "lines": [n, ...], "ids": {pattern id: count}, "categories": {category: count}}}` for every file with at least one hit."""
    result: dict[str, dict] = {}
    for rel in files if files is not None else tracked_files(root):
        try:
            raw = (root / rel).read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8000]:
            continue  # binary
        lines: set[int] = set()
        ids: Counter[str] = Counter()
        cats: Counter[str] = Counter()
        for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
            for pat in PATTERNS:
                if pat.rx.search(line):
                    lines.add(number)
                    ids[pat.id] += 1
                    cats[pat.category] += 1
        if lines:
            result[rel] = {"kind": kind_of(rel), "lines": sorted(lines), "ids": dict(sorted(ids.items())),
                           "categories": dict(sorted(cats.items()))}
    return result


# ---------------------------------------------------------------------------------------------
# The policy: which decision, and why
# ---------------------------------------------------------------------------------------------

def load_policy(root: Path) -> dict:
    return json.loads((root / POLICY).read_text(encoding="utf-8"))


def subject_of(path: str) -> str | None:
    """The script a mutation guard or a selftest belongs to, or None. Those files take the decision of the script they test: a guard for a gate
    that moves to rails-stack moves with it, and a separate row for it would only restate the decision."""
    kind = kind_of(path)
    plugin, rest = path.split("/")[1], path.split("/", 2)[2]
    if kind == "mutation":
        return f"plugins/{plugin}/scripts/{Path(rest).name}"
    if kind == "selftest" and rest.startswith("scripts/") and rest.endswith("_selftest.py"):
        return f"plugins/{plugin}/scripts/{Path(rest).name[: -len('_selftest.py')]}.py"
    return None


def resolve(path: str, rules: list[dict]) -> tuple[int, dict] | None:
    for index, rule in enumerate(rules):
        if any(fnmatch.fnmatchcase(path, glob) for glob in rule["match"]):
            return index, rule
    return None


def setup_flow_findings(decided: dict[str, dict], sf: dict | None) -> list[str]:
    """setup-flow is one 1,100-line file holding both the neutral rules scaffold and Rails-only proposals, so its sections are decided
    separately: every hit line must fall in exactly one declared section, and the section's issue must be filed (#2164 requirement)."""
    if not sf:
        return []
    out: list[str] = []
    row = decided.get(sf["file"])
    if row is None:
        return [f"setup_flow: {sf['file']} has no hits or no file rule; the section table is for a file the scan finds"]
    if not isinstance(sf.get("issue"), int):
        out.append("setup_flow: no issue number filed under #2162 yet")
    for sec in sf["sections"]:
        if sec["disposition"] not in DECISIONS:
            out.append(f"setup_flow section {sec['lines']}: disposition {sec['disposition']!r} is not one of {', '.join(DECISIONS)}")
        if not any(sec["lines"][0] <= n <= sec["lines"][1] for n in row["lines"]):
            out.append(f"setup_flow section {sec['lines']}: no hit line falls inside it (the file changed): fix the range")
    for n in row["lines"]:
        owners = [s for s in sf["sections"] if s["lines"][0] <= n <= s["lines"][1]]
        if len(owners) != 1:
            out.append(f"setup_flow: hit line {n} is in {len(owners)} sections, expected exactly one")
    return out


def decide(hits: dict[str, dict], policy: dict) -> tuple[dict[str, dict], list[str]]:
    """`({path: {..., "decision", "move", "assumes", "how", "followed"}}, findings)`: the scan joined to the policy, both directions."""
    findings: list[str] = []
    rules: list[dict] = policy["rules"]
    moves: dict = policy.get("moves", {})
    used: Counter[int] = Counter()
    out: dict[str, dict] = {}
    for path in sorted(hits):
        row = dict(hits[path])
        found, followed = None, None
        subject = subject_of(path)
        if subject is not None:  # a guard or selftest takes its script's decision before any glob over its own path
            found = resolve(subject, rules)
            followed = subject if found else None
        if found is None:
            found = resolve(path, rules)
        if found is None:
            findings.append(f"{path}: {len(row['lines'])} line(s) name Rails and no rule in {POLICY} decides this file")
            continue
        index, rule = found
        used[index] += 1
        if rule["decision"] == "neutral":
            recorded = rule.get("lines", {}).get(path)
            if recorded != len(row["lines"]):
                findings.append(f"{path}: decided neutral with {len(row['lines'])} hit line(s) but the policy records {recorded}: a neutral file must not gain a Rails "
                                f"reference without a new decision (reclassify it or remove the line); lower the recorded count when a reference goes away")
        row.update({"decision": rule["decision"], "move": rule.get("move", ""), "assumes": rule.get("assumes", ""), "how": rule.get("how", ""),
                    "followed": followed or ""})
        out[path] = row
    for index, rule in enumerate(rules):
        title = rule["match"][0]
        if rule.get("decision") not in DECISIONS:
            findings.append(f"rule {title}: decision {rule.get('decision')!r} is not one of {', '.join(DECISIONS)}")
        if not rule.get("how"):
            findings.append(f"rule {title}: no `how`: say what the file does after the decision, or why it needs nothing")
        if rule.get("decision") == "rails-stack":
            move = rule.get("move")
            if move not in moves:
                findings.append(f"rule {title}: a rails-stack decision names move {move!r}, which {POLICY} does not declare under `moves`")
        elif rule.get("move"):
            findings.append(f"rule {title}: only a rails-stack decision carries a move group (this one is {rule.get('decision')})")
        if not used[index]:
            findings.append(f"rule {title}: matches no file with a hit (the file moved, was cleaned, or the glob is wrong): delete or fix the rule")
    findings += setup_flow_findings(out, policy.get("setup_flow"))
    move_used = {r.get("move") for r in rules if r.get("decision") == "rails-stack"}
    for name, move in moves.items():
        if name not in move_used:
            findings.append(f"move {name}: no rails-stack rule names it")
        if not isinstance(move.get("issue"), int):
            findings.append(f"move {name} ({move.get('title', '?')}): no issue number filed under #2162 yet")
    return out, findings


# ---------------------------------------------------------------------------------------------
# The report
# ---------------------------------------------------------------------------------------------

def summarise(decided: dict[str, dict]) -> dict:
    """Every number the page and the PR quote, derived from the joined rows and nothing else."""
    by_decision = {d: {"files": 0, "lines": 0} for d in DECISIONS}
    by_flow: dict[str, dict] = {flow: {"files": 0, "lines": 0, **{d: 0 for d in DECISIONS}} for flow in FLOWS}
    by_category: Counter[str] = Counter()
    by_pattern: Counter[str] = Counter()
    by_kind: dict[str, dict] = {}
    for path, row in decided.items():
        flow = path.split("/")[1]
        n = len(row["lines"])
        by_decision[row["decision"]]["files"] += 1
        by_decision[row["decision"]]["lines"] += n
        by_flow[flow]["files"] += 1
        by_flow[flow]["lines"] += n
        by_flow[flow][row["decision"]] += 1
        kind = by_kind.setdefault(row["kind"], {"files": 0, "lines": 0})
        kind["files"] += 1
        kind["lines"] += n
        by_category.update(row["categories"])
        by_pattern.update(row["ids"])
    return {"files": len(decided), "lines": sum(len(r["lines"]) for r in decided.values()), "by_decision": by_decision, "by_flow": by_flow,
            "by_kind": dict(sorted(by_kind.items())), "by_category": {c: by_category.get(c, 0) for c in CATEGORIES},
            "by_pattern": {i: by_pattern.get(i, 0) for i in PATTERN_IDS}}


def build_json(decided: dict[str, dict], policy: dict) -> str:
    payload = {"generated_by": "scripts/rails_assumptions.py", "policy": POLICY, "summary": summarise(decided),
               "moves": policy.get("moves", {}), "files": {p: {k: v for k, v in r.items() if k != "followed" or v} for p, r in decided.items()}}
    return json.dumps(payload, indent=1, sort_keys=True) + "\n"


def _lines_cell(lines: list[int], path: str) -> str:
    shown = ", ".join(str(n) for n in lines[:5])
    more = f" +{len(lines) - 5} more" if len(lines) > 5 else ""
    return f"`{path.split('/', 2)[2]}:{lines[0]}`<br>L{shown}{more}"


def build_md(decided: dict[str, dict], policy: dict) -> str:
    s = summarise(decided)
    moves: dict = policy.get("moves", {})
    out: list[str] = []
    w = out.append
    w("# Rails assumptions in the flows\n")
    w("_Generated by `scripts/rails_assumptions.py` from the committed policy `docs/architecture/rails-assumptions.policy.json`; do not edit. "
      "`python3 scripts/rails_assumptions.py --check` fails when this page is stale._\n")
    w("Slice 2 of the `nextjs-stack` epic (#2162, #2164). `plugin-boundaries` rule 1: the flows stay one stack-neutral core, so every place they assume "
      "Rails gets one decision. The scan finds the lines that **name** a Rails thing (a CLI, a gem, a Rails path, the framework); the decision per file is "
      "a person's, made by reading it, with the reason in the policy. A flow that assumes Rails without naming it is not found here.\n")
    w("## Decisions\n")
    w("| decision | what it means | files | lines |\n|---|---|---:|---:|")
    meaning = {"rails-stack": "exists only for Rails projects; moves to `rails-stack` and registers through its manifest",
               "detector": "flow logic that hardwires a Rails command or path; stays and asks the stack detector (#2163)",
               "reword": "prose or metadata that says Rails and drives no behaviour; reworded where the file is next touched",
               "neutral": "incidental hits (an example, a fixture, a fragment of another word); nothing to change"}
    for d in DECISIONS:
        w(f"| `{d}` | {meaning[d]} | {s['by_decision'][d]['files']} | {s['by_decision'][d]['lines']} |")
    w(f"| **all** | | **{s['files']}** | **{s['lines']}** |\n")
    w("## By flow\n")
    w("| flow | files | lines | " + " | ".join(f"`{d}`" for d in DECISIONS) + " |\n|---|---:|---:|" + "---:|" * len(DECISIONS))
    for flow, c in s["by_flow"].items():
        w(f"| `{flow}` | {c['files']} | {c['lines']} | " + " | ".join(str(c[d]) for d in DECISIONS) + " |")
    w("\n## By what is named\n")
    w("| category | lines naming it |\n|---|---:|")
    for cat in CATEGORIES:
        w(f"| {cat} | {s['by_category'][cat]} |")
    w("\nA line that names two things counts once per category it names in this table and once overall in the totals above.\n")
    w("## The moves (each is an issue under #2162)\n")
    for name, move in moves.items():
        files = [p for p, r in decided.items() if r["move"] == name]
        issue = f"#{move['issue']}" if isinstance(move.get("issue"), int) else "(no issue yet)"
        w(f"### {name}: {move['title']} ({issue})\n")
        w(f"{move['summary']}\n")
        w("Files: " + ", ".join(f"`{p.split('/', 2)[2]}` ({p.split('/')[1]})" for p in files) + "\n")
    sf = policy.get("setup_flow")
    if sf and sf["file"] in decided:
        row = decided[sf["file"]]
        w(f"## setup-flow, section by section (issue #{sf['issue']})\n" if isinstance(sf.get("issue"), int) else "## setup-flow, section by section\n")
        w(sf["summary"] + "\n")
        w("| lines | Rails hit lines | what it assumes | decision | how |\n|---|---:|---|---|---|")
        for sec in sf["sections"]:
            a, b = sec["lines"]
            n = sum(1 for x in row["lines"] if a <= x <= b)
            w(f"| {a}-{b} | {n} | {sec['assumes']} | `{sec['disposition']}` | {sec['how']} |")
        w("\n**Proposal for a `nextjs-stack` repo.**\n")
        for step in sf["proposal"]:
            w(f"- {step}")
        w("")
    w("## The inventory, file by file\n")
    w("`file:first line` and up to five line numbers are shown; every line number is in `rails-assumptions.json`. Mutation guards and selftests "
      "follow the script they test (marked ↳).\n")
    for flow in FLOWS:
        rows = [(p, r) for p, r in decided.items() if p.split("/")[1] == flow]
        if not rows:
            continue
        w(f"### {flow}\n")
        w("| file | kind | lines | what it assumes | decision | how |\n|---|---|---:|---|---|---|")
        for path, r in rows:
            follow = " ↳" if r["followed"] else ""
            decision = f"`{r['decision']}`" + (f" ({r['move']})" if r["move"] else "")
            w(f"| {_lines_cell(r['lines'], path)}{follow} | {r['kind']} | {len(r['lines'])} | {r['assumes']} | {decision} | {r['how']} |")
        w("")
    return "\n".join(out) + "\n"


def committed_blob(rel: str, root: Path = REPO) -> str | None:
    try:
        r = subprocess.run(["git", "show", f"HEAD:{rel}"], cwd=root, env=hermetic_git.env(), capture_output=True, text=True, check=False)
    except OSError:
        return None
    return r.stdout if r.returncode == 0 else None


# ---------------------------------------------------------------------------------------------
# Selftest: every rule must FIRE on a broken fixture and stay SILENT on a good one
# ---------------------------------------------------------------------------------------------

def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    def ids(text: str) -> set[str]:
        return {p.id for p in PATTERNS if p.rx.search(text)}

    # patterns fire
    check("bin/rails is a tool hit", "bin-rails" in ids("run bin/rails db:migrate"))
    check("`rails runner` without bin/ is a tool hit", "bin-rails" in ids("docker exec app rails runner x"))
    check("bundle exec is a tool hit", "bundler" in ids("bundle exec rspec spec/models"))
    check("rspec names the runner", "rspec" in ids("rspec spec/models"))
    check("a gem name is a gem hit", "gem" in ids("add simple_form to the Gemfile"))
    check("Gemfile is a path hit", "gemfile" in ids("read the Gemfile"))
    check("db/migrate is a path hit", "db" in ids("a file under db/migrate/"))
    check("a secondary schema file is a path hit", "db" in ids("db/queue_schema.rb"))
    check("app/models is a path hit", "app-layers" in ids("app/models/user.rb"))
    check("the framework's name is a concept hit", "rails-word" in ids("a Rails 8 app"))
    check("Turbo is a hotwire hit", "hotwire" in ids("a Turbo frame"))
    check(".erb is a concept hit", "erb" in ids("app/views/x.html.erb"))
    # patterns stay silent
    check("this marketplace's plugin names are not hits", not ids("rails-flow and /rails-flow:feature and rails-stack and rails-8"))
    check("a word containing rake is not a hit", "rake" not in ids("a brake pad and a drake"))
    check("rspec-rails is the gem, not the runner", "rspec" not in ids("add rspec-rails") and "gem" in ids("add rspec-rails"))
    check("bundler-audit is not the bundler pattern", "bundler" not in ids("run bundler-audit"))
    check("plain prose names nothing", not ids("the stack detector reads the project and answers"))
    check("a line naming nothing is no hit and `Railsish` words are not the framework", "rails-word" not in ids("Railsish things"))
    # the scan, on files that exist only for this test
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "plugins/rails-flow/scripts/mutations").mkdir(parents=True)
        (root / "plugins/rails-flow/commands").mkdir(parents=True)
        (root / "plugins/pipeline/scripts").mkdir(parents=True)
        files = {"plugins/rails-flow/scripts/gate.py": "x = 'bin/rails db:migrate'\ny = 1\nz = 'config/routes.rb'\n",
                 "plugins/rails-flow/scripts/gate_selftest.py": "assert 'rspec spec/'\n",
                 "plugins/rails-flow/scripts/mutations/gate.py": "# a Rails fixture\n",
                 "plugins/rails-flow/commands/feature.md": "no hits here\n",
                 "plugins/pipeline/scripts/note.py": "# the word rails-flow only\n"}
        for rel, text in files.items():
            (root / rel).write_text(text, encoding="utf-8")
        (root / "plugins/pipeline/scripts/blob.bin").write_bytes(b"bin/rails\0\1\2")
        hits = scan(root, sorted([*files, "plugins/pipeline/scripts/blob.bin"]))
        check("a file with hits is found", "plugins/rails-flow/scripts/gate.py" in hits)
        check("hit lines are exact", hits["plugins/rails-flow/scripts/gate.py"]["lines"] == [1, 3])
        check("a file with no hit is absent", "plugins/rails-flow/commands/feature.md" not in hits)
        check("the plugin's own name is not a hit", "plugins/pipeline/scripts/note.py" not in hits)
        check("a binary file is skipped", "plugins/pipeline/scripts/blob.bin" not in hits)
        check("a mutation guard follows its script", subject_of("plugins/rails-flow/scripts/mutations/gate.py") == "plugins/rails-flow/scripts/gate.py")
        check("a selftest follows its script", subject_of("plugins/rails-flow/scripts/gate_selftest.py") == "plugins/rails-flow/scripts/gate.py")
        check("a plain script follows nothing", subject_of("plugins/rails-flow/scripts/gate.py") is None)
        policy = {"moves": {"M1": {"title": "t", "summary": "s", "issue": 1}},
                  "rules": [{"match": ["plugins/rails-flow/scripts/gate.py"], "decision": "rails-stack", "move": "M1", "assumes": "a", "how": "h"}]}
        decided, findings = decide(hits, policy)
        check("a complete policy is clean", findings == [])
        check("the guard and the selftest take the script's decision",
              decided.get("plugins/rails-flow/scripts/gate_selftest.py", {}).get("decision") == "rails-stack"
              and decided.get("plugins/rails-flow/scripts/mutations/gate.py", {}).get("followed") == "plugins/rails-flow/scripts/gate.py")
        check("an unresolved file is a finding", any("no rule" in f for f in decide(hits, {"moves": {}, "rules": []})[1]))
        stale = {**policy, "rules": policy["rules"] + [{"match": ["plugins/gone/*"], "decision": "neutral", "how": "h"}]}
        check("a rule matching nothing is a finding", any("matches no file" in f for f in decide(hits, stale)[1]))
        wrong = {**policy, "rules": [{**policy["rules"][0], "decision": "maybe"}]}
        check("a decision outside the four is a finding", any("not one of" in f for f in decide(hits, wrong)[1]))
        nomove = {**policy, "rules": [{**policy["rules"][0], "move": "M9"}]}
        check("a rails-stack rule with an undeclared move is a finding", any("does not declare" in f for f in decide(hits, nomove)[1]))
        noissue = {**policy, "moves": {"M1": {"title": "t", "summary": "s"}}}
        check("a move with no issue is a finding", any("no issue number" in f for f in decide(hits, noissue)[1]))
        unused = {**policy, "moves": {**policy["moves"], "M2": {"title": "u", "summary": "s", "issue": 2}}}
        check("a move no rule names is a finding", any("no rails-stack rule names it" in f for f in decide(hits, unused)[1]))
        nohow = {**policy, "rules": [{**policy["rules"][0], "how": ""}]}
        check("a rule with no `how` is a finding", any("no `how`" in f for f in decide(hits, nohow)[1]))
        movedwrong = {**policy, "rules": [{**policy["rules"][0], "decision": "detector"}]}
        check("a move on a non-rails-stack rule is a finding", any("only a rails-stack decision" in f for f in decide(hits, movedwrong)[1]))
        sf = {"file": "plugins/rails-flow/scripts/gate.py", "issue": 5, "summary": "s", "proposal": ["p"],
              "sections": [{"lines": [1, 2], "assumes": "a", "disposition": "detector", "how": "h"}, {"lines": [3, 9], "assumes": "a", "disposition": "rails-stack", "how": "h"}]}
        check("setup_flow sections covering every hit line are clean", setup_flow_findings(decided, sf) == [])
        gap = {**sf, "sections": sf["sections"][:1]}
        check("a hit line in no section is a finding", any("expected exactly one" in f for f in setup_flow_findings(decided, gap)))
        overlap = {**sf, "sections": [*sf["sections"], {"lines": [1, 1], "assumes": "a", "disposition": "neutral", "how": "h"}]}
        check("a hit line in two sections is a finding", any("in 2 sections" in f for f in setup_flow_findings(decided, overlap)))
        check("a section with no issue is a finding", any("no issue number" in f for f in setup_flow_findings(decided, {**sf, "issue": None})))
        check("a section no hit falls in is a finding", any("no hit line falls" in f for f in setup_flow_findings(decided, {**sf, "sections": [*sf["sections"], {"lines": [50, 60], "assumes": "a", "disposition": "neutral", "how": "h"}]})))
        s = summarise(decided)
        check("the summary counts files and lines from the joined rows", s["files"] == len(decided) and s["lines"] == 4)
        check("the summary splits by decision", s["by_decision"]["rails-stack"]["files"] == 3 and s["by_decision"]["neutral"]["files"] == 0)
        check("the page renders the same text twice", build_md(decided, policy) == build_md(decided, policy))
        check("the page names the file and its decision", "gate.py:1" in build_md(decided, policy) and "`rails-stack` (M1)" in build_md(decided, policy))
        check("the JSON carries every line number", json.loads(build_json(decided, policy))["files"]["plugins/rails-flow/scripts/gate.py"]["lines"] == [1, 3])
    # the patterns match a tool or gem named in any case (a lowercase-only pattern let "Run RuboCop and Brakeman and Capybara" pass clean)
    check("RuboCop in any case is a tool hit", "rubocop" in ids("Run RuboCop on changed files") and "rubocop" in ids("run rubocop"))
    check("Brakeman, Capybara and Bundler in any case are hits", {"brakeman", "gem", "bundler"} <= ids("Brakeman and Capybara via Bundler"))
    check("the framework in lowercase before a Rails noun is a hit", "rails-word" in ids("this is a rails app"))
    check("`off-rails` and `the rails` are not the framework", not ids("goes off-rails; the run inside the rails"))
    check("rails-flow, rails_flow and rails: stay plugin names, not hits", not ids("rails-flow rails_flow RAILS_FLOW_LANE rails:begin"))
    # the scope is all four flows
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for flow in FLOWS:
            (root / "plugins" / flow).mkdir(parents=True)
            (root / "plugins" / flow / "x.md").write_text("a Rails app\n", encoding="utf-8")
        (root / "plugins" / "elsewhere").mkdir()
        (root / "plugins" / "elsewhere" / "x.md").write_text("a Rails app\n", encoding="utf-8")
        fixture_git.init(root)
        fixture_git.run(root, "add", "--", *[f"plugins/{f}/x.md" for f in (*FLOWS, "elsewhere")])
        found = tracked_files(root)
        check("every flow is scanned", all(f"plugins/{flow}/x.md" in found for flow in FLOWS))
        check("a plugin that is not a flow is not scanned", "plugins/elsewhere/x.md" not in found)
    # --check, end to end, in a temp repository: a stale or missing committed page is a finding, a matching one is clean
    def repo(policy: dict, page_ok: bool = True, committed: bool = True, extra: str = "") -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".claude-plugin").mkdir()
            (root / ".claude-plugin" / "marketplace.json").write_text("{}\n", encoding="utf-8")
            (root / "docs" / "architecture").mkdir(parents=True)
            (root / "plugins" / "rails-flow" / "scripts").mkdir(parents=True)
            (root / "plugins" / "rails-flow" / "scripts" / "gate.py").write_text("x = 'bin/rails db:migrate'\n" + extra, encoding="utf-8")
            (root / POLICY).write_text(json.dumps(policy), encoding="utf-8")
            fixture_git.init(root)
            fixture_git.run(root, "add", "--", "plugins/rails-flow/scripts/gate.py", POLICY, ".claude-plugin/marketplace.json")
            decided, _ = decide(scan(root), policy)
            (root / MD_OUT).write_text(build_md(decided, policy) + ("" if page_ok else "stale\n"), encoding="utf-8")
            (root / JSON_OUT).write_text(build_json(decided, policy), encoding="utf-8")
            if committed:
                fixture_git.run(root, "add", "--", MD_OUT, JSON_OUT)
            fixture_git.run(root, "commit", "-qm", "fixture", "--allow-empty")
            sink = io.StringIO()
            sys.stdout, sys.stderr, old = sink, sink, (sys.stdout, sys.stderr)
            try:
                return main(["--check"], root), sink.getvalue()
            finally:
                sys.stdout, sys.stderr = old
    good = {"moves": {"M1": {"title": "t", "summary": "s", "issue": 1}},
            "rules": [{"match": ["plugins/rails-flow/scripts/gate.py"], "decision": "rails-stack", "move": "M1", "assumes": "a", "how": "h"}]}
    check("--check on a repository whose committed page matches is clean", repo(good)[0] == 0)
    check("--check on a stale committed page is a finding", repo(good, page_ok=False)[0] == 1 and "does not match a clean build" in repo(good, page_ok=False)[1])
    check("--check on a page that was built but never committed is a finding", repo(good, committed=False)[0] == 1 and "is not committed" in repo(good, committed=False)[1])
    nlint = {"moves": {}, "rules": [{"match": ["plugins/rails-flow/scripts/gate.py"], "decision": "neutral", "assumes": "a", "how": "h",
                                      "lines": {"plugins/rails-flow/scripts/gate.py": 1}}]}
    check("a neutral file at its recorded hit-line count is clean", repo(nlint)[0] == 0)
    check("a neutral file that gains a Rails line is a finding", repo(nlint, extra="y = 'a Rails thing'\n")[0] == 1)
    print(f"rails_assumptions selftest: {ok} checks passed, {len(bad)} failed")
    for label in bad:
        print(f"  FAIL: {label}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str] | None = None, root: Path = REPO) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="the policy resolves every file and the committed page matches a clean build")
    ap.add_argument("--status", action="store_true", help="print the counts from a fresh scan")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:  # fixtures only: runs from a staged copy that has no marketplace.json
        return _selftest()
    if not (root / ".claude-plugin" / "marketplace.json").is_file():
        print("not the claude-skills repo", file=sys.stderr)
        return 2
    policy = load_policy(root)
    decided, findings = decide(scan(root), policy)
    summary = summarise(decided)
    if a.status:
        print(f"{summary['files']} files, {summary['lines']} lines name Rails in {', '.join(FLOWS)}")
        for d in DECISIONS:
            print(f"  {d:12} {summary['by_decision'][d]['files']:4} files {summary['by_decision'][d]['lines']:5} lines")
        for cat, n in summary["by_category"].items():
            print(f"  names {cat:8} {n:5} lines")
    built_md, built_json = build_md(decided, policy), build_json(decided, policy)
    if a.check:
        for rel, built in ((MD_OUT, built_md), (JSON_OUT, built_json)):
            blob = committed_blob(rel, root)
            if blob is None:
                findings.append(f"{rel} is not committed: build it, `git add docs/` and COMMIT")
            elif blob != built:
                findings.append(f"{rel} does not match a clean build: rebuild it, `git add docs/` and COMMIT; this check reads the blob at HEAD, so staging alone leaves it red")
    elif not a.status and not findings:
        (root / MD_OUT).write_text(built_md, encoding="utf-8")
        (root / JSON_OUT).write_text(built_json, encoding="utf-8")
        print(f"wrote {MD_OUT} and {JSON_OUT}: {summary['files']} files, {summary['lines']} lines. `git add docs/` AND COMMIT; the drift gate compares the blob at HEAD.")
    if findings:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    if a.check:
        print(f"clean: {summary['files']} files decided, the page matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
