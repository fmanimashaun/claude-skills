#!/usr/bin/env python3
"""The component-class page: every shipped hook, command, agent, skill, script and gate, and whether it works on every stack (#2192).

Run:  python3 scripts/component_classes.py              # rebuild docs/architecture/component-classes.{html,json}
      python3 scripts/component_classes.py --check      # drift gate: every component classified and verified, the page matches the blob at HEAD
      python3 scripts/component_classes.py --status     # the counts, from a fresh scan
      python3 scripts/component_classes.py --selftest   # prove each rule fires AND stays silent

WHY THIS EXISTS. The owner's words: "stack specific hooks, commands, mods and so many more, and the neutral ones that work across stacks."
`docs/architecture/rails-assumptions.md` (#2164) lists the files that NAME a Rails thing. It cannot show the components that name nothing,
so nobody could see which parts of the toolchain are already neutral. This page lists all of them, per plugin, with one class each:

  neutral  works the same on every stack; the scan finds no Rails or Next.js reference in it
  rails    exists only for Rails projects; it moves to rails-stack, or for a design-flow component lives in its Rails UI adapter (the issue is named)
  nextjs   exists only for Next.js projects
  mixed    stays where it is but still assumes a stack in places; it names its seam (where it will ask the stack detector, or that it is
           wording only) and the plan issue that fixes it

THE CLASS IS DECLARED ONCE AND VERIFIED BY THE SCAN. The declaration lives in `docs/architecture/rails-assumptions.policy.json`, the one file
that already holds the per-file decisions: a file that names a Rails thing takes its class from its `rules` entry (rails-stack -> rails,
detector or reword -> mixed, neutral -> neutral), and anything else takes it from `components.declared`. A gate row in a `checks.json` and a
hook take the class of the script they run, so that class is never written twice. The scan verifies, in both directions:

  * a component with NO declaration fails (a new directory or file type cannot arrive unclassified);
  * a component declared neutral that names a Rails or Next.js thing fails, unless the policy records the reference as incidental;
  * a mixed component with no seam or no issue number fails;
  * a declaration that matches no component fails (it rotted when the file moved).

WHAT IT IS HONESTLY NOT. The scan finds the lines that NAME a stack. A component that assumes Rails without naming it (a path convention in
prose) reads as neutral here, so `neutral` means "the scan finds nothing", not "proven to run on every stack".

The page bytes are a function of the policy and the tracked files, nothing else (no git state, no dates). Stdlib only.
Exit codes: 0 clean · 1 findings · 2 not this repo.
"""
from __future__ import annotations

import argparse
import io
import fnmatch
import html
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "rails-flow" / "scripts"))
import fixture_git  # noqa: E402  (#1588: a selftest fixture's git touches only its own temp repo)
import rails_assumptions as ra  # noqa: E402  (the scanner, the policy loader, the subject rule: one home each)

REPO = ra.REPO
HTML_OUT = "docs/architecture/component-classes.html"
JSON_OUT = "docs/architecture/component-classes.json"
CLASSES = ("neutral", "rails", "nextjs", "mixed")
TYPES = ("command", "agent", "hook", "skill", "script", "gate", "test", "support")
FROM_DECISION = {"rails-stack": "rails", "detector": "mixed", "reword": "mixed", "neutral": "neutral"}
SKILLS_PLUGIN = "rails-stack"  # one plugin on the page, its skills and its manifest together (#2182)

# A Next.js reference is a hit the way a Rails one is. These name Next.js itself or its two vendors; plain Node, TypeScript, React or npm do not
# (the neutral qa-flow scaffold is TypeScript), so none of those is a hit.
NEXT_PATTERNS: tuple[ra.Pattern, ...] = (
    ra.Pattern("nextjs", "nextjs", r"\bNext\.js\b|\bnext\.config\b|\bnext/(?:image|link|navigation|headers|server)\b|\bApp Router\b|\bgetServerSideProps\b",
               "Next.js by name"),
    ra.Pattern("vercel", "nextjs", r"\bVercel\b|\bvercel\.json\b|\bvercel (?:deploy|env|pull|build)\b", "Vercel"),
    ra.Pattern("supabase", "nextjs", r"\bSupabase\b|\bsupabase (?:start|db|migration|functions)\b", "Supabase"),
)


