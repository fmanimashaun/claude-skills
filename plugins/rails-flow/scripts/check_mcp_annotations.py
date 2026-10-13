#!/usr/bin/env python3
"""Every MCP tool declares `read_only_hint` and `open_world_hint` explicitly (#1882, umbrella #1306).

WHY IT IS A GATE. `rails-8/references/mcp-server.md` §3 rule 2 says to set the annotations of a reporting tool
and never rely on the defaults, and nothing ran it. The schema's `ToolAnnotations` defaults describe the OPPOSITE
tool (`readOnlyHint` false, `destructiveHint` true, `openWorldHint` true), so a tool that forgets them is described to
every client as destructive and open-world.

WHAT THE SOURCE IS, NOT THE WIRE. The `mcp` gem omits `annotations` from `tools/list` when none is declared, but when
ANY is declared it fills every other hint with the spec defaults and emits all four (lib/mcp/tool/annotations.rb:8 and
`to_h`, v1.6.0 and v1.7.0). The wire therefore cannot tell "stated" from "defaulted", so this reads the Ruby source.

HOW (ruby-sdk v1.6.0 / v1.7.0, identical for all of it; the real doctrine-verifier's verdicts are recorded in PR 1892):
  * `class X < MCP::Tool` ... `annotations(read_only_hint: true, open_world_hint: false)`: the macro takes ONE positional
    Hash splatted into `Annotations.new`, which accepts five keys (destructive_hint, idempotent_hint, open_world_hint,
    read_only_hint, title) and raises on any other (tool.rb:121-127). This gate requires TWO of them, explicit.
  * `MCP::Tool.define(..., annotations: {...})`, `Sub.define(...)` on a tool subclass (tool.rb:129), and
    `server.define_tool(..., annotations: {...})` (server.rb:297/302).
  * `Class.new(MCP::Tool) { annotations(...) }`, an anonymous subclass.
A class that inherits an application base tool class (`class X < ApplicationTool`, itself `< MCP::Tool`) is a tool too.
Annotations are NOT inherited: `Tool.inherited` resets them (tool.rb:37-47), so each concrete tool states its own. A class
that other scanned classes inherit from is treated as an abstract base and not judged, UNLESS it defines `call`: a tool that
implements `call` is served, whoever inherits from it, so it is judged too. A name declared twice (`Admin::Report`, `Api::Report`)
is judged per declaration, by that declaration's own base.
The hint must be a literal key (`read_only_hint:` or `:read_only_hint =>`). An `annotations(SOME_CONSTANT)` cannot be read
statically and is a finding, never a pass.

COULD NOT CHECK, never a pass (exit 2): a place this scan cannot read.
  * `MCP::Server.new(tools: SOMETHING)` where the value is not a literal `[...]`, UNLESS the call carries the declaration below.
    A registry-driven server (`tools: policy.tools`, a role-filtered list) cannot be a literal list, and `tools: [*policy.tools]` would tell this
    scan nothing, so the app says where the tools come from and the scan checks THAT (#1988, our own design, the maintainer's decision on the issue):
        # mcp-tools: registry Mcp::Tools::ALL        (on the line above the call, or trailing the line it ends on)
    The scan then requires the registry, by its FULL path (`Mcp::Tools::ALL` is not `Colors::ALL`; the enclosing `module` lines spell the namespace), to
    be defined ONCE in app/ or lib/ as exactly a literal list of constants (`ALL = [A, B].freeze`: a splat, an empty list, a computed definition, a call
    or `+ EXTRA` after the `]` is could-not-check, as is any `<<`, push, concat, `+=` ... on the constant anywhere in the scanned code), every entry to
    be a tool class it found (judged like any other), and every concrete tool class it found to be in the list (an unlisted class is a finding). The
    mark is read as a COMMENT only: the same words inside a string literal declare nothing. What it cannot see: that the server's `tools:` value really comes from that registry. The declaration
    is a stated, checked claim about the registry, not a proof about the server; a tool added any other way is still caught by the next bullet.
  * A tool added after construction. `Server#tools` is an `attr_accessor` over a HASH keyed by tool name (`@tools = tools.to_h { |t| [t.name_value, t] }`,
    server.rb:217/222; `@tools[tool_name] = tool`, :302/307; `@tools.values`, :555/560), so the late forms are Hash forms:
    `server.tools = {...}`, `server.tools['name'] = T`, `.tools.merge!/store/update/replace(...)`. (`<<`, `.push` and `.concat` raise on a Hash and
    register nothing.) The gem has no add_tool.
  * MCP code this scan does not parse as tools: any `.rb` file outside `app/` and `lib/` naming `MCP::Tool`, `MCP::Server` or `define_tool` (a
    `config/initializers/mcp.rb`, a top-level `mcp/`), and any non-`.rb` Ruby anywhere (`config.ru`, `*.rake`, a Rakefile,
    a script whose first line is a ruby shebang, such as `bin/mcp_server`). A Gemfile that merely names the `mcp` gem is NOT enough: an app that is only an MCP client depends on it too.
    `spec/`, `test/`, `vendor/`, `node_modules/`, `tmp/`, `log/`, `db/`, `coverage/` and `public/` are skipped by design, so a served tool kept
    under one of them is not seen.
A tool registered that way may be defined anywhere, so a clean run would claim more than was looked at.

LIMITS, stated: a class body ends at the next `end` at the class line's indent (so `end # A` and a one-line
`class A < MCP::Tool; end` are read right), and code that is not indented that way is not read right; whole-line `#`
comments are ignored, a trailing one is not; quote-delimited string literals are blanked before a hint is looked for, so a hint named inside one
does not count (a heredoc body or a `%q(...)` literal is NOT blanked and can still forge both keys); only a statement-start `annotations(` in a class body counts (not `meta.annotations(...)`, not a word in a description); a
base named relative to a namespace (`module MCP; class A < Tool`) is not recognised and reads as "not applicable"; a tool built by other
metaprogramming is invisible here; and `read_only_hint: nil` or `false` counts as stated, since the gate asks for an explicit declaration, not
a particular value. The check proves the declaration exists, not that the value is TRUE: a tool whose code writes while declaring
`read_only_hint: true` is the request spec's job ("No tool writes", mcp-server.md §4).

Run:  check_mcp_annotations.py [--root DIR]
      check_mcp_annotations.py --selftest
Exit: 0 clean · 1 finding(s) · 2 unusable (a source file unreadable, or a tool list that cannot be read) · 3 not applicable (no MCP tool)
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from pathlib import Path

REQUIRED = ("read_only_hint", "open_world_hint")
SCAN_DIRS = ("app", "lib")
CLASS = re.compile(r"^(?P<indent>[ \t]*)class\s+(?P<name>[\w:]+)\s*<\s*(?P<base>[\w:]+)")
CALL = re.compile(r"(?:(?P<recv>[\w:]+)\.define(?!\w)|\.define_tool(?!\w))\s*\(?")
CLASS_NEW = re.compile(r"\bClass\.new\(\s*(?P<base>[\w:]+)\s*\)")
SERVER_NEW = re.compile(r"MCP::Server\.new\s*\(")
# a registry-driven server (`tools: policy.tools`, a role-filtered list) names the registry it draws from; the scan then reads the registry (#1988)
REGISTRY_MARK = re.compile(r"#[ \t]*mcp-tools:[ \t]*registry[ \t]+(?P<const>[A-Z]\w*(?:::[A-Z]\w*)*)(?![\w:])")
CONST_PATH = re.compile(r"[A-Z]\w*(?:::[A-Z]\w*)*")
# `Server#tools` is a Hash keyed by tool name: these are the ways to put a tool into it after construction
TOOLS_MUTATED = re.compile(r"\.tools\s*(?:=(?![=~>])|\[[^\]]*\]\s*(?:\|\||&&)?=(?![=~>])|\.(?:merge!|(?:store|update|replace)\b))")
CALLS = re.compile(r"\bdef\s+(?:self\.)?call\b")
MCP_TOOL = {"MCP::Tool", "::MCP::Tool"}
MCP_TEXT = re.compile(r"\bMCP::(?:Tool|Server)\b|\bdefine_tool\b")
STRING = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")
SKIP_DIRS = {"vendor", "node_modules", "tmp", "log", "spec", "test", "db", ".git", "coverage", "public"}


class Unusable(RuntimeError):
    pass


def _balanced(text: str, start: int, opener: str, closer: str) -> str:
    """The text from the `opener` at `start` to its matching `closer`, skipping strings and comments."""
    depth, i, quote = 0, start, ""
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            i = text.find("\n", i)
            if i < 0:
                break
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    return text[start:]


def _keys(chunk: str) -> set[str]:
    return {k for k in REQUIRED if re.search(rf"(?:\b{k}\s*:|:{k}\s*=>)", chunk)}


def _blank_strings(text: str) -> str:
    """Every string literal's contents as spaces (offsets and newlines kept), so a hint named inside a string is not a hint."""
    return STRING.sub(lambda m: m.group(0)[0] + re.sub(r"[^\n]", " ", m.group(0)[1:-1]) + m.group(0)[-1], text)


