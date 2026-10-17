#!/usr/bin/env python3
"""Production configuration is validated by something (#2120).

WHY IT IS A GATE. `skills/rails-8/references/auth-security.md` documents the worst trap -- `config.hosts` is empty in
production and does NOTHING -- and no gate read `config/environments/production.rb`. A downstream app shipped with
the line commented out (Retask #2060: Host-header and DNS-rebinding protection off, an emailed link built from the
request host). Static and offline, like `check_unauthenticated_writes.py`: it reads files and boots nothing.

WHAT IT READS, IN RAILS' LOAD ORDER: `config/application.rb`, then `config/environments/production.rb`, then
`config/initializers/*.rb` (sorted), as ONE sequence, so the LAST setting wins: production.rb's `config.hosts = nil` or
`.clear` empties what application.rb set. `config/routes.rb` is read for what is mounted. Comments are removed by a small
Ruby-aware scanner (strings, `#{}`, `%w[]`, regexps, heredocs and `=begin`/`=end` are understood), so a `#` inside a
string neither starts a comment nor hides code, and a setting inside a heredoc or an `=begin` block is not a setting.

A setting made only CONDITIONALLY does not count as made: inside an `if`/`unless`/`case`/`while` block, under a trailing
`if`/`unless` modifier, or with a ternary or `ENV` value. A static check cannot know the branch, so it fails closed. Five
rules, each a finding id:
  hosts           `config.hosts` ends non-empty: assigned, `<<`, `+=`, `.push`, `.concat` ... with a literal list or host,
                  unconditionally. `= nil`, `= []` and `.clear` empty it (even conditionally).
  force-ssl       the last setting is `config.force_ssl = true`, literally and unconditionally (`assume_ssl` is not it).
  local-requests  `config.consider_all_requests_local` is not `true`; a conditional or non-literal value is unjudgeable
                  (`= (true)`, `= true if ENV[...]`) and a finding: set it to a literal `false`.
  wildcard-cors   no Rack::Cors `origins` that allows everyone: `"*"`, `%w[*]`, a constant or variable bound to one, a
                  `/.*/` or `/.+/` regexp, or a block whose body is `true`.
  debug-route     no dev-only engine or route (letter_opener, rails_db, GraphiQL, /rails/info, /rails/mailers) mounted
                  outside a development guard, and no admin/job dashboard (Sidekiq::Web, MissionControl::Jobs::Engine,
                  PgHero, Blazer, Flipper::UI) mounted outside a development guard OR an access constraint
                  (`constraints ... do`, `authenticate ... do`, or a `constraints:` option on the mount).
Credential literals are NOT checked here: secret detection is #2121, which adopts an established scanner.

LIMITS (not read): a setting made in a file the sequence above does not list, through a method call or a gem; an engine not
named above; a `/` read as division where Ruby reads a regexp (or the reverse); string forms beyond `'`, `"`, `` ` ``, `%`
literals and heredocs; a character literal (`?#`, `?"`) is read as a quote or a comment, which fails closed (a false finding,
never a missed one); an auth constraint that is a lambda defined elsewhere is trusted as a constraint, not evaluated.
Such a project declares the exemption with a reason.

EXEMPTIONS are declared, never inferred, one file per project:
    .rails-flow/production-config.json
    {"exempt": [{"rule": "hosts", "reason": "host filtered at the proxy (named): kamal-proxy host retask.example"}]}
An entry without a rule or a reason, for an unknown rule, or for a rule that already passes, is itself a finding.
Without the declaration the rule still fails.

Run:  check_production_config.py [--root DIR]
      check_production_config.py --selftest
Exit: 0 clean · 1 finding(s) · 2 unusable (a config file is unreadable) · 3 not applicable (no production.rb)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

PRODUCTION = Path("config/environments/production.rb")
APPLICATION = Path("config/application.rb")
INITIALIZERS = Path("config/initializers")
ROUTES = Path("config/routes.rb")
EXEMPT_FILE = Path(".rails-flow/production-config.json")
RULES = ("hosts", "force-ssl", "local-requests", "wildcard-cors", "debug-route")

DEBUG_ROUTE = re.compile(r"\b(?:LetterOpenerWeb|RailsDb|GraphiQL)\b|[\"']/?rails/(?:info|mailers|conductor)")
ADMIN_MOUNT = re.compile(r"\b(?:Sidekiq::Web|Sidekiq::Pro::Web|MissionControl::Jobs::Engine|PgHero::Engine|Blazer::Engine|Flipper::UI)\b")
DEV_ONLY = (r"(?:Rails\.env\.(?:development|test|local)\?(?:\s*\|\|\s*Rails\.env\.(?:development|test|local)\?)*"
            r"|!\s*Rails\.env\.production\?)")
GUARD_BLOCK = re.compile(rf"^(?:if\s+{DEV_ONLY}|unless\s+Rails\.env\.production\?)\s*$")
GUARD_MODIFIER = re.compile(rf"\b(?:if\s+{DEV_ONLY}|unless\s+Rails\.env\.production\?)\s*$")
ACCESS_BLOCK = re.compile(r"^(?:constraints|authenticate|authenticated)\b.*\bdo(?:\s*\|[^|]*\|)?$|^(?:constraints|authenticate|authenticated)\b[^=]*\{\s*$")
BLOCK_OPEN = re.compile(r"^(?:if|unless|case|while|until)\b|\bdo(?:\s*\|[^|]*\|)?$")
APPEND_METHODS = r"(?:push|concat|append|prepend|unshift|insert)"


class Unusable(RuntimeError):
    pass


def read(root: Path, rel: Path) -> str | None:
    path = root / rel
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise Unusable(f"{rel} is unreadable: {exc}") from exc


# ---- a Ruby-aware comment scanner ------------------------------------------------------------------------------
OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}", "<": ">"}
HEREDOC = re.compile(r"<<([~-]?)(['\"]?)([A-Z_][A-Z0-9_]*)\2")
BEFORE_LITERAL = set("(,=[{|&!~?:;<>+-*%^")
KEYWORD_BEFORE = re.compile(r"(?:^|\W)(?:if|unless|when|and|or|not|return|while|until|then)\s*$")


def scan(src: str) -> list[tuple[int, str, str]]:
    """Per physical line (number, code, masked). `code` is the line with comments, `=begin` blocks removed and strings
    KEPT; `masked` is the same with every string's content (heredoc bodies included) blanked to `_`, so keywords and
    brackets can be read from it without a string fooling them. Both have the same length."""
    lines: list[tuple[int, str, str]] = []
    cur_c: list[str] = []
    cur_m: list[str] = []
    stack: list[list] = []          # ["str", closer, opener, interp, depth, regex] / ["interp", depth]
    pending: list[tuple[str, str]] = []
    state = {"ln": 1}

    def emit(ch: str, in_str: bool) -> None:
        cur_c.append(ch)
        cur_m.append("_" if in_str and ch != "\n" else ch)

    def newline() -> None:
        lines.append((state["ln"], "".join(cur_c), "".join(cur_m)))
        cur_c.clear()
        cur_m.clear()
        state["ln"] += 1

    def prev_allows_literal() -> bool:
        so_far = "".join(cur_m).rstrip()
        return not so_far or so_far[-1] in BEFORE_LITERAL or bool(KEYWORD_BEFORE.search(so_far))

    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        top = stack[-1] if stack else None
        if ch == "\n":
            newline()
            i += 1
            while pending and not stack:
                kind, ident = pending.pop(0)
                while i < n:
                    j = src.find("\n", i)
                    j = n if j < 0 else j
                    raw = src[i:j]
                    for c2 in raw:
                        emit(c2, True)
                    i = min(j + 1, n)
                    newline()
                    if (raw.strip() if kind else raw) == ident:
                        break
            continue
        if top is None:
            if ch == "#":
                while i < n and src[i] != "\n":
                    i += 1
                continue
            if ch == "_" and not cur_c and src.startswith("__END__", i) and src[i + 7:i + 8] in ("", "\n", "\r"):
                break       # DATA follows: nothing after `__END__` is code
            if ch == "=" and not cur_c and src.startswith("=begin", i):
                while i < n:
                    j = src.find("\n", i)
                    j = n if j < 0 else j
                    done = src.startswith("=end", i)
                    i = min(j + 1, n)
                    newline()
                    if done:
                        break
                continue
            if ch == "<":
                hm = HEREDOC.match(src, i)
                if hm and prev_allows_literal() or (hm and "".join(cur_m).rstrip()[-1:] in ("=", "(", ",")):
                    pending.append((hm.group(1), hm.group(3)))
                    for c2 in hm.group(0):
                        emit(c2, False)
                    i = hm.end()
                    continue
        if top is None or top[0] == "interp":
            in_str = top is not None
            if ch in "\"'`":
                stack.append(["str", ch, None, ch != "'", 0, False])
                emit(ch, in_str)
                i += 1
                continue
            if top is None and ch == "/" and prev_allows_literal():
                stack.append(["str", "/", None, True, 0, True])
                emit(ch, False)
                i += 1
                continue
            if top is None and ch == "%" and prev_allows_literal():
                pm = re.match(r"%([qQwWiIrsx]?)([^\w\s])", src[i:i + 3])
                if pm:
                    letter, opener = pm.groups()
                    stack.append(["str", OPEN_TO_CLOSE.get(opener, opener), opener if opener in OPEN_TO_CLOSE else None,
                                  letter in ("", "Q", "W", "I", "r", "x"), 0, letter == "r"])
                    for c2 in pm.group(0):
                        emit(c2, False)
                    i += len(pm.group(0))
                    continue
            if top is not None:
                if ch == "{":
                    top[1] += 1
                elif ch == "}":
                    if top[1] == 0:
                        stack.pop()
                    else:
                        top[1] -= 1
                emit(ch, True)
                i += 1
                continue
            emit(ch, False)
            i += 1
            continue
        # inside a string / regexp / % literal
        _, closer, opener, interp, depth, regex = top
        if ch == "\\" and i + 1 < n and src[i + 1] != "\n":
            emit(ch, True)
            emit(src[i + 1], True)
            i += 2
            continue
        if ch == "#" and interp and i + 1 < n and src[i + 1] == "{":
            emit("#", True)
            emit("{", True)
            stack.append(["interp", 0])
            i += 2
            continue
        if opener and ch == opener:
            top[4] += 1
            emit(ch, True)
        elif ch == closer:
            if top[4] > 0:
                top[4] -= 1
                emit(ch, True)
            else:
                stack.pop()
                emit(ch, bool(stack))
        else:
            emit(ch, True)
        i += 1
    if cur_c or not lines:
        newline()
    return lines


def code_lines(src: str) -> list[tuple[int, str]]:
    """(line number, code) for every non-blank physical line, comments removed and strings kept."""
    return [(n, c) for n, c, m in scan(src) if m.strip()]


def unfinished(m: str) -> bool:
    opens = sum(m.count(c) for c in "([{")
    closes = sum(m.count(c) for c in ")]}")
    return opens > closes or bool(re.search(r"(?:,|\\|&&|\|\||=)\s*$", m))


def statements(src: str) -> list[tuple[int, str, str, bool]]:
    """(first line, code, masked, conditional) per logical statement. Continuation lines are joined, `;` splits, and the
    block structure is tracked: a statement is CONDITIONAL inside an `if`/`unless`/`case`/`while` block or under a
    trailing `if`/`unless`/`while`/`until` modifier."""
    lines = [(n, c, m) for n, c, m in scan(src) if m.strip()]
    out = []
    stack: list[bool] = []
    i = 0
    while i < len(lines):
        n, c, m = lines[i]
        c, m = c.strip(), m.strip()
        j = i
        while unfinished(m) and j + 1 < len(lines):
            j += 1
            c += " " + lines[j][1].strip()
            m += " " + lines[j][2].strip()
        i = j + 1
        parts, start = [], 0
        for k, ch in enumerate(m):
            if ch == ";":
                parts.append((c[start:k], m[start:k]))
                start = k + 1
        parts.append((c[start:], m[start:]))
        for pc, pm in parts:
            pc, pm = pc.strip(), pm.strip()
            if not pm:
                continue
            if re.match(r"end\b", pm):
                if stack:
                    stack.pop()
            elif re.match(r"(?:if|unless|case|while|until)\b", pm):
                stack.append(True)
            elif re.match(r"(?:begin|class|module|def)\b", pm) or re.search(r"\bdo(?:\s*\|[^|]*\|)?$", pm):
                stack.append(False)
            elif re.match(r"(?:else|elsif|when|rescue|ensure)\b", pm):
                continue
            else:
                modifier = bool(re.search(r"(?<=\S)\s+(?:if|unless|while|until)\b", pm))
                out.append((n, pc, pm, any(stack) or modifier))
    return out


# ---- settings, evaluated in load order -----------------------------------------------------------------------
def events(rel: Path, src: str, name: str) -> list[dict]:
    """Every statement that changes `config.<name>`: assign, append or clear, with its value and whether it is conditional."""
    pat = re.compile(rf"^(?:Rails\.application\.)?config\.{re.escape(name)}"
                     rf"(?:(?P<clear>\.clear\b)|\.(?P<meth>{APPEND_METHODS})\b\(?(?P<arg>.*?)\)?$"
                     r"|\s*(?P<op><<|\+=|\|=|=(?![=~]))\s*(?P<val>.*))$")
    out = []
    for n, c, m, cond in statements(src):
        # a trailing modifier is not part of the value (`= nil if ENV["X"]` assigns nil, conditionally)
        cut = re.search(r"(?<=\S)\s+(?:if|unless|while|until)\b", m)
        if cut:
            c, m = c[:cut.start()], m[:cut.start()]
        mm = pat.match(m)
        if not mm:
            continue
        if mm.group("clear"):
            out.append({"rel": rel, "line": n, "op": "clear", "value": "", "masked": "", "cond": cond})
        elif mm.group("meth"):
            out.append({"rel": rel, "line": n, "op": "append", "value": c[mm.start("arg"):mm.end("arg")],
                        "masked": mm.group("arg"), "cond": cond})
        else:
            op = "assign" if mm.group("op") == "=" else "append"
            out.append({"rel": rel, "line": n, "op": op, "value": c[mm.start("val"):mm.end("val")],
                        "masked": mm.group("val"), "cond": cond})
    return out


def classify(value: str, masked: str) -> str:
    """empty / literal / dynamic for a hosts-like value."""
    if re.sub(r"\s+", "", value) in ("nil", "[]", "%w[]", "%i[]"):
        return "empty"
    if re.search(r"\bENV\b|\s\?\s.*\s:\s", masked) or not re.match(r"[\[\"'/%]", value):
        return "dynamic"
    return "literal"


def hosts_state(evs: list[dict]) -> tuple[bool, str | None]:
    """(non-empty at the end, why a setting was not counted)."""
    state, why = False, None
    for ev in evs:
        at = f"{ev['rel']}:{ev['line']}"
        if ev["op"] == "clear":
            state, why = False, f"emptied by `.clear` at {at}"
            continue
        cls = classify(ev["value"], ev["masked"])
        if ev["op"] == "assign" and cls == "empty":
            state, why = False, f"emptied at {at}"
        elif ev["cond"] or cls == "dynamic":
            why = f"set only {'conditionally' if ev['cond'] else 'with a non-literal value'} at {at}"
        else:
            state = True
    return state, why


def bool_state(evs: list[dict]) -> tuple[str | None, str | None]:
    """The last setting of a boolean: 'true', 'false', or 'unjudgeable' when it is conditional or not a literal."""
    state, at = None, None
    for ev in evs:
        v = ev["value"].strip()
        if ev["op"] == "assign" and not ev["cond"] and v in ("true", "false"):
            state = v
        else:
            state = "unjudgeable"
        at = f"{ev['rel']}:{ev['line']}"
    return state, at


# ---- CORS ------------------------------------------------------------------------------------------------------
def has_wildcard(code: str) -> bool:
    if re.search(r"[\"']\*[\"']", code):
        return True
    for lm in re.finditer(r"%[wi][\[(]([^\])]*)[\])]", code):
        if "*" in lm.group(1).split():
            return True
    return bool(re.search(r"/(?:\\A)?\.[*+](?:\\z)?/|%r[{(\[]\.[*+][})\]]", code))


def wildcard_names(sources: list[tuple[Path, str]]) -> set[str]:
    names = set()
    for _rel, src in sources:
        for _n, c, m, _cond in statements(src):
            am = re.match(r"^(?:@{0,2}|\$?)([A-Za-z_]\w*)\s*=(?![=~])\s*(.*)$", m)
            if am and has_wildcard(c[am.start(2):am.end(2)]):
                names.add(am.group(1))
    return names


def wildcard_origins(rel: Path, src: str, names: set[str]) -> list[str]:
    """`file:line` of every `origins` that allows everyone."""
    out = []
    for n, c, m, _cond in statements(src):
        if re.match(r"^origins\b", m):
            if has_wildcard(c) or names & set(re.findall(r"\b[A-Za-z_]\w*\b", m)):
                out.append(f"{rel}:{n}")
            elif re.match(r"^origins\s*(?:\(\s*\))?\s*\{\s*(?:\|[^|]*\|)?\s*true\s*\}\s*$", m):
                out.append(f"{rel}:{n}")
    lines = [(n, c.strip(), m.strip()) for n, c, m in scan(src) if m.strip()]
    for k, (n, _c, m) in enumerate(lines):
        if re.match(r"^origins\s*(?:\(\s*\))?\s*do\b", m):
            body = []
            for _n2, _c2, m2 in lines[k + 1:]:
                if re.match(r"^end\b", m2):
                    break
                body.append(m2)
            if [b for b in body if not re.fullmatch(r"\|[^|]*\|", b)] == ["true"]:
                out.append(f"{rel}:{n}")
    return out


# ---- routes ------------------------------------------------------------------------------------------------------
def unguarded_debug_routes(src: str) -> list[tuple[int, str]]:
    """Dev-only mounts outside a development guard, and admin dashboards outside a development guard or an access
    constraint. The guard stack holds (development guard, access constraint) per open block; `else` is not guarded."""
    stack: list[list[bool]] = []
    out = []
    for n, c, m in scan(src):
        s, code = m.strip(), c.strip()
        if not s:
            continue
        if re.match(r"^end\b", s):
            if stack:
                stack.pop()
            continue
        if re.match(r"^(?:else|elsif)\b", s):
            if stack:
                stack[-1][0] = False
            continue
        modified = bool(GUARD_MODIFIER.search(s)) and not re.match(r"^(?:if|unless)\b", s)
        dev = any(f[0] for f in stack) or modified
        access = any(f[1] for f in stack) or bool(re.search(r"\bconstraints\s*:|\bconstraints\s*=>", s))
        if DEBUG_ROUTE.search(code) and not dev:
            out.append((n, code))
        elif ADMIN_MOUNT.search(code) and not dev and not access:
            out.append((n, code))
        if BLOCK_OPEN.search(s) and not modified:
            stack.append([bool(GUARD_BLOCK.match(s)), bool(ACCESS_BLOCK.match(s))])
    return out


def load_exempt(root: Path) -> tuple[dict[str, str], list[str]]:
    path = root / EXEMPT_FILE
    if not path.is_file():
        return {}, []
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("exempt", [])
    except (ValueError, AttributeError) as exc:
        return {}, [f"  [bad-exemption] {EXEMPT_FILE} is unreadable: {exc}"]
    exempt, problems = {}, []
    for e in entries:
        rule, reason = (e or {}).get("rule"), ((e or {}).get("reason") or "").strip()
        if not rule or not reason:
            problems.append(f"  [bad-exemption] {EXEMPT_FILE}: every exemption needs a rule and a reason -- got {e!r}")
        elif rule not in RULES:
            problems.append(f"  [bad-exemption] {EXEMPT_FILE}: unknown rule {rule!r} (rules: {', '.join(RULES)})")
        else:
            exempt[rule] = reason
    return exempt, problems


def check(root: Path) -> tuple[int, list[str]]:
    try:
        prod = read(root, PRODUCTION)
        if prod is None:
            return 3, [f"not applicable: no {PRODUCTION}"]
        # Rails' load order: application.rb, the environment file, then the initializers
        sources: list[tuple[Path, str]] = [(APPLICATION, read(root, APPLICATION) or ""), (PRODUCTION, prod)]
        for p in sorted((root / INITIALIZERS).glob("*.rb")) if (root / INITIALIZERS).is_dir() else []:
            sources.append((p.relative_to(root), read(root, p.relative_to(root)) or ""))
        routes = read(root, ROUTES) or ""
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    exempt, problems = load_exempt(root)
    failing: dict[str, str] = {}

    def evs(name: str) -> list[dict]:
        return [e for rel, src in sources for e in events(rel, src, name)]

    hosts_ok, why = hosts_state(evs("hosts"))
    if not hosts_ok:
        commented = next((n for n, line in enumerate(prod.splitlines(), 1) if re.match(r"^\s*#\s*config\.hosts\b", line)), None)
        where = (why if why else f"{PRODUCTION}:{commented} has it commented out" if commented
                 else f"{PRODUCTION} never sets it")
        failing["hosts"] = (f"{where}, so Host-header and DNS-rebinding protection is off in production "
                            "(auth-security.md: `config.hosts` is empty in production and does nothing). Set it "
                            f"unconditionally with a literal list, or declare an exemption in {EXEMPT_FILE} whose reason "
                            "names the proxy that filters Host")
    ssl, ssl_at = bool_state(evs("force_ssl"))
    if ssl != "true":
        failing["force-ssl"] = (f"the last `config.force_ssl` setting is {'unjudgeable (conditional or not a literal) at ' + ssl_at if ssl == 'unjudgeable' else 'false at ' + ssl_at if ssl == 'false' else 'missing'}: "
                                f"set `config.force_ssl = true` unconditionally in {PRODUCTION} (`assume_ssl` only tells Rails the "
                                "proxy spoke https; the cookie still goes out without the Secure flag)")
    local, local_at = bool_state(evs("consider_all_requests_local"))
    if local in ("true", "unjudgeable"):
        failing["local-requests"] = (f"`config.consider_all_requests_local` is {'true' if local == 'true' else 'unjudgeable (conditional or not a literal)'} "
                                     f"at {local_at}: stack traces are shown in production unless it is a literal `false`")
    names = wildcard_names(sources)
    cors = [loc for rel, src in sources for loc in wildcard_origins(rel, src, names)]
    if cors:
        failing["wildcard-cors"] = "a wildcard CORS origin: " + ", ".join(cors)
    dbg = unguarded_debug_routes(routes)
    if dbg:
        failing["debug-route"] = ("a dev-only route or an admin dashboard is mounted in production without a guard: "
                                  + "; ".join(f"{ROUTES}:{n} `{s}`" for n, s in dbg)
                                  + " -- wrap a dev-only one in `if Rails.env.development?`, put a dashboard behind `constraints`/`authenticate`")

    findings = list(problems)
    for rule in RULES:
        if rule in failing and rule not in exempt:
            findings.append(f"  [{rule}] {failing[rule]}")
    for rule in sorted(set(exempt) - set(failing)):
        findings.append(f"  [stale-exemption] {rule} is exempted in {EXEMPT_FILE} but the rule passes")
    if findings:
        return 1, [f"{len(findings)} finding(s) in the production configuration:", *findings]
    return 0, [f"production configuration: {len(RULES) - len(failing)} of {len(RULES)} rules hold, "
               f"{len(failing)} exempted with a reason" if failing else
               f"production configuration: all {len(RULES)} rules hold"]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_production_config.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, lines = check(a.root.resolve())
    print("\n".join(lines))
    return code


GOOD_PRODUCTION = """Rails.application.configure do
  config.consider_all_requests_local = false
  config.assume_ssl = true
  config.force_ssl = true
  config.hosts = [ "retask.example", /.*\\.retask\\.example/ ]