# ---------------------------------------------------------------------------------------------
# What a component is
# ---------------------------------------------------------------------------------------------

def components_scope(root: Path) -> list[str]:
    """Every tracked file of every shipped plugin and every root skill, sorted. The unit the page classifies is derived from the path."""
    out = subprocess.run(["git", "ls-files", "-z", "--", "plugins", "skills"], cwd=root, capture_output=True, text=True, check=True).stdout
    return sorted(p for p in out.split("\0") if p)


# The shipped skills: plugins/rails-stack/skills/<name>/ since #2182 (skills/<name>/ before).
SKILLS_PREFIX = "plugins/rails-stack/skills/"


def _skill_parts(path: str) -> int:
    """How many leading path parts name a skill directory, or 0 when the path is not in a skill."""
    if path.startswith(SKILLS_PREFIX):
        return 4
    return 2 if path.startswith("skills/") else 0


def plugin_of(path: str) -> str:
    return SKILLS_PLUGIN if _skill_parts(path) else path.split("/")[1]


def type_of(path: str) -> str:
    """command, agent, hook, skill, script, test or support, from the path alone."""
    if _skill_parts(path):
        return "skill"
    rest = path.split("/", 2)[2] if path.count("/") >= 2 else path
    kind = ra.kind_of(path)
    if kind in ("mutation", "selftest"):
        return "test"
    if rest.startswith(("commands/",)):
        return "command"
    if rest.startswith("agents/"):
        return "agent"
    if rest.startswith(("hooks/", "git-hooks/", "git-shim/")):
        return "hook" if not rest.endswith(".json") or rest == "hooks/hooks.json" else "support"
    if rest.startswith("scripts/"):
        return "script"
    return "support"


def component_id(path: str) -> str:
    """A skill is one component, its directory; everything else is one file."""
    if (n := _skill_parts(path)):
        return "/".join(path.split("/")[:n])
    return path


def gate_rows(root: Path, files: list[str]) -> list[dict]:
    """One component per `checks.json` row: `{path: <file>#<id>, script: <plugin-relative script or None>}`."""
    rows: list[dict] = []
    for rel in files:
        if not rel.endswith("/checks.json") or rel.count("/") != 2:
            continue
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        plugin = rel.split("/")[1]
        for check in data.get("checks", []):
            script = next((f"plugins/{plugin}/" + t.split("{plugin}/", 1)[1] for t in check.get("command", []) if t.startswith("{plugin}/")), None)
            rows.append({"path": f"{rel}#{check['id']}", "plugin": plugin, "script": script})
    return rows


def hook_registrations(root: Path, files: list[str]) -> dict[str, list[str]]:
    """`{script path: ["PreToolUse Bash", ...]}` from every plugin's `hooks/hooks.json`: shown beside the hook; the hook's class is its script's."""
    reg: dict[str, list[str]] = {}
    for rel in files:
        if not rel.endswith("/hooks/hooks.json"):
            continue
        plugin = rel.split("/")[1]
        data = json.loads((root / rel).read_text(encoding="utf-8"))
        for event, groups in data.get("hooks", {}).items():
            for group in groups:
                for hook in group.get("hooks", []):
                    m = re.search(r"\$\{CLAUDE_PLUGIN_ROOT\}/(\S+?)\\?\"?(?:\s|$)", hook.get("command", ""))
                    if m:
                        label = f"{event} {group['matcher']}" if group.get("matcher") else event
                        reg.setdefault(f"plugins/{plugin}/{m.group(1).rstrip(chr(34))}", []).append(label)
    return reg


# ---------------------------------------------------------------------------------------------
# Classify and verify
# ---------------------------------------------------------------------------------------------

def _match(path: str, rule: dict) -> bool:
    return any(fnmatch.fnmatchcase(path, g) for g in rule["match"])