# a class body declares annotations as a statement; a define call passes them as a keyword, after `(` or `,`
BODY_DECL = re.compile(r"(?m)(?:^|[{;])[ \t]*annotations\b(?:\s*(?P<open>\()|(?=[ \t]+\w+[ \t]*:)(?P<bare>))")
ARGS_DECL = re.compile(r"(?:\A|[(,])\s*annotations\b\s*(?P<open>:)")


def _judge(scope: str, decl: re.Pattern = BODY_DECL) -> str:
    """'' when `scope` declares both hints; otherwise what is wrong with it."""
    scope = _blank_strings(scope)
    m = decl.search(scope)
    if not m:
        return "declares no annotations, so a client reads it as destructive and open-world"
    if m.groupdict().get("open") == "(":
        args = _balanced(scope, m.end() - 1, "(", ")")
    elif m.groupdict().get("bare") is not None:
        # `annotations read_only_hint: true, ...`: the statement runs on while a line ends in a comma
        rows = scope[m.end() :].split("\n")
        n = next((k for k, r in enumerate(rows) if not r.rstrip().endswith(",")), len(rows) - 1)
        args = "\n".join(rows[: n + 1])
    else:
        rest = scope[m.end() :].lstrip()
        args = _balanced(rest, 0, "{", "}") if rest.startswith("{") else rest.split("\n", 1)[0]
    if not re.search(r"\w+\s*:|=>", args):
        return f"annotations are not a literal hash ({args.strip()[:40]!r}), so the hints cannot be read statically"
    missing = [k for k in REQUIRED if k not in _keys(args)]
    return f"does not set {' and '.join(missing)} explicitly" if missing else ""


def _class_body(lines: list[str], i: int, indent: str) -> str:
    """The class (or block) starting at line `i`: to the next `end` at its indent (`end # A` counts), or the line itself for `class A < MCP::Tool; end`."""
    if re.search(r";\s*end\s*$", lines[i]):
        return lines[i]
    stop = re.compile(rf"^{indent}end\b")
    end = next((j for j in range(i + 1, len(lines)) if stop.match(lines[j])), len(lines))
    return "\n".join(lines[i:end])


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def _is_tool(name: str, tools: set[str]) -> bool:
    return name in MCP_TOOL or name.split("::")[-1] in tools