end
"""


def selftest() -> int:
    import contextlib
    import io
    import tempfile

    fails: list[str] = []

    def check_(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{label} {detail}".rstrip())

    def app(t: Path, production: str | None = GOOD_PRODUCTION, application: str = "", inits: dict | None = None,
            routes: str = "", exempt=None, raw_exempt: str | None = None) -> Path:
        (t / "config" / "environments").mkdir(parents=True)
        (t / "config" / "initializers").mkdir()
        if production is not None:
            (t / PRODUCTION).write_text(production)
        (t / APPLICATION).write_text(application)
        (t / ROUTES).write_text(routes)
        for name, body in (inits or {}).items():
            (t / INITIALIZERS / name).write_text(body)
        if exempt is not None or raw_exempt is not None:
            (t / EXEMPT_FILE).parent.mkdir()
            (t / EXEMPT_FILE).write_text(raw_exempt if raw_exempt is not None else json.dumps({"exempt": exempt}))
        return t

    def ids(out: list[str]) -> set[str]:
        return {m.group(1) for line in out for m in [re.match(r"\s*\[([\w-]+)\]", line)] if m}

    def prod_with(line: str, base: str = GOOD_PRODUCTION) -> str:
        return base.replace('  config.hosts = [ "retask.example", /.*\\.retask\\.example/ ]\n', line)

    def scanned(src: str) -> str:
        return "\n".join(c for _n, c, _m in scan(src))

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        n = iter(range(1000))

        def run(**kw) -> tuple[int, list[str]]:
            return check(app(t / f"a{next(n)}", **kw))

        code, out = run()
        check_("CONTROL: a configuration that holds every rule is clean", code == 0, f"{code} {out}")

        # the scanner: comments only, strings kept (#2134 review)
        check_("scan: a # inside a string does not start a comment", 'x = "a # b"' in scanned('x = "a # b" # real\n'), scanned('x = "a # b" # real\n'))
        check_("scan: the real comment after it is removed", "real" not in scanned('x = "a # b" # real\n'))
        check_("scan: single quotes keep a #", "x = 'a#b'" in scanned("x = 'a#b' # c\n"))
        check_("scan: a #{} interpolation with a nested string and a # keeps the whole string", 'x = "a#{"#"}b"' in scanned('x = "a#{"#"}b" # c\n') and "c" not in scanned('x = "a#{"#"}b" # c\n').split("b")[-1])
        check_("scan: a regexp holding a # keeps it", "x = /a#b/" in scanned("x = /a#b/ # c\n"))
        check_("scan: %w[] holding a # keeps it", "%w[a#b c]" in scanned("x = %w[a#b c] # c\n"))
        check_("scan: =begin/=end is removed", "force_ssl" not in scanned("=begin\nconfig.force_ssl = true\n=end\nx = 1\n") and "x = 1" in scanned("=begin\nconfig.force_ssl = true\n=end\nx = 1\n"))
        check_("scan: nothing after a line that is exactly __END__ is code", "force_ssl" not in scanned("x = 1\n__END__\nconfig.force_ssl = true\n") and "x = 1" in scanned("x = 1\n__END__\nconfig.force_ssl = true\n"))
        check_("scan: __END__ inside a longer word or after code is not the marker", "force_ssl" in scanned("__END__x\nconfig.force_ssl = true\n") and "force_ssl" in scanned("y = 1 # __END__\nconfig.force_ssl = true\n"))
        heredoc = 'x = <<~EOS\n  config.force_ssl = true # not code\nEOS\ny = 2\n'
        masked = "\n".join(m for _n, _c, m in scan(heredoc))
        check_("scan: a heredoc body is blanked in the masked view and the code after it is kept", "force_ssl" not in masked and "y = 2" in masked, masked)
        check_("scan: the line after a heredoc keeps its own number", dict((c.strip(), ln) for ln, c, _m in scan("x = <<~E\n  b\nE\nz = 1\n")).get("z = 1") == 4)
        check_("scan: a comment inside the program text of an unterminated string does not crash", isinstance(scan('x = "abc\n'), list))

        # hosts: the Retask #2060 shape is the trap itself
        trap = prod_with('  # config.hosts = [\n  #   "example.com",\n  # ]\n')
        code, out = run(production=trap)
        check_("a commented-out config.hosts is a finding that names its line", code == 1 and ids(out) == {"hosts"}
               and any("production.rb:5 has it commented out" in line for line in out), f"{code} {out}")
        code, out = run(production=prod_with(""))
        check_("a config.hosts that is never mentioned is a finding", code == 1 and ids(out) == {"hosts"}
               and any("never sets it" in line for line in out), f"{out}")
        for label, line in (("= nil", "config.hosts = nil"), ("= []", "config.hosts = []"),
                            (".clear", "config.hosts.clear"), ("an empty wrapped list", "config.hosts = [\n  ]")):
            code, out = run(production=prod_with(f"  {line}\n"))
            check_(f"config.hosts {label} is unset, so a finding", code == 1 and "hosts" in ids(out), f"{out}")
        for label, line in (("<<", 'config.hosts << "retask.example"'), ("+=", 'config.hosts += ["retask.example"]'),
                            (".push(", 'config.hosts.push("retask.example")'), (".concat(", 'config.hosts.concat(["retask.example"])'),
                            ("|=", 'config.hosts |= ["retask.example"]')):
            code, out = run(production=prod_with(f"  {line}\n"))
            check_(f"config.hosts {label} a host is set", code == 0, f"{out}")
        code, out = run(production=trap, application='  config.hosts = ["a.example"]\n')
        check_("config.hosts set in application.rb counts", code == 0, f"{out}")
        code, out = run(production=trap, inits={"hosts.rb": 'Rails.application.config.hosts = ["a.example"]\n'})
        check_("an initializer assigning Rails.application.config.hosts counts", code == 0, f"{out}")
        code, out = run(production=trap, inits={"hosts.rb": 'Rails.application.configure do\n  config.hosts = ["a.example"]\nend\n'})
        check_("an initializer's configure block setting config.hosts counts", code == 0, f"{out}")
        code, out = run(production=prod_with("  config.hosts.clear\n"), inits={"hosts.rb": 'Rails.application.config.hosts = ["a.example"]\n'})
        check_("CONTROL: an initializer that sets hosts AFTER production.rb's clear leaves them set", code == 0, f"{out}")

        # load order: the later setting wins (#2134 review, the exact #2060 trap)
        app_hosts = '  config.hosts = ["a.example"]\n'
        for label, line in (("= nil", "config.hosts = nil"), (".clear", "config.hosts.clear"), ("= []", "config.hosts = []")):
            code, out = run(production=prod_with(f"  {line}\n"), application=app_hosts)
            check_(f"application.rb sets hosts, production.rb `{label}` empties them: a finding that names production.rb", code == 1 and "hosts" in ids(out)
                   and any("production.rb" in line for line in out), f"{out}")
        code, out = run(production=prod_with(""), application=app_hosts, inits={"z.rb": "Rails.application.config.hosts = nil\n"})
        check_("an initializer that empties hosts after application.rb set them is a finding", code == 1 and "hosts" in ids(out), f"{out}")
        code, out = run(production=prod_with("  config.hosts.clear\n"), application=app_hosts, inits={"z.rb": 'Rails.application.config.hosts = ["b.example"]\n'})
        check_("CONTROL: set, cleared, set again in load order is set", code == 0, f"{out}")

        # a # inside a string is not a comment, and hides nothing (#2134 review)
        code, out = run(production=prod_with('  config.hosts = [] ; x = "#"\n'))
        check_("`config.hosts = [] ; x = \"#\"` is an empty list, so a finding", code == 1 and "hosts" in ids(out), f"{out}")
        code, out = run(production=prod_with('  config.hosts = ["a#b.example"] # note\n'))
        check_("CONTROL: a host holding a # is set, and the trailing comment is ignored", code == 0, f"{out}")

        # a setting made only conditionally is not made (#2134 review)
        for label, body in (("an `if ENV` block", '  if ENV["NEVER"]\n    config.hosts = ["a.example"]\n  end\n'),
                            ("an `unless` block", '  unless ENV["X"]\n    config.hosts = ["a.example"]\n  end\n'),
                            ("a trailing `if` modifier", '  config.hosts << "a.example" if ENV["NEVER"]\n'),
                            ("a trailing `unless` modifier", '  config.hosts = ["a.example"] unless ENV["X"]\n'),
                            ("a ternary", '  config.hosts = ENV["X"] ? ["a.example"] : []\n'),
                            ("an ENV-derived value", '  config.hosts = ENV.fetch("HOSTS").split(",")\n'),
                            ("a case branch", '  case ENV["X"]\n  when "1"\n    config.hosts = ["a.example"]\n  end\n')):
            code, out = run(production=prod_with(body))
            check_(f"config.hosts set only by {label} is a finding that says why", code == 1 and "hosts" in ids(out)
                   and any("only conditionally" in line or "non-literal" in line for line in out), f"{out}")
        code, out = run(production=prod_with('  if ENV["X"]\n    config.hosts = ["a.example"]\n  end\n  config.hosts = ["b.example"]\n'))
        check_("CONTROL: an unconditional setting after the conditional one counts", code == 0, f"{out}")
        code, out = run(production=prod_with('  config.hosts = ["a.example"]\n  config.hosts = nil if ENV["X"]\n'))
        check_("a conditional EMPTYING fails closed", code == 1 and "hosts" in ids(out), f"{out}")

        # force_ssl
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", ""))
        check_("assume_ssl without force_ssl is a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("config.force_ssl = true", "config.force_ssl = false"))
        check_("force_ssl = false is a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", "  # config.force_ssl = true\n"))
        check_("a commented force_ssl is a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", '  config.force_ssl = true if ENV["SSL"]\n'))
        check_("force_ssl = true only under a modifier is a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", '  config.force_ssl = true\n  config.force_ssl = false if ENV["X"]\n'))
        check_("a conditional force_ssl = false after true is unjudgeable, so a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", "=begin\n  config.force_ssl = true\n=end\n"))
        check_("force_ssl = true inside =begin/=end is not a setting", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", "") + "__END__\nconfig.force_ssl = true\n")
        check_("force_ssl = true after __END__ is not a setting", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", "  x = <<~EOS\n    config.force_ssl = true\n  EOS\n"))
        check_("force_ssl = true inside a heredoc is not a setting", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", ""), application="  config.force_ssl = true\n")
        check_("CONTROL: force_ssl = true in application.rb counts", code == 0, f"{out}")

        # consider_all_requests_local
        code, out = run(production=GOOD_PRODUCTION.replace("requests_local = false", "requests_local = true"))
        check_("consider_all_requests_local = true is a finding", code == 1 and ids(out) == {"local-requests"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION, application="  config.consider_all_requests_local = true\n")
        check_("CONTROL: production.rb's false wins over application.rb's true", code == 0, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("requests_local = false", "requests_local = (true)"))
        check_("consider_all_requests_local = (true) is unjudgeable, so a finding", code == 1 and ids(out) == {"local-requests"}
               and any("unjudgeable" in line for line in out), f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("requests_local = false", 'requests_local = true if ENV["DEBUG"]'))
        check_("consider_all_requests_local = true under a modifier is a finding", code == 1 and ids(out) == {"local-requests"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("requests_local = false", 'requests_local = ENV["DEBUG"] == "1"'))
        check_("consider_all_requests_local from ENV is unjudgeable, so a finding", code == 1 and ids(out) == {"local-requests"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.consider_all_requests_local = false\n", ""))
        check_("CONTROL: consider_all_requests_local never set is Rails' default false, so clean", code == 0, f"{out}")

        # wildcard CORS
        cors = 'Rails.application.config.middleware.insert_before 0, Rack::Cors do\n  allow do\n    origins %s\n    resource "*"\n  end\nend\n'
        code, out = run(inits={"cors.rb": cors % '"*"'})
        check_("origins \"*\" is a finding that names its file and line", code == 1 and ids(out) == {"wildcard-cors"}
               and any("cors.rb:3" in line for line in out), f"{out}")
        for label, body in (("a wildcard among other origins", "'retask.example', '*'"), ("%w[*]", "%w[*]"),
                            ("%w[a.example *]", "%w[a.example *]"), ("/.*/", "/.*/"), ("/.+/", "/.+/"),
                            ("/\\A.+\\z/", "/\\A.+\\z/"), ("a # string before it", '"#", "*"'),
                            ("an interpolated string before it", '"#{ENV["A"]}", "*"'),
                            ("a wrapped list", "'retask.example',\n      '*'")):
            code, out = run(inits={"cors.rb": cors % body})
            check_(f"origins {label} is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": 'ALLOWED = "*"\n' + cors % "ALLOWED"})
        check_("a constant bound to \"*\" is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": 'allowed = %w[*]\n' + cors % "allowed"})
        check_("a variable bound to %w[*] is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": 'ALLOWED = %w[a.example]\n' + cors % "ALLOWED"})
        check_("CONTROL: a constant bound to a named origin is clean", code == 0, f"{out}")
        code, out = run(inits={"cors.rb": cors.replace("origins %s", "origins { |source, env| true }") % ()})
        check_("an origins block returning true is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": cors.replace("origins %s", "origins do |source, env|\n      true\n    end") % ()})
        check_("a multi-line origins block returning true is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": cors.replace("origins %s", "origins { |source, env| source.end_with?(\".retask.example\") }") % ()})
        check_("CONTROL: an origins block that decides is clean", code == 0, f"{out}")
        code, out = run(application=cors % '"*"')
        check_("a wildcard in application.rb is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": cors % '"https://retask.example"'})
        check_("CONTROL: a named origin, with `resource \"*\"` in the block, is clean (a bare grep for * would flag it)", code == 0, f"{out}")
        code, out = run(inits={"cors.rb": cors % '"https://*.retask.example"'})
        check_("CONTROL: a subdomain pattern is not an any-origin wildcard (a bare grep for * would flag it)", code == 0, f"{out}")
        code, out = run(inits={"cors.rb": "  # origins '*'\n"})
        check_("a commented wildcard is not a finding", code == 0, f"{out}")

        # debug routes and admin dashboards
        code, out = run(routes='Rails.application.routes.draw do\n  mount LetterOpenerWeb::Engine, at: "/letter_opener"\nend\n')
        check_("an unguarded letter_opener mount is a finding that names its line", code == 1 and ids(out) == {"debug-route"}
               and any("routes.rb:2" in line for line in out), f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  if Rails.env.development?\n    mount LetterOpenerWeb::Engine, at: "/letter_opener"\n  end\nend\n')
        check_("CONTROL: the same mount inside `if Rails.env.development?` is clean", code == 0, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  mount LetterOpenerWeb::Engine, at: "/lo" if Rails.env.development?\nend\n')
        check_("CONTROL: a trailing `if Rails.env.development?` modifier is clean", code == 0, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  unless Rails.env.production?\n    mount GraphiQL::Rails::Engine, at: "/graphiql"\n  end\nend\n')
        check_("CONTROL: `unless Rails.env.production?` is a guard", code == 0, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  if Rails.env.development?\n    get "/x", to: "x#y"\n  else\n    mount LetterOpenerWeb::Engine, at: "/lo"\n  end\nend\n')
        check_("the else branch of a development guard is NOT guarded", code == 1 and "debug-route" in ids(out), f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  if Rails.env.development?\n    get "/x", to: "x#y"\n  end\n  mount RailsDb::Engine, at: "/rails/db"\nend\n')
        check_("a mount AFTER a closed development guard is a finding", code == 1 and "debug-route" in ids(out), f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  scope "/a" do\n    mount LetterOpenerWeb::Engine, at: "/lo"\n  end\nend\n')
        check_("a mount inside an unrelated block is a finding", code == 1 and "debug-route" in ids(out), f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  # mount LetterOpenerWeb::Engine, at: "/lo"\nend\n')
        check_("a commented mount is not a finding", code == 0, f"{out}")
        for engine in ("Sidekiq::Web", "MissionControl::Jobs::Engine", "PgHero::Engine", "Blazer::Engine", "Flipper::UI.app(Flipper)"):
            code, out = run(routes=f'Rails.application.routes.draw do\n  mount {engine}, at: "/ops"\nend\n')
            check_(f"an unguarded `mount {engine}` is a finding", code == 1 and ids(out) == {"debug-route"}, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  constraints SystemHealth::AccessConstraint.new do\n    mount MissionControl::Jobs::Engine, at: "/jobs"\n  end\nend\n')
        check_("CONTROL: a dashboard inside `constraints ... do` is clean (Retask's own shape)", code == 0, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  authenticate :user, ->(u) { u.admin? } do\n    mount Sidekiq::Web => "/sidekiq"\n  end\nend\n')
        check_("CONTROL: a dashboard inside `authenticate ... do` is clean", code == 0, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  mount Sidekiq::Web, at: "/sidekiq", constraints: AdminConstraint.new\nend\n')
        check_("CONTROL: a dashboard mounted with a `constraints:` option is clean", code == 0, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  if Rails.env.development?\n    mount Sidekiq::Web, at: "/sidekiq"\n  end\nend\n')
        check_("CONTROL: a dashboard under a development guard is clean", code == 0, f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  constraints SystemHealth::AccessConstraint.new do\n    get "/x", to: "x#y"\n  end\n  mount Sidekiq::Web, at: "/sidekiq"\nend\n')
        check_("a dashboard AFTER a closed constraints block is a finding", code == 1 and "debug-route" in ids(out), f"{out}")
        code, out = run(routes='Rails.application.routes.draw do\n  constraints SystemHealth::AccessConstraint.new do\n    mount LetterOpenerWeb::Engine, at: "/lo"\n  end\nend\n')
        check_("a constraint is not a development guard: letter_opener inside `constraints` is still a finding", code == 1 and "debug-route" in ids(out), f"{out}")

        # exemptions
        why = "host filtered at the proxy (named): kamal-proxy host retask.example"
        code, out = run(production=trap, exempt=[{"rule": "hosts", "reason": why}])
        check_("an exemption with a reason clears the rule", code == 0, f"{code} {out}")
        code, out = run(production=trap, exempt=[{"rule": "hosts", "reason": "  "}])
        check_("an exemption without a reason does not clear it, and is a finding", code == 1
               and {"hosts", "bad-exemption"} <= ids(out), f"{out}")
        code, out = run(production=trap, exempt=[{"reason": why}])
        check_("an exemption without a rule is a finding", code == 1 and "bad-exemption" in ids(out), f"{out}")
        code, out = run(production=trap, exempt=[{"rule": "hosts-ish", "reason": why}])
        check_("an unknown rule is a finding", code == 1 and any("unknown rule 'hosts-ish'" in line for line in out), f"{out}")
        code, out = run(production=GOOD_PRODUCTION, exempt=[{"rule": "hosts", "reason": why}])
        check_("an exemption for a rule that passes is a stale-exemption finding", code == 1 and ids(out) == {"stale-exemption"}, f"{out}")
        code, out = run(production=trap, exempt=[{"rule": "force-ssl", "reason": why}])
        check_("an exemption for ANOTHER rule does not clear hosts", code == 1 and "hosts" in ids(out), f"{out}")
        code, out = run(production=trap, raw_exempt="{not json")
        check_("an unreadable exemption file is a finding, and the rule still fails", code == 1 and {"hosts", "bad-exemption"} <= ids(out), f"{out}")

        # every rule at once is every finding
        bad = 'Rails.application.configure do\n  config.consider_all_requests_local = true\nend\n'
        code, out = run(production=bad, inits={"cors.rb": cors % '"*"'}, routes='  mount RailsDb::Engine, at: "/db"\n')
        check_("every rule failing at once reports all five", code == 1 and ids(out) == set(RULES), f"{ids(out)}")

        # applicability and usability
        code, out = check(app(t / "na", production=None))
        check_("no production.rb is not applicable (exit 3), never clean", code == 3, f"{code} {out}")
        root = app(t / "bad")
        (root / PRODUCTION).write_bytes(b"\xff\xfe\x00")
        check_("an unreadable production.rb is UNUSABLE (exit 2), never clean", check(root)[0] == 2, f"{check(root)}")
        root = app(t / "m", production=trap)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["--root", str(root)])
        check_("main returns the check's exit code", rc == 1, f"rc={rc}")

    for f in fails:
        print(f"FAIL {f}")
    print(f"check_production_config selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