def classify(root: Path, policy: dict, files: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """`(components, findings)`: every component with its class, how the class was decided, and the Rails and Next.js hit lines."""
    files = files if files is not None else components_scope(root)
    findings: list[str] = []
    rails_hits = ra.scan(root, files)
    next_hits = ra.scan(root, files, NEXT_PATTERNS)
    rules: list[dict] = policy["rules"]
    moves: dict = policy.get("moves", {})
    declared: list[dict] = policy.get("components", {}).get("declared", [])
    used_declared: Counter[int] = Counter()
    by_path: dict[str, dict] = {}

    def own_class(path: str) -> dict | None:
        """The class of a file, ignoring any other file: a decision rule when the file names Rails, else a declaration."""
        found = None
        if path in rails_hits:
            subject = ra.subject_of(path)
            found = ra.resolve(subject, rules) if subject else None
            if found is None:
                found = ra.resolve(path, rules)
        if found is not None:
            _, rule = found
            cls = FROM_DECISION.get(rule["decision"])
            issue = moves[rule["move"]]["issue"] if rule.get("move") in moves else rule.get("issues", {}).get(plugin_of(path), rule.get("issue"))
            seam = rule.get("seam", "")
            return {"class": cls, "seam": seam, "issue": issue, "via": "decision", "why": rule.get("how", ""), "rule": rule}
        for index, d in enumerate(declared):
            if _match(path, d):
                used_declared[index] += 1
                return {"class": d["class"], "seam": d.get("seam", ""), "issue": d.get("issue"), "via": "declared", "why": d.get("why", ""), "rule": d}
        return None

    for path in files:
        if component_id(path) != path:
            continue  # skill files are aggregated below
        info = own_class(path)
        by_path[path] = {"path": path, "plugin": plugin_of(path), "type": type_of(path), "rails": rails_hits.get(path, {}).get("lines", []),
                         "next": next_hits.get(path, {}).get("lines", []), "info": info}
    skills: dict[str, dict] = {}
    for path in files:
        cid = component_id(path)
        if cid == path:
            continue
        s = skills.setdefault(cid, {"path": cid, "plugin": SKILLS_PLUGIN, "type": "skill", "rails": [], "next": [], "info": None, "files": 0})
        s["files"] += 1
        s["rails"] += [f"{path.split('/', 2)[2]}:{n}" for n in rails_hits.get(path, {}).get("lines", [])]
        s["next"] += [f"{path.split('/', 2)[2]}:{n}" for n in next_hits.get(path, {}).get("lines", [])]
    for cid, s in skills.items():
        for index, d in enumerate(declared):
            if _match(cid, d) or _match(cid + "/SKILL.md", d):
                used_declared[index] += 1
                s["info"] = {"class": d["class"], "seam": d.get("seam", ""), "issue": d.get("issue"), "via": "declared", "why": d.get("why", ""), "rule": d}
                break
        by_path[cid] = s
    # a mutation guard or selftest takes the class of the script it tests, so the class of a script is never written twice
    for path, comp in list(by_path.items()):
        if comp["type"] == "test":
            subject = ra.subject_of(path)
            if subject in by_path and by_path[subject]["info"] is not None:
                comp["info"] = {**by_path[subject]["info"], "via": f"tests {subject.split('/')[-1]}"}
    # gate rows and hooks take the class of the script they run
    comps: list[dict] = list(by_path.values())
    reg = hook_registrations(root, files)
    for row in gate_rows(root, files):
        script = by_path.get(row["script"]) if row["script"] else None
        info = None
        if script is not None and script["info"] is not None:
            info = {**script["info"], "via": f"runs {row['script'].split('/')[-1]}"}
        else:
            for index, d in enumerate(declared):
                if _match(row["path"], d):
                    used_declared[index] += 1
                    info = {"class": d["class"], "seam": d.get("seam", ""), "issue": d.get("issue"), "via": "declared", "why": d.get("why", ""), "rule": d}
                    break
        comps.append({"path": row["path"], "plugin": row["plugin"], "type": "gate", "rails": script["rails"] if script else [], "next": script["next"] if script else [],
                      "info": info})
    for comp in comps:
        comp["registered"] = reg.get(comp["path"], [])
    # verification
    for comp in sorted(comps, key=lambda c: c["path"]):
        info, path = comp["info"], comp["path"]
        if info is None:
            findings.append(f"{path}: no class declared (no decision rule and no `components.declared` entry matches this {comp['type']})")
            continue
        if info["class"] not in CLASSES:
            findings.append(f"{path}: class {info['class']!r} is not one of {', '.join(CLASSES)}")
            continue
        if info["class"] == "neutral":
            incidental = info["via"] == "decision" or info["via"].startswith(("tests ", "runs "))  # a `neutral` decision rule records the reference as incidental, with the reason; a derived class was verified on its source
            if (comp["rails"] or comp["next"]) and not incidental:
                findings.append(f"{path}: declared neutral but the scan finds {len(comp['rails'])} Rails and {len(comp['next'])} Next.js reference line(s); "
                                f"classify it rails, nextjs or mixed, or record the reference as incidental with a `neutral` rule")
        if info["class"] == "mixed" and (not info["seam"] or not isinstance(info["issue"], int)):
            findings.append(f"{path}: mixed needs a `seam` and a plan issue number (it has seam={info['seam']!r}, issue={info['issue']!r})")
        if info["class"] == "rails" and not isinstance(info["issue"], int) and info["via"] == "decision":
            findings.append(f"{path}: a rails component moved by a decision rule needs its move issue number")
        if info["class"] != "nextjs" and comp["next"] and info["class"] != "mixed" and info["via"] != "decision":
            findings.append(f"{path}: declared {info['class']} but names Next.js on {len(comp['next'])} line(s)")
    for index, d in enumerate(declared):
        if not used_declared[index]:
            findings.append(f"declaration {d['match'][0]}: matches no component (the file moved or the glob is wrong): delete or fix it")
        if d.get("class") == "mixed" and (not d.get("seam") or not isinstance(d.get("issue"), int)):
            findings.append(f"declaration {d['match'][0]}: mixed needs a `seam` and a plan issue number")
    return sorted(comps, key=lambda c: (c["plugin"], TYPES.index(c["type"]), c["path"])), findings


# ---------------------------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------------------------

def summarise(comps: list[dict]) -> dict:
    by_class = Counter(c["info"]["class"] for c in comps if c["info"])
    by_plugin: dict[str, dict] = {}
    for c in comps:
        row = by_plugin.setdefault(c["plugin"], {"total": 0, **{k: 0 for k in CLASSES}})
        row["total"] += 1
        if c["info"]:
            row[c["info"]["class"]] += 1
    by_type: dict[str, dict] = {}
    for c in comps:
        row = by_type.setdefault(c["type"], {"total": 0, **{k: 0 for k in CLASSES}})
        row["total"] += 1
        if c["info"]:
            row[c["info"]["class"]] += 1
    return {"components": len(comps), "by_class": {k: by_class.get(k, 0) for k in CLASSES}, "by_plugin": dict(sorted(by_plugin.items())),
            "by_type": {t: by_type[t] for t in TYPES if t in by_type}}


def build_json(comps: list[dict]) -> str:
    rows = [{"path": c["path"], "plugin": c["plugin"], "type": c["type"], "class": c["info"]["class"] if c["info"] else None,
             "seam": c["info"]["seam"] if c["info"] else "", "issue": c["info"]["issue"] if c["info"] else None,
             "via": c["info"]["via"] if c["info"] else "", "registered": c["registered"], "rails_lines": len(c["rails"]), "nextjs_lines": len(c["next"])}
            for c in comps]
    return json.dumps({"generated_by": "scripts/component_classes.py", "summary": summarise(comps), "components": rows}, indent=1, sort_keys=True) + "\n"


CSS = """
:root{--bg:#fbfaf7;--fg:#1d1d1b;--mute:#66645d;--line:#dcd8cf;--card:#fff;--neutral:#2e7d4f;--rails:#b3261e;--nextjs:#1b5fa8;--mixed:#a86a00}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#161614;--fg:#ecebe6;--mute:#9a978e;--line:#34332f;--card:#1e1e1b;--neutral:#5fc088;--rails:#f08a82;--nextjs:#7db4ee;--mixed:#e5b04d}}
:root[data-theme="dark"]{--bg:#161614;--fg:#ecebe6;--mute:#9a978e;--line:#34332f;--card:#1e1e1b;--neutral:#5fc088;--rails:#f08a82;--nextjs:#7db4ee;--mixed:#e5b04d}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.7rem;margin:.2em 0}h2{margin-top:2em;border-bottom:1px solid var(--line);padding-bottom:.2em}
p,li{max-width:70ch}.mute{color:var(--mute)}table{border-collapse:collapse;width:100%;margin:.6em 0;font-size:.92rem}
th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{color:var(--mute);font-weight:600}
code{font:.85em ui-monospace,monospace;word-break:break-all}.num{text-align:right;font-variant-numeric:tabular-nums}
.tag{display:inline-block;padding:0 .5em;border-radius:1em;border:1px solid currentColor;font-size:.8rem;font-weight:600}
.neutral{color:var(--neutral)}.rails{color:var(--rails)}.nextjs{color:var(--nextjs)}.mixed{color:var(--mixed)}
.gloss{margin:.4em 0 1em}.gloss dt{font-weight:600;float:left;clear:left;width:9.5em}.gloss dd{margin:0 0 .35em 9.5em;max-width:62ch}.box{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:12px 16px;margin:12px 0}
details{margin:.4em 0}summary{cursor:pointer}.wrap{overflow-x:auto}
"""


def _tag(cls: str | None) -> str:
    return f'<span class="tag {cls}">{cls}</span>' if cls else '<span class="tag mixed">unclassified</span>'


def build_html(comps: list[dict]) -> str:
    s = summarise(comps)
    e = html.escape
    out: list[str] = []
    w = out.append
    w('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">')
    w("<title>Component classes</title><style>" + CSS + "</style></head><body><main>")
    w("<h1>Which parts of the toolchain work on every stack</h1>")
    w('<p class="mute">Generated by <code>scripts/component_classes.py</code> from <code>docs/architecture/rails-assumptions.policy.json</code>; do not edit. '
      "<code>python3 scripts/component_classes.py --check</code> fails when this page is stale. Issue #2192, under the nextjs-stack epic #2162.</p>")
    w('<div class="box"><h2 style="margin-top:0;border:0">How to read this</h2>')
    w("<p>Every hook, command, agent, skill, script and gate we ship is listed once, under the plugin it ships in, with one class:</p><ul>")
    w(f'<li>{_tag("neutral")} works the same on any stack. A scan of its text finds no Rails or Next.js reference.</li>')
    w(f'<li>{_tag("rails")} exists only for Rails projects. It will move into the <code>rails-stack</code> plugin, or for a design-flow component stay in its Rails UI adapter (<code>ui/viewcomponent-erb</code>); the issue that moves it is named.</li>')
    w(f'<li>{_tag("nextjs")} exists only for Next.js projects.</li>')
    w(f'<li>{_tag("mixed")} stays where it is but still assumes a stack somewhere. The <b>seam</b> says where it will ask the stack detector instead '
      "(or that it is only wording), and the issue is the plan step that fixes it.</li></ul>")
    w('<dl class="gloss"><dt>hook</dt><dd>a script the assistant runs automatically at a moment in a session (before a command, when it stops) to block or warn.</dd>'
      "<dt>command</dt><dd>a <code>/name</code> a person types to start a workflow.</dd>"
      "<dt>agent</dt><dd>a specialist the assistant hands one job to, with its own instructions.</dd>"
      "<dt>skill</dt><dd>a folder of written guidance the assistant loads when a task matches.</dd>"
      "<dt>script</dt><dd>a program that does the checking or generating work behind the rest.</dd>"
      "<dt>gate</dt><dd>one check that must pass before work moves on; each is a row in a plugin's <code>checks.json</code>.</dd>"
      "<dt>seam</dt><dd>the place a stack-specific step will be swapped for one the stack provides.</dd>"
      "<dt>stack detector</dt><dd>the shared code (#2163) that looks at a project and answers which stack it uses and which commands and paths to run.</dd>"
      "<dt>policy file</dt><dd><code>docs/architecture/rails-assumptions.policy.json</code>: where each decision and class is written down.</dd>"
      "<dt>scan</dt><dd>a search of every file's text for Rails and Next.js names, run by <code>component_classes.py</code>.</dd></dl>")
    w("<p>The class is written down once, in the policy file, and the scan checks it: a component marked neutral that names a Rails or Next.js thing fails the check, "
      "and so does a component nobody classified. <b>Limit:</b> the scan finds references by name. A component that assumes Rails without ever naming it still reads as "
      "neutral, so neutral means &ldquo;nothing found&rdquo;, not &ldquo;proven on every stack&rdquo;. The per-file reasons are in "
      "<code>docs/architecture/rails-assumptions.md</code>.</p></div>")
    w(f"<h2>Totals ({s['components']} components)</h2><div class=\"wrap\"><table><tr><th>class</th><th class=\"num\">components</th></tr>")
    for k in CLASSES:
        w(f"<tr><td>{_tag(k)}</td><td class=\"num\">{s['by_class'][k]}</td></tr>")
    w("</table></div>")
    w('<h2>By plugin</h2><div class="wrap"><table><tr><th>plugin</th><th class="num">all</th>' + "".join(f'<th class="num">{k}</th>' for k in CLASSES) + "</tr>")
    for plugin, row in s["by_plugin"].items():
        w(f"<tr><td><code>{e(plugin)}</code></td><td class=\"num\">{row['total']}</td>" + "".join(f'<td class="num">{row[k]}</td>' for k in CLASSES) + "</tr>")
    w("</table></div>")
    w('<h2>By kind</h2><div class="wrap"><table><tr><th>kind</th><th class="num">all</th>' + "".join(f'<th class="num">{k}</th>' for k in CLASSES) + "</tr>")
    for kind, row in s["by_type"].items():
        w(f"<tr><td>{kind}</td><td class=\"num\">{row['total']}</td>" + "".join(f'<td class="num">{row[k]}</td>' for k in CLASSES) + "</tr>")
    w("</table></div>")
    plugins = sorted({c["plugin"] for c in comps})
    for plugin in plugins:
        mine = [c for c in comps if c["plugin"] == plugin]
        w(f"<h2><code>{e(plugin)}</code> ({len(mine)})</h2>")
        for kind in TYPES:
            rows = [c for c in mine if c["type"] == kind]
            if not rows:
                continue
            counts = Counter(c["info"]["class"] if c["info"] else "unclassified" for c in rows)
            summary = ", ".join(f"{counts[k]} {k}" for k in (*CLASSES, "unclassified") if counts.get(k))
            fold = kind in ("test", "support")
            w(("<details>" if fold else "<details open>") + f"<summary><b>{kind}s</b> ({len(rows)}: {summary})</summary>")
            w('<div class="wrap"><table><tr><th>component</th><th>class</th><th>seam</th><th>issue</th><th>registered on</th></tr>')
            for c in rows:
                i = c["info"] or {}
                name = c["path"].split("/", 2)[2] if c["path"].startswith("plugins/") else c["path"].split("/", 1)[1]
                issue = f"#{i['issue']}" if isinstance(i.get("issue"), int) else ""
                w(f"<tr><td><code>{e(name)}</code></td><td>{_tag(i.get('class'))}</td><td>{e(i.get('seam') or '')}</td><td>{issue}</td>"
                  f"<td>{e(', '.join(c['registered']))}</td></tr>")
            w("</table></div></details>")
    w("</main></body></html>")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------------------------

def _selftest() -> int:
    ok, bad = 0, []

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    def run(files: dict[str, str], policy: dict) -> tuple[list[dict], list[str]]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel, text in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            return classify(root, policy, sorted(files))

    def pol(decl: list[dict] | None = None, rules: list[dict] | None = None) -> dict:
        return {"moves": {"M1": {"title": "t", "summary": "s", "issue": 7}}, "rules": rules or [],
                "components": {"declared": decl if decl is not None else [] if rules else [
                    {"match": ["plugins/p/commands/*", "plugins/p/scripts/*", "plugins/p/agents/*"], "class": "neutral", "why": "names no stack"}]}}

    clean = {"plugins/p/commands/a.md": "do the thing\n", "plugins/p/scripts/b.py": "print(1)\n"}
    comps, f = run(clean, pol())
    check("neutral components that name nothing are clean", f == [] and {c["info"]["class"] for c in comps} == {"neutral"})
    check("every file is one component", len(comps) == 2)
    _, f = run({**clean, "plugins/p/hooks/new.sh": "echo\n"}, pol())
    check("a component nothing declares is a finding", any("no class declared" in x for x in f))
    _, f = run({**clean, "plugins/p/scripts/c.py": "run('bin/rails db:migrate')\n"}, pol())
    check("a neutral component naming Rails is a finding", any("declared neutral" in x and "c.py" in x for x in f))
    _, f = run({**clean, "plugins/p/scripts/d.py": "see Next.js and Vercel\n"}, pol())
    check("a neutral component naming Next.js is a finding", any("d.py" in x and "Next.js" in x for x in f))
    _, f = run({**clean, "plugins/p/scripts/e.ts": "import x from 'react'\nnpm run build\n"}, pol())
    check("plain TypeScript and npm are not Next.js", f == [])
    _, f = run({"plugins/p/scripts/c.py": "bin/rails db:migrate\n"}, pol(decl=[], rules=[{"match": ["plugins/p/scripts/c.py"], "decision": "rails-stack", "move": "M1", "how": "h"}]))
    check("a rails decision classifies the file rails, with its move issue", f == [])
    comps, _ = run({"plugins/p/scripts/c.py": "bin/rails db:migrate\n"}, pol(rules=[{"match": ["plugins/p/scripts/c.py"], "decision": "rails-stack", "move": "M1", "how": "h"}]))
    check("the rails class carries the move's issue", comps[0]["info"]["class"] == "rails" and comps[0]["info"]["issue"] == 7)
    _, f = run({"plugins/p/scripts/c.py": "bin/rails db:migrate\n"}, pol(rules=[{"match": ["plugins/p/scripts/c.py"], "decision": "detector", "how": "h"}]))
    check("a mixed component with no seam or issue is a finding", any("mixed needs" in x for x in f))
    _, f = run({"plugins/p/scripts/c.py": "bin/rails db:migrate\n"}, pol(rules=[{"match": ["plugins/p/scripts/c.py"], "decision": "detector", "seam": "stack detector", "issue": 9, "how": "h"}]))
    check("a mixed component with a seam and an issue is clean", f == [])
    _, f = run({"plugins/p/scripts/c.py": "a Rails fixture\n"}, pol(rules=[{"match": ["plugins/p/scripts/c.py"], "decision": "neutral", "how": "an example"}]))
    check("a recorded incidental reference keeps a component neutral", f == [])
    _, f = run(clean, pol(decl=[{"match": ["plugins/p/commands/*", "plugins/p/scripts/*"], "class": "neutral", "why": "w"},
                                {"match": ["plugins/gone/*"], "class": "neutral", "why": "w"}]))
    check("a declaration that matches nothing is a finding", any("matches no component" in x for x in f))
    _, f = run(clean, pol(decl=[{"match": ["plugins/p/commands/*", "plugins/p/scripts/*"], "class": "maybe", "why": "w"}]))
    check("a class outside the four is a finding", any("is not one of" in x for x in f))
    _, f = run(clean, pol(decl=[{"match": ["plugins/p/commands/*", "plugins/p/scripts/*"], "class": "mixed", "why": "w"}]))
    check("a mixed declaration with no seam is a finding", any("mixed needs" in x for x in f))
    gate = {"plugins/p/scripts/g.py": "x\n", "plugins/p/checks.json": json.dumps({"checks": [{"id": "g", "command": ["python3", "{plugin}/scripts/g.py"]}]})}
    comps, f = run(gate, pol(decl=[{"match": ["plugins/p/scripts/*", "plugins/p/checks.json"], "class": "neutral", "why": "w"}]))
    check("a gate row takes the class of the script it runs", f == [] and [c["info"]["class"] for c in comps if c["type"] == "gate"] == ["neutral"])
    comps, f = run({"plugins/rails-stack/skills/s/SKILL.md": "x\n", "plugins/rails-stack/skills/s/ref.md": "a Rails thing\n"}, pol(decl=[{"match": ["plugins/rails-stack/skills/s"], "class": "rails", "issue": 1, "why": "w"}]))
    check("a skill is one component, its directory", len(comps) == 1 and comps[0]["type"] == "skill" and f == [])
    _, f = run({"plugins/rails-stack/skills/s/SKILL.md": "x\n", "plugins/rails-stack/skills/s/ref.md": "a Rails thing\n"}, pol(decl=[{"match": ["plugins/rails-stack/skills/s"], "class": "neutral", "why": "w"}]))
    check("a neutral skill naming Rails in any of its files is a finding", any("plugins/rails-stack/skills/s" in x and "declared neutral" in x for x in f))
    reg = {"plugins/p/hooks/hooks.json": json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
        {"type": "command", "command": '/bin/bash -p "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/g.sh"'}]}]}}), "plugins/p/hooks/scripts/g.sh": "echo\n"}
    comps, f = run(reg, pol(decl=[{"match": ["plugins/p/hooks/*"], "class": "neutral", "why": "w"}]))
    check("a hook shows the event and matcher it is registered on", any(c["registered"] == ["PreToolUse Bash"] for c in comps))
    # --check, end to end, in a temp repository: a stale or never-committed page is a finding, a matching one is clean
    def repo(page_ok: bool = True, committed: bool = True) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            policy = pol()
            for rel, text in {".claude-plugin/marketplace.json": "{}\n", "plugins/p/commands/a.md": "do the thing\n", ra.POLICY: json.dumps(policy)}.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")
            fixture_git.init(root)
            fixture_git.run(root, "add", "--", ".claude-plugin/marketplace.json", "plugins/p/commands/a.md", ra.POLICY)
            built, _ = classify(root, policy)
            (root / HTML_OUT).write_text(build_html(built) + ("" if page_ok else "<!-- stale -->\n"), encoding="utf-8")
            (root / JSON_OUT).write_text(build_json(built), encoding="utf-8")
            if committed:
                fixture_git.run(root, "add", "--", HTML_OUT, JSON_OUT)
            fixture_git.run(root, "commit", "-qm", "fixture", "--allow-empty")
            sink = io.StringIO()
            sys.stdout, sys.stderr, old = sink, sink, (sys.stdout, sys.stderr)
            try:
                return main(["--check"], root), sink.getvalue()
            finally:
                sys.stdout, sys.stderr = old
    check("--check on a repository whose committed page matches is clean", repo()[0] == 0)
    check("--check on a stale committed page is a finding", repo(page_ok=False)[0] == 1 and "does not match a clean build" in repo(page_ok=False)[1])
    check("--check on a page that was built but never committed is a finding", repo(committed=False)[0] == 1 and "is not committed" in repo(committed=False)[1])
    check("the page renders the same bytes twice", build_html(comps) == build_html(comps) and build_json(comps) == build_json(comps))
    check("the page carries the how-to-read header", "How to read this" in build_html(comps))
    print(f"component_classes selftest: {ok} checks passed, {len(bad)} failed")
    for label in bad:
        print(f"  FAIL: {label}", file=sys.stderr)
    return 1 if bad else 0