def _parsed(root: Path) -> list[tuple[Path, str, list[str]]]:
    """Every .rb under SCAN_DIRS as (path, text with whole-line comments blanked, lines); raises Unusable on an unreadable file."""
    files = [p for d in SCAN_DIRS for p in sorted((root / d).rglob("*.rb"))] if root.is_dir() else []
    parsed: list[tuple[Path, str, list[str]]] = []
    for p in files:
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as e:
            raise Unusable(f"{p}: {e}") from e
        # a commented-out declaration is not one: blank whole-line comments (line numbers stay)
        lines = ["" if ln.lstrip().startswith("#") else ln for ln in text.split("\n")]
        parsed.append((p, "\n".join(lines), lines))
    return parsed


def _tool_names(parsed: list[tuple[Path, str, list[str]]]) -> tuple[set[str], set[str]]:
    """(the short names of every class that reaches MCP::Tool, the abstract bases among them -- not judged)."""
    # one name may be declared twice (`Admin::Report`, `Api::Report`): keep every base it has, so no declaration hides another
    classes: dict[str, set[str]] = {}
    served: set[str] = set()
    for _, _, lines in parsed:
        for i, line in enumerate(lines):
            m = CLASS.match(line)
            if m:
                name = m["name"].split("::")[-1]
                classes.setdefault(name, set()).add(m["base"])
                if CALLS.search(_class_body(lines, i, m["indent"])):
                    served.add(name)
    tools = {n for n, bs in classes.items() if bs & MCP_TOOL}
    grew = True
    while grew:
        grew = False
        for n, bs in classes.items():
            if n not in tools and any(b.split("::")[-1] in tools for b in bs):
                tools.add(n)
                grew = True
    # a base is abstract (not judged) only when it has a tool subclass AND defines no `call`: a tool that implements `call` is served
    bases = {b.split("::")[-1] for n in tools for b in classes[n]} - served
    return tools, bases


def class_tools(root: Path) -> list[tuple[Path, int, str, str]]:
    """Every concrete class-form tool as (path, 1-based line, class name, class body): ONE definition of "what is an MCP tool
    class", shared by this gate and check_mcp_personal_fields.py (#1931). The Define and Class.new forms are scanned only here."""
    parsed = _parsed(root)
    tools, bases = _tool_names(parsed)
    return [(p, i + 1, name, body) for p, lines in ((p, lines) for p, _t, lines in parsed)
            for i, name, body in _concrete_classes(lines, tools, bases)]


def _concrete_classes(lines: list[str], tools: set[str], bases: set[str]) -> list[tuple[int, str, str]]:
    """(0-based line, class name, body) of each class in one file that is a tool and not an abstract base."""
    out = []
    for i, line in enumerate(lines):
        m = CLASS.match(line)
        if m and _is_tool(m["base"], tools) and m["name"].split("::")[-1] not in bases:
            out.append((i, m["name"], _class_body(lines, i, m["indent"])))
    return out


NESTING = re.compile(r"^(?P<indent>[ \t]*)(?:module|class)\s+(?P<name>[A-Z][\w:]*)")
# a way to grow or rewrite a constant list after its definition: `ALL << X`, `ALL.push(X)`, `ALL += [X]`
GROWN = r"\s*(?:<<|\+=|\|=|\.(?:push|append|concat|unshift|prepend|insert|replace)\b)"


def _definitions(parsed: list[tuple[Path, str, list[str]]], path: str) -> list[tuple[str, int]]:
    """Every assignment to the FULL constant path `path` (`Mcp::Tools::ALL`) as (file text, offset of what follows the `=`). The enclosing
    `module`/`class` lines spell the namespace (by indentation, as the rest of this scan reads a body), so `Colors::ALL` is not `Mcp::Tools::ALL`."""
    out = []
    for _, text, lines in parsed:
        stack: list[tuple[int, str]] = []
        offset = 0
        for line in lines:
            if line.strip():
                width = len(line) - len(line.lstrip())
                while stack and stack[-1][0] >= width:
                    stack.pop()
                m = NESTING.match(line)
                if m:
                    stack.append((width, m["name"]))
                a = re.match(r"[ \t]*(?P<lhs>(?:[A-Z]\w*::)*[A-Z]\w*)[ \t]*=(?![=~>])", line)
                if a and "::".join([n for _, n in stack] + [a["lhs"]]) == path:
                    out.append((text, offset + a.end()))
            offset += len(line) + 1
    return out


