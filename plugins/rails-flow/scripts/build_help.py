#!/usr/bin/env python3
"""build_help.py -- the in-app Help & SOP of a Rails project, generated from the repository (#934).

WHY GENERATED, AND WHY HERE. An interface should carry the name, the unit, the state and the action;
the explanation belongs in Help. A Help written inside the app -- a rich-text editor, drafts, an archive --
is typed by whoever is signed in, cites nothing, and drifts from the product the moment a setting is added.
The owner's ruling (Retask, 5 Sep 2026): "we will prefer to generate all documentation and procedure, well
researched, via the repo." So Help is AUTHORED as markdown beside the spec, reviewed through a PR, joined
with the app's own registries, and built into one file the app renders read-only, stamped with the release.

  source (under docs/product/help/)   what it is
  registry.json                       STRUCTURED, produced by the app itself (a rake task dumping its settings,
                                      permissions and screens registries; see reference/help.md) -- never typed
  procedures/*.md                     one procedure each; frontmatter title:, area:, spec: (the § it derives from)
  rules/*.md                          one enforced rule each; frontmatter title:, spec:
  glossary/*.md                       one term each; frontmatter term:, versus: (the word it is not)
  screens/<key>.md                    one guide per screen in the registry; frontmatter screen: <key>

  output   _build/help.json           every page with its rendered HTML, the three references, a search index,
                                      the commit and version from the registry -- a function of the inputs only

  (no flag)   build and write              --check   rebuild in memory, DRIFT if the committed build differs
  --json      print the model               --selftest

Exit 0 written / clean · 1 DRIFT · 2 PROBLEM (a screen with no guide, a procedure or rule with no spec citation,
a guide for a screen the registry does not know, a setting or permission with no description, unreadable source)
· 3 not applicable (no registry yet; or --check before the first build). A PROBLEM is what makes the join honest:
a setting, permission or screen cannot ship without its Help entry, the way a wiki page cannot drift from its source.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import tempfile
from pathlib import Path

HELP = Path("docs/product/help")
REGISTRY = HELP / "registry.json"
BUILD = HELP / "_build"
OUT = BUILD / "help.json"
KINDS = ("procedures", "rules", "glossary", "screens")
CITED = ("procedures", "rules")           # a procedure or a rule with no § behind it is opinion, not doctrine


# ----------------------------------------------------------------------------- sources (structured)

def load_registry(root: Path) -> dict:
    return json.loads((root / REGISTRY).read_text(encoding="utf-8"))


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """`---\\nkey: value\\n---\\nbody` -- flat keys, values as written. No YAML library: the shape is fixed."""
    m = re.match(r"\A---\n(.*?)\n---\n?(.*)\Z", text, re.S)
    if not m:
        return {}, text
    meta: dict = {}
    for line in m.group(1).splitlines():
        k, sep, v = line.partition(":")
        if sep:
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, m.group(2)


def load_pages(root: Path) -> list[dict]:
    pages = []
    for kind in KINDS:
        d = root / HELP / kind
        if not d.is_dir():
            continue
        for p in sorted(d.glob("*.md")):
            meta, body = parse_frontmatter(p.read_text(encoding="utf-8"))
            pages.append({"kind": kind, "file": p.relative_to(root).as_posix(), "slug": p.stem, "meta": meta, "body": body.strip()})
    return pages


# ----------------------------------------------------------------------------- markdown (the writing subset)

INLINE = (
    (re.compile(r"`([^`]+)`"), r"<code>\1</code>"),
    (re.compile(r"\*\*([^*]+)\*\*"), r"<strong>\1</strong>"),
    (re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)"), r"<em>\1</em>"),
    (re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)"), r'<a href="\2">\1</a>'),
)


def inline(text: str) -> str:
    out = html.escape(text, quote=False)
    for rx, rep in INLINE:
        out = rx.sub(rep, out)
    return out


def render_markdown(md: str) -> str:
    """Headings, paragraphs, ordered and unordered lists, blockquotes, and the inline set. The tags a Help body
    may hold are the tags the app allows (p strong em code h2 h3 ol ul li blockquote a), so nothing here needs
    a sanitizer to be safe and nothing is lost to one."""
    out: list[str] = []
    para: list[str] = []
    lst: list[str] = []
    lst_tag = ""
    quote: list[str] = []

    def flush_para() -> None:
        if para:
            out.append("<p>" + inline(" ".join(s.strip() for s in para)) + "</p>"); para.clear()

    def flush_list() -> None:
        nonlocal lst_tag
        if lst:
            out.append(f"<{lst_tag}>" + "".join(f"<li>{inline(i)}</li>" for i in lst) + f"</{lst_tag}>"); lst.clear(); lst_tag = ""

    def flush_quote() -> None:
        if quote:
            out.append("<blockquote><p>" + inline(" ".join(quote)) + "</p></blockquote>"); quote.clear()

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_para(); flush_list(); flush_quote(); continue
        h = re.match(r"^(#{1,3})\s+(.*)$", line)
        if h:
            flush_para(); flush_list(); flush_quote()
            level = min(len(h.group(1)) + 1, 3)          # a page's own title is the h1; body headings start at h2
            out.append(f"<h{level}>{inline(h.group(2))}</h{level}>"); continue
        ol = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        ul = re.match(r"^\s*[-*]\s+(.*)$", line)
        if ol or ul:
            flush_para(); flush_quote()
            tag = "ol" if ol else "ul"
            if lst and lst_tag != tag:
                flush_list()
            lst_tag = tag; lst.append((ol or ul).group(1)); continue
        if line.lstrip().startswith(">"):
            flush_para(); flush_list(); quote.append(line.lstrip()[1:].strip()); continue
        flush_list(); flush_quote(); para.append(line)
    flush_para(); flush_list(); flush_quote()
    return "\n".join(out)


def plain(text: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", text).split())


def split_list(value: str) -> list[str]:
    """`roles: Admin, Front desk` -> ["Admin", "Front desk"]; a blank value is an empty list."""
    return [v.strip() for v in str(value or "").split(",") if v.strip()]


# ----------------------------------------------------------------------------- the model

def build_model(root: Path) -> dict:
    reg = load_registry(root)
    pages = load_pages(root)
    problems: list[str] = []
    for key in ("settings", "permissions", "screens"):
        if not isinstance(reg.get(key), list):
            problems.append(f"{REGISTRY.as_posix()} has no `{key}` list -- the registry is the app's own dump, see reference/help.md")
    settings = reg.get("settings") or []
    permissions = reg.get("permissions") or []
    screens = reg.get("screens") or []

    for s in settings:
        if not s.get("what"):
            problems.append(f"setting `{s.get('key')}` has no `what` -- a setting without a description cannot ship")
    for p in permissions:
        if not p.get("allows"):
            problems.append(f"permission `{p.get('key')}` has no `allows` -- a permission without a description cannot ship")

    guides = {pg["meta"].get("screen"): pg for pg in pages if pg["kind"] == "screens"}
    known = {s.get("key") for s in screens}
    for s in screens:
        if s.get("key") not in guides:
            problems.append(f"screen `{s.get('key')}` ({s.get('label', '')}) has no guide -- write {HELP.as_posix()}/screens/{s.get('key')}.md")
    for k, pg in guides.items():
        if k not in known:
            problems.append(f"{pg['file']} guides screen `{k}`, which the registry does not know")
    for pg in pages:
        if pg["kind"] in CITED and not pg["meta"].get("spec"):
            problems.append(f"{pg['file']} has no `spec:` -- a {pg['kind'][:-1]} with no section behind it is opinion, not doctrine")
        if pg["kind"] == "glossary" and not pg["meta"].get("term"):
            problems.append(f"{pg['file']} has no `term:`")
        if pg["kind"] != "glossary" and not pg["meta"].get("title") and pg["kind"] != "screens":
            problems.append(f"{pg['file']} has no `title:`")

    rendered = []
    for pg in pages:
        meta = pg["meta"]
        if pg["kind"] == "screens":
            reg_screen = next((s for s in screens if s.get("key") == meta.get("screen")), {})
            title = meta.get("title") or reg_screen.get("label") or pg["slug"]
        elif pg["kind"] == "glossary":
            title = meta.get("term") or pg["slug"]
        else:
            title = meta.get("title") or pg["slug"]
        body_html = render_markdown(pg["body"])
        rendered.append({
            "kind": pg["kind"], "slug": pg["slug"], "title": title,
            "spec": meta.get("spec", ""), "area": meta.get("area", ""), "screen": meta.get("screen", ""),
            "versus": meta.get("versus", ""), "source": pg["file"], "html": body_html,
            "steps": body_html.count("<li>"),
            # The rest of the frontmatter, as written, and the roles list split -- a page names the roles
            # whose Help it belongs to (`roles: Admin, Freelancer`); empty means every role.
            "meta": meta,
            "roles": split_list(meta.get("roles", "")),
        })
    index = [{"kind": r["kind"], "slug": r["slug"], "title": r["title"], "text": plain(r["html"])[:600]} for r in rendered]
    index += [{"kind": "settings", "slug": s.get("key", ""), "title": s.get("label") or s.get("key", ""), "text": plain(f"{s.get('what', '')} {s.get('affects', '')} {s.get('unit', '')}")} for s in settings]
    index += [{"kind": "permissions", "slug": p.get("key", ""), "title": p.get("name") or p.get("key", ""), "text": plain(p.get("allows", ""))} for p in permissions]
    return {
        "commit": reg.get("commit", ""), "version": reg.get("version", ""),
        "pages": rendered, "settings": settings, "permissions": permissions, "screens": screens,
        "index": index,
        "totals": {"pages": len(rendered), **{k: sum(1 for r in rendered if r["kind"] == k) for k in KINDS},
                   "settings": len(settings), "permissions": len(permissions), "screens": len(screens)},
        "problems": problems,
    }


def render_build(m: dict) -> str:
    """The one file the app reads. Sorted keys, fixed indent: the same inputs give the same bytes."""
    out = {k: v for k, v in m.items() if k != "problems"}
    out["generator"] = "rails-flow/build_help.py"
    return json.dumps(out, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


def assert_totals(m: dict, text: str) -> list[str]:
    """The build must carry every page and every registry entry -- a renderer that drops one must FAIL, not
    print a shorter file."""
    built = json.loads(text)
    problems = []
    if len(built["pages"]) != m["totals"]["pages"]:
        problems.append(f"the build holds {len(built['pages'])} page(s) where the sources have {m['totals']['pages']}")
    for key in ("settings", "permissions", "screens"):
        if len(built[key]) != m["totals"][key]:
            problems.append(f"the build holds {len(built[key])} {key} where the registry has {m['totals'][key]}")
    if len(built["index"]) != len(m["index"]):
        problems.append("the search index is shorter than the pages and references it should cover")
    return problems


# ----------------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="rebuild in memory; exit 1 on drift, write nothing")
    ap.add_argument("--json", action="store_true", help="print the model")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--root", default=".")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root)
    if not (root / REGISTRY).is_file():
        print(f"n/a: no {REGISTRY.as_posix()} — the app dumps its settings, permissions and screens there (reference/help.md); Help is a join over it")
        return 3
    try:
        m = build_model(root)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"cannot read a source: {exc}", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps({k: v for k, v in m.items() if k != "pages"}, indent=2, ensure_ascii=False))
        return 0
    text = render_build(m)
    problems = m["problems"] + assert_totals(m, text)
    for p in problems:
        print(f"PROBLEM {p}", file=sys.stderr)
    if problems:
        return 2
    out = root / OUT
    if a.check:
        if not out.is_file():
            print(f"n/a: no {OUT.as_posix()} yet — build it first (run without --check)")
            return 3
        if out.read_text(encoding="utf-8") != text:
            print(f"DRIFT: {OUT.as_posix()} is not a clean build of {HELP.as_posix()}/ — rebuild and commit it with the change that moved them")
            return 1
        print(f"clean: {OUT.as_posix()} matches its sources ({m['totals']['pages']} pages, {m['totals']['settings']} settings, {m['totals']['permissions']} permissions, {m['totals']['screens']} screens)")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    (out.parent / ".generated").write_text("build_help.py output — do not hand-edit; rebuild with the script.\n", encoding="utf-8")
    changed = not out.is_file() or out.read_text(encoding="utf-8") != text
    if changed:
        out.write_text(text, encoding="utf-8")
    print(f"{'wrote' if changed else 'unchanged'} {OUT.as_posix()} — {m['totals']['pages']} pages, {m['totals']['settings']} settings, {m['totals']['permissions']} permissions, {m['totals']['screens']} screens; commit it with the change")
    return 0


# ----------------------------------------------------------------------------- selftest

REG = {"commit": "abc1234", "version": "v0.4.0",
       "settings": [{"key": "task_aging_hours_before_escalation", "label": "Aging hours before escalation", "unit": "hours", "group": "queue",
                     "what": "Unclaimed this long and the task is flagged as aging.", "affects": "The dashboard's aging figure and the Throughput report."}],
       "permissions": [{"key": "screen_defect", "name": "Screen and attribute a defect", "allows": "Decide fault on a filed defect.", "roles": ["Admin"]}],
       "screens": [{"key": "defects", "area": "Accountability", "label": "Defect queue", "purpose": "Filed defects awaiting screening.", "permission": "screen_defect"}]}
PROC = "---\ntitle: Screen a filed defect\narea: Accountability\nspec: §7.2\nroles: Admin, IT\nsummary: Decide fault. Three outcomes.\n---\n\nDecide fault before anyone is notified.\n\n1. Open the defect and read the **evidence**.\n2. Compare the form against the scan.\n\n> Only the third outcome notifies anyone.\n"
RULE = "---\ntitle: Screening is atomic\nspec: §7.2\n---\n\nTwo holders cannot screen the same defect into two outcomes.\n"
TERM = "---\nterm: Defect\nversus: Flag\n---\n\nAn error found after the work was accepted.\n"
GUIDE = "---\nscreen: defects\n---\n\n## What this screen holds\n\nFiled defects awaiting screening, oldest first.\n\n- Screen opens the decision.\n- Open the request shows the pages.\n"


def selftest() -> int:
    failures = 0

    def check_(label: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1; print(f"FAIL {label} — {detail}")

    def project(td: str, **files: str) -> Path:
        root = Path(td)
        (root / REGISTRY).parent.mkdir(parents=True, exist_ok=True)
        (root / REGISTRY).write_text(json.dumps(REG), encoding="utf-8")
        defaults = {"procedures/screen-defect.md": PROC, "rules/screening-is-atomic.md": RULE, "glossary/defect.md": TERM, "screens/defects.md": GUIDE}
        defaults.update(files)
        for rel, text in defaults.items():
            if text is None:
                continue
            p = root / HELP / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text, encoding="utf-8")
        return root

    with tempfile.TemporaryDirectory() as td:
        root = project(td)
        check_("no registry is n/a, never a pass", main(["--root", str(Path(td) / "nowhere")]) == 3)
        check_("--check before the first build is n/a", main(["--check", "--root", td]) == 3)
        check_("a complete project builds", main(["--root", td]) == 0)
        built = json.loads((root / OUT).read_text(encoding="utf-8"))
        check_("the build carries every page, reference and the registry's commit", built["totals"]["pages"] == 4 and built["commit"] == "abc1234" and len(built["settings"]) == 1, str(built["totals"]))
        proc = next(p for p in built["pages"] if p["kind"] == "procedures")
        check_("markdown renders headings, ordered steps, bold and the callout", "<ol><li>Open the defect and read the <strong>evidence</strong>.</li>" in proc["html"] and "<blockquote>" in proc["html"] and proc["steps"] == 2, proc["html"])
        check_("a page carries its roles as a list and the rest of its frontmatter as meta", proc["roles"] == ["Admin", "IT"] and proc["meta"].get("summary") == "Decide fault. Three outcomes.", str(proc.get("roles")) + " " + str(proc.get("meta")))
        rule = next(p for p in built["pages"] if p["kind"] == "rules")
        check_("a page with no roles line belongs to every role: an empty list", rule["roles"] == [], str(rule.get("roles")))
        guide = next(p for p in built["pages"] if p["kind"] == "screens")
        check_("a screen guide takes its title from the registry and its body heading starts at h2", guide["title"] == "Defect queue" and "<h3>What this screen holds</h3>" in guide["html"], guide["html"][:120])
        check_("the search index covers pages, settings and permissions", any(i["kind"] == "settings" for i in built["index"]) and any(i["kind"] == "permissions" for i in built["index"]))
        check_("a clean build passes --check", main(["--check", "--root", td]) == 0)
        check_("the same inputs give the same bytes", render_build(build_model(root)) == (root / OUT).read_text(encoding="utf-8"))
        (root / HELP / "rules/screening-is-atomic.md").write_text(RULE.replace("Two holders", "Three holders"), encoding="utf-8")
        check_("a source that moved makes --check report DRIFT", main(["--check", "--root", td]) == 1)
        (root / HELP / "_build" / "help.json").unlink()
        (root / HELP / "rules/screening-is-atomic.md").write_text(RULE, encoding="utf-8")

    with tempfile.TemporaryDirectory() as td:
        root = project(td, **{"screens/defects.md": None})
        check_("a screen with no guide is a PROBLEM", main(["--root", td]) == 2)
    with tempfile.TemporaryDirectory() as td:
        root = project(td, **{"procedures/screen-defect.md": PROC.replace("spec: §7.2\n", "")})
        check_("a procedure with no spec citation is a PROBLEM", main(["--root", td]) == 2)
    with tempfile.TemporaryDirectory() as td:
        root = project(td, **{"screens/ghost.md": "---\nscreen: ghost\n---\n\nA screen the app does not have.\n"})
        check_("a guide for a screen the registry does not know is a PROBLEM", main(["--root", td]) == 2)
    with tempfile.TemporaryDirectory() as td:
        root = project(td)
        reg = json.loads(json.dumps(REG)); reg["settings"][0].pop("what")
        (root / REGISTRY).write_text(json.dumps(reg), encoding="utf-8")
        check_("a setting with no description is a PROBLEM", main(["--root", td]) == 2)
    with tempfile.TemporaryDirectory() as td:
        root = project(td)
        m = build_model(root)
        short = render_build({**m, "pages": m["pages"][:-1]})
        check_("a page the renderer dropped is a PROBLEM, not a shorter file", assert_totals(m, short) != [])

    print(f"build_help selftest: {failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