def main(argv: list[str] | None = None, root: Path = REPO) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="every component classified and verified, and the committed page matches a clean build")
    ap.add_argument("--status", action="store_true", help="print the counts from a fresh scan")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:  # fixtures only: runs from a staged copy that has no marketplace.json
        return _selftest()
    if not (root / ".claude-plugin" / "marketplace.json").is_file():
        print("not the claude-skills repo", file=sys.stderr)
        return 2
    policy = ra.load_policy(root)
    comps, findings = classify(root, policy)
    s = summarise(comps)
    if a.status:
        print(f"{s['components']} components: " + ", ".join(f"{s['by_class'][k]} {k}" for k in CLASSES))
        for plugin, row in s["by_plugin"].items():
            print(f"  {plugin:24} {row['total']:4} " + " ".join(f"{k}={row[k]}" for k in CLASSES))
    built_html, built_json = build_html(comps), build_json(comps)
    if a.check:
        for rel, built in ((HTML_OUT, built_html), (JSON_OUT, built_json)):
            blob = ra.committed_blob(rel, root)
            if blob is None:
                findings.append(f"{rel} is not committed: build it, `git add docs/` and COMMIT")
            elif blob != built:
                findings.append(f"{rel} does not match a clean build: rebuild it, `git add docs/` and COMMIT; this check reads the blob at HEAD, so staging alone leaves it red")
    elif not a.status and not findings:
        (root / HTML_OUT).write_text(built_html, encoding="utf-8")
        (root / JSON_OUT).write_text(built_json, encoding="utf-8")
        print(f"wrote {HTML_OUT} and {JSON_OUT}: {s['components']} components. `git add docs/` AND COMMIT; the drift gate compares the blob at HEAD.")
    if findings:
        print(f"\n{len(findings)} finding(s):", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        return 1
    if a.check:
        print(f"clean: {s['components']} components classified, the page matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