def _registry(parsed: list[tuple[Path, str, list[str]]], const: str, tools: set[str], concrete: set[str]) -> tuple[list[str], list[str]]:
    """(findings, unchecked) for a server that declares `# mcp-tools: registry CONST`. The declaration is only as good as what it can be checked
    against, so it passes only when CONST (the FULL path) is defined ONCE, as exactly a literal list of constants (a trailing `.freeze` is all that
    may follow the `]`), is never grown or rewritten anywhere in the scanned code, every entry is a tool class this scan found (and so judged), and
    no tool class found is missing from it. What it cannot see, and says so: that the server's `tools:` value is really drawn from CONST."""
    path = const.lstrip(":")
    last = path.split("::")[-1]
    defs = _definitions(parsed, path)
    if len(defs) != 1:
        return [], [f"`# mcp-tools: registry {const}` names a registry that is defined {len(defs)} times in app/ or lib/ (the full path, as written), not once, so the tools it serves cannot be found"]
    text, at = defs[0]
    rest = text[at:].lstrip(" \t")
    if not rest.startswith("["):
        return [], [f"registry {const} is defined as {rest.split(chr(10))[0].strip()[:40]!r}, not a literal list, so the tools it serves cannot be found"]
    lst = _balanced(rest, 0, "[", "]")
    tail = re.sub(r"#[^\n]*", "", rest[len(lst):]).split("\n")
    after = tail[0].strip()
    following = next((ln.strip() for ln in tail[1:] if ln.strip()), "")
    if after not in ("", ".freeze") or re.match(r"[.&+\-|*]", following):
        return [], [f"registry {const} has more after its list ({(after or following)[:40]!r}), so the tools it serves cannot be found"]
    if any(re.search(rf"(?<![\w])(?:[A-Z]\w*::)*{last}{GROWN}", t) for _, t, _ in parsed):
        return [], [f"registry {const} is grown or rewritten after its definition (`<<`, push, concat, `+=` ...), so the tools it serves cannot be found"]
    body = re.sub(r"#[^\n]*", "", lst)[1:-1]
    items = [x.strip() for x in body.split(",") if x.strip()]
    bad = [x for x in items if not CONST_PATH.fullmatch(x)]
    if bad or not items:
        return [], [f"registry {const} is not a literal list of constants ({(bad or ['empty'])[0][:40]!r}), so the tools it serves cannot be found"]
    listed = {x.split("::")[-1] for x in items}
    findings = [f"registry {const} lists {x}, which is not an MCP tool class this scan found, so it is served unread" for x in sorted(listed - tools)]
    findings += [f"tool class {x} is not in registry {const}, which the server declares it draws from" for x in sorted(concrete - listed)]
    return findings, []


def _comment(line: str) -> str:
    """The comment on one line of Ruby ('' when there is none): the text from the first `#` that is outside a string literal."""
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            return line[i:]
        i += 1
    return ""


def scan(root: Path) -> tuple[int, list[str], list[str]]:
    """(tools found, findings, places this scan could not read)."""
    parsed = _parsed(root)
    tools, bases = _tool_names(parsed)
    concrete = {name.split("::")[-1] for _, _, lines in parsed for _, name, _ in _concrete_classes(lines, tools, bases)}
    found, findings, unchecked = 0, [], []
    for p, text, lines in parsed:
        rel = p.relative_to(root)
        for i, name, body in _concrete_classes(lines, tools, bases):
            found += 1
            why = _judge(body)
            if why:
                findings.append(f"{rel}:{i + 1}: tool {name} {why}")
        for m in CALL.finditer(text):
            if m["recv"] and not _is_tool(m["recv"], tools):
                continue
            open_at = m.end() - 1 if m.group(0).endswith("(") else None
            args = _balanced(text, open_at, "(", ")") if open_at is not None else text[m.end() : text.find("\n", m.end())]
            found += 1
            why = _judge(args, ARGS_DECL)
            if why:
                findings.append(f"{rel}:{_line_of(text, m.start())}: a tool defined by {m.group(0).strip('( ')} {why}")
        for m in CLASS_NEW.finditer(text):
            if not _is_tool(m["base"], tools):
                continue
            found += 1
            rest = text[m.end() :].lstrip(" ")
            if rest.startswith("{"):
                scope = _balanced(rest, 0, "{", "}")
            elif rest.startswith("do"):
                at = _line_of(text, m.start()) - 1
                scope = _class_body(lines, at, re.match(r"[ \t]*", lines[at])[0])
            else:
                scope = ""
            why = _judge(scope)
            if why:
                findings.append(f"{rel}:{_line_of(text, m.start())}: a tool built by Class.new({m['base']}) {why}")
        for m in SERVER_NEW.finditer(text):
            args = _balanced(text, m.end() - 1, "(", ")")
            t = re.search(r"\btools:\s*(\S)", args)
            if t and t[1] != "[":
                where = f"{rel}:{_line_of(text, m.start())}"
                # the declaration is a comment and `parsed` blanks whole-line comments, so read it from the file: the line above the call through the line it ends on
                raw = p.read_text(encoding="utf-8").split("\n")
                first, last = _line_of(text, m.start()) - 1, _line_of(text, m.end() - 1 + len(args)) - 1
                span = "\n".join(_comment(ln) for ln in raw[max(first - 1, 0) : last + 1])   # comments only: the same words in a string are not a declaration
                mark = REGISTRY_MARK.search(span)
                if not mark:
                    unchecked.append(f"{where}: MCP::Server.new(tools: ...) is not a literal list, so the tools it serves cannot be found")
                    continue
                fs, us = _registry(parsed, mark["const"], tools, concrete)
                findings += [f"{where}: {f}" for f in fs]
                unchecked += [f"{where}: {u}" for u in us]
        for m in TOOLS_MUTATED.finditer(text):
            unchecked.append(f"{rel}:{_line_of(text, m.start())}: tools are added to a server after construction ({m.group(0).strip()}), so they cannot be found")
    unchecked.extend(_outside(root))
    return found, findings, unchecked


def _rubyish(name: str, path: Path) -> bool:
    """A Ruby file this scan does not parse as `.rb`: a `.rake` or `.ru`, a Rakefile, or any file whose first line is a ruby shebang."""
    if name.endswith((".rake", ".ru")) or name == "Rakefile":
        return True
    try:
        with open(path, "rb") as fh:
            line = fh.readline(200)
            return line.startswith(b"#!") and b"ruby" in line
    except OSError:
        return False


