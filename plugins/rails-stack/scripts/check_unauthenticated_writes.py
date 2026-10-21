#!/usr/bin/env python3
"""Every public write route needs a rate_limit covering its action (#1300).

WHY IT IS A GATE. #1289 made "a rate limit on every unauthenticated endpoint" part of the launch
baseline, proven only by request specs, and nothing ran it: downstream, a one-time-code check and a
magic-link sender took unlimited requests while every gate read clean. This checks it statically.

HOW. Routes come from the committed architecture graph (`docs/architecture/graph.json`, drift-checked
by `architecture-graph-drift`): each route node carries its verb, controller file and `action:<name>`.
For every POST/PATCH/PUT/DELETE route:
  1. PUBLIC is computed per action from the controller's `allow_unauthenticated_access`
     (`only:` / `except:` / bare), never from the graph's controller-wide `public` tag.
  2. It must be covered by a `rate_limit` in the same controller (`only:` / `except:` / bare).
Statements are read whole: a `%i[ ... ]` or a trailing comma continues onto the next line.

EXEMPTIONS are declared, never inferred: `.rails-flow/unauthenticated-endpoints.json`
    {"exempt": [{"route": "POST /webhooks/zoho", "reason": "HMAC-verified webhook"}]}
An entry without a reason, or for a route that does not exist, is itself a finding.

A WARNING, not a failure: `config/environments/test.rb` setting `cache_store = :null_store` while a
`rate_limit` counts through it -- the limits then do nothing in tests, so no spec can prove them. A
limiter has a real store, and is not warned about, when its call passes `store:` or when test.rb sets a
non-null `config.action_controller.cache_store`, the fix auth-security.md prescribes (#1324).

Honeypots are NOT gated: there is no static signal. They stay required by doctrine and request specs.

Run:  check_unauthenticated_writes.py [--root DIR]
      check_unauthenticated_writes.py --selftest
Exit: 0 clean (warnings may print) · 1 finding(s) · 2 unusable (no graph, or unreadable)
      · 3 not applicable (no authentication concern, so publicness cannot be computed)
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

GRAPH = Path("docs/architecture/graph.json")
AUTH_CONCERN = Path("app/controllers/concerns/authentication.rb")
EXEMPT_FILE = Path(".rails-flow/unauthenticated-endpoints.json")
WRITE_VERBS = ("POST", "PATCH", "PUT", "DELETE")
LIST = re.compile(r"(?:%[iw]\[(?P<pct>[^\]]*)\]|\[(?P<arr>[^\]]*)\]|:(?P<sym>\w+)|\"(?P<str>\w+)\")")


class Unusable(RuntimeError):
    pass


def statements(src: str, macro: str) -> list[str]:
    """Each `macro ...` call, whole: joined while a bracket is open or a line ends with a comma."""
    lines = src.splitlines()
    out = []
    for i, line in enumerate(lines):
        code = line.split("#", 1)[0]
        if not re.match(rf"^\s*{macro}\b", code):
            continue
        stmt = code
        j = i
        while (stmt.count("[") > stmt.count("]") or stmt.rstrip().endswith(",")) and j + 1 < len(lines):
            j += 1
            stmt += " " + lines[j].split("#", 1)[0]
        out.append(stmt)
    return out


def _names(stmt: str, key: str) -> set[str] | None:
    """The action names under `key:` in a macro call, or None when the key is absent."""
    m = re.search(rf"\b{key}:\s*", stmt)
    if not m:
        return None
    lm = LIST.match(stmt, m.end())
    if not lm:
        return set()
    body = lm.group("pct") or lm.group("arr") or lm.group("sym") or lm.group("str") or ""
    return set(re.findall(r"\w+", body))


def covers(stmt_list: list[str], action: str) -> bool:
    """Whether any of these macro calls applies to `action` (bare, `only:` or `except:`)."""
    for stmt in stmt_list:
        only, except_ = _names(stmt, "only"), _names(stmt, "except")
        if only is not None:
            if action in only:
                return True
        elif except_ is not None:
            if action not in except_:
                return True
        else:
            return True
    return False


def load_graph(root: Path) -> list[dict]:
    path = root / GRAPH
    if not path.is_file():
        raise Unusable(f"no {GRAPH} -- run /rails-flow:graph; without routes nothing is checked, "
                       "which is not a clean result")
    try:
        nodes = json.loads(path.read_text(encoding="utf-8"))["nodes"]
    except (ValueError, KeyError, TypeError) as exc:
        raise Unusable(f"{GRAPH} is unreadable: {exc}") from exc
    return [n for n in nodes if n.get("type") == "route"]


def load_exempt(root: Path) -> tuple[dict[str, str], list[str]]:
    path = root / EXEMPT_FILE
    if not path.is_file():
        return {}, []
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("exempt", [])
    except (ValueError, AttributeError) as exc:
        return {}, [f"{EXEMPT_FILE} is unreadable: {exc}"]
    exempt, problems = {}, []
    for e in entries:
        route, reason = (e or {}).get("route"), ((e or {}).get("reason") or "").strip()
        if not route or not reason:
            problems.append(f"{EXEMPT_FILE}: every exemption needs a route and a reason -- got {e!r}")
        else:
            exempt[route] = reason
    return exempt, problems


def check(root: Path) -> tuple[int, list[str]]:
    if not (root / AUTH_CONCERN).is_file():
        return 3, [f"not applicable: no {AUTH_CONCERN}, so which actions are public cannot be computed"]
    try:
        routes = load_graph(root)
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    exempt, problems = load_exempt(root)
    findings: list[str] = list(problems)
    public_writes = 0
    storeless_limit = False
    seen_routes = set()
    cache: dict[str, str] = {}
    for n in sorted(routes, key=lambda n: n["id"]):
        seen_routes.add(n["id"])
        verb = n["id"].split(" ", 1)[0]
        action = next((t.split(":", 1)[1] for t in n.get("tags", []) if t.startswith("action:")), None)
        rel = n.get("file")
        if verb not in WRITE_VERBS or not action or not rel or not (root / rel).is_file():
            continue
        src = cache.setdefault(rel, (root / rel).read_text(encoding="utf-8"))
        limits = statements(src, "rate_limit")
        storeless_limit = storeless_limit or any(not re.search(r"\bstore:", s) for s in limits)
        if not covers(statements(src, "allow_unauthenticated_access"), action):
            continue
        public_writes += 1
        if n["id"] in exempt:
            continue
        if not covers(limits, action):
            findings.append(f"  [unlimited-public-write] {n['id']} -- {rel}#{action} is public and no "
                            "`rate_limit` covers it")
    for route in sorted(set(exempt) - seen_routes):
        findings.append(f"  [stale-exemption] {route} is exempted in {EXEMPT_FILE} but is not a route")
    notes = []
    test_env = root / "config" / "environments" / "test.rb"
    env = test_env.read_text(encoding="utf-8") if test_env.is_file() else ""
    limiter_store = re.search(r"^\s*config\.action_controller\.cache_store\s*=\s*(\S+)", env, re.M)
    if (storeless_limit and re.search(r"^\s*config\.cache_store\s*=\s*:null_store", env, re.M)
            and not (limiter_store and limiter_store.group(1) != ":null_store")):
        notes.append("WARNING: config/environments/test.rb sets `cache_store = :null_store` and a `rate_limit` "
                     "without `store:` counts through it, so the limit does nothing in tests and no spec can "
                     "prove it. Set `config.action_controller.cache_store = :memory_store` there.")
    if findings:
        return 1, [f"{len(findings)} finding(s) across {public_writes} public write route(s):", *findings, *notes]
    return 0, [f"every one of {public_writes} public write route(s) is rate-limited or exempted with a reason",
               *notes]


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_unauthenticated_writes.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, lines = check(a.root.resolve())
    print("\n".join(lines))
    return code


def selftest() -> int:
    import contextlib
    import io
    import tempfile

    fails: list[str] = []

    def check_(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{label} {detail}".rstrip())

    # Statement joining and list forms.
    src = ("class S < ApplicationController\n"
           "  allow_unauthenticated_access only: %i[ new create\n"
           "                                          magic_link verify ]\n"
           "  rate_limit to: 10, within: 3.minutes, only: :create,\n"
           "             with: -> { redirect_to root_path }\n"
           "end\n")
    allow = statements(src, "allow_unauthenticated_access")
    check_("a %i[ ] list wrapped onto the next line is read whole", covers(allow, "verify"), str(allow))
    check_("...and an action outside it is not public", not covers(allow, "destroy"))
    limit = statements(src, "rate_limit")
    check_("a rate_limit with only: :create covers create", covers(limit, "create"))
    check_("...and not magic_link", not covers(limit, "magic_link"))
    check_("a bare macro covers every action", covers(["  rate_limit to: 5, within: 1.minute"], "anything"))
    check_("except: covers what it does not name", covers(["  rate_limit to: 5, except: %i[show]"], "create")
           and not covers(["  rate_limit to: 5, except: %i[show]"], "show"))
    check_("an array list is read", covers(["  allow_unauthenticated_access only: [:new, :create]"], "create"))
    check_("a commented-out macro is not read", statements("  # rate_limit to: 1\n", "rate_limit") == [])

    def app(tmp: Path, controllers: dict[str, str], routes: list[tuple[str, str, str]],
            exempt=None, null_store=False, auth=True) -> Path:
        (tmp / "app" / "controllers" / "concerns").mkdir(parents=True, exist_ok=True)
        if auth:
            (tmp / AUTH_CONCERN).write_text("module Authentication\nend\n", encoding="utf-8")
        for name, body in controllers.items():
            (tmp / "app" / "controllers" / f"{name}_controller.rb").write_text(body, encoding="utf-8")
        nodes = [{"id": rid, "type": "route", "file": f"app/controllers/{ctrl}_controller.rb",
                  "tags": [f"action:{act}", "public"]} for rid, ctrl, act in routes]
        (tmp / "docs" / "architecture").mkdir(parents=True, exist_ok=True)
        (tmp / GRAPH).write_text(json.dumps({"nodes": nodes}), encoding="utf-8")
        if exempt is not None:
            (tmp / ".rails-flow").mkdir(exist_ok=True)
            (tmp / EXEMPT_FILE).write_text(json.dumps({"exempt": exempt}), encoding="utf-8")
        (tmp / "config" / "environments").mkdir(parents=True, exist_ok=True)
        (tmp / "config" / "environments" / "test.rb").write_text(
            "Rails.application.configure do\n" + ("  config.cache_store = :null_store\n" if null_store else "")
            + "end\n", encoding="utf-8")
        return tmp

    sessions = src
    routes = [("POST /login", "sessions", "create"), ("POST /login/link", "sessions", "magic_link"),
              ("POST /login/code", "sessions", "verify"), ("DELETE /logout", "sessions", "destroy"),
              ("GET /login", "sessions", "new")]
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        root = app(t / "a", {"sessions": sessions}, routes)
        code, out = check(root)
        check_("the unlimited public writes are findings", code == 1
               and any("POST /login/link" in l for l in out) and any("POST /login/code" in l for l in out), f"{out}")
        check_("CONTROL: the rate-limited public write is not", not any("] POST /login --" in l for l in out), f"{out}")
        check_("a write that is not public (destroy, outside only:) is not a finding",
               not any("DELETE /logout" in l for l in out), f"{out}")
        check_("a GET is never a write finding", not any("GET /login" in l for l in out))

        fixed = sessions.replace("only: :create,", "only: %i[create magic_link verify],")
        root = app(t / "b", {"sessions": fixed}, routes)
        code, out = check(root)
        check_("CONTROL: covering every public write is clean", code == 0, f"{code} {out}")

        webhook = "class Hook < ApplicationController\n  allow_unauthenticated_access\nend\n"
        root = app(t / "c", {"sessions": fixed, "hook": webhook}, routes + [("POST /webhooks/zoho", "hook", "create")])
        check_("an unexempted webhook is a finding", any("POST /webhooks/zoho" in l for l in check(root)[1]))
        root = app(t / "d", {"sessions": fixed, "hook": webhook}, routes + [("POST /webhooks/zoho", "hook", "create")],
                   exempt=[{"route": "POST /webhooks/zoho", "reason": "HMAC-verified webhook"}])
        check_("an exemption with a reason clears it", check(root)[0] == 0, str(check(root)))
        root = app(t / "e", {"sessions": fixed, "hook": webhook}, routes + [("POST /webhooks/zoho", "hook", "create")],
                   exempt=[{"route": "POST /webhooks/zoho", "reason": ""}])
        check_("an exemption without a reason is a finding", check(root)[0] == 1
               and any("needs a route and a reason" in l for l in check(root)[1]))
        root = app(t / "f", {"sessions": fixed}, routes, exempt=[{"route": "POST /gone", "reason": "old"}])
        check_("an exemption for a route that does not exist is a finding",
               any("[stale-exemption] POST /gone" in l for l in check(root)[1]))

        root = app(t / "g", {"sessions": fixed}, routes, null_store=True)
        code, out = check(root)
        check_("null_store with rate_limit is a WARNING on a clean result", code == 0
               and any(l.startswith("WARNING:") and "null_store" in l for l in out), f"{out}")
        root = app(t / "h", {"sessions": fixed}, routes)
        check_("CONTROL: no WARNING without null_store", not any(l.startswith("WARNING") for l in check(root)[1]))
        # #1324: a limiter with its own store is not counting through the null cache_store.
        def warned(r: Path) -> bool:
            return any(l.startswith("WARNING") for l in check(r)[1])
        stored = fixed.replace("rate_limit ", "rate_limit store: RateLimits::STORE, ")
        root = app(t / "k", {"sessions": stored}, routes, null_store=True)
        check_("null_store with every rate_limit passing store: is not warned", not warned(root), f"{check(root)[1]}")
        root = app(t / "k2", {"sessions": stored.replace("rate_limit store: RateLimits::STORE, ", "rate_limit ", 1)},
                   routes, null_store=True)
        check_("CONTROL: one rate_limit without store: is still warned", warned(root), f"{check(root)[1]}")
        root = app(t / "l", {"sessions": fixed}, routes, null_store=True)
        env = root / "config" / "environments" / "test.rb"
        env.write_text(env.read_text().replace("end\n", "  config.action_controller.cache_store = :memory_store\nend\n"))
        check_("a non-null config.action_controller.cache_store is not warned", not warned(root), env.read_text())
        env.write_text(env.read_text().replace(":memory_store", ":null_store"))
        check_("CONTROL: a null config.action_controller.cache_store is still warned", warned(root), env.read_text())

        root = app(t / "i", {"sessions": fixed}, routes, auth=False)
        check_("no authentication concern: not applicable (exit 3)", check(root)[0] == 3)
        root = app(t / "j", {"sessions": fixed}, routes)
        (root / GRAPH).unlink()
        check_("no graph: UNUSABLE (exit 2), never clean", check(root)[0] == 2)

        root = app(t / "k", {"sessions": sessions}, routes)
        with contextlib.redirect_stdout(io.StringIO()):
            rc = main(["--root", str(root)])
        check_("main returns the check's exit code", rc == 1, f"rc={rc}")

    for f in fails:
        print(f"FAIL {f}")
    print(f"check_unauthenticated_writes selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
