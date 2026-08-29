#!/usr/bin/env python3
"""Refuse a Gemfile missing a gem this stack mandates, or config that is inert without one (#778).

WHY THIS EXISTS. `ecosystem-gems.md` §1 marks three gems **Always**, and §2 is emphatic: *"simple_form
is mandatory in this stack -- no form, and no form element, is built any other way."* Two of the three
already have gates (`architecture-boundaries` -> archspec, `erb-lint` -> herb), each `applies_when`
its config file exists, so an unadopted project reports not-applicable rather than a pass.

simple_form had **neither an installer nor a gate**. The doctrine was stated, performed by nothing,
and checked by nothing -- and it landed twice, from two clean runs of the documented path on two
unrelated greenfield apps. The recurrence is what makes it structural rather than user error.

THE SECOND RULE IS THE MORE INTERESTING ONE, and it is claims-vs-enforcement inside the user's own
project rather than ours. `project-setup.md` prescribes a generators block naming
`fixture_replacement :factory_bot`; without `factory_bot_rails` in the Gemfile that line is **inert**,
so `bin/rails generate` silently emits no factories and the config reads as though it does something.
Config that names a gem the project does not have is a claim nothing makes true.

THREE STATES. No Gemfile -> **not applicable**, reported by name, never a pass. `project_gates.py`
prints that state, so a repo with nothing to check cannot borrow this gate's green.

SCOPED TO WHAT THE DOCTRINE ACTUALLY MANDATES. archspec and herb are deliberately NOT here: they were
adopted opt-in in v1.93.0, their gates already exist, and duplicating them would fail every project
that made the documented choice not to adopt them.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

GEMFILE = Path("Gemfile")
APPLICATION_RB = Path("config/application.rb")

# `gem "name"` / `gem 'name'`, comments stripped first so a commented line never counts.
GEM = re.compile(r"""^\s*gem\s+(?P<q>['"])(?P<name>[A-Za-z0-9_\-]+)(?P=q)""", re.M)


def declared_gems(gemfile: str) -> set[str]:
    """Every gem the Gemfile declares.

    NO COMMENT STRIPPING: `GEM` is anchored with `^\\s*gem`, so `# gem "x"` never matched and a
    mutation removing the strip survived every fixture -- a line no fixture can distinguish is a line
    that does nothing. The commented-gem fixture below now witnesses the ANCHOR, which is what
    actually does the work.
    """
    return {m.group("name") for m in GEM.finditer(gemfile)}


def problems(gems: set[str], application_rb: str | None) -> list[str]:
    found: list[str] = []
    if "simple_form" not in gems:
        found.append(
            "`simple_form` is absent from the Gemfile. ecosystem-gems.md §2: \"simple_form is "
            "mandatory in this stack — no form, and no form element, is built any other way.\"\n"
            "    Install:  bundle add simple_form && bin/rails generate simple_form:install")
    # Inert config: the generators block names factory_bot but the gem is not there.
    if application_rb and re.search(r"fixture_replacement\s+:factory_bot", application_rb):
        if "factory_bot_rails" not in gems:
            found.append(
                "config/application.rb sets `fixture_replacement :factory_bot` but "
                "`factory_bot_rails` is not in the Gemfile, so that line is INERT — "
                "`bin/rails generate` emits no factories and nothing says so.\n"
                "    Install:  bundle add factory_bot_rails --group 'development,test'")
    return found


def run(root: Path = Path(".")) -> tuple[int, str]:
    """(exit, message). 0 pass, 1 fail, 3 not-applicable."""
    gemfile = root / GEMFILE
    if not gemfile.is_file():
        return 3, f"not applicable — no {GEMFILE} in this repo (nothing to check, NOT a pass)"
    app = root / APPLICATION_RB
    found = problems(declared_gems(gemfile.read_text(encoding="utf-8")),
                     app.read_text(encoding="utf-8") if app.is_file() else None)
    if not found:
        return 0, f"{GEMFILE} declares every gem this stack mandates"
    return 1, f"{len(found)} finding(s):\n" + "\n".join(f"  - {f}" for f in found)


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    def verdict(gemfile: str | None, app_rb: str | None = None) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            if gemfile is not None:
                (root / "Gemfile").write_text(gemfile, encoding="utf-8")
            if app_rb is not None:
                (root / "config").mkdir()
                (root / "config" / "application.rb").write_text(app_rb, encoding="utf-8")
            return run(root)

    BARE = 'source "https://rubygems.org"\ngem "rails", "~> 8.1"\n'
    WITH_SF = BARE + 'gem "simple_form"\n'

    code, msg = verdict(BARE)
    check("a Gemfile without simple_form FAILS", code == 1, f"exit {code}")
    check("...and quotes the doctrine that mandates it", "no form element" in msg, msg[:120])
    check("...and names the install command", "bundle add simple_form" in msg, msg[:120])

    # THE PASS. Without it the gate could be "always fail".
    code, _ = verdict(WITH_SF)
    check("a Gemfile with simple_form passes", code == 0)

    # SINGLE QUOTES are the same declaration.
    code, _ = verdict(BARE + "gem 'simple_form'\n")
    check("single-quoted gem declarations count", code == 0)

    # A COMMENTED gem is not a gem. Without this, commenting the line out would pass.
    code, _ = verdict(BARE + '# gem "simple_form"\n')
    check("a commented-out gem does not count", code == 1)

    # THE INERT-CONFIG RULE. Fires only when the config names factory_bot.
    GEN = "Rails.application.configure do\n  config.generators do |g|\n" \
          "    g.fixture_replacement :factory_bot, dir: \"spec/factories\"\n  end\nend\n"
    code, msg = verdict(WITH_SF, GEN)
    check("fixture_replacement without the gem FAILS", code == 1, f"exit {code}")
    check("...and says the line is inert", "INERT" in msg, msg[:120])

    code, _ = verdict(WITH_SF + 'gem "factory_bot_rails"\n', GEN)
    check("...and passes once the gem is declared", code == 0)

    # THE NEGATIVE that keeps it conditional: no such config, no such requirement. Without this the
    # rule would be "every project must carry factory_bot_rails", which the doctrine does not say.
    code, _ = verdict(WITH_SF, "Rails.application.configure do\nend\n")
    check("no fixture_replacement config, no factory_bot requirement", code == 0)
    code, _ = verdict(WITH_SF, None)
    check("...and no application.rb at all is fine too", code == 0)

    # NOT APPLICABLE is the third state and never a pass.
    code, msg = verdict(None)
    check("no Gemfile is not-applicable, not a pass", code == 3, f"exit {code}")
    check("...and says so rather than reporting clean", "NOT a pass" in msg, msg)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} mandated-gems assertion(s)")
    print("no findings." if not failures else f"{len(failures)} finding(s).")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="run the fixtures and exit")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, msg = run()
    print(msg, file=sys.stderr if code == 1 else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main())