def _outside(root: Path) -> list[str]:
    """Ruby outside what `scan` parses that names MCP tooling: not read as tools here, so it must not make the run clean.
    That is every `.rb` outside app/ and lib/, and the non-`.rb` Ruby anywhere (`config.ru`, `*.rake`, a Rakefile, a script with a ruby shebang such as `bin/mcp_server`)."""
    out = []
    for dirpath, dirs, names in os.walk(root):
        here = Path(dirpath).relative_to(root)
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        top = here.parts[0] if here.parts else ""
        for n in sorted(names):
            p = Path(dirpath) / n
            if n.endswith(".rb"):
                if top in SCAN_DIRS:
                    continue
            elif not _rubyish(n, p):
                continue
            try:
                text = p.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as e:
                if n.endswith(".rb"):
                    raise Unusable(f"{p}: {e}") from e
                continue
            code = "\n".join("" if ln.lstrip().startswith("#") else ln for ln in text.split("\n"))
            if MCP_TEXT.search(code):
                out.append(f"{here / n}: names MCP tooling this scan does not read as tools (outside app/ and lib/, or not a .rb file)")
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", default=".")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        found, findings, unchecked = scan(Path(a.root))
    except Unusable as e:
        print(f"mcp-annotations: unusable: {e}")
        return 2
    for f in findings:
        print(f"mcp-annotations: {f}")
    for u in unchecked:
        print(f"mcp-annotations: could not check: {u}")
    if findings:
        print(f"mcp-annotations: {found} tool(s), {len(findings)} finding(s), {len(unchecked)} place(s) not checked")
        return 1
    if unchecked:
        print(f"mcp-annotations: {found} tool(s) read clean, but {len(unchecked)} place(s) could not be checked, so this is not a pass")
        return 2
    if not found:
        print("mcp-annotations: not applicable (no MCP tool in app/ or lib/)")
        return 3
    print(f"mcp-annotations: {found} tool(s), 0 findings")
    return 0


GOOD = "class SalesReport < MCP::Tool\n  annotations(read_only_hint: true, open_world_hint: false)\nend\n"
BASE = "class ApplicationTool < MCP::Tool\nend\n"
SUB = "class Sub < ApplicationTool\n  annotations(read_only_hint: true, open_world_hint: false)\nend\n"
# (label, files, tools expected, findings expected, text a finding must contain, places not checked expected)
def _tool(name: str, hints: str = "read_only_hint: true, open_world_hint: false") -> str:
    return f"class {name} < MCP::Tool\n  annotations({hints})\nend\n"


def _registry_case(label: str, registry: str, mark: str, tools: str, want_tools: int, want_findings: int, needle: str, want_unchecked: int, after: bool = False):
    call = "    MCP::Server.new(name: 'x', tools: policy.tools)" + (f"  {mark}" if after else "") + "\n"
    server = "class Factory\n  def build\n" + ("" if after else f"    {mark}\n") + call + "  end\nend\n"
    return (label, {"app/mcp/tools.rb": tools + registry, "app/mcp/factory.rb": server}, want_tools, want_findings, needle, want_unchecked)


