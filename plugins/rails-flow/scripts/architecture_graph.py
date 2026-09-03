#!/usr/bin/env python3
"""rails-flow — living architecture graph for a Rails 8 app.

Extracts ONE artefact and serves three consumers: humans (the HTML + mermaid
views), agents (structural context without reading the whole codebase), and
qa-flow (reverse-walk `edges` for blast radius).

Emits into `docs/architecture/`:
  graph.json   {nodes, edges, flows} + commit, generated_at, content_digest
  index.html   THE DIAGRAM — an inline SVG, one column per layer, edges as paths,
               click a node to trace it or a flow to light its path — plus an index
               and detail view; inline CSS/JS, embedded JSON, ZERO external requests
               (opens from disk, offline, forever)
  graph.md     mermaid views, so a repo browser sees a picture (.html does not
               render on GitHub)

Design decisions worth knowing before editing:

* **Stdlib only, no AST, no third-party tool.** Regex + a line scanner over
  Ruby/ERB/JS. It must run in any clone with nothing installed. Rails
  metaprogramming is therefore invisible to it; that is a known, stated limit,
  not a bug. `--enrich` folds in a graph tool's output WHEN present, into a
  block that is deliberately excluded from the digest (see below).

* **Drift is detected by regenerating and comparing a content digest** — the
  same shape as the proven `dist/` guard (rebuild, then diff), not by
  fingerprinting input files. Fingerprinting inputs would fire on every
  prose-only edit to a view; digesting the extracted `{nodes, edges, flows}`
  fires exactly when the structure the artefact claims has actually changed.
  `generated_at` and `commit` are volatile and excluded from the digest, so a
  re-run on an unchanged tree is a no-op rather than a permanent diff.

* **Enrichment never enters the digest.** A graph built with graphify installed
  and one built without it must agree, or CI would report drift for a local
  tool's absence. Enriched edges live under `enrichment`, outside the digest.

* **Edge direction is uniform: from → to means "the subject acts on the
  object".** So `enqueues` runs enqueuer → job (the issue's example text says
  "enqueued_by"; the stated edge vocabulary says `enqueues`, and one vocabulary
  with one direction beats two names for one fact).

* **`concern` is a node type** though it is not in the issue's kind list: the
  specified `includes` edge has nowhere to point without it.

Exit codes: 0 success/fresh · 1 drift or a failed check · 2 usage/environment.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

GENERATOR = "rails-flow/architecture_graph.py"
SCHEMA = "rails-flow/architecture-graph@1"

LAYERS = {
    "controller": "web",
    "route": "web",
    "channel": "web",
    "model": "domain",
    "table": "domain",
    "service": "domain",
    "concern": "domain",
    "job": "async",
    "mailer": "async",
    "component": "ui",
    "stimulus": "ui",
    "turbo": "ui",
}

LAYER_ORDER = ["web", "domain", "async", "ui"]

# --------------------------------------------------------------------------
# inflection — small, deliberate, covers Rails' conventional cases
# --------------------------------------------------------------------------

IRREGULAR_PLURAL_TO_SINGULAR = {
    "people": "person", "children": "child", "men": "man", "women": "woman",
    "teeth": "tooth", "feet": "foot", "mice": "mouse", "geese": "goose",
    "data": "datum", "indices": "index", "matrices": "matrix",
    "vertices": "vertex", "analyses": "analysis", "diagnoses": "diagnosis",
    "lives": "life", "knives": "knife", "wives": "wife", "leaves": "leaf",
    "criteria": "criterion", "media": "medium",
}
IRREGULAR_SINGULAR_TO_PLURAL = {v: k for k, v in IRREGULAR_PLURAL_TO_SINGULAR.items()}
UNCOUNTABLE = {"money", "information", "equipment", "series", "species", "news"}


def singularize(word: str) -> str:
    w = word
    if w in UNCOUNTABLE:
        return w
    if w in IRREGULAR_PLURAL_TO_SINGULAR:
        return IRREGULAR_PLURAL_TO_SINGULAR[w]
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    for suffix in ("sses", "shes", "ches", "xes", "zes", "ses"):
        if w.endswith(suffix):
            return w[:-2]
    if w.endswith("s") and not w.endswith(("ss", "us", "is")):
        return w[:-1]
    return w


def pluralize(word: str) -> str:
    w = word
    if w in UNCOUNTABLE:
        return w
    if w in IRREGULAR_SINGULAR_TO_PLURAL:
        return IRREGULAR_SINGULAR_TO_PLURAL[w]
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    if w.endswith(("s", "x", "z", "ch", "sh")):
        return w + "es"
    return w + "s"


def camelize(snake: str) -> str:
    parts = snake.replace("/", "::").split("::")
    out = []
    for part in parts:
        out.append("".join(seg[:1].upper() + seg[1:] for seg in part.split("_") if seg))
    return "::".join(p for p in out if p)


def underscore(camel: str) -> str:
    s = camel.replace("::", "/")
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", s)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.replace("-", "_").lower()


def tableize(class_name: str) -> str:
    path = underscore(class_name).replace("/", "_")
    head, _, tail = path.rpartition("_")
    if head:
        return head + "_" + pluralize(tail)
    return pluralize(path)


def humanize(word: str) -> str:
    s = underscore(word).replace("_", " ").strip()
    return s[:1].upper() + s[1:] if s else s


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


# --------------------------------------------------------------------------
# source scanning helpers
# --------------------------------------------------------------------------

CONST_RE = re.compile(r"\b([A-Z][A-Za-z0-9]*(?:::[A-Z][A-Za-z0-9]*)*)\b")


def read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def walk(root: str, rel: str, exts: tuple[str, ...]) -> list[str]:
    """Every file under root/rel with one of `exts`, sorted for determinism."""
    base = os.path.join(root, rel)
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        for name in sorted(filenames):
            if name.endswith(exts):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


def strip_ruby_comments(src: str) -> str:
    """Drop `#` comments and =begin/=end blocks, leaving strings intact.

    Quote-aware so `"#{interpolation}"` and `"# not a comment"` survive; that
    matters because a stripped interpolation would lose the constant inside it.
    """
    out = []
    in_block = False
    for line in src.split("\n"):
        stripped = line.strip()
        if stripped.startswith("=begin"):
            in_block = True
            out.append("")
            continue
        if stripped.startswith("=end"):
            in_block = False
            out.append("")
            continue
        if in_block:
            out.append("")
            continue
        kept = []
        quote = None
        i = 0
        while i < len(line):
            ch = line[i]
            if quote:
                kept.append(ch)
                if ch == "\\" and i + 1 < len(line):
                    kept.append(line[i + 1])
                    i += 2
                    continue
                if ch == quote:
                    quote = None
                i += 1
                continue
            if ch in ("'", '"'):
                quote = ch
                kept.append(ch)
                i += 1
                continue
            if ch == "#":
                break
            kept.append(ch)
            i += 1
        out.append("".join(kept))
    return "\n".join(out)


def method_bodies(src: str) -> list[dict]:
    """Ordered `def`s with their bodies and visibility.

    Indentation-matched `end` rather than a real parser: correct for
    conventionally formatted Rails code, and a mis-parse costs a flow step, not
    correctness of the node/edge core.
    """
    lines = src.split("\n")
    results = []
    visibility = "public"
    i = 0
    while i < len(lines):
        line = lines[i]
        vis = re.match(r"^\s*(private|protected|public)\s*$", line)
        if vis:
            visibility = vis.group(1)
            i += 1
            continue
        head = re.match(r"^(\s*)def\s+(self\.)?([A-Za-z_][A-Za-z0-9_]*[?!=]?)", line)
        if not head:
            i += 1
            continue
        indent = len(head.group(1))
        body = []
        j = i + 1
        while j < len(lines):
            candidate = lines[j]
            if candidate.strip() == "end" and len(candidate) - len(candidate.lstrip()) == indent:
                break
            body.append(candidate)
            j += 1
        results.append({
            "name": head.group(3),
            "body": "\n".join(body),
            "visibility": visibility,
            "singleton": head.group(2) is not None,
            "line": i + 1,
        })
        i = j + 1
    return results


def class_name_from_path(root: str, path: str, rel_base: str) -> str:
    rel = os.path.relpath(path, os.path.join(root, rel_base))
    rel = rel.replace(os.sep, "/")
    rel = re.sub(r"\.(rb|js)$", "", rel)
    # `concerns/` is an autoload root, not a namespace: app/models/concerns/
    # auditable.rb defines Auditable, never Concerns::Auditable. Getting this
    # wrong silently breaks every `includes` edge.
    rel = "/".join(part for part in rel.split("/") if part != "concerns")
    return camelize(rel)


# Rails' tenant idiom — `Current.account.invoices…` — names no constant, so a
# constant scan cannot see the model. This resolves the association segment
# instead, which is how most scoped queries in a Rails 8 app are written.
CURRENT_CHAIN_RE = re.compile(r"Current\.\w+((?:\.\w+[!?]?(?:\([^()]*\))?)+)")


def current_chain_models(text: str, known: dict) -> list[tuple[str, str]]:
    """Ordered (model_id, tail_text) pairs reachable through a `Current.` chain."""
    found: list[tuple[str, str]] = []
    seen = set()
    for match in CURRENT_CHAIN_RE.finditer(text):
        chain = match.group(1)
        for segment in re.finditer(r"\.(\w+)[!?]?", chain):
            name = segment.group(1)
            candidate = camelize(singularize(name))
            if candidate in known and known[candidate]["type"] == "model" and candidate not in seen:
                seen.add(candidate)
                found.append((candidate, chain[segment.end(0):] or chain))
    return found


def git_output(root: str, args: list[str]) -> str:
    try:
        proc = subprocess.run(
            ["git"] + args, cwd=root, capture_output=True, text=True, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


# --------------------------------------------------------------------------
# routes
# --------------------------------------------------------------------------

RESOURCE_ROUTES = [
    ("index", "GET", ""),
    ("create", "POST", ""),
    ("new", "GET", "/new"),
    ("edit", "GET", "/:id/edit"),
    ("show", "GET", "/:id"),
    ("update", "PATCH", "/:id"),
    ("destroy", "DELETE", "/:id"),
]

SINGULAR_RESOURCE_ROUTES = [
    ("create", "POST", ""),
    ("new", "GET", "/new"),
    ("edit", "GET", "/edit"),
    ("show", "GET", ""),
    ("update", "PATCH", ""),
    ("destroy", "DELETE", ""),
]

VERB_RE = re.compile(r"^\s*(get|post|patch|put|delete)\s+(.+)$")


def _parse_list_option(text: str, key: str) -> list[str] | None:
    """`only: [:a, :b]`, `only: %i[a b]`, `only: :a` -> ['a', 'b'] / ['a']."""
    match = re.search(key + r":\s*(%[iw]?\[[^\]]*\]|\[[^\]]*\]|:[a-z0-9_]+)", text)
    if not match:
        return None
    return re.findall(r"[a-z0-9_]+", match.group(1))


def callback_applies(options: str, action: str) -> bool:
    """Honour `only:`/`except:` on a callback. Ignoring them makes every action
    look like it runs every filter — the flow steps then describe work the
    action does not do."""
    only = _parse_list_option(options, "only")
    if only is not None:
        return action in only
    excluded = _parse_list_option(options, "except")
    if excluded is not None:
        return action not in excluded
    return True


def parse_routes(root: str, notes: list[str]) -> list[dict]:
    """Static parse of config/routes.rb.

    Deliberately not `bin/rails routes`: that boots the app (slow, needs a
    working DB/credentials) and the artefact must be generatable in any clone.
    Unrecognised route DSL is reported in `notes`, never silently dropped.
    """
    path = os.path.join(root, "config", "routes.rb")
    src = strip_ruby_comments(read_text(path))
    if not src.strip():
        return []

    routes: list[dict] = []
    stack: list[dict] = []
    unparsed = 0

    # Each frame carries the ABSOLUTE prefix that applies to its children,
    # resolved at push time. Summing per-frame fragments cannot express the two
    # different prefixes a `resources` block hands out: nested resources get
    # `/invoices/:invoice_id`, while `member do` gets `/invoices/:id`.
    def path_prefix() -> str:
        return stack[-1]["prefix"] if stack else ""

    def module_prefix() -> str:
        return stack[-1]["mod"] if stack else ""

    def enclosing_resource() -> dict | None:
        for frame in reversed(stack):
            if frame["kind"] == "resources":
                return frame
        return None

    def controller_for(name: str) -> str:
        return camelize(module_prefix() + name) + "Controller"

    def add(verb: str, route_path: str, controller: str, action: str, line: int) -> None:
        clean = re.sub(r"/+", "/", route_path) or "/"
        if clean != "/" and clean.endswith("/"):
            clean = clean[:-1]
        routes.append({
            "verb": verb, "path": clean, "controller": controller,
            "action": action, "line": line,
        })

    for lineno, raw_line in enumerate(src.split("\n"), start=1):
        line = raw_line.strip()
        if not line:
            continue

        if re.match(r"^Rails\.application\.routes\.draw\s+do", line):
            stack.append({"kind": "draw", "prefix": "", "mod": "", "name": ""})
            continue

        if line == "end" or line.startswith("end "):
            if stack:
                stack.pop()
            continue

        block = line.endswith(" do") or line.endswith("do")

        namespace = re.match(r"^namespace\s+:?['\"]?([a-z0-9_]+)['\"]?", line)
        if namespace:
            name = namespace.group(1)
            if block:
                stack.append({
                    "kind": "namespace",
                    "prefix": path_prefix() + "/" + name,
                    "mod": module_prefix() + name + "/",
                    "name": name,
                })
            continue

        scope = re.match(r"^scope\s+(.*)$", line)
        if scope and block:
            text = scope.group(1)
            scope_path = ""
            scope_module = ""
            explicit_path = re.search(r"path:\s*['\":]([a-z0-9_/]+)", text)
            bare_path = re.match(r"^['\"]([a-z0-9_/]+)['\"]", text)
            if explicit_path:
                scope_path = "/" + explicit_path.group(1).strip("/")
            elif bare_path:
                scope_path = "/" + bare_path.group(1).strip("/")
            explicit_module = re.search(r"module:\s*['\":]([a-z0-9_]+)", text)
            if explicit_module:
                scope_module = explicit_module.group(1) + "/"
            stack.append({
                "kind": "scope",
                "prefix": path_prefix() + scope_path,
                "mod": module_prefix() + scope_module,
                "name": "",
            })
            continue

        resources = re.match(r"^(resources|resource)\s+:([a-z0-9_]+)(.*)$", line)
        if resources:
            macro, name, rest = resources.groups()
            only = _parse_list_option(rest, "only")
            except_ = _parse_list_option(rest, "except")
            path_option = re.search(r"path:\s*['\"]([^'\"]+)['\"]", rest)
            controller_option = re.search(r"controller:\s*['\"]([^'\"]+)['\"]", rest)
            segment = path_option.group(1).strip("/") if path_option else name
            controller = (
                camelize(module_prefix() + controller_option.group(1)) + "Controller"
                if controller_option else controller_for(name)
            )
            plural = macro == "resources"
            table = RESOURCE_ROUTES if plural else SINGULAR_RESOURCE_ROUTES
            base = path_prefix() + "/" + segment
            for action, verb, suffix in table:
                if only is not None and action not in only:
                    continue
                if except_ is not None and action in except_:
                    continue
                add(verb, base + suffix, controller, action, lineno)
            if block:
                stack.append({
                    "kind": "resources",
                    # children of a plural resource are scoped by the parent id
                    "prefix": base + ("/:%s_id" % singularize(name) if plural else ""),
                    "own": base,
                    "mod": module_prefix(),
                    "name": name,
                    "controller": controller,
                    "plural": plural,
                })
            continue

        if re.match(r"^(member|collection)\s*do$", line):
            kind = line.split()[0]
            parent = enclosing_resource()
            base = parent["own"] if parent else path_prefix()
            if kind == "member" and parent and parent.get("plural"):
                base += "/:id"
            stack.append({"kind": kind, "prefix": base, "mod": module_prefix(), "name": ""})
            continue

        root_route = re.match(r"^root\s+(?:to:\s*)?['\"]([a-z0-9_/]+)#([a-z0-9_]+)['\"]", line)
        if root_route:
            controller_path, action = root_route.groups()
            add("GET", path_prefix() or "/", camelize(module_prefix() + controller_path) + "Controller",
                action, lineno)
            continue

        verb_match = VERB_RE.match(raw_line)
        if verb_match:
            verb, rest = verb_match.groups()
            rest = rest.strip()
            target = re.search(r"(?:to:\s*|=>\s*)['\"]([a-z0-9_/]+)#([a-z0-9_]+)['\"]", rest)
            first = re.match(r"^[:'\"]([a-z0-9_/]+)['\"]?", rest)
            parent = enclosing_resource()
            inside_member = any(f["kind"] in ("member", "collection") for f in stack)
            if target:
                controller_path, action = target.groups()
                controller = camelize(module_prefix() + controller_path) + "Controller"
                segment = first.group(1) if first else action
                add(verb.upper(), path_prefix() + "/" + segment.strip("/"), controller, action, lineno)
            elif inside_member and parent and first:
                action = first.group(1).strip("/")
                add(verb.upper(), path_prefix() + "/" + action, parent["controller"], action, lineno)
            else:
                unparsed += 1
            continue

        if line.startswith(("mount ", "direct ", "resolve ", "concern ", "concerns ", "match ", "defaults ")):
            unparsed += 1

    if unparsed:
        notes.append(
            f"{unparsed} route line(s) in config/routes.rb used DSL this static parser does "
            "not model (mount/match/concern/dynamic segments) and are absent from the graph."
        )
    # Deterministic, and stable against reordering inside routes.rb.
    routes.sort(key=lambda r: (r["path"], r["verb"], r["controller"], r["action"]))
    return routes


# --------------------------------------------------------------------------
# graph construction
# --------------------------------------------------------------------------

class GraphBuilder:
    def __init__(self, root: str, max_flows: int):
        self.root = root
        self.max_flows = max_flows
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple[str, str, str], dict] = {}
        self.flows: list[dict] = []
        self.notes: list[str] = []
        self.sources: dict[str, dict] = {}          # class name -> parsed source
        self.controller_actions: dict[str, dict] = {}
        self.stimulus_ids: set[str] = set()
        self.table_names: set[str] = set()

    # -- primitives ------------------------------------------------------

    def add_node(self, node_id: str, node_type: str, file: str | None = None,
                 loc: int = 0, tags: list[str] | None = None) -> str:
        existing = self.nodes.get(node_id)
        if existing:
            if existing["type"] != node_type:
                self.notes.append(
                    f"id collision: '{node_id}' seen as both {existing['type']} and "
                    f"{node_type}; kept {existing['type']}."
                )
            return node_id
        self.nodes[node_id] = {
            "id": node_id,
            "type": node_type,
            "file": file,
            "layer": LAYERS.get(node_type, "domain"),
            "loc": loc,
            "tags": sorted(set(tags or [])),
        }
        return node_id

    def add_edge(self, source: str, target: str, kind: str) -> None:
        if not source or not target or source == target:
            return
        self.edges[(source, target, kind)] = {"from": source, "to": target, "kind": kind}

    def rel(self, path: str) -> str:
        return os.path.relpath(path, self.root).replace(os.sep, "/")

    # -- passes ----------------------------------------------------------

    def build(self) -> dict:
        self.scan_tables()
        self.scan_stimulus()
        self.scan_ruby("app/models", "model")
        self.scan_ruby("app/controllers", "controller")
        self.scan_ruby("app/jobs", "job")
        self.scan_ruby("app/mailers", "mailer")
        self.scan_ruby("app/services", "service")
        self.scan_ruby("app/components", "component")
        self.scan_ruby("app/channels", "channel")
        self.scan_views()
        self.resolve_edges()
        routes = parse_routes(self.root, self.notes)
        self.add_routes(routes)
        self.build_flows(routes)
        return self.result()

    def scan_tables(self) -> None:
        src = read_text(os.path.join(self.root, "db", "schema.rb"))
        if not src:
            return
        rel = "db/schema.rb"
        for match in re.finditer(
            r'create_table\s+"([a-z0-9_]+)"(.*?)\n(\s*)end', src, re.S
        ):
            name, body = match.group(1), match.group(2)
            self.table_names.add(name)
            self.add_node(name, "table", rel, loc=len(body.strip().split("\n")))

    def scan_stimulus(self) -> None:
        base = "app/javascript/controllers"
        for path in walk(self.root, base, ("_controller.js", "_controller.ts")):
            rel_path = os.path.relpath(path, os.path.join(self.root, base)).replace(os.sep, "/")
            identifier = re.sub(r"_controller\.(js|ts)$", "", rel_path).replace("/", "--").replace("_", "-")
            if not identifier:
                continue
            self.stimulus_ids.add(identifier)
            src = read_text(path)
            targets = re.search(r"static\s+targets\s*=\s*\[([^\]]*)\]", src)
            tags = []
            if targets:
                names = re.findall(r"[\w-]+", targets.group(1))
                if names:
                    tags.append(f"targets:{len(names)}")
            self.add_node(identifier, "stimulus", self.rel(path),
                          loc=len(src.split("\n")), tags=tags)

    def scan_ruby(self, rel_base: str, default_type: str) -> None:
        for path in walk(self.root, rel_base, (".rb",)):
            rel_path = self.rel(path)
            raw = read_text(path)
            src = strip_ruby_comments(raw)
            name = class_name_from_path(self.root, path, rel_base)
            if not name:
                continue
            node_type = default_type
            if "/concerns/" in rel_path:
                node_type = "concern"
            elif default_type == "controller" and not name.endswith("Controller"):
                # app/controllers holds the occasional non-controller helper
                node_type = "service"
            superclass = re.search(r"^\s*class\s+[\w:]+\s*<\s*([\w:]+)", src, re.M)
            parent = superclass.group(1) if superclass else None
            tags = self.tags_for(node_type, name, src, rel_path, parent)
            self.add_node(name, node_type, rel_path, loc=len(raw.split("\n")), tags=tags)
            self.sources[name] = {
                "type": node_type, "src": src, "file": rel_path,
                "parent": parent, "bodies": method_bodies(src),
            }
            if node_type == "model":
                self.scan_model(name, src, parent)
            if node_type == "controller":
                self.scan_controller(name, src)

    def tags_for(self, node_type: str, name: str, src: str, rel_path: str,
                 parent: str | None) -> list[str]:
        tags: list[str] = []
        if name.startswith("Admin::") or "/admin/" in rel_path:
            tags.append("admin")
        if node_type == "controller":
            if name.startswith("Api::") or (parent or "").endswith("API"):
                tags.append("api")
            # Rails 8's generated auth is opt-out: a controller is authenticated
            # unless it explicitly allows unauthenticated access.
            if re.search(r"allow_unauthenticated_access", src) or re.search(
                r"skip_before_action\s+:(authenticate|require_authentication)", src
            ):
                tags.append("public")
            else:
                tags.append("authenticated")
            if re.search(r"\bauthorize\b|\bcan\?|\bpolicy\b|\bpundit\b", src):
                tags.append("authorized")
        if node_type == "model":
            if re.search(r"broadcasts?(_to|_refreshes|_replace_to|_append_to)?\b", src):
                tags.append("broadcasts")
            if re.search(r"\bdiscard\b|deleted_at|\bacts_as_paranoid\b", src):
                tags.append("soft-deleted")
        if node_type == "job":
            queue = re.search(r"queue_as\s+:?['\"]?([a-z0-9_]+)", src)
            if queue:
                tags.append("queue:" + queue.group(1))
        if re.search(r"Current\.(account|organization|organisation|tenant|company|workspace)", src):
            tags.append("tenant-scoped")
        return tags

    def scan_model(self, name: str, src: str, parent: str | None) -> None:
        record = parent in (None, "ApplicationRecord") or (parent or "").startswith("ActiveRecord")
        if record and parent is not None:
            explicit = re.search(r"self\.table_name\s*=\s*['\"]([a-z0-9_]+)['\"]", src)
            table = explicit.group(1) if explicit else tableize(name)
            if table in self.table_names:
                self.add_edge(name, table, "persists")
            else:
                self.add_node(table, "table", None, loc=0, tags=["not-in-schema"])
                self.add_edge(name, table, "persists")
        for macro, target_name, options in re.findall(
            r"^\s*(belongs_to|has_many|has_one|has_and_belongs_to_many)\s+:([a-z0-9_]+)(.*)$",
            src, re.M,
        ):
            explicit = re.search(r"class_name:\s*['\"]([\w:]+)['\"]", options)
            if explicit:
                target = explicit.group(1)
            elif macro in ("has_many", "has_and_belongs_to_many"):
                target = camelize(singularize(target_name))
            else:
                target = camelize(target_name)
            through = re.search(r"through:\s*:([a-z0-9_]+)", options)
            kind = "has_many" if macro == "has_and_belongs_to_many" else macro
            self.add_edge(name, target, kind)
            if through:
                self.add_edge(name, camelize(singularize(through.group(1))), "has_many")

    def scan_controller(self, name: str, src: str) -> None:
        bodies = method_bodies(src)
        actions = [b for b in bodies if b["visibility"] == "public" and not b["singleton"]]
        privates = {b["name"]: b["body"] for b in bodies if b["visibility"] != "public"}
        before_actions = re.findall(
            r"^\s*before_action\s+:([a-z0-9_]+[?!]?)(.*)$", src, re.M
        )
        allow_unauth = re.search(r"^\s*allow_unauthenticated_access(.*)$", src, re.M)
        self.controller_actions[name] = {
            "actions": {b["name"]: b["body"] for b in actions},
            "order": [b["name"] for b in actions],
            "privates": privates,
            "before_actions": before_actions,
            "allow_unauth": allow_unauth.group(1) if allow_unauth else None,
            "src": src,
        }

    def scan_views(self) -> None:
        """Views are not nodes; their structural content is attributed to the
        controller that renders them (app/views/invoices/* -> InvoicesController)
        or to the component that owns the template."""
        for path in walk(self.root, "app/views", (".erb", ".haml", ".slim")):
            rel_path = self.rel(path)
            parts = rel_path.split("/")
            if len(parts) < 3:
                continue
            owner_dir = "/".join(parts[2:-1])
            if not owner_dir or owner_dir in ("layouts", "shared", "application"):
                owner = "ApplicationController"
            else:
                owner = camelize(owner_dir) + "Controller"
            if owner not in self.nodes:
                continue
            self.scan_markup(owner, read_text(path))
        for path in walk(self.root, "app/components", (".erb", ".haml", ".slim")):
            rel_path = self.rel(path)
            owner = class_name_from_path(self.root, re.sub(r"\.html\..*$", ".rb", path), "app/components")
            owner = re.sub(r"(\.|_)?[Hh]tml.*$", "", owner)
            if owner in self.nodes:
                self.scan_markup(owner, read_text(path))

    def scan_markup(self, owner: str, markup: str) -> None:
        for match in re.finditer(r'data-controller=["\']([^"\']+)["\']', markup):
            for identifier in match.group(1).split():
                if identifier in self.stimulus_ids:
                    self.add_edge(owner, identifier, "renders")
        for match in re.finditer(r'controller:\s*["\']([^"\']+)["\']', markup):
            for identifier in match.group(1).split():
                if identifier in self.stimulus_ids:
                    self.add_edge(owner, identifier, "renders")
        for match in re.finditer(r"render\s+\(?([A-Z][\w:]*(?:Component))\b", markup):
            self.add_edge(owner, match.group(1), "renders")
        if re.search(r"turbo_stream|turbo_frame_tag", markup):
            self.add_node("turbo_stream", "turbo", None)
            self.add_edge(owner, "turbo_stream", "renders")

    def resolve_edges(self) -> None:
        """Second pass: constant references only become edges once every node is
        known, so a forward reference is not silently dropped."""
        known = set(self.nodes)
        for name, info in sorted(self.sources.items()):
            src = info["src"]
            for match in re.finditer(
                r"\b([A-Z][\w:]*(?:Job|Mailer))\s*(?:\.|\n)", src
            ):
                target = match.group(1)
                if target == name or target not in known:
                    continue
                delivered = re.search(
                    re.escape(target) + r"[\s\S]{0,200}?(perform_later|perform_now|deliver_later|deliver_now)",
                    src,
                )
                self.add_edge(name, target, "enqueues" if delivered else "references")
            for match in re.finditer(r"^\s*include\s+([A-Z][\w:]*)", src, re.M):
                target = match.group(1)
                if target in known:
                    self.add_edge(name, target, "includes")
            for match in re.finditer(r"broadcast\w*_to\s+([^\n]+)", src):
                for const in CONST_RE.findall(match.group(1)):
                    if const in known and const != name:
                        self.add_edge(name, const, "broadcasts")
            if re.search(r"broadcast\w*(_to|_later_to)?\b", src):
                if info["type"] in ("model", "job", "service"):
                    self.add_node("turbo_stream", "turbo", None)
                    self.add_edge(name, "turbo_stream", "broadcasts")
            for match in re.finditer(r"render\s+\(?([A-Z][\w:]*Component)\b", src):
                if match.group(1) in known:
                    self.add_edge(name, match.group(1), "renders")
            for model, _ in current_chain_models(src, self.nodes):
                self.add_edge(name, model, "references")
            # Generic constant references, minus what a more specific kind claimed.
            for const in sorted(set(CONST_RE.findall(src))):
                if const == name or const not in known:
                    continue
                node_type = self.nodes[const]["type"]
                if node_type not in ("model", "service", "component", "concern"):
                    continue
                if any((name, const, kind) in self.edges for kind in
                       ("includes", "renders", "belongs_to", "has_many", "has_one", "persists")):
                    continue
                self.add_edge(name, const, "references")

    def add_routes(self, routes: list[dict]) -> None:
        for route in routes:
            route_id = f"{route['verb']} {route['path']}"
            controller = route["controller"]
            tags = [route["verb"].lower(), f"action:{route['action']}"]
            if controller in self.nodes:
                tags.extend(t for t in self.nodes[controller]["tags"]
                            if t in ("authenticated", "public", "admin", "api", "tenant-scoped"))
            self.add_node(route_id, "route",
                          self.nodes.get(controller, {}).get("file") or "config/routes.rb",
                          loc=0, tags=tags)
            if controller in self.nodes:
                self.add_edge(route_id, controller, "references")

    # -- flows -----------------------------------------------------------

    ACTION_PHRASE = {
        "index": "List {plural}",
        "show": "View {article} {singular}",
        "new": "New {singular} form",
        "edit": "Edit {article} {singular}",
        "create": "Create {article} {singular}",
        "update": "Update {article} {singular}",
        "destroy": "Delete {article} {singular}",
    }

    def flow_name(self, controller: str, action: str) -> str:
        stripped = re.sub(r"Controller$", "", controller)
        segments = stripped.split("::")
        subject = underscore(segments[-1]).replace("_", " ")
        singular = singularize(subject)
        template = self.ACTION_PHRASE.get(action)
        if template:
            name = template.format(plural=pluralize(singular), singular=singular,
                                   article=article(singular))
        else:
            # A custom action carries its own verb; forcing it into "<verb> a <noun>"
            # produces nonsense like "Pricing a marketing".
            name = f"{humanize(action)} ({singular})"
        # Namespace stays in the DISPLAY name: `Admin::InvoicesController#index` and
        # `InvoicesController#index` are different flows, and "List invoices" twice in
        # a release note tells a reviewer nothing about which one moved.
        if len(segments) > 1:
            namespace = "/".join(underscore(s).replace("_", " ") for s in segments[:-1])
            name = f"{name} ({namespace})"
        return name

    def describe_entry(self, controller: str, action: str, body: str) -> str:
        """Describe what the entry step actually does FOR THIS ACTION — every
        claim here is action-scoped, never a file-level summary."""
        info = self.controller_actions.get(controller, {})
        parts = []
        allow_unauth = info.get("allow_unauth")
        public = allow_unauth is not None and callback_applies(allow_unauth, action)
        if not public and "public" not in self.nodes.get(controller, {}).get("tags", []):
            parts.append("authenticate")
        callbacks = [(name, options) for name, options in info.get("before_actions", [])
                     if callback_applies(options, action)]
        if re.search(r"\bauthorize\b|\bcan\?", body) or any(
            re.search(r"authori[sz]e|\bpolicy\b", name) for name, _ in callbacks
        ):
            parts.append("authorise")
        loaders = [name for name, _ in callbacks
                   if name.startswith("set_") or name.startswith("load_")]
        if loaders:
            parts.append(loaders[0].replace("_", " "))
        if re.search(r"_params\b", body):
            parts.append("permit params")
        return " + ".join(parts) if parts else "handle the request"

    def model_step_verb(self, body: str, model: str) -> str | None:
        window = re.search(re.escape(model) + r"[\s\S]{0,120}", body)
        # No window means the caller passed a pre-sliced chain tail; use it whole.
        text = window.group(0) if window else body
        if re.search(r"\.(create|create!|new)\b", text) or re.search(r"\.save[!]?\b", body):
            return "validate, persist" + (" in a transaction" if "transaction" in body else "")
        if re.search(r"\.update[!]?\b", text) or re.search(r"\.update[!]?\b", body):
            return "validate, update" + (" in a transaction" if "transaction" in body else "")
        if re.search(r"\.destroy[!]?\b", text):
            return "delete"
        if re.search(r"\.(find|find_by|where|includes|order|all|first|last)\b", text):
            return "load records"
        return None

    def render_step(self, body: str) -> tuple[str, str] | None:
        if re.search(r"turbo_stream", body):
            actions = sorted(set(re.findall(
                r"turbo_stream\.(append|prepend|replace|update|remove|before|after)", body)))
            detail = ", ".join(actions) if actions else "stream the response"
            self.add_node("turbo_stream", "turbo", None)
            return "turbo_stream", detail
        redirect = re.search(r"redirect_to\s+([^\n,]+)", body)
        if redirect:
            flash = ", flash notice" if re.search(r"notice:|flash\[", body) else ""
            return None, "redirect" + flash
        render = re.search(r"render\s+:?['\"]?([a-z_]+)", body)
        if render:
            return None, f"render {render.group(1)}"
        return None, "render the default template"

    def build_flows(self, routes: list[dict]) -> None:
        candidates = []
        for route in routes:
            controller = route["controller"]
            info = self.controller_actions.get(controller)
            if not info:
                continue
            action = route["action"]
            body = info["actions"].get(action)
            if body is None:
                continue
            # Inline the private helpers this action actually reaches — those it
            # calls directly, plus the before_action callbacks that apply to it
            # (a `show` with an empty body still loads a record via set_invoice).
            expanded = body
            reachable = {helper for helper in info["privates"]
                         if re.search(r"\b" + re.escape(helper) + r"\b", body)}
            reachable |= {name for name, options in info["before_actions"]
                          if callback_applies(options, action)}
            for helper in sorted(reachable):
                helper_body = info["privates"].get(helper)
                if helper_body:
                    expanded += "\n" + helper_body

            steps = [{
                "node": f"{controller}#{action}",
                "does": self.describe_entry(controller, action, expanded),
            }]

            seen = set()
            for const in CONST_RE.findall(expanded):
                if const in seen or const not in self.nodes or const == controller:
                    continue
                node_type = self.nodes[const]["type"]
                if node_type == "model":
                    verb = self.model_step_verb(expanded, const)
                    if verb:
                        seen.add(const)
                        steps.append({"node": const, "does": verb})
                elif node_type == "service":
                    seen.add(const)
                    steps.append({"node": const, "does": f"run {const}"})
            # Models reached only through `Current.<scope>.<association>`, which
            # names no constant for the scan above to find.
            for model, tail in current_chain_models(expanded, self.nodes):
                if model in seen:
                    continue
                verb = self.model_step_verb(tail, model) or self.model_step_verb(expanded, model)
                if verb:
                    seen.add(model)
                    steps.append({"node": model, "does": verb})
            for const in CONST_RE.findall(expanded):
                if const in seen or const not in self.nodes:
                    continue
                node_type = self.nodes[const]["type"]
                if node_type == "job":
                    seen.add(const)
                    steps.append({"node": const, "does": "enqueue delivery"})
                elif node_type == "mailer":
                    seen.add(const)
                    steps.append({"node": const, "does": "deliver mail"})

            # A destroy/update acts on a loaded ivar, not on the constant, so the
            # verb above reads only the load. With a single model in play the
            # mutation is unambiguous — say both halves.
            model_steps = [s for s in steps
                           if self.nodes.get(s["node"], {}).get("type") == "model"]
            if len(model_steps) == 1:
                if action == "destroy" and re.search(r"@?\w+\.destroy[!]?\b", expanded):
                    model_steps[0]["does"] = "load, then delete"
                elif action == "update" and re.search(r"@?\w+\.update[!]?\b", expanded):
                    model_steps[0]["does"] = "load, then validate + update"

            rendered = self.render_step(expanded)
            if rendered:
                node_id, detail = rendered
                steps.append({"node": node_id or f"{controller}#{action}", "does": detail})

            if len(steps) < 2:
                continue
            trigger = f"{route['verb']} {route['path']}"
            candidates.append({
                # `id` is the IDENTITY (stable, unique); `name` is display text only.
                # Keying a delta by name silently drops a flow whenever two share one
                # — e.g. Admin::InvoicesController#index vs InvoicesController#index.
                "id": f"{trigger} -> {controller}#{action}",
                "name": self.flow_name(controller, action),
                "trigger": trigger,
                "entry": controller,
                "action": action,
                "steps": steps,
            })

        candidates.sort(key=lambda f: (f["trigger"], f["id"]))
        if len(candidates) > self.max_flows:
            dropped = len(candidates) - self.max_flows
            self.notes.append(
                f"{dropped} flow(s) beyond --max-flows={self.max_flows} were not emitted "
                "(raise the cap to include them)."
            )
            candidates = candidates[: self.max_flows]
        self.flows = candidates

    # -- assembly --------------------------------------------------------

    def result(self) -> dict:
        nodes = sorted(self.nodes.values(), key=lambda n: (LAYER_ORDER.index(n["layer"]), n["type"], n["id"]))
        edges = sorted(self.edges.values(), key=lambda e: (e["from"], e["kind"], e["to"]))
        return {"nodes": nodes, "edges": edges, "flows": self.flows, "notes": sorted(self.notes)}


def content_digest(core: dict) -> str:
    payload = json.dumps(
        {"nodes": core["nodes"], "edges": core["edges"], "flows": core["flows"],
         "notes": core["notes"]},
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


DEFAULT_MAX_FLOWS = 80


def check_cap(committed: dict | None, requested: int | None, default: int) -> int:
    """The flow cap a run should build with (#836).

    An explicit `--max-flows` always wins. Otherwise `--check` rebuilds with the cap the COMMITTED
    graph records, because comparing a graph built at 200 against a rebuild at 80 reports drift on
    every run with nothing in the tree having changed -- the truncation note sits inside the digest.
    A graph from before the cap was recorded, or no graph at all, gets the default.
    """
    if requested is not None:
        return requested
    if committed is not None and isinstance(committed.get("max_flows"), int):
        return committed["max_flows"]
    return default


def build_graph(root: str, max_flows: int) -> dict:
    core = GraphBuilder(root, max_flows).build()
    by_layer: dict[str, int] = {}
    by_type: dict[str, int] = {}
    for node in core["nodes"]:
        by_layer[node["layer"]] = by_layer.get(node["layer"], 0) + 1
        by_type[node["type"]] = by_type.get(node["type"], 0) + 1
    graph = {
        "schema": SCHEMA,
        "generator": GENERATOR,
        "generated_at": os.environ.get("RAILS_FLOW_GRAPH_NOW")
        or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "commit": git_output(root, ["rev-parse", "--short", "HEAD"]) or "unknown",
        "content_digest": content_digest(core),
        # The cap the graph was built with (#836). OUTSIDE the digest, which covers only nodes,
        # edges, flows and notes -- but the truncation note IS in `notes`, so a graph built with
        # --max-flows 200 and re-checked at the default 80 differed forever. `--check` rebuilds
        # with this value unless told otherwise.
        "max_flows": max_flows,
        "stats": {
            "nodes": len(core["nodes"]),
            "edges": len(core["edges"]),
            "flows": len(core["flows"]),
            "by_layer": dict(sorted(by_layer.items())),
            "by_type": dict(sorted(by_type.items())),
        },
        "notes": core["notes"],
        "nodes": core["nodes"],
        "edges": core["edges"],
        "flows": core["flows"],
    }
    return graph


def enrich(graph: dict, root: str) -> None:
    """Fold a third-party graph tool's edges in — OUTSIDE the digest.

    graphify/code-review-graph output is machine-local and optional; letting it
    change the digest would make CI report drift on a teammate's machine for the
    absence of a tool. So it lands in its own block, and the schema is probed
    rather than trusted.
    """
    candidates = [
        ("graphify", os.path.join(root, "graphify-out", "graph.json")),
        ("code-review-graph", os.path.join(root, ".code-review-graph", "graph.json")),
    ]
    for source, path in candidates:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            graph.setdefault("notes", []).append(
                f"enrichment: {source} output at {os.path.relpath(path, root)} was unreadable; skipped."
            )
            continue
        raw_edges = data.get("edges") if isinstance(data, dict) else None
        if not isinstance(raw_edges, list):
            graph.setdefault("notes", []).append(
                f"enrichment: {source} output did not match the expected "
                "{nodes, edges} shape; skipped rather than guessed."
            )
            continue
        known = {node["id"] for node in graph["nodes"]}
        # Built once: rebuilding it per candidate edge is O(base x enriched).
        base_keys = {(e["from"], e["to"], e["kind"]) for e in graph["edges"]}
        seen: set[tuple[str, str, str]] = set()
        matched, unmatched = [], 0
        for edge in raw_edges:
            if not isinstance(edge, dict):
                continue
            source_id = edge.get("from") or edge.get("source")
            target_id = edge.get("to") or edge.get("target")
            kind = str(edge.get("kind") or edge.get("type") or "references")
            if source_id in known and target_id in known:
                key = (source_id, target_id, kind)
                if key not in base_keys and key not in seen:
                    seen.add(key)
                    matched.append({"from": source_id, "to": target_id, "kind": kind})
            else:
                unmatched += 1
        graph["enrichment"] = {
            "source": source,
            "note": "excluded from content_digest — machine-local and optional",
            "edges": sorted(matched, key=lambda e: (e["from"], e["kind"], e["to"])),
            "unmatched_endpoints": unmatched,
        }
        return


# --------------------------------------------------------------------------
# mermaid view
# --------------------------------------------------------------------------

MERMAID_SHAPE = {
    "controller": ("[", "]"),
    "route": ("([", "])"),
    "model": ("(", ")"),
    "table": ("[(", ")]"),
    "job": ("{{", "}}"),
    "mailer": ("{{", "}}"),
    "service": ("[/", "/]"),
    "concern": ("[/", "/]"),
    "component": ("[", "]"),
    "stimulus": (">", "]"),
    "channel": ("([", "])"),
    "turbo": (">", "]"),
}


def mermaid_id(node_id: str) -> str:
    return "n" + re.sub(r"[^A-Za-z0-9]", "_", node_id)


def mermaid_label(node_id: str) -> str:
    return node_id.replace('"', "'")


def render_mermaid(graph: dict, max_nodes: int, max_flows: int) -> str:
    degree: dict[str, int] = {node["id"]: 0 for node in graph["nodes"]}
    for edge in graph["edges"]:
        if edge["from"] in degree:
            degree[edge["from"]] += 1
        if edge["to"] in degree:
            degree[edge["to"]] += 1

    nodes = graph["nodes"]
    truncated = 0
    if len(nodes) > max_nodes:
        ranked = sorted(nodes, key=lambda n: (-degree.get(n["id"], 0), n["type"], n["id"]))
        kept = {n["id"] for n in ranked[:max_nodes]}
        truncated = len(nodes) - max_nodes
        nodes = [n for n in graph["nodes"] if n["id"] in kept]
    else:
        kept = {n["id"] for n in nodes}

    lines = [
        "<!-- Generated by rails-flow architecture_graph.py — do not edit by hand. -->",
        "# Architecture",
        "",
        f"`{graph['commit']}` · generated {graph['generated_at']} · "
        f"{graph['stats']['nodes']} nodes · {graph['stats']['edges']} edges · "
        f"{graph['stats']['flows']} flows",
        "",
        "Interactive view: [`index.html`](index.html) (open from disk — no server, no network).",
        "Machine-readable: [`graph.json`](graph.json).",
        "",
        "## Structure",
        "",
    ]
    if truncated:
        lines += [
            f"> Showing the {max_nodes} most-connected nodes; **{truncated} lower-degree "
            f"node(s) are omitted from this diagram** (all are present in `graph.json`).",
            "",
        ]
    lines += ["```mermaid", "flowchart LR"]
    for layer in LAYER_ORDER:
        layer_nodes = [n for n in nodes if n["layer"] == layer]
        if not layer_nodes:
            continue
        lines.append(f'  subgraph {layer}["{layer}"]')
        for node in layer_nodes:
            open_shape, close_shape = MERMAID_SHAPE.get(node["type"], ("[", "]"))
            lines.append(
                f'    {mermaid_id(node["id"])}{open_shape}"{mermaid_label(node["id"])}"{close_shape}'
            )
        lines.append("  end")
    for edge in graph["edges"]:
        if edge["from"] not in kept or edge["to"] not in kept:
            continue
        lines.append(
            f'  {mermaid_id(edge["from"])} -->|{edge["kind"]}| {mermaid_id(edge["to"])}'
        )
    lines += ["```", ""]

    flows = graph["flows"][:max_flows]
    if flows:
        lines += ["## Flows", ""]
        if len(graph["flows"]) > len(flows):
            lines += [
                f"> {len(graph['flows']) - len(flows)} further flow(s) are in `graph.json` "
                "but not drawn here.",
                "",
            ]
        for flow in flows:
            lines += [f"### {flow['name']}", "", f"`{flow['trigger']}`", "", "```mermaid",
                      "flowchart LR"]
            previous = None
            for index, step in enumerate(flow["steps"]):
                step_id = f"s{index}"
                label = mermaid_label(step["node"])
                detail = mermaid_label(step["does"])
                lines.append(f'  {step_id}["{label}<br/><small>{detail}</small>"]')
                if previous:
                    lines.append(f"  {previous} --> {step_id}")
                previous = step_id
            lines += ["```", ""]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# HTML view — self-contained by decision (issue #141): no CDN, no webfont,
# no remote image, no fetch. Verifiable: open with the network disabled.
# --------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
/* Fidara dark palette, copied as LITERAL values on purpose: this file is a
   standalone artefact outside any app build, so it cannot read the `@theme`
   tokens in app/assets/tailwind/application.css. Source of truth for these
   values: skills/design-system/references/foundations-tokens.md (.dark roles).
   One deliberate deviation: --ring lifts to electric, because cerulean at 30%
   is not a legible focus ring on a navy surface. */
:root {
  --bg: #0C1B33;          /* fm-navy      */
  --surface: #1A2B45;     /* fm-ink       */
  --raised: #152238;      /* fm-midnight  */
  --fg: #F8F9FB;          /* slate-50     */
  --muted-fg: #8F96A3;    /* slate-400    */
  --border: #1C2531;      /* slate-800    */
  --primary: #00A3FF;     /* fm-electric  */
  --ring: #00A3FF;
  --web: #00A3FF;         /* fm-electric  */
  --domain: #00D4FF;      /* fm-cyan      */
  --async: #FF6B35;       /* fm-orange    */
  --ui: #22C55E;          /* fm-success   */
  --mono: "Overpass Mono", ui-monospace, SFMono-Regular, Menlo, monospace;
  --sans: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg); font-family: var(--sans);
  /* rem, not px: a px base overrides the reader's browser font-size preference.
     Every size below is rem for the same reason. */
  font-size: 1rem; line-height: 1.5;
}
a { color: var(--primary); }
header {
  padding: 1.25rem 1.5rem; border-bottom: 1px solid var(--border);
  display: flex; flex-wrap: wrap; gap: 0.75rem 1.5rem; align-items: baseline;
}
header h1 { font-size: 1.125rem; margin: 0; font-weight: 600; letter-spacing: -0.01em; }
header .meta { color: var(--muted-fg); font-family: var(--mono); font-size: 0.8125rem; }
/* the diagram (#850) */
.diagram { border-bottom: 1px solid var(--border); padding: 0.75rem 1.5rem 1rem; }
.diagram-bar { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; align-items: baseline; margin-bottom: 0.5rem; }
.legend { display: inline-flex; gap: 0.75rem; font-size: 0.75rem; color: var(--muted-fg); }
.legend .sw { display: inline-block; width: 0.625rem; height: 0.625rem; border-radius: 2px; margin-right: 0.3rem; vertical-align: -1px; }
.legend .web { background: var(--web); } .legend .domain { background: var(--domain); }
.legend .async { background: var(--async); } .legend .ui { background: var(--ui); }
.diagram-scroll { overflow: auto; max-height: 60vh; border: 1px solid var(--border); border-radius: 10px; background: var(--raised); }
svg.arch { display: block; }
svg.arch .col-title { fill: var(--muted-fg); font: 0.6875rem var(--sans); text-transform: uppercase; letter-spacing: 0.06em; }
svg.arch .node rect { fill: var(--surface); stroke: var(--border); stroke-width: 1.25; }
svg.arch .node text { fill: var(--fg); font: 0.75rem var(--mono); pointer-events: none; }
svg.arch .node { cursor: pointer; }
svg.arch .node.layer-web rect { stroke: var(--web); } svg.arch .node.layer-domain rect { stroke: var(--domain); }
svg.arch .node.layer-async rect { stroke: var(--async); } svg.arch .node.layer-ui rect { stroke: var(--ui); }
svg.arch .node:focus-visible { outline: none; } svg.arch .node:focus-visible rect { stroke: var(--ring); stroke-width: 2.5; }
svg.arch .node.sel rect { stroke: var(--primary); stroke-width: 2.5; fill: var(--bg); }
svg.arch .node.dim { opacity: 0.3; }
svg.arch .edge { fill: none; stroke: var(--muted-fg); stroke-opacity: 0.45; stroke-width: 1.25; }
svg.arch .edge.on { stroke: var(--primary); stroke-opacity: 1; stroke-width: 2; }
svg.arch .edge.dim { stroke-opacity: 0.08; }
.layout { display: grid; grid-template-columns: minmax(280px, 24rem) 1fr; min-height: calc(100vh - 5rem); }
.sidebar { border-right: 1px solid var(--border); padding: 1rem; overflow-y: auto; max-height: calc(100vh - 5rem); }
.detail { padding: 1.5rem; overflow-y: auto; max-height: calc(100vh - 5rem); }
.controls { display: flex; flex-direction: column; gap: 0.75rem; margin-bottom: 1rem; }
input[type="search"] {
  width: 100%; padding: 0.5rem 0.625rem; background: var(--raised); color: var(--fg);
  border: 1px solid var(--border); border-radius: 6px; font: inherit;
}
.chips { display: flex; flex-wrap: wrap; gap: 0.375rem; }
button {
  font: inherit; cursor: pointer; background: var(--raised); color: var(--fg);
  border: 1px solid var(--border); border-radius: 999px; padding: 0.25rem 0.625rem;
  font-size: 0.8125rem;
}
button[aria-pressed="true"] { background: var(--primary); color: #052134; border-color: var(--primary); font-weight: 600; }
:focus-visible { outline: 2px solid var(--ring); outline-offset: 2px; }
.tabs { display: flex; gap: 0.375rem; margin-bottom: 0.75rem; }
ul.list { list-style: none; margin: 0; padding: 0; }
ul.list li { margin-bottom: 2px; }
ul.list button.row {
  width: 100%; text-align: left; border-radius: 6px; border: 1px solid transparent;
  background: none; padding: 0.375rem 0.5rem; display: flex; gap: 0.5rem; align-items: center;
}
ul.list button.row:hover { background: var(--raised); }
ul.list button.row[aria-current="true"] { background: var(--raised); border-color: var(--primary); }
.badge {
  font-family: var(--mono); font-size: 0.6875rem; text-transform: uppercase;
  border: 1px solid currentColor; border-radius: 4px; padding: 0 0.25rem; flex: none;
}
.badge.web { color: var(--web); } .badge.domain { color: var(--domain); }
.badge.async { color: var(--async); } .badge.ui { color: var(--ui); }
.row .name { font-family: var(--mono); font-size: 0.8125rem; overflow-wrap: anywhere; }
.row .kind { color: var(--muted-fg); font-size: 0.75rem; margin-left: auto; flex: none; }
.detail h2 { margin: 0 0 0.25rem; font-family: var(--mono); font-size: 1.0625rem; overflow-wrap: anywhere; }
.detail .sub { color: var(--muted-fg); font-size: 0.8125rem; margin-bottom: 1.25rem; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 1rem 1.125rem; margin-bottom: 1rem; }
.card h3 { margin: 0 0 0.625rem; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--muted-fg); }
dl.kv { margin: 0; display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 1rem; }
dl.kv dt { color: var(--muted-fg); font-size: 0.8125rem; }
dl.kv dd { margin: 0; font-family: var(--mono); font-size: 0.8125rem; overflow-wrap: anywhere; }
.edge { display: flex; gap: 0.5rem; align-items: baseline; padding: 0.1875rem 0; }
.edge .k { font-family: var(--mono); font-size: 0.6875rem; color: var(--muted-fg); min-width: 6.5rem; }
.linkish { background: none; border: none; color: var(--primary); padding: 0; font-family: var(--mono); font-size: 0.8125rem; text-align: left; }
ol.steps { margin: 0; padding-left: 1.25rem; }
ol.steps li { margin-bottom: 0.5rem; }
ol.steps .does { color: var(--muted-fg); font-size: 0.8125rem; }
.tag { font-family: var(--mono); font-size: 0.6875rem; background: var(--raised); border: 1px solid var(--border); border-radius: 4px; padding: 0 0.3125rem; margin-right: 0.25rem; }
.empty { color: var(--muted-fg); font-size: 0.875rem; }
.notes { border-left: 2px solid var(--async); padding-left: 0.75rem; color: var(--muted-fg); font-size: 0.8125rem; }
kbd { font-family: var(--mono); font-size: 0.75rem; border: 1px solid var(--border); border-radius: 4px; padding: 0 0.25rem; }
@media (prefers-reduced-motion: no-preference) {
  ul.list button.row, button { transition: background-color 120ms ease, border-color 120ms ease; }
}
/* Touch targets: 44px on EVERY interactive control, unconditionally — matching
   min-h-touch in the design system, which applies it in the class list rather than
   behind a pointer query (22 of its 23 usages are unconditional, including
   list-shaped things like menu items and nav links). An earlier revision gated this
   on `pointer: coarse` to keep the node list dense on a desktop; that was a
   deviation from house practice dressed up as a judgment call, so it is gone. */
