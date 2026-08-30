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
import json
import re
import sys
from pathlib import Path

GEMFILE = Path("Gemfile")
APPLICATION_RB = Path("config/application.rb")
# The testing stack, DERIVED from `skills/rails-8/references/testing.md` and committed beside this
# script by `scripts/derive_mandated_gems.py` (#797). Read from a file in THIS plugin at a fixed
# offset -- reading testing.md at runtime would cross into rails-stack, where a clone and an install
# differ in depth and not offset (#617 / #763 / #777). The `mandated gems derived` gate fails if
# this file and the doctrine disagree, so the list cannot rot.
MANDATED = Path(__file__).resolve().parent.parent / "mandated_gems.json"

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


def testing_stack() -> list[str]:
    """The gems `testing.md` prescribes, or [] if the artifact is absent.

    An absent artifact yields an EMPTY list rather than raising: this check also runs from an
    install, and a missing sidecar there must degrade to "cannot check the testing stack" rather
    than failing a user's project for a packaging problem of ours. The maintainer-side
    `mandated gems derived` gate is what guarantees it is present and current in what ships.
    """
    if not MANDATED.is_file():
        return []
    try:
        return list(json.loads(MANDATED.read_text(encoding="utf-8")).get("testing_stack") or [])
    except ValueError:
        return []


def problems(gems: set[str], application_rb: str | None) -> list[str]:
    found: list[str] = []
    # THE PRESCRIBED TESTING STACK (#797). `testing.md` is described as "this skill's testing
    # doctrine" and its Gemfile block is not a menu -- yet 9 gems were written as literal `gem`
    # lines while 4 were installed by any command and 2 were checked. A project could hold
    # rspec-rails and no simplecov, webmock or vcr and report clean everywhere.
    missing = [g for g in testing_stack() if g not in gems]
    if missing:
        found.append(
            f"the prescribed testing stack is incomplete — missing "
            f"{', '.join('`' + g + '`' for g in missing)}.\n"
            f"    skills/rails-8/references/testing.md declares the full block; that file is this "
            f"stack's testing doctrine, not a menu.\n"
            f"    Install:  bundle add {' '.join(missing)} --group 'development,test'")
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

    # The testing stack is now required, so a fixture meant to PASS must declare it. Built from
    # `testing_stack()` rather than a second hardcoded list -- a fixture that pinned its own copy
    # would keep passing after the doctrine changed, which is the drift this check exists to catch.
    STACK = "".join(f'gem "{g}"\n' for g in testing_stack())
    BARE = 'source "https://rubygems.org"\ngem "rails", "~> 8.1"\n' + STACK
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
    # `factory_bot_rails` is now IN the derived testing stack, so this fixture has to take it back
    # out to exercise the inert-config rule at all. Left as-is it tested nothing: the gem was
    # present, so the rule could never fire.
    NO_FB = WITH_SF.replace('gem "factory_bot_rails"\n', "", 1)
    code, msg = verdict(NO_FB, GEN)
    check("fixture_replacement without the gem FAILS", code == 1, f"exit {code}")
    check("...and says the line is inert", "INERT" in msg, msg[:160])

    code, _ = verdict(WITH_SF, GEN)
    check("...and passes once the gem is declared", code == 0)

    # THE NEGATIVE that keeps it conditional: no such config, no such requirement. Without this the
    # rule would be "every project must carry factory_bot_rails", which the doctrine does not say.
    # The Gemfile must LACK factory_bot for this to test anything: `WITH_SF` now carries it (it is
    # in the derived stack), so the rule could not fire either way and a mutation making it
    # unconditional survived. Drop the gem AND the config -- the requirement must stay conditional
    # on the config, which is the whole point of the rule.
    code, msg = verdict(NO_FB, "Rails.application.configure do\nend\n")
    check("no fixture_replacement config, no factory_bot requirement",
          "INERT" not in msg, msg[:120])
    code, _ = verdict(WITH_SF, None)
    check("...and no application.rb at all is fine too", code == 0)

    # ---- THE PRESCRIBED TESTING STACK (#797) --------------------------------------------------
    # 9 gems written as literal `gem` lines in testing.md; 4 installed by any command, 2 checked.
    if testing_stack():
        one_short = WITH_SF.replace('gem "simplecov"\n', "", 1)
        code, msg = verdict(one_short)
        check("a Gemfile missing simplecov FAILS", code == 1, f"exit {code}")
        check("...naming the gem that is missing", "simplecov" in msg, msg[:140])
        check("...and pointing at the doctrine that declares it", "testing.md" in msg, msg[:140])
        check("...with an install command", "bundle add" in msg, msg[:140])

        # THE PASS, or the clause above could be "always fail".
        code, _ = verdict(WITH_SF)
        check("a complete Gemfile passes", code == 0)

        # DERIVED, not hardcoded: every gem in the artifact is actually required. Without this the
        # check could enforce one gem and ignore the other eight.
        # Read the ARTIFACT directly rather than calling `testing_stack()`. The first version
        # looped over `testing_stack()`, so a mutation shrinking that function shrank the fixture
        # with it and the check passed over one gem instead of nine -- a test that recomputes its
        # subject cannot witness the subject changing.
        declared = json.loads(MANDATED.read_text(encoding="utf-8"))["testing_stack"]
        unenforced = []
        for g in declared:
            c, m = verdict(WITH_SF.replace(f'gem "{g}"\n', "", 1))
            if c != 1 or g not in m:
                unenforced.append(g)
        check("EVERY gem in the derived list is required", not unenforced,
              f"not enforced: {unenforced}")
        check("...and there are as many as the artifact declares", len(declared) >= 8,
              f"{len(declared)}")

        # A SITUATIONAL gem is NOT demanded -- demanding one is the false positive that gets a
        # gate switched off (#476). None of these appears in testing.md's block.
        code, msg = verdict(WITH_SF)
        check("a situational gem is not demanded", code == 0 and not any(
            g in msg for g in ("pagy", "pundit", "ransack", "bullet", "prosopite")), msg[:120])
        # ...and database_cleaner is commented out IN the doctrine, so it must never be required.
        check("database_cleaner is not required", "database_cleaner" not in msg, msg[:120])

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