_MARK = "# mcp-tools: registry ALL"
_FULL = "# mcp-tools: registry Mcp::Tools::ALL"
CASES: list[tuple[str, dict[str, str], int, int, str, int]] = [
    _registry_case("registry: a declared registry of scanned tool classes passes", "ALL = [A, B].freeze\n", _MARK, _tool("A") + _tool("B"), 2, 0, "", 0),
    _registry_case("registry: the declaration may trail the call's line", "ALL = [A, B].freeze\n", _MARK, _tool("A") + _tool("B"), 2, 0, "", 0, after=True),
    _registry_case("registry: a registry spread over lines with comments passes", "ALL = [\n  A, # reads\n  B,\n].freeze\n", _MARK, _tool("A") + _tool("B"), 2, 0, "", 0),
    _registry_case("registry: a listed class that is not a tool is a finding, not a pass", "ALL = [A, Ghost].freeze\n", _MARK, _tool("A"), 1, 1, "lists Ghost", 0),
    _registry_case("registry: a tool class the registry does not list is a finding", "ALL = [A].freeze\n", _MARK, _tool("A") + _tool("B"), 2, 1, "tool class B is not in registry ALL", 0),
    _registry_case("registry: a listed tool that states no hints is still judged", "ALL = [A, B].freeze\n", _MARK, _tool("A") + "class B < MCP::Tool\nend\n", 2, 1, "declares no annotations", 0),
    _registry_case("registry: a registry that is not defined is could-not-check", "OTHER = [A].freeze\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: a registry defined twice is could-not-check", "ALL = [A].freeze\nALL = [A].freeze\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: a splat in the registry is could-not-check", "ALL = [A, *OTHER].freeze\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: an empty registry is could-not-check", "ALL = [].freeze\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: a declaration three lines above the call is not beside it", "ALL = [A].freeze\n", _MARK + "\n\n", _tool("A"), 1, 0, "", 1),
    # dd's review of #1988 (each of these passed with 0 findings before): the wrong constant, an unread tail, a grown list, a mark in a string
    _registry_case("registry: another module's ALL is not the declared Mcp::Tools::ALL", "module Colors\n  ALL = [A, B].freeze\nend\n", _FULL, _tool("A") + _tool("B"), 2, 0, "", 1),
    _registry_case("registry: a computed Mcp::Tools::ALL is could-not-check even with a literal ALL elsewhere",
                   "module Mcp\n  module Tools\n    ALL = ObjectSpace.each_object(Class).select { |c| c < MCP::Tool }\n  end\nend\nmodule Colors\n  ALL = [A, B].freeze\nend\n", _FULL, _tool("A") + _tool("B"), 2, 0, "", 1),
    _registry_case("registry: the declared full path, nested as modules, is read", "module Mcp\n  module Tools\n    ALL = [A, B].freeze\n  end\nend\n", _FULL, _tool("A") + _tool("B"), 2, 0, "", 0),
    _registry_case("registry: the declared full path, compact as `module Mcp::Tools`, is read", "module Mcp::Tools\n  ALL = [A, B].freeze\nend\n", _FULL, _tool("A") + _tool("B"), 2, 0, "", 0),
    _registry_case("registry: a literal head with an unread tail (`[A] + EXTRA`) is could-not-check", "ALL = [A] + EXTRA\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: a list followed by `.concat(EXTRA)` on the next line is could-not-check", "ALL = [A]\n  .concat(EXTRA)\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: a list with a chained call (`.map`) is could-not-check", "ALL = [A].map(&:itself)\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: `ALL << Rogue` after the definition is could-not-check", "ALL = [A]\nALL << Rogue\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: `ALL.push(Rogue)` after the definition is could-not-check", "ALL = [A]\nALL.push(Rogue)\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: `ALL += [Rogue]` after the definition is could-not-check", "ALL = [A]\nALL += [Rogue]\n", _MARK, _tool("A"), 1, 0, "", 1),
    _registry_case("registry: `ALL.freeze` is not a mutation", "ALL = [A]\nALL.freeze\n", _MARK, _tool("A"), 1, 0, "", 0),
    ("registry: the declaration inside a string is not a declaration",
     {"app/mcp/tools.rb": _tool("A") + "ALL = [A].freeze\n", "app/mcp/factory.rb": "class F\n  def b\n    MCP::Server.new(name: '# mcp-tools: registry ALL', tools: policy.tools)\n  end\nend\n"}, 1, 0, "", 1),
    ("registry: the declaration in a comment after code on its own line still counts",
     {"app/mcp/tools.rb": _tool("A") + "ALL = [A].freeze\n", "app/mcp/factory.rb": "class F\n  def b\n    MCP::Server.new(name: 'x #', tools: policy.tools) # mcp-tools: registry ALL\n  end\nend\n"}, 1, 0, "", 0),
    ("explicit class macro is clean", {"app/mcp/a.rb": GOOD}, 1, 0, "", 0),
    ("no annotations at all is a finding", {"app/mcp/a.rb": "class A < MCP::Tool\n  description 'x'\nend\n"}, 1, 1, "declares no annotations", 0),
    ("only read_only_hint set misses open_world_hint",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations(read_only_hint: true)\nend\n"}, 1, 1, "open_world_hint", 0),
    ("only open_world_hint set misses read_only_hint",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations(open_world_hint: false)\nend\n"}, 1, 1, "read_only_hint", 0),
    ("all five keys with both required ones is clean",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations(title: 'A', read_only_hint: true, destructive_hint: false,\n    idempotent_hint: true, open_world_hint: false)\nend\n"}, 1, 0, "", 0),
    ("a hash rocket spelling counts",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations(:read_only_hint => true, :open_world_hint => false)\nend\n"}, 1, 0, "", 0),
    ("a constant argument cannot be read and fails",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations(HINTS)\nend\n"}, 1, 1, "not a literal hash", 0),
    ("a hint named only in a comment does not count",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  # read_only_hint: true, open_world_hint: false\n  annotations(title: 'x')\nend\n"}, 1, 1, "does not set", 0),
    ("a subclass of an application base is judged, the base is not",
     {"app/mcp/base.rb": BASE, "app/mcp/a.rb": "class A < ApplicationTool\n  description 'x'\nend\n"}, 1, 1, "tool A", 0),
    ("a subclass that states its own is clean",
     {"app/mcp/base.rb": BASE,
      "app/mcp/a.rb": "class A < ApplicationTool\n  annotations(read_only_hint: true, open_world_hint: false)\nend\n"}, 1, 0, "", 0),
    ("Tool.define with both hints is clean",
     {"app/mcp/a.rb": "T = MCP::Tool.define(name: 'a',\n  annotations: { read_only_hint: true, open_world_hint: false }) { }\n"}, 1, 0, "", 0),
    ("Tool.define without annotations is a finding",
     {"app/mcp/a.rb": "T = MCP::Tool.define(name: 'a', description: 'x') { }\n"}, 1, 1, "declares no annotations", 0),
    ("Sub.define on a tool subclass without annotations is a finding",
     {"app/mcp/base.rb": BASE, "app/mcp/b.rb": SUB,
      "app/mcp/a.rb": "T = ApplicationTool.define(name: 'a') { }\n"}, 2, 1, "a tool defined by ApplicationTool.define", 0),
    ("Sub.define on a tool subclass with both hints is clean",
     {"app/mcp/base.rb": BASE, "app/mcp/b.rb": SUB,
      "app/mcp/a.rb": "T = ApplicationTool.define(name: 'a', annotations: { read_only_hint: true, open_world_hint: false }) { }\n"}, 2, 0, "", 0),
    ("define on something that is not a tool is ignored", {"app/mcp/a.rb": "Foo.define(name: 'a')\n" + GOOD}, 1, 0, "", 0),
    ("define_tool without open_world_hint is a finding",
     {"app/mcp/a.rb": "server.define_tool(name: 'a', annotations: { read_only_hint: true }) { }\n"}, 1, 1, "open_world_hint", 0),
    ("Class.new(MCP::Tool) block with both hints is clean",
     {"app/mcp/a.rb": "T = Class.new(MCP::Tool) do\n  annotations(read_only_hint: true, open_world_hint: false)\nend\n"}, 1, 0, "", 0),
    ("Class.new(MCP::Tool) block without annotations is a finding",
     {"app/mcp/a.rb": "T = Class.new(MCP::Tool) do\n  description 'x'\nend\n"}, 1, 1, "Class.new(MCP::Tool)", 0),
    ("Class.new(MCP::Tool) with a brace block and one hint is a finding",
     {"app/mcp/a.rb": "T = Class.new(MCP::Tool) { annotations(read_only_hint: true) }\n"}, 1, 1, "open_world_hint", 0),
    ("Class.new of something that is not a tool is ignored", {"app/mcp/a.rb": "T = Class.new(StandardError)\n" + GOOD}, 1, 0, "", 0),
    ("tools: with a literal list is read", {"app/mcp/a.rb": GOOD + "S = MCP::Server.new(name: 'x', tools: [SalesReport])\n"}, 1, 0, "", 0),
    ("tools: with a constant could not be checked",
     {"app/mcp/a.rb": GOOD + "S = MCP::Server.new(name: 'x', tools: TOOLS)\n"}, 1, 0, "", 1),
    ("tools: with a method call could not be checked",
     {"app/mcp/a.rb": "S = MCP::Server.new(name: 'x', tools: Registry.tools)\n"}, 0, 0, "", 1),
    ("server.tools = could not be checked", {"app/mcp/a.rb": GOOD + "server.tools = [SalesReport]\n"}, 1, 0, "", 1),
    ("server.tools[name] = could not be checked", {"app/mcp/a.rb": GOOD + "server.tools['sales'] = SalesReport\n"}, 1, 0, "", 1),
    ("server.tools.merge! could not be checked", {"app/mcp/a.rb": GOOD + "server.tools.merge!('a' => SalesReport)\n"}, 1, 0, "", 1),
    ("server.tools.store could not be checked", {"app/mcp/a.rb": GOOD + "server.tools.store('a', SalesReport)\n"}, 1, 0, "", 1),
    ("server.tools.update could not be checked", {"app/mcp/a.rb": GOOD + "server.tools.update('a' => SalesReport)\n"}, 1, 0, "", 1),
    ("server.tools.replace could not be checked", {"app/mcp/a.rb": GOOD + "server.tools.replace({})\n"}, 1, 0, "", 1),
    ("a commented-out server.tools = is not a mutation", {"app/mcp/a.rb": GOOD + "# server.tools = []\n"}, 1, 0, "", 0),
    ("a commented-out MCP::Server.new(tools: X) is not an unreadable list", {"app/mcp/a.rb": "# S = MCP::Server.new(tools: TOOLS)\n"}, 0, 0, "", 0),
    ("a commented-out Tool.define is not a tool", {"app/mcp/a.rb": "# T = MCP::Tool.define(name: 'a')\n"}, 0, 0, "", 0),
    ("server.tools[name] ||= could not be checked", {"app/mcp/a.rb": GOOD + "server.tools[:a] ||= SalesReport\n"}, 1, 0, "", 1),
    ("server.tools[name] &&= could not be checked", {"app/mcp/a.rb": GOOD + "server.tools[:a] &&= SalesReport\n"}, 1, 0, "", 1),
    ("an entry script in bin/ could not be checked",
     {"app/mcp/a.rb": GOOD, "bin/mcp_server": "#!/usr/bin/env ruby\nMCP::Server.new(tools: [SalesReport]).run\n"}, 1, 0, "", 1),
    ("config.ru naming MCP could not be checked", {"app/mcp/a.rb": GOOD, "config.ru": "run MCP::Server.new(tools: [SalesReport])\n"}, 1, 0, "", 1),
    ("a .rake task naming MCP could not be checked",
     {"app/mcp/a.rb": GOOD, "lib/tasks/mcp.rake": "task(:serve) { MCP::Server.new(tools: [SalesReport]) }\n"}, 1, 0, "", 1),
    ("an extensionless ruby-shebang script elsewhere could not be checked",
     {"app/mcp/a.rb": GOOD, "script/serve": "#!/usr/bin/env ruby\nMCP::Server.new(tools: [SalesReport])\n"}, 1, 0, "", 1),
    ("a Ruby script that does not name MCP is not a place to check",
     {"app/mcp/a.rb": GOOD, "bin/setup": "#!/usr/bin/env ruby\nputs 'setup'\n", "lib/tasks/x.rake": "task(:x) { }\n"}, 1, 0, "", 0),
    ("an extensionless file that is not Ruby is not read",
     {"app/mcp/a.rb": GOOD, "NOTES": "MCP::Server is mentioned here\n", "script/other": "#!/bin/sh\necho MCP::Server\n"}, 1, 0, "", 0),
    ("a comparison of tools is not a mutation", {"app/mcp/a.rb": GOOD + "ok = server.tools == []\n"}, 1, 0, "", 0),
    ("reading tools, or a non-mutating merge, is not a mutation",
     {"app/mcp/a.rb": GOOD + "n = server.tools.keys\nm = server.tools.merge('a' => SalesReport)\n"}, 1, 0, "", 0),
    ("MCP code in config/ could not be checked",
     {"app/mcp/a.rb": GOOD, "config/initializers/mcp.rb": "server.define_tool(name: 'x') { }\n"}, 1, 0, "", 1),
    ("MCP code in a top-level mcp/ with no tool found could not be checked",
     {"mcp/bad.rb": "class Bad < MCP::Tool\nend\n"}, 0, 0, "", 1),
    ("MCP code in spec/ is not read", {"app/mcp/a.rb": GOOD, "spec/mcp/a_spec.rb": "MCP::Tool\n"}, 1, 0, "", 0),
    ("a comment naming MCP outside app/ is not MCP code", {"app/mcp/a.rb": GOOD, "config/x.rb": "# MCP::Server is not used here\n"}, 1, 0, "", 0),
    ("a hint named inside a string is not a hint",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations(title: 'read_only_hint: true, open_world_hint: false')\nend\n"}, 1, 1, "does not set", 0),
    ("a description naming annotations is not a declaration",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  description 'annotations(read_only_hint: true, open_world_hint: false)'\nend\n"}, 1, 1, "declares no annotations", 0),
    ("annotations on another receiver is not this tool's declaration",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  def self.call(**)\n    meta.annotations(read_only_hint: true, open_world_hint: false)\n  end\nend\n"}, 1, 1, "declares no annotations", 0),
    ("a one-line class does not borrow the next class's annotations",
     {"app/mcp/a.rb": "class A < MCP::Tool; end\n" + GOOD}, 2, 1, "tool A", 0),
    ("an end with a trailing comment closes the class",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  description 'x'\nend # A\n" + GOOD}, 2, 1, "tool A", 0),
    ("paren-less annotations are read", {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations read_only_hint: true, open_world_hint: false\nend\n"}, 1, 0, "", 0),
    ("paren-less annotations continue over lines ending in a comma",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations read_only_hint: true,\n    open_world_hint: false\nend\n"}, 1, 0, "", 0),
    ("paren-less annotations with one hint are a finding",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  annotations read_only_hint: true\nend\n"}, 1, 1, "open_world_hint", 0),
    ("a one-line class with its own hints is clean",
     {"app/mcp/a.rb": "class A < MCP::Tool; annotations(read_only_hint: true, open_world_hint: false); end\n"}, 1, 0, "", 0),
    ("a commented-out annotations call is not a declaration",
     {"app/mcp/a.rb": "class A < MCP::Tool\n  # annotations(read_only_hint: true, open_world_hint: false)\nend\n"}, 1, 1, "declares no annotations", 0),
    ("a base that defines call is a served tool, and judged",
     {"app/mcp/base.rb": "class Report < MCP::Tool\n  def self.call(**)\n  end\nend\n", "app/mcp/b.rb": "class Sub < Report\n  annotations(read_only_hint: true, open_world_hint: false)\nend\n"},
     2, 1, "tool Report", 0),
    ("a name declared in two places is judged per declaration",
     {"app/a/tool.rb": "module Admin\n  class Report < MCP::Tool\n    description 'x'\n  end\nend\n", "app/b/other.rb": "module Api\n  class Report < Struct\n  end\nend\n"},
     1, 1, "tool Report", 0),
    ("a name declared in two places still passes its tool-ness to a subclass",
     {"app/a/tool.rb": "module Admin\n  class Report < MCP::Tool\n  end\nend\n", "app/b/other.rb": "module Api\n  class Report < Struct\n  end\nend\n",
      "app/c/x.rb": "class X < Report\n  description 'x'\nend\n"}, 1, 1, "tool X", 0),
    ("a file with no tool is not applicable", {"app/models/user.rb": "class User < ApplicationRecord\nend\n"}, 0, 0, "", 0),
    ("a class that is not a tool is ignored", {"app/mcp/a.rb": "class A < Struct\nend\n" + GOOD}, 1, 0, "", 0),
]


def selftest() -> int:
    failed = 0
    for label, files, want_tools, want_findings, needle, want_unchecked in CASES:
        with tempfile.TemporaryDirectory(prefix="mcp-annotations-") as d:
            for rel, body in files.items():
                (Path(d) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(d) / rel).write_text(body, encoding="utf-8")
            found, findings, unchecked = scan(Path(d))
        ok = (found == want_tools and len(findings) == want_findings and all(needle in f for f in findings)
              and len(unchecked) == want_unchecked)
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" -> tools={found} findings={findings} unchecked={unchecked}"))
    # the exit code, not only the lists: unchecked is never a pass, and never "not applicable"
    for label, body, want in (("an unchecked tool list exits 2, not 0", GOOD + "server.tools = []\n", 2),
                              ("an unchecked tool list with no tool found exits 2, not 3", "S = MCP::Server.new(tools: T)\n", 2)):
        with tempfile.TemporaryDirectory(prefix="mcp-annotations-") as d:
            (Path(d) / "app").mkdir()
            (Path(d) / "app" / "a.rb").write_text(body, encoding="utf-8")
            code = _quiet_main(["--root", d])
        ok = code == want
        failed += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {label}" + ("" if ok else f" -> exit {code}"))
    # #1873: the exit-3 site, driven through main(): a project with no MCP tool is NOT APPLICABLE (3), which the gate runner grades as n/a and never fails.
    with tempfile.TemporaryDirectory(prefix="mcp-annotations-") as d:
        (Path(d) / "app").mkdir()
        (Path(d) / "app" / "user.rb").write_text("class User < ApplicationRecord\nend\n", encoding="utf-8")
        code = _quiet_main(["--root", d])
    if code != 3:
        print(f"FAIL no MCP tool in app/ or lib/ is not applicable (exit 3, n/a), never a pass: exit {code}")
        failed += 1
    else:
        print("ok   no MCP tool in app/ or lib/ is not applicable (exit 3, n/a)")
    with tempfile.TemporaryDirectory(prefix="mcp-annotations-") as d:
        (Path(d) / "app").mkdir()
        (Path(d) / "app" / "bad.rb").write_bytes(b"\xff\xfe")
        try:
            scan(Path(d))
            failed += 1
            print("FAIL an unreadable source file is unusable")
        except Unusable:
            print("ok   an unreadable source file is unusable")
    total = len(CASES) + 4
    print(f"{total - failed}/{total} passed")
    return 1 if failed else 0


def _quiet_main(argv: list[str]) -> int:
    import contextlib
    import io

    with contextlib.redirect_stdout(io.StringIO()):
        return main(argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