button, ul.list button.row, input[type="search"] { min-height: 44px; }
.linkish { min-height: 44px; display: inline-flex; align-items: center; }
@media (max-width: 860px) {
  .layout { grid-template-columns: 1fr; }
  .sidebar { border-right: none; border-bottom: 1px solid var(--border); max-height: none; }
  .detail { max-height: none; }
}
@media print {
  :root { --bg: #fff; --surface: #fff; --raised: #fff; --fg: #000; --muted-fg: #444; --border: #999; }
  .sidebar { display: none; }
  .layout { display: block; }
  .detail { max-height: none; overflow: visible; }
  .print-only { display: block !important; }
}
.print-only { display: none; }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <span class="meta">__COMMIT__ · __GENERATED__</span>
  <span class="meta">__STATS__</span>
</header>

<section class="diagram" aria-label="Architecture diagram">
  <div class="diagram-bar">
    <span class="meta">Columns are layers, left to right in request order. Click a node to trace its edges, or pick a flow below to light its path.</span>
    <span class="legend"><span><i class="sw web"></i>web</span><span><i class="sw domain"></i>domain</span><span><i class="sw async"></i>async</span><span><i class="sw ui"></i>ui</span></span>
  </div>
  <div class="diagram-scroll">__SVG__</div>
</section>

<div class="layout">
  <nav class="sidebar" aria-label="Graph index">
    <div class="controls">
      <div class="tabs" role="tablist" aria-label="View">
        <button id="tab-nodes" role="tab" aria-pressed="true" aria-controls="panel-list">Nodes</button>
        <button id="tab-flows" role="tab" aria-pressed="false" aria-controls="panel-list">Flows</button>
      </div>
      <label for="q" class="meta">Search <kbd>/</kbd></label>
      <input id="q" type="search" placeholder="name, file, layer…" autocomplete="off">
      <div class="chips" id="layers" role="group" aria-label="Filter by layer"></div>
    </div>
    <ul class="list" id="panel-list"></ul>
    <p class="empty" id="count"></p>
    <div id="notes"></div>
  </nav>

  <main class="detail" id="detail" tabindex="-1" aria-live="polite">
    <p class="empty">Select a node or a flow.</p>
  </main>
</div>

<script type="application/json" id="graph-data">__GRAPH_JSON__</script>
<script>
(function () {
  "use strict";
  var GRAPH = JSON.parse(document.getElementById("graph-data").textContent);
  var byId = {};
  GRAPH.nodes.forEach(function (n) { byId[n.id] = n; });

  var out = {}, incoming = {};
  GRAPH.edges.forEach(function (e) {
    (out[e.from] = out[e.from] || []).push(e);
    (incoming[e.to] = incoming[e.to] || []).push(e);
  });
  (GRAPH.enrichment && GRAPH.enrichment.edges ? GRAPH.enrichment.edges : []).forEach(function (e) {
    e.enriched = true;
    (out[e.from] = out[e.from] || []).push(e);
    (incoming[e.to] = incoming[e.to] || []).push(e);
  });

  var flowsByNode = {};
  GRAPH.flows.forEach(function (f, i) {
    f.steps.forEach(function (s) {
      var id = s.node.split("#")[0];
      var key = byId[s.node] ? s.node : id;
      (flowsByNode[key] = flowsByNode[key] || []).push(i);
    });
  });

  var LAYERS = ["web", "domain", "async", "ui"];
  var state = { mode: "nodes", query: "", layers: {}, selected: null };
  LAYERS.forEach(function (l) { state.layers[l] = true; });

  var listEl = document.getElementById("panel-list");
  var countEl = document.getElementById("count");
  var detailEl = document.getElementById("detail");
  var queryEl = document.getElementById("q");

  var chips = document.getElementById("layers");
  LAYERS.forEach(function (layer) {
    var b = document.createElement("button");
    b.textContent = layer;
    b.setAttribute("aria-pressed", "true");
    b.addEventListener("click", function () {
      state.layers[layer] = !state.layers[layer];
      b.setAttribute("aria-pressed", String(state.layers[layer]));
      render();
    });
    chips.appendChild(b);
  });

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function matches(node) {
    if (!state.layers[node.layer]) return false;
    if (!state.query) return true;
    var q = state.query.toLowerCase();
    return (node.id + " " + node.type + " " + node.layer + " " + (node.file || "") + " " +
            node.tags.join(" ")).toLowerCase().indexOf(q) !== -1;
  }

  function flowMatches(flow) {
    if (!state.query) return true;
    var q = state.query.toLowerCase();
    return (flow.name + " " + flow.trigger + " " +
            flow.steps.map(function (s) { return s.node + " " + s.does; }).join(" ")
           ).toLowerCase().indexOf(q) !== -1;
  }

  function badge(layer) {
    var b = el("span", "badge " + layer, layer.charAt(0).toUpperCase());
    b.title = layer + " layer";
    b.setAttribute("aria-label", layer + " layer");
    return b;
  }

  function render() {
    listEl.innerHTML = "";
    var items = state.mode === "nodes"
      ? GRAPH.nodes.filter(matches)
      : GRAPH.flows.filter(flowMatches);

    items.forEach(function (item, index) {
      var li = el("li");
      var b = el("button", "row");
      b.type = "button";
      if (state.mode === "nodes") {
        b.appendChild(badge(item.layer));
        b.appendChild(el("span", "name", item.id));
        b.appendChild(el("span", "kind", item.type));
        b.setAttribute("aria-current", String(state.selected === item.id));
        b.addEventListener("click", function () { selectNode(item.id); });
      } else {
        b.appendChild(el("span", "name", item.name));
        b.appendChild(el("span", "kind", item.trigger));
        b.addEventListener("click", function () { selectFlow(GRAPH.flows.indexOf(item)); });
      }
      b.dataset.index = String(index);
      li.appendChild(b);
      listEl.appendChild(li);
    });

    countEl.textContent = items.length + " " + state.mode +
      (state.mode === "nodes" ? " of " + GRAPH.nodes.length : " of " + GRAPH.flows.length);
  }

  function edgeList(edges, direction) {
    if (!edges || !edges.length) return el("p", "empty", "none");
    var wrap = el("div");
    edges.slice().sort(function (a, b) {
      return (a.kind + a.to + a.from).localeCompare(b.kind + b.to + b.from);
    }).forEach(function (e) {
      var row = el("div", "edge");
      row.appendChild(el("span", "k", e.kind + (e.enriched ? " *" : "")));
      var other = direction === "out" ? e.to : e.from;
      if (byId[other]) {
        var link = el("button", "linkish", other);
        link.type = "button";
        link.addEventListener("click", function () { selectNode(other); });
        row.appendChild(link);
      } else {
        row.appendChild(el("span", "name", other));
      }
      wrap.appendChild(row);
    });
    return wrap;
  }

  // The diagram (#850): the same selection the list drives, painted onto the SVG.
  var svg = document.querySelector("svg.arch");
  function paintNode(id) {
    if (!svg) return;
    svg.querySelectorAll(".node").forEach(function (g) {
      g.classList.toggle("sel", g.dataset.id === id); g.classList.remove("dim");
    });
    svg.querySelectorAll(".edge").forEach(function (p) {
      var touches = p.dataset.from === id || p.dataset.to === id;
      p.classList.toggle("on", touches); p.classList.toggle("dim", !touches);
    });
    var g = svg.querySelector('.node[data-id="' + id.replace(/"/g, '\\"') + '"]');
    if (g && g.scrollIntoView) g.scrollIntoView({ block: "nearest", inline: "nearest" });
  }
  function paintFlow(flow) {
    if (!svg) return;
    var ids = {}; ids[flow.entry] = true;
    flow.steps.forEach(function (s) { ids[s.node] = true; });
    svg.querySelectorAll(".node").forEach(function (g) {
      var on = !!ids[g.dataset.id]; g.classList.toggle("sel", on); g.classList.toggle("dim", !on);
    });
    svg.querySelectorAll(".edge").forEach(function (p) {
      var on = !!(ids[p.dataset.from] && ids[p.dataset.to]); p.classList.toggle("on", on); p.classList.toggle("dim", !on);
    });
  }
  if (svg) {
    svg.addEventListener("click", function (ev) {
      var g = ev.target.closest(".node"); if (g) selectNode(g.dataset.id);
    });
    svg.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" && ev.key !== " ") return;
      var g = ev.target.closest(".node"); if (g) { ev.preventDefault(); selectNode(g.dataset.id); }
    });
  }

  function selectNode(id) {
    var node = byId[id];
    if (!node) return;
    paintNode(id);
    state.selected = id;
    state.mode = "nodes";
    syncTabs();
    detailEl.innerHTML = "";
    detailEl.appendChild(el("h2", null, node.id));
    // Layer is always stated as TEXT here, never colour alone.
    detailEl.appendChild(el("p", "sub", node.type + " · " + node.layer + " layer"));

    var facts = el("div", "card");
    facts.appendChild(el("h3", null, "Facts"));
    var dl = el("dl", "kv");
    dl.appendChild(el("dt", null, "file"));
    dl.appendChild(el("dd", null, node.file || "—"));
    dl.appendChild(el("dt", null, "lines"));
    dl.appendChild(el("dd", null, node.loc ? String(node.loc) : "—"));
    dl.appendChild(el("dt", null, "tags"));
    var tags = el("dd");
    if (node.tags.length) {
      node.tags.forEach(function (t) { tags.appendChild(el("span", "tag", t)); });
    } else { tags.textContent = "—"; }
    dl.appendChild(tags);
    facts.appendChild(dl);
    detailEl.appendChild(facts);

    var o = el("div", "card");
    o.appendChild(el("h3", null, "Depends on (outgoing)"));
    o.appendChild(edgeList(out[node.id], "out"));
    detailEl.appendChild(o);

    var i = el("div", "card");
    i.appendChild(el("h3", null, "Depended on by (incoming — blast radius)"));
    i.appendChild(edgeList(incoming[node.id], "in"));
    detailEl.appendChild(i);

    var related = [];
    Object.keys(flowsByNode).forEach(function (key) {
      if (key === node.id || key.split("#")[0] === node.id) {
        flowsByNode[key].forEach(function (index) {
          if (related.indexOf(index) === -1) related.push(index);
        });
      }
    });
    var f = el("div", "card");
    f.appendChild(el("h3", null, "Flows it participates in"));
    if (!related.length) {
      f.appendChild(el("p", "empty", "none"));
    } else {
      var ul = el("ul", "list");
      related.sort().forEach(function (index) {
        var li = el("li");
        var b = el("button", "linkish", GRAPH.flows[index].name + " — " + GRAPH.flows[index].trigger);
        b.type = "button";
        b.addEventListener("click", function () { selectFlow(index); });
        li.appendChild(b);
        ul.appendChild(li);
      });
      f.appendChild(ul);
    }
    detailEl.appendChild(f);
    render();
  }

  function selectFlow(index) {
    var flow = GRAPH.flows[index];
    if (!flow) return;
    paintFlow(flow);
    state.mode = "flows";
    state.selected = null;
    syncTabs();
    detailEl.innerHTML = "";
    detailEl.appendChild(el("h2", null, flow.name));
    detailEl.appendChild(el("p", "sub", "flow · trigger " + flow.trigger));
    var card = el("div", "card");
    card.appendChild(el("h3", null, "Steps"));
    var ol = el("ol", "steps");
    flow.steps.forEach(function (step) {
      var li = el("li");
      var target = byId[step.node] ? step.node : step.node.split("#")[0];
      if (byId[target]) {
        var b = el("button", "linkish", step.node);
        b.type = "button";
        b.addEventListener("click", function () { selectNode(target); });
        li.appendChild(b);
      } else {
        li.appendChild(el("span", "name", step.node));
      }
      li.appendChild(el("div", "does", step.does));
      ol.appendChild(li);
    });
    card.appendChild(ol);
    detailEl.appendChild(card);
    render();
  }

  function syncTabs() {
    document.getElementById("tab-nodes").setAttribute("aria-pressed", String(state.mode === "nodes"));
    document.getElementById("tab-flows").setAttribute("aria-pressed", String(state.mode === "flows"));
  }

  document.getElementById("tab-nodes").addEventListener("click", function () {
    state.mode = "nodes"; syncTabs(); render();
  });
  document.getElementById("tab-flows").addEventListener("click", function () {
    state.mode = "flows"; syncTabs(); render();
  });
  queryEl.addEventListener("input", function () { state.query = queryEl.value; render(); });

  document.addEventListener("keydown", function (event) {
    if (event.key === "/" && event.target !== queryEl) {
      event.preventDefault();
      queryEl.focus();
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    var rows = Array.prototype.slice.call(listEl.querySelectorAll("button.row"));
    if (!rows.length) return;
    var current = rows.indexOf(document.activeElement);
    if (current === -1 && event.target !== queryEl) return;
    event.preventDefault();
    var next = event.key === "ArrowDown" ? current + 1 : current - 1;
    if (next < 0) next = 0;
    if (next >= rows.length) next = rows.length - 1;
    rows[next].focus();
  });

  // Notes live in the sidebar, not the detail pane: the detail pane is cleared on
  // every selection, and a stated limit of the extraction must not disappear the
  // moment someone clicks something.
  if (GRAPH.notes && GRAPH.notes.length) {
    var notes = el("div", "card");
    notes.appendChild(el("h3", null, "Extraction notes (" + GRAPH.notes.length + ")"));
    var wrap = el("div", "notes");
    GRAPH.notes.forEach(function (n) { wrap.appendChild(el("p", null, n)); });
    notes.appendChild(wrap);
    document.getElementById("notes").appendChild(notes);
  }

  render();
})();
</script>
</body>
</html>
"""


# --------------------------------------------------------------------------
# diagram (#850)
# --------------------------------------------------------------------------
# The page called itself an "interactive view" and drew nothing: zero SVG, zero canvas -- a styled
# list over the embedded JSON. The only picture was graph.md's mermaid, capped and rendered only
# where mermaid is supported. This draws the graph at generation time, in Python, as inline SVG:
# no library and no network, which the page's own header already promises. A layered layout --
# one column per layer in LAYER_ORDER, rows in the graph's own (layer, type, id) order -- is the
# honest shape for a Rails app: requests enter at the web layer and fan into domain, async, ui.
# It is deliberately not a force layout; a deterministic picture diffs, a physics one does not.
COL_W, ROW_H, NODE_W, NODE_H, MARGIN, HEADER_H = 300, 40, 220, 28, 24, 36


def layout(graph: dict) -> dict[str, tuple[int, int, int, int]]:
    """`{node_id: (column, row, x, y)}` -- every node placed exactly once, columns by layer."""
    next_row = {layer: 0 for layer in LAYER_ORDER}
    positions: dict[str, tuple[int, int, int, int]] = {}
    for node in graph["nodes"]:
        layer = node.get("layer") if node.get("layer") in next_row else "domain"
        col = LAYER_ORDER.index(layer)
        row = next_row[layer]
        next_row[layer] = row + 1
        positions[node["id"]] = (col, row, MARGIN + col * COL_W, MARGIN + HEADER_H + row * ROW_H)
    return positions


def _label(text: str, limit: int = 30) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def render_svg(graph: dict, positions: dict | None = None) -> str:
    """The diagram as one `<svg>` string. Everything user-derived is escaped: ids are file-derived."""
    pos = layout(graph) if positions is None else positions
    if not pos:
        return ('<svg class="arch" viewBox="0 0 480 60" width="480" height="60" role="img" '
                'aria-label="architecture diagram: no nodes">'
                '<text class="col-title" x="24" y="36">no nodes — the graph is empty</text></svg>')
    width = MARGIN * 2 + (len(LAYER_ORDER) - 1) * COL_W + NODE_W
    height = MARGIN * 2 + HEADER_H + max(p[1] for p in pos.values()) * ROW_H + NODE_H
    out = [f'<svg class="arch" viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
           f'aria-label="architecture diagram: {len(pos)} nodes in {len(LAYER_ORDER)} layers">', '<g class="cols">']
    for i, layer in enumerate(LAYER_ORDER):
        out.append(f'<text class="col-title" x="{MARGIN + i * COL_W}" y="{MARGIN + 14}">{html.escape(layer)}</text>')
    out.append('</g><g class="edges">')
    for e in graph["edges"]:  # every edge, drawn once
        a, b = pos.get(e["from"]), pos.get(e["to"])
        if not a or not b:
            continue  # an edge to a node outside the graph (an id collision, an enrichment) draws nothing
        x1, y1 = a[2] + NODE_W, a[3] + NODE_H // 2
        x2, y2 = b[2], b[3] + NODE_H // 2
        if b[0] > a[0]:
            # forward: leave the source's right edge, enter the target's left edge
            d = f"M{x1},{y1} C{x1 + COL_W // 3},{y1} {x2 - COL_W // 3},{y2} {x2},{y2}"
        else:
            # same column or backward: bow out to the right of the source and come back to the
            # target's right edge, so the path is visible instead of hidden behind the boxes
            bow = max(x1, b[2] + NODE_W) + 40
            d = f"M{x1},{y1} C{bow},{y1} {bow},{y2} {b[2] + NODE_W},{y2}"
        out.append(f'<path class="edge kind-{html.escape(e["kind"])}" data-from="{html.escape(e["from"])}" '
                   f'data-to="{html.escape(e["to"])}" d="{d}"><title>{html.escape(e["from"])} —{html.escape(e["kind"])}→ '
                   f'{html.escape(e["to"])}</title></path>')
    out.append('</g><g class="nodes">')
    for node in graph["nodes"]:
        p = pos[node["id"]]
        nid, ntype, nlayer = html.escape(node["id"]), html.escape(node["type"]), html.escape(node["layer"])
        out.append(f'<g class="node layer-{nlayer} type-{ntype}" data-id="{nid}" tabindex="0" role="button" '
                   f'aria-label="{nid} ({ntype})"><title>{nid} · {ntype}</title>'
                   f'<rect x="{p[2]}" y="{p[3]}" width="{NODE_W}" height="{NODE_H}" rx="6"/>'
                   f'<text x="{p[2] + 10}" y="{p[3] + NODE_H // 2 + 4}">{html.escape(_label(node["id"]))}</text></g>')
    out.append('</g></svg>')
    return "".join(out)


def render_html(graph: dict, title: str) -> str:
    # `</script>` and `<!--` inside the JSON would end the host element early;
    # escaping `<` at the unicode level keeps the payload valid JSON.
    payload = json.dumps(graph, sort_keys=True, separators=(",", ":")).replace("<", "\\u003c")
    stats = graph["stats"]
    summary = (
        f"{stats['nodes']} nodes · {stats['edges']} edges · {stats['flows']} flows"
    )
    return (
        HTML_TEMPLATE
        .replace("__SVG__", render_svg(graph))
        .replace("__GRAPH_JSON__", payload)
        .replace("__TITLE__", title)
        .replace("__COMMIT__", graph["commit"])
        .replace("__GENERATED__", graph["generated_at"])
        .replace("__STATS__", summary)
    )


# --------------------------------------------------------------------------
# delta (release notes)
# --------------------------------------------------------------------------

def flow_signature(flow: dict) -> str:
    return " → ".join(step["node"] for step in flow["steps"])


def flow_key(flow: dict) -> str:
    """Identity for set/dict operations across TWO graph versions.

    Deliberately derived from `trigger` + `entry` rather than read from `id`: a delta
    compares an older committed graph against a fresh build, so the key must be
    computable from fields both sides have and neither redefines. Keying on `id`
    breaks the moment `id`'s format changes; keying on `name` breaks when display
    text changes (adding the namespace suffix did exactly that) — either way every
    flow reads as simultaneously added and removed, which is worse than the
    duplicate-name bug this replaced. A trigger is one route, and each flow comes
    from exactly one route, so trigger+entry is both stable and unique.
    """
    trigger = flow.get("trigger")
    entry = flow.get("entry")
    if trigger and entry:
        return f"{trigger} -> {entry}"
    return flow.get("id") or trigger or flow.get("name", "")


def flow_label(flow: dict) -> str:
    """Display text. Carries the trigger so two same-named flows stay distinguishable."""
    name = flow.get("name") or flow_key(flow)
    trigger = flow.get("trigger")
    return f"{name} [{trigger}]" if trigger else name


def compute_delta(old: dict | None, new: dict) -> dict:
    if old is None:
        return {"first": True, "nodes_added": [], "nodes_removed": [],
                "flows_added": [], "flows_removed": [], "flows_changed": [],
                "edge_delta": len(new["edges"])}
    old_nodes = {n["id"]: n for n in old.get("nodes", [])}
    new_nodes = {n["id"]: n for n in new.get("nodes", [])}
    old_flows = {flow_key(f): f for f in old.get("flows", [])}
    new_flows = {flow_key(f): f for f in new.get("flows", [])}
    changed = []
    for key, flow in sorted(new_flows.items()):
        if key in old_flows and flow_signature(old_flows[key]) != flow_signature(flow):
            changed.append({
                "name": flow_label(flow),
                "before": flow_signature(old_flows[key]),
                "after": flow_signature(flow),
                "step_delta": len(flow["steps"]) - len(old_flows[key]["steps"]),
            })
    return {
        "first": False,
        "nodes_added": sorted(set(new_nodes) - set(old_nodes)),
        "nodes_removed": sorted(set(old_nodes) - set(new_nodes)),
        "flows_added": sorted(flow_label(new_flows[k]) for k in set(new_flows) - set(old_flows)),
        "flows_removed": sorted(flow_label(old_flows[k]) for k in set(old_flows) - set(new_flows)),
        "flows_changed": changed,
        "edge_delta": len(new.get("edges", [])) - len(old.get("edges", [])),
    }


def render_delta_markdown(delta: dict, new: dict) -> str:
    if delta["first"]:
        return (
            "### Architecture graph\n\n"
            f"First generation — {new['stats']['nodes']} nodes, "
            f"{new['stats']['edges']} edges, {new['stats']['flows']} flows.\n"
        )
    lines = ["### Architecture graph", ""]
    if not any([delta["nodes_added"], delta["nodes_removed"], delta["flows_added"],
                delta["flows_removed"], delta["flows_changed"], delta["edge_delta"]]):
        lines.append("No structural change.")
        return "\n".join(lines) + "\n"
    for label, key in (("New", "nodes_added"), ("Removed", "nodes_removed")):
        if delta[key]:
            lines.append(f"- **{label} nodes** ({len(delta[key])}): " +
                         ", ".join("`%s`" % n for n in delta[key][:20]) +
                         (" …" if len(delta[key]) > 20 else ""))
    if delta["flows_added"]:
        lines.append("- **New flows**: " + ", ".join("*%s*" % f for f in delta["flows_added"]))
    if delta["flows_removed"]:
        lines.append("- **Removed flows**: " + ", ".join("*%s*" % f for f in delta["flows_removed"]))
    for change in delta["flows_changed"]:
        direction = "gained" if change["step_delta"] > 0 else (
            "lost" if change["step_delta"] < 0 else "reshaped")
        count = abs(change["step_delta"])
        detail = f"{direction} {count} step(s)" if count else "reshaped"
        lines.append(f"- **Flow changed** — *{change['name']}* {detail}: "
                     f"`{change['before']}` → `{change['after']}`")
    if delta["edge_delta"]:
        sign = "+" if delta["edge_delta"] > 0 else ""
        lines.append(f"- **Edges**: {sign}{delta['edge_delta']}")
    return "\n".join(lines) + "\n"


def load_graph_at_ref(root: str, ref: str, rel_path: str) -> dict | None:
    raw = git_output(root, ["show", f"{ref}:{rel_path}"])
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


def load_graph_file(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def write_if_changed(path: str, content: str) -> bool:
    """Only touch the file when bytes differ — keeps `git status` honest and
    stops a no-op regeneration from looking like a change."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as handle:
            if handle.read() == content:
                return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    return True


def selftest() -> int:
    """The contract #836 fixed: the cap is recorded, --check rebuilds with it, the digest ignores it.

    This file had no test at all -- the second-largest script in the repo. These fixtures cover the
    one mechanism that was found broken; the graph builder itself is still exercised only by use.
    """
    import tempfile
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}" if detail else label)

    check("an explicit --max-flows wins over the committed cap", check_cap({"max_flows": 200}, 5, 80) == 5)
    check("--check rebuilds with the COMMITTED cap when none is given", check_cap({"max_flows": 200}, None, 80) == 200)
    check("a graph from before the cap was recorded gets the default", check_cap({"schema": 1}, None, 80) == 80)
    check("no committed graph at all gets the default", check_cap(None, None, 80) == 80)
    check("a non-integer recorded cap is ignored, not crashed on", check_cap({"max_flows": "200"}, None, 80) == 80)

    with tempfile.TemporaryDirectory() as td:
        g7 = build_graph(td, 7)
        g80 = build_graph(td, 80)
        check("the graph RECORDS the cap it was built with", g7.get("max_flows") == 7, f"got {g7.get('max_flows')!r}")
        check("...so --check can read it back", check_cap(g7, None, 80) == 7)
        check("the digest does not depend on the cap when nothing was truncated",
              g7["content_digest"] == g80["content_digest"])
        core = {k: g7[k] for k in ("nodes", "edges", "flows", "notes")}
        check("the digest is computed from the four core keys only -- the cap sits outside it",
              content_digest(core) == g7["content_digest"])

    # ---- THE DIAGRAM (#850) ---------------------------------------------------------------------
    # A synthetic graph, no Rails app: five nodes across all four layers, a forward edge, a backward
    # edge, an edge to a node the graph does not contain, and an id carrying `<` -- the escaping case.
    import re as _re
    import xml.etree.ElementTree as _ET
    g = {"nodes": [
            {"id": "InvoicesController", "type": "controller", "layer": "web", "file": "a", "loc": 1, "tags": []},
            {"id": "Invoice", "type": "model", "layer": "domain", "file": "b", "loc": 1, "tags": []},
            {"id": "Customer<Org>", "type": "model", "layer": "domain", "file": "c", "loc": 1, "tags": []},
            {"id": "InvoiceMailerJob", "type": "job", "layer": "async", "file": "d", "loc": 1, "tags": []},
            {"id": "Ui::Button", "type": "component", "layer": "ui", "file": "e", "loc": 1, "tags": []}],
         "edges": [{"from": "InvoicesController", "to": "Invoice", "kind": "references"},
                   {"from": "Invoice", "to": "Customer<Org>", "kind": "references"},
                   {"from": "InvoiceMailerJob", "to": "Invoice", "kind": "persists"},
                   {"from": "Invoice", "to": "Ghost", "kind": "references"}],
         "flows": [], "notes": [], "stats": {"nodes": 5, "edges": 4, "flows": 0},
         "commit": "abc1234", "generated_at": "2026-09-03T00:00:00Z"}
    pos = layout(g)
    check("the diagram places every node exactly once", set(pos) == {n["id"] for n in g["nodes"]}, f"{sorted(pos)}")
    check("columns follow LAYER_ORDER: x grows with the layer index",
          pos["InvoicesController"][2] < pos["Invoice"][2] < pos["InvoiceMailerJob"][2] < pos["Ui::Button"][2])
    check("two nodes in one column take different rows", pos["Invoice"][3] != pos["Customer<Org>"][3])
    try:
        svg = render_svg(g, pos)
    except Exception as exc:  # noqa: BLE001 -- the fixture reports, it does not crash
        svg = ""
        check("render_svg survives an edge to a node outside the graph", False, repr(exc))
    try:
        _ET.fromstring(svg)
        parsed = True
    except _ET.ParseError as exc:
        parsed = False
        detail = str(exc)
    check("the SVG parses as XML -- an id carrying `<` is escaped", parsed, detail if not parsed else "")
    check("one node element per node", svg.count('class="node ') == 5, f"{svg.count(chr(99) + 'lass=' + chr(34) + 'node ')}")
    check("edges whose both endpoints are placed are drawn; the one to a missing node is not",
          svg.count('class="edge ') == 3, f"{svg.count('class=' + chr(34) + 'edge ')}")
    check("a backward edge (async -> domain) is drawn, not dropped", 'data-from="InvoiceMailerJob"' in svg)
    refs = _re.findall(r'data-from="([^"]*)" data-to="([^"]*)"', svg)
    check("every drawn edge names two placed nodes",
          all(html.unescape(a) in pos and html.unescape(b) in pos for a, b in refs), f"{refs}")
    check("an empty graph renders a diagram that says so, rather than crashing",
          "no nodes" in render_svg({"nodes": [], "edges": [], "flows": [], "notes": []}))
    try:
        page = render_html(g, "t")
    except Exception as exc:  # noqa: BLE001 -- report, never abort the run before the failures print
        page = ""
        check("render_html survives the same graph", False, repr(exc))
    check("the page embeds the diagram", "__SVG__" not in page and 'class="arch"' in page)

    if failures:
        print(f"architecture_graph selftest: {len(failures)} of {checks} checks FAILED", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"architecture_graph selftest: {checks} checks passed")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="architecture_graph.py",
        description="Extract and emit the living architecture graph for a Rails app.",
    )
    parser.add_argument("--root", default=".", help="Rails app root (default: cwd)")
    parser.add_argument("--out", default="docs/architecture",
                        help="output directory, relative to --root")
    parser.add_argument("--selftest", action="store_true", help="prove the cap-recording contract (#836)")
    parser.add_argument("--check", action="store_true",
                        help="drift check: regenerate and compare the content digest; "
                             "exit 1 if the committed graph is stale")
    parser.add_argument("--if-present", action="store_true",
                        help="with --check: exit 0 when docs/architecture/graph.json does not "
                             "exist (the graph is opt-in per project). Without this flag a "
                             "missing graph is DRIFT, which is correct for a project that opted "
                             "in. Exists so a caller never has to branch on the file's existence "
                             "in shell — that guard belonged here, and putting it in a doc's "
                             "prose is how #151 shipped a release gate that could not block.")
    parser.add_argument("--delta", metavar="REF", nargs="?", const="origin/main",
                        help="print the graph delta vs REF (default origin/main) and exit")
    parser.add_argument("--format", choices=("md", "json"), default="md",
                        help="--delta output format")
    parser.add_argument("--enrich", action="store_true",
                        help="fold in graphify/code-review-graph edges (kept out of the digest)")
    parser.add_argument("--title", default=None, help="HTML title (default: <dir> architecture)")
    parser.add_argument("--max-flows", type=int, default=None,
                        help=f"flow cap (default {DEFAULT_MAX_FLOWS}; --check defaults to the committed graph's cap)")
    parser.add_argument("--max-mermaid-nodes", type=int, default=60)
    parser.add_argument("--max-mermaid-flows", type=int, default=8)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest()

    # Windows consoles default to a legacy code page, which turns the arrows in a
    # flow signature into mojibake (or backslash escapes on stderr). The artefacts
    # are UTF-8; make the streams agree.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    root = os.path.abspath(args.root)
    if not os.path.isdir(os.path.join(root, "app")):
        print(f"architecture_graph: {root} has no app/ — not a Rails app root.", file=sys.stderr)
        return 2

    out_dir = os.path.join(root, args.out)
    json_rel = os.path.join(args.out, "graph.json").replace(os.sep, "/")
    json_path = os.path.join(out_dir, "graph.json")

    def say(message: str) -> None:
        if not args.quiet:
            print(message)

    if args.delta is not None:
        new = load_graph_file(json_path) or build_graph(root, check_cap(None, args.max_flows, DEFAULT_MAX_FLOWS))
        old = load_graph_at_ref(root, args.delta, json_rel)
        delta = compute_delta(old, new)
        if args.format == "json":
            print(json.dumps(delta, indent=2, sort_keys=True))
        else:
            print(render_delta_markdown(delta, new), end="")
        return 0

    committed = load_graph_file(json_path) if args.check else None
    fresh = build_graph(root, check_cap(committed, args.max_flows, DEFAULT_MAX_FLOWS))

    if args.check:
        if committed is None:
            if args.if_present:
                say("architecture graph: not generated in this project — skipping the check "
                    "(the graph is opt-in). Run /rails-flow:graph to adopt it.")
                return 0
            print("architecture graph DRIFT: docs/architecture/graph.json is missing — "
                  "the graph has never been generated for this tree.", file=sys.stderr)
            print("Fix: /rails-flow:graph (or python3 architecture_graph.py) and commit.",
                  file=sys.stderr)
            return 1
        if committed.get("content_digest") == fresh["content_digest"]:
            say(f"architecture graph fresh: {fresh['stats']['nodes']} nodes, "
                f"{fresh['stats']['edges']} edges, {fresh['stats']['flows']} flows "
                f"({fresh['content_digest'][:21]})")
            return 0
        delta = compute_delta(committed, fresh)
        print("architecture graph DRIFT: the code changed but "
              "docs/architecture/graph.json did not.", file=sys.stderr)
        print(f"  committed digest {committed.get('content_digest', 'none')}", file=sys.stderr)
        print(f"  rebuilt   digest {fresh['content_digest']}", file=sys.stderr)
        print(render_delta_markdown(delta, fresh), file=sys.stderr)
        print("Fix: /rails-flow:graph (or python3 architecture_graph.py) and commit "
              "docs/architecture/.", file=sys.stderr)
        return 1

    if args.enrich:
        enrich(fresh, root)

    title = args.title or (os.path.basename(root) + " architecture")
    written = []
    if write_if_changed(json_path, json.dumps(fresh, indent=2, sort_keys=True) + "\n"):
        written.append("graph.json")
    if write_if_changed(os.path.join(out_dir, "index.html"), render_html(fresh, title)):
        written.append("index.html")
    if write_if_changed(
        os.path.join(out_dir, "graph.md"),
        render_mermaid(fresh, args.max_mermaid_nodes, args.max_mermaid_flows),
    ):
        written.append("graph.md")

    say(f"architecture graph: {fresh['stats']['nodes']} nodes, {fresh['stats']['edges']} edges, "
        f"{fresh['stats']['flows']} flows")
    say("  by layer: " + ", ".join(f"{k} {v}" for k, v in fresh["stats"]["by_layer"].items()))
    say("  wrote: " + (", ".join(written) if written else "nothing (already current)"))
    for note in fresh["notes"]:
        say("  note: " + note)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
