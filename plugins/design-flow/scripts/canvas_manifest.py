#!/usr/bin/env python3
"""canvas_manifest.py -- give "done" a denominator: what a Claude Design canvas export SAYS, as a checklist (#908).

WHY. `/design-flow:port` asks for "visual parity against the source" and nothing measures it, so an agent
can implement three of an artboard's seven sections, pass the design-system audit (the three are
on-catalogue) and truthfully say the checks passed. This reads the export STRUCTURALLY and lists every
thing it specifies; the port is not done until every item is accounted for by name.

WHAT A `.dc.html` EXPORT IS (measured on a real one, `Admin.dc.html`, 207 KB): `<x-dc>` wrapping a
`<helmet>` and the screen; 408 inline styles and NO heading tags (headings are spans with font-size);
a template runtime -- `<sc-for list="{{ nav }}" as="item">` repeats, `<sc-if value="{{ x }}">`
conditionals, 526 `{{ binding }}` placeholders -- and a `<script type="text/x-dc">` of 123 KB holding
the DATA the template binds (nav labels, table columns, badges, copy). Most of the spec lives in that
script, as `label: '...'` pairs and short Title-case literals. So the manifest reads both halves.

  extract <canvas.dc.html> [--out manifest.json]   one entry per artboard; under it the items below
  compare  <manifest.json> --root DIR              audit: which items' text is present anywhere under DIR's
                                                   views / components / locales -- no report needed
  check    <manifest.json> --report report.json    every item accounted for (implemented|dropped-scaffolding|
                                                   token-gap|deferred); `implemented` copy must exist in the
                                                   file it names. Exit 0 accounted · 1 gaps · 3 no manifest
  --selftest

Items and their kinds: `heading` (text styled >= 18px, or h1-h6), `copy` (a literal text run of 3+ words),
`binding` (a `{{ root }}` the screen displays), `control` (button/a/input/select/textarea with its label),
`repeat` (an sc-for: the list it iterates), `condition` (an sc-if: the state it switches on), `icon`
(Phosphor `ph-*`), `data-label` (a `label|title|hint|placeholder|empty|caption|cta: '...'` in the script),
`data-copy` (a 3+-word literal in the script). Stable ids: `<artboard>:<kind>:<sha1(text)[:8]>`.

NOT claimed: pixel parity. Claimed: every thing the canvas says is present in the port or decided about,
by name, before "done". Stdlib only; no browser; no network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
CONTROLS = {"button", "a", "input", "select", "textarea"}
BIND = re.compile(r"\{\{\s*([A-Za-z_$][\w$]*)(?:[.\[][^}]*?)?\s*\}\}")
STATE_WORDS = ("empty", "loading", "error", "success", "disabled", "no results", "nothing", "failed", "pending")
LABEL_KEYS = ("label", "title", "hint", "placeholder", "empty", "caption", "cta", "heading", "subtitle", "name", "help")
SCRIPT_RE = re.compile(r'<script type="text/x-dc"[^>]*>(.*?)</script>', re.S)
FONT_SIZE = re.compile(r"font-size:\s*(\d+(?:\.\d+)?)px")


def _id(artboard: str, kind: str, text: str) -> str:
    return f"{artboard}:{kind}:{hashlib.sha1(text.encode('utf-8')).hexdigest()[:8]}"


class Canvas(HTMLParser):
    """Walks the export once; void elements never enter the stack (the first draft counted every
    `<input>`/`<img>`/`<link>` as still open, and the screen's root div vanished behind the helmet)."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.in_x = False
        self.artboards: list[str] = []
        self.cur: str = ""
        self.items: list[dict] = []
        self._text_target: tuple[str, dict] | None = None
        self._pending_control: dict | None = None
        self._skip = 0                         # inside helmet / style / script

    def _add(self, kind: str, text: str, **extra) -> None:
        text = " ".join(text.split())
        if not text:
            return
        item = {"id": _id(self.cur or "canvas", kind, text), "artboard": self.cur or "canvas", "kind": kind, "text": text}
        item.update(extra)
        if not any(i["id"] == item["id"] for i in self.items):
            self.items.append(item)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "x-dc":
            self.in_x = True
            return
        if not self.in_x:
            return
        if tag in ("helmet", "style", "script"):
            self._skip += 1
        if self._skip:
            if tag not in VOID:
                self.stack.append((tag, a))
            return
        depth = len(self.stack)
        if depth == 0:                          # a direct child of <x-dc>: an artboard
            name = a.get("data-name") or a.get("id") or a.get("aria-label") or f"artboard-{len(self.artboards) + 1}"
            self.artboards.append(name); self.cur = name
        for v in a.values():                     # `value="{{ empty }}"`, `onClick="{{ screen }}"`: bound in attributes
            for m in BIND.finditer(v or ""):
                self._add("binding", m.group(1))
        if tag == "sc-for":
            self._add("repeat", f"{a.get('as', '?')} in {a.get('list', '?')}", count_hint=a.get("hint-placeholder-count", ""))
        elif tag == "sc-if":
            self._add("condition", a.get("value", "?"))
        elif tag in CONTROLS:
            label = a.get("aria-label") or a.get("placeholder") or a.get("title") or a.get("value", "") or ""
            ctl = {"tag": tag, "type": a.get("type", ""), "label": label, "href": a.get("href", ""), "text": ""}
            if tag in VOID:                       # <input> never closes: record it now or lose it
                self._flush_control(ctl)
            else:
                self._pending_control = ctl
        elif tag == "i" and "ph-" in a.get("class", ""):
            icon = next((c for c in a.get("class", "").split() if c.startswith("ph-") and c != "ph"), "")
            if icon:
                self._add("icon", icon)
        m = FONT_SIZE.search(a.get("style", ""))
        big = bool(m and float(m.group(1)) >= 18) or tag in ("h1", "h2", "h3", "h4", "h5", "h6")
        if tag not in VOID:
            self.stack.append((tag, {**a, "_big": big}))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if tag == "x-dc":
            self.in_x = False; return
        if not self.in_x or tag in VOID:
            return
        if self.stack and self.stack[-1][0] == tag:
            self.stack.pop()
        else:                                   # tolerate mis-nesting: pop to the nearest match
            for i in range(len(self.stack) - 1, -1, -1):
                if self.stack[i][0] == tag:
                    del self.stack[i:]; break
        if tag in ("helmet", "style", "script") and self._skip:
            self._skip -= 1
        if tag in CONTROLS and self._pending_control is not None:
            c = self._pending_control; self._pending_control = None
            self._flush_control(c)

    def _flush_control(self, c: dict) -> None:
        label = c["label"] or c["text"] or c["href"]
        kind = f"{c['tag']}{('[' + c['type'] + ']') if c['type'] else ''}"
        self._add("control", f"{kind}: {label}" if label else f"{kind}: (unlabelled)")

    def handle_data(self, data):
        if not self.in_x or self._skip:
            return
        t = " ".join(data.split())
        if not t:
            return
        if self._pending_control is not None and not BIND.fullmatch(t):
            self._pending_control["text"] = (self._pending_control["text"] + " " + t).strip()
        for m in BIND.finditer(t):
            self._add("binding", m.group(1))
        literal = BIND.sub("", t).strip(" :·—-")
        if not literal:
            return
        big = any(a.get("_big") for _, a in self.stack[-3:])
        if big and len(literal) <= 80:
            self._add("heading", literal)
        elif len(literal.split()) >= 3:
            states = [w for w in STATE_WORDS if w in literal.lower()]
            cond = next((a.get("value") for t, a in reversed(self.stack) if t == "sc-if"), None)
            if cond:
                states.append(f"shown when {cond}")
            self._add("copy", literal, **({"states": states} if states else {}))


def script_items(html: str, artboard: str) -> list[dict]:
    """The data half: `label: '...'` pairs and Title-case literals from the x-dc script, never code."""
    m = SCRIPT_RE.search(html)
    if not m:
        return []
    js = m.group(1)
    out: list[dict] = []
    seen: set[str] = set()

    def add(kind: str, text: str) -> None:
        text = " ".join(text.split())
        if text and text not in seen and not re.search(r"[{}$<>=;`\\]|=>|\(\)", text):
            seen.add(text); out.append({"id": _id(artboard, kind, text), "artboard": artboard, "kind": kind, "text": text})
    for mm in re.finditer(r"\b(" + "|".join(LABEL_KEYS) + r")\s*:\s*(?:'([^'\n]{1,120})'|\"([^\"\n]{1,120})\")", js):
        add("data-label", mm.group(2) or mm.group(3))
    for mm in re.finditer(r"(?<![\w$])(?:'([^'\n]{3,160})'|\"([^\"\n]{3,160})\")", js):
        v = mm.group(1) or mm.group(2)
        if len(v.split()) >= 3 and v[:1].isalpha():
            add("data-copy", v)
    return out


def extract(path: Path) -> dict:
    html = path.read_text(encoding="utf-8", errors="replace")
    c = Canvas(); c.feed(html)
    artboards = c.artboards or ["canvas"]
    items = c.items + script_items(html, artboards[0] if len(artboards) == 1 else "script")
    kinds: dict[str, int] = {}
    for i in items:
        kinds[i["kind"]] = kinds.get(i["kind"], 0) + 1
    return {"source": path.name, "artboards": artboards, "items": items, "totals": kinds,
            "generator": "design-flow/canvas_manifest.py"}


# ----------------------------------------------------------------------------- compare / check

TEXT_KINDS = ("heading", "copy", "control", "data-label", "data-copy")
DEFAULT_PATHS = ("app/views", "app/components", "app/javascript", "config/locales", "app/helpers")


def _corpus(root: Path, paths: tuple[str, ...]) -> dict[str, str]:
    files: dict[str, str] = {}
    for rel in paths:
        d = root / rel
        if not d.exists():
            continue
        for p in (d.rglob("*") if d.is_dir() else [d]):
            if p.is_file() and p.suffix in (".erb", ".rb", ".yml", ".yaml", ".js", ".ts", ".html", ".haml", ".slim", ".md", ".json"):
                try:
                    files[p.relative_to(root).as_posix()] = " ".join(p.read_text(encoding="utf-8", errors="replace").split()).lower()
                except OSError:
                    pass
    return files


def _needle(item: dict) -> str:
    t = item["text"]
    if item["kind"] == "control":
        t = t.split(": ", 1)[1] if ": " in t else t
        if t == "(unlabelled)":
            return ""
    return " ".join(t.split()).lower()


def compare(manifest: dict, root: Path, paths: tuple[str, ...] = DEFAULT_PATHS) -> dict:
    corpus = _corpus(root, paths)
    found, missing, skipped, bound = [], [], [], []
    for item in manifest["items"]:
        if item["kind"] not in TEXT_KINDS:
            continue
        n = _needle(item)
        if "{{" in n:
            bound.append(item); continue             # data-driven: its literal lives in the script's data-labels
        if len(n) < 4:
            skipped.append(item); continue
        where = [f for f, body in corpus.items() if n in body]
        (found if where else missing).append({**item, "where": where[:3]})
    by_kind: dict[str, dict[str, int]] = {}
    for bucket, name in ((found, "found"), (missing, "missing")):
        for i in bucket:
            by_kind.setdefault(i["kind"], {"found": 0, "missing": 0})[name] += 1
    return {"root": str(root), "files_searched": len(corpus), "found": found, "missing": missing, "skipped": len(skipped), "bound": len(bound), "by_kind": by_kind}


STATUSES = ("implemented", "dropped-scaffolding", "token-gap", "deferred")


def check(manifest: dict, report: dict, root: Path) -> list[str]:
    problems: list[str] = []
    entries = report.get("items", {})
    for item in manifest["items"]:
        e = entries.get(item["id"])
        if e is None:
            problems.append(f"{item['id']} ({item['kind']}: {item['text'][:60]!r}) is not accounted for")
            continue
        st = e.get("status")
        if st not in STATUSES:
            problems.append(f"{item['id']}: status {st!r} is not one of {', '.join(STATUSES)}")
            continue
        if st == "deferred" and not e.get("reason"):
            problems.append(f"{item['id']}: deferred with no reason -- a deferral the user did not approve is a gap")
        if st == "implemented":
            where = e.get("where", "")
            if not where:
                problems.append(f"{item['id']}: implemented with no `where` -- name the file")
            elif item["kind"] in TEXT_KINDS:
                n = _needle(item)
                p = root / where
                body = " ".join(p.read_text(encoding="utf-8", errors="replace").split()).lower() if p.is_file() else ""
                locales = " ".join(" ".join(q.read_text(encoding="utf-8", errors="replace").split()).lower() for q in (root / "config" / "locales").glob("*.yml")) if (root / "config" / "locales").is_dir() else ""
                if n and len(n) >= 4 and n not in body and n not in locales:
                    problems.append(f"{item['id']}: implemented in {where} but the text {item['text'][:50]!r} is in neither that file nor config/locales")
    extra = [k for k in entries if not any(i["id"] == k for i in manifest["items"])]
    if extra:
        problems.append(f"{len(extra)} report entr(ies) name ids not in the manifest: {', '.join(extra[:3])}")
    return problems


# ----------------------------------------------------------------------------- CLI

def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="mode")
    e = sub.add_parser("extract"); e.add_argument("canvas"); e.add_argument("--out"); e.add_argument("--json", action="store_true")
    c = sub.add_parser("compare"); c.add_argument("manifest"); c.add_argument("--root", default="."); c.add_argument("--paths", default=",".join(DEFAULT_PATHS)); c.add_argument("--json", action="store_true"); c.add_argument("--show", type=int, default=12)
    k = sub.add_parser("check"); k.add_argument("manifest"); k.add_argument("--report", required=True); k.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if a.mode == "extract":
        p = Path(a.canvas)
        if not p.is_file():
            print(f"no such export: {p}", file=sys.stderr); return 2
        m = extract(p)
        if a.out:
            Path(a.out).parent.mkdir(parents=True, exist_ok=True); Path(a.out).write_text(json.dumps(m, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if a.json or not a.out:
            print(json.dumps(m if a.json else m["totals"], indent=2, ensure_ascii=False))
        else:
            print(f"{p.name}: {len(m['items'])} item(s) across {len(m['artboards'])} artboard(s) -> {a.out}  " + ", ".join(f"{k} {v}" for k, v in sorted(m["totals"].items())))
        return 0
    if a.mode in ("compare", "check"):
        mp = Path(a.manifest)
        if not mp.is_file():
            print(f"n/a: no manifest at {mp} -- run `extract` on the canvas export first"); return 3
        manifest = json.loads(mp.read_text(encoding="utf-8"))
        root = Path(a.root)
        if a.mode == "compare":
            r = compare(manifest, root, tuple(a.paths.split(",")))
            if a.json:
                print(json.dumps(r, indent=2, ensure_ascii=False)); return 0
            print(f"{manifest['source']} vs {root.resolve().name}: {len(r['found'])} of {len(r['found']) + len(r['missing'])} literal text items present ({r['files_searched']} files searched; {r['bound']} bound to data, {r['skipped']} too short to search)")
            for kind, c in sorted(r["by_kind"].items()):
                print(f"  {kind:<11} {c['found']:>4} found  {c['missing']:>4} missing")
            for i in r["missing"][:a.show]:
                print(f"  - missing {i['kind']}: {i['text'][:90]}")
            if len(r["missing"]) > a.show:
                print(f"  ... {len(r['missing']) - a.show} more (--show N, or --json)")
            return 1 if r["missing"] else 0
        rp = Path(a.report)
        if not rp.is_file():
            print(f"no port report at {rp} -- the porter writes it: every manifest id -> status (+ where / reason)"); return 1
        problems = check(manifest, json.loads(rp.read_text(encoding="utf-8")), root)
        for pr in problems:
            print(f"- {pr}")
        print("accounted for: every item in the manifest has a status, and every implemented text is where it says" if not problems
              else f"\n{len(problems)} gap(s). The port is not done: account for each item, then re-run.")
        return 1 if problems else 0
    ap.print_help(); return 2


# ----------------------------------------------------------------------------- selftest

FIXTURE = """<!DOCTYPE html><html><head><meta charset="utf-8"><script src="./support.js"></script></head><body>
<x-dc>
<helmet><link rel="stylesheet" href="_ds/x/colors_and_type.css"><style>body{margin:0}</style></helmet>
<div id="admin" style="padding: 24px; font-family: 'Noto Sans'">
  <div style="display:flex"><img src="assets/brand.svg" alt="Reliance Health"><input type="text" placeholder="Search defects"></div>
  <span style="font-size: 26px; font-weight: 600">Defects awaiting screening</span>
  <p style="font-size: 14px">You are not country-scoped. Narrowing here is a filter you chose.</p>
  <sc-for list="{{ nav }}" as="item" hint-placeholder-count="7"><a href="{{ item.href }}"><i class="ph ph-gauge"></i>{{ item.label }}</a></sc-for>
  <sc-if value="{{ empty }}" hint-placeholder-val="{{ false }}"><div>No defects match this filter yet.</div></sc-if>
  <button type="button" onClick="{{ screen }}" aria-label="Screen defect"><i class="ph ph-check"></i></button>
  <button type="button">Export CSV</button>
  <select><option>All countries</option></select>
</div>
<script type="text/x-dc" data-dc-script>
const TONE = { ok: ['#E8F5F0', '#288D68'] };
const nav = [{ label: 'Defects', href: '#', badge: 'New' }, { label: 'Payout runs', href: '#' }];
const empty = 'No defects match this filter yet.';
const hint = `template ${x} literal`;
const cols = ['Freelancer', 'Country', 'Fault attributed to'];
</script>
</x-dc></body></html>
"""


def selftest() -> int:
    import tempfile
    n, failures = 0, []

    def check_(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    with tempfile.TemporaryDirectory() as td:
        root = Path(td); canvas = root / "Admin.dc.html"; canvas.write_text(FIXTURE, encoding="utf-8")
        m = extract(canvas)
        kinds = {i["kind"]: [x["text"] for x in m["items"] if x["kind"] == i["kind"]] for i in m["items"]}
        check_("the screen's root div is the artboard, not the helmet (void tags do not stay open)", m["artboards"] == ["admin"], str(m["artboards"]))
        check_("a span styled >= 18px is a heading", "Defects awaiting screening" in kinds.get("heading", []), str(kinds.get("heading")))
        check_("a literal run of 3+ words is copy; a binding is not copy", "You are not country-scoped. Narrowing here is a filter you chose." in kinds.get("copy", [])
               and not any("{{" in t for t in kinds.get("copy", [])), str(kinds.get("copy")))
        check_("bindings are recorded by root identifier", set(kinds.get("binding", [])) >= {"item", "empty", "screen"}, str(kinds.get("binding")))
        check_("a bound text with inner spaces (`{{ crumb }}`) is never copy", not any("{{" in t for t in kinds.get("copy", []) + kinds.get("heading", [])))
        check_("controls carry their label: aria-label, placeholder or inner text", {"button[button]: Screen defect", "button[button]: Export CSV", "input[text]: Search defects"} <= set(kinds.get("control", [])), str(kinds.get("control")))
        check_("a repeat names what it iterates; a condition names its state", "item in {{ nav }}" in kinds.get("repeat", []) and "{{ empty }}" in kinds.get("condition", []))
        check_("copy naming a state is tagged", any(i.get("states") for i in m["items"] if i["text"].startswith("No defects")))
        check_("icons are listed by name", {"ph-gauge", "ph-check"} <= set(kinds.get("icon", [])))
        check_("the x-dc script's label pairs are items; a template literal is not", {"Defects", "Payout runs"} <= set(kinds.get("data-label", [])) and not any("template" in t for t in kinds.get("data-label", []) + kinds.get("data-copy", [])), str(kinds.get("data-label")))
        check_("a 3+-word literal in the script is data-copy", "Fault attributed to" in kinds.get("data-copy", []) or "No defects match this filter yet." in kinds.get("data-copy", []), str(kinds.get("data-copy")))
        check_("ids are stable across runs", [i["id"] for i in extract(canvas)["items"]] == [i["id"] for i in m["items"]])
        # compare: a project that implemented half
        (root / "app" / "views" / "admin").mkdir(parents=True)
        (root / "app" / "views" / "admin" / "index.html.erb").write_text("<h1>Defects awaiting screening</h1><p>You are not country-scoped. Narrowing here is a filter you chose.</p><%= button_to 'Export CSV' %>\n", encoding="utf-8")
        (root / "config" / "locales").mkdir(parents=True); (root / "config" / "locales" / "en.yml").write_text("en:\n  admin:\n    search: Search defects\n", encoding="utf-8")
        r = compare(m, root)
        found = {i["text"] for i in r["found"]}; missing = {i["text"] for i in r["missing"]}
        check_("compare finds copy in a view and a label in the locales", "Defects awaiting screening" in found and "input[text]: Search defects" in found, str(found))
        check_("compare names what the project lacks", "button[button]: Screen defect" in missing and "Payout runs" in missing, str(missing))
        check_("compare counts by kind", r["by_kind"]["heading"]["found"] == 1)
        # check: a report that accounts for everything vs one that skips an item / lies about where
        full = {"items": {i["id"]: {"status": "implemented", "where": "app/views/admin/index.html.erb"} if i["text"] in ("Defects awaiting screening", "Export CSV", "button[button]: Export CSV", "You are not country-scoped. Narrowing here is a filter you chose.")
                          else {"status": "deferred", "reason": "phase 2, approved 2026-09-03"} for i in m["items"]}}
        check_("a report accounting for every item, with real text where it says, is clean", check(m, full, root) == [], "; ".join(check(m, full, root))[:300])
        partial = {"items": {k: v for k, v in list(full["items"].items())[:-1]}}
        check_("an unaccounted item is a gap named by id and text", any("is not accounted for" in p for p in check(m, partial, root)))
        liar = json.loads(json.dumps(full)); liar["items"][next(i["id"] for i in m["items"] if i["text"] == "button[button]: Screen defect")] = {"status": "implemented", "where": "app/views/admin/index.html.erb"}
        check_("`implemented` whose text is in neither the named file nor the locales is a gap", any("in neither that file nor config/locales" in p for p in check(m, liar, root)))
        deferred_id = next((k for k, v in full["items"].items() if v["status"] == "deferred"), None)
        check_("the fixture has a deferred item to test with", deferred_id is not None)
        nodefer = json.loads(json.dumps(full)); nodefer["items"][deferred_id or next(iter(full["items"]))] = {"status": "deferred"}
        check_("a deferral without a reason is a gap", any("deferred with no reason" in p for p in check(m, nodefer, root)))
        check_("no manifest is n/a (exit 3)", main(["compare", str(root / "none.json"), "--root", str(root)]) == 3)
    for f in failures:
        print(f"FAIL {f}")
    print(f"canvas_manifest selftest: {n} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
