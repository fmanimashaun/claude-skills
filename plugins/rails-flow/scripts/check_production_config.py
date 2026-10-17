#!/usr/bin/env python3
"""Production configuration is validated by something (#2120).

WHY IT IS A GATE. `skills/rails-8/references/auth-security.md` documents the worst trap -- `config.hosts` is empty in
production and does NOTHING -- and no gate read `config/environments/production.rb`. A downstream app shipped with
the line commented out (Retask #2060: Host-header and DNS-rebinding protection off, an emailed link built from the
request host). Static and offline, like `check_unauthenticated_writes.py`: it reads files and boots nothing.

WHAT IT READS. `config/environments/production.rb`, `config/application.rb` and `config/initializers/*.rb` for the
settings, `config/routes.rb` for what is mounted. Only UNCOMMENTED code counts (a `# config.hosts = [` is the trap, not
a setting). Five rules, each a finding id:
  hosts           `config.hosts` set to something non-empty. `= nil`, `= []` and `.clear` are unset.
  force-ssl       `config.force_ssl = true`. `assume_ssl` alone is not it: it only tells Rails the proxy spoke https.
  local-requests  `config.consider_all_requests_local` is not true (production.rb wins over application.rb).
  wildcard-cors   no `origins "*"` (or a match-everything regexp) in a Rack::Cors block.
  debug-route     no known dev-only engine (letter_opener, rails_db, GraphiQL, /rails/info, /rails/mailers) mounted
                  outside an `if Rails.env.development?` / `unless Rails.env.production?` guard.
Matching is structural (whole statements, never a bare grep for `*`). Credential literals are NOT checked here: secret
detection is #2121, which adopts an established scanner.

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
DEV_ONLY = (r"(?:Rails\.env\.(?:development|test|local)\?(?:\s*\|\|\s*Rails\.env\.(?:development|test|local)\?)*"
            r"|!\s*Rails\.env\.production\?)")
GUARD_BLOCK = re.compile(rf"^(?:if\s+{DEV_ONLY}|unless\s+Rails\.env\.production\?)\s*$")
GUARD_MODIFIER = re.compile(rf"\b(?:if\s+{DEV_ONLY}|unless\s+Rails\.env\.production\?)\s*$")
BLOCK_OPEN = re.compile(r"^(?:if|unless|case|begin|while|until)\b|\bdo(?:\s*\|[^|]*\|)?$")


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


def code_lines(src: str) -> list[tuple[int, str]]:
    """(line number, code with the comment removed) for every non-blank line."""
    out = []
    for n, line in enumerate(src.splitlines(), 1):
        code = line.split("#", 1)[0].rstrip()
        if code.strip():
            out.append((n, code))
    return out


def setting(src: str, name: str) -> tuple[int, str] | None:
    """The LAST uncommented `config.<name> = value` in `src` as (line, value), or None."""
    found = None
    for n, code in code_lines(src):
        m = re.match(rf"^\s*config\.{re.escape(name)}\s*=(?!=)\s*(.*)$", code)
        if m:
            found = (n, m.group(1).strip())
    return found


def hosts_set(src: str) -> int | None:
    """The line of an uncommented, NON-EMPTY `config.hosts` assignment or append, or None."""
    lines = code_lines(src)
    hit = None
    for i, (n, code) in enumerate(lines):
        if re.match(r"^\s*config\.hosts\s*<<\s*\S", code):
            hit = n
            continue
        m = re.match(r"^\s*config\.hosts\s*=(?!=)\s*(.*)$", code)
        if not m:
            if re.match(r"^\s*config\.hosts\.clear\b", code):
                hit = None
            continue
        value = m.group(1).strip()
        nxt = lines[i + 1][1].strip() if i + 1 < len(lines) else ""
        empty = value in ("nil", "[]", "%w[]", "%i[]") or (value in ("[", "%w[", "%i[") and nxt.startswith("]"))
        hit = None if empty else n
    return hit


def wildcard_origins(src: str) -> list[int]:
    """Lines of `origins` statements, read whole, that name a wildcard."""
    lines = code_lines(src)
    out = []
    for i, (n, code) in enumerate(lines):
        if not re.match(r"^\s*origins\b", code):
            continue
        stmt, j = code, i
        while (stmt.count("(") > stmt.count(")") or stmt.count("[") > stmt.count("]")
               or stmt.rstrip().endswith(",")) and j + 1 < len(lines):
            j += 1
            stmt += " " + lines[j][1]
        if re.search(r"(?:^|[\s(\[,])[\"']\*[\"']|/(?:\\A)?\.\*(?:\\z)?/", stmt):
            out.append(n)
    return out


def unguarded_debug_routes(src: str) -> list[tuple[int, str]]:
    """Dev-only mounts that are not inside (or modified by) a development-only guard."""
    stack: list[bool] = []
    out = []
    for n, code in code_lines(src):
        s = code.strip()
        if re.match(r"^end\b", s):
            if stack:
                stack.pop()
            continue
        if re.match(r"^(?:else|elsif)\b", s):
            if stack:
                stack[-1] = False
            continue
        modified = bool(GUARD_MODIFIER.search(s)) and not re.match(r"^(?:if|unless)\b", s)
        if DEBUG_ROUTE.search(s) and not any(stack) and not modified:
            out.append((n, s))
        if BLOCK_OPEN.search(s) and not modified:
            stack.append(bool(GUARD_BLOCK.match(s)))
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
        app = read(root, APPLICATION) or ""
        inits = {}
        for p in sorted((root / INITIALIZERS).glob("*.rb")) if (root / INITIALIZERS).is_dir() else []:
            inits[p.relative_to(root)] = read(root, p.relative_to(root)) or ""
        routes = read(root, ROUTES) or ""
    except Unusable as exc:
        return 2, [f"UNUSABLE: {exc}"]
    exempt, problems = load_exempt(root)
    failing: dict[str, str] = {}

    if not any(hosts_set(s) for s in (prod, app, *inits.values())):
        commented = next((n for n, line in enumerate(prod.splitlines(), 1) if re.match(r"^\s*#\s*config\.hosts\b", line)), None)
        where = f"{PRODUCTION}:{commented} has it commented out" if commented else f"{PRODUCTION} never sets it"
        failing["hosts"] = (f"{where}, so Host-header and DNS-rebinding protection is off in production "
                            "(auth-security.md: `config.hosts` is empty in production and does nothing). Set it, or "
                            f"declare an exemption in {EXEMPT_FILE} whose reason names the proxy that filters Host")
    ssl = setting(prod, "force_ssl") or setting(app, "force_ssl")
    if not ssl or ssl[1] != "true":
        failing["force-ssl"] = (f"{PRODUCTION} does not set `config.force_ssl = true` (`assume_ssl` only tells Rails the "
                                "proxy spoke https; the cookie still goes out without the Secure flag)")
    local = setting(prod, "consider_all_requests_local") or setting(app, "consider_all_requests_local")
    if local and local[1] == "true":
        failing["local-requests"] = f"`config.consider_all_requests_local = true` ({local[0]}) shows stack traces in production"
    cors = [(rel, n) for rel, s in (*inits.items(), (PRODUCTION, prod)) for n in wildcard_origins(s)]
    if cors:
        failing["wildcard-cors"] = "a wildcard CORS origin: " + ", ".join(f"{rel}:{n}" for rel, n in cors)
    dbg = unguarded_debug_routes(routes)
    if dbg:
        failing["debug-route"] = ("a dev-only route is mounted in production: "
                                  + "; ".join(f"{ROUTES}:{n} `{s}`" for n, s in dbg)
                                  + " -- wrap it in `if Rails.env.development?`")

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

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        n = iter(range(1000))

        def run(**kw) -> tuple[int, list[str]]:
            return check(app(t / f"a{next(n)}", **kw))

        code, out = run()
        check_("CONTROL: a configuration that holds every rule is clean", code == 0, f"{code} {out}")

        # hosts: the Retask #2060 shape is the trap itself
        trap = GOOD_PRODUCTION.replace('  config.hosts = [ "retask.example", /.*\\.retask\\.example/ ]\n',
                                       '  # config.hosts = [\n  #   "example.com",\n  # ]\n')
        code, out = run(production=trap)
        check_("a commented-out config.hosts is a finding that names its line", code == 1 and ids(out) == {"hosts"}
               and any("production.rb:5 has it commented out" in line for line in out), f"{code} {out}")
        code, out = run(production=GOOD_PRODUCTION.replace('  config.hosts = [ "retask.example", /.*\\.retask\\.example/ ]\n', ""))
        check_("a config.hosts that is never mentioned is a finding", code == 1 and ids(out) == {"hosts"}
               and any("never sets it" in line for line in out), f"{out}")
        for label, line in (("= nil", "config.hosts = nil"), ("= []", "config.hosts = []"),
                            (".clear", "config.hosts.clear"), ("an empty wrapped list", "config.hosts = [\n  ]")):
            code, out = run(production=GOOD_PRODUCTION.replace('config.hosts = [ "retask.example", /.*\\.retask\\.example/ ]', line))
            check_(f"config.hosts {label} is unset, so a finding", code == 1 and "hosts" in ids(out), f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("config.hosts = [", "config.hosts <<").replace(' "retask.example", /.*\\.retask\\.example/ ]', ' "retask.example"'))
        check_("config.hosts << a host is set", code == 0, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("end\n", "  config.hosts.clear\nend\n"))
        check_("config.hosts.clear after an assignment unsets it, so a finding", code == 1 and "hosts" in ids(out), f"{out}")
        code, out = run(production=trap, application='  config.hosts = ["a.example"]\n')
        check_("config.hosts set in application.rb counts", code == 0, f"{out}")
        code, out = run(production=trap, inits={"hosts.rb": 'Rails.application.config.hosts = ["a.example"]\n'})
        check_("an initializer assigning config.hosts through Rails.application is not read as a setting (only `config.hosts` lines are)", code == 1, f"{out}")
        code, out = run(production=trap, inits={"hosts.rb": 'Rails.application.configure do\n  config.hosts = ["a.example"]\nend\n'})
        check_("an initializer's configure block setting config.hosts counts", code == 0, f"{out}")

        # force_ssl
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", ""))
        check_("assume_ssl without force_ssl is a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("config.force_ssl = true", "config.force_ssl = false"))
        check_("force_ssl = false is a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION.replace("  config.force_ssl = true\n", "  # config.force_ssl = true\n"))
        check_("a commented force_ssl is a finding", code == 1 and ids(out) == {"force-ssl"}, f"{out}")

        # consider_all_requests_local
        code, out = run(production=GOOD_PRODUCTION.replace("local = false", "local = true").replace("requests_local = false", "requests_local = true"))
        check_("consider_all_requests_local = true is a finding", code == 1 and ids(out) == {"local-requests"}, f"{out}")
        code, out = run(production=GOOD_PRODUCTION, application="  config.consider_all_requests_local = true\n")
        check_("CONTROL: production.rb's false wins over application.rb's true", code == 0, f"{out}")

        # wildcard CORS
        cors = 'Rails.application.config.middleware.insert_before 0, Rack::Cors do\n  allow do\n    origins %s\n    resource "*"\n  end\nend\n'
        code, out = run(inits={"cors.rb": cors % '"*"'})
        check_("origins \"*\" is a finding that names its file and line", code == 1 and ids(out) == {"wildcard-cors"}
               and any("cors.rb:3" in line for line in out), f"{out}")
        code, out = run(inits={"cors.rb": cors % "'retask.example', '*'"})
        check_("a wildcard among other origins is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": cors % "/.*/"})
        check_("a match-everything regexp is a finding", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": cors % "'retask.example',\n      '*'"})
        check_("a wrapped origins list is read whole", code == 1 and "wildcard-cors" in ids(out), f"{out}")
        code, out = run(inits={"cors.rb": cors % '"https://retask.example"'})
        check_("CONTROL: a named origin, with `resource \"*\"` in the block, is clean (a bare grep for * would flag it)", code == 0, f"{out}")
        code, out = run(inits={"cors.rb": cors % '"https://*.retask.example"'})
        check_("CONTROL: a subdomain pattern is not an any-origin wildcard (a bare grep for * would flag it)", code == 0, f"{out}")
        code, out = run(inits={"cors.rb": "  # origins '*'\n"})
        check_("a commented wildcard is not a finding", code == 0, f"{out}")

        # debug routes
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
        code, out = run(routes='Rails.application.routes.draw do\n  mount MissionControl::Jobs::Engine, at: "/jobs"\nend\n')
        check_("CONTROL: an engine that is legitimate in production is not flagged", code == 0, f"{out}")

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
