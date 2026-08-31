#!/usr/bin/env python3
"""Refuse an i18n setup that serves the previous visitor's language (#799).

WHY THIS IS DECLARATION-DRIVEN. Most apps are monolingual, and demanding locale files everywhere is
the false positive that gets a rule ignored. But demanding nothing leaves a multi-locale app silently
monolingual. Neither is checkable without knowing what the project chose -- so `/rails-flow:setup-flow`
asks, and the answer is recorded as `config.x.locales`.

Recording it is what makes a SITUATIONAL rule gateable at all. Without a declaration there are only
two options and both are wrong: gate everyone, or gate nobody. With one, the check has three honest
states -- conforming, drifted, and **not applicable because this project declared monolingual**.
Identical mechanism to `config.x.brand.pack` (#788), for the identical reason: a check that cannot
tell what a project chose has not measured anything.

THE CLAUSE THAT MATTERS is the thread leak. Rails' own guide: *"I18n.locale can leak into subsequent
requests served by the same thread/process if it is not consistently set in every controller... For
that reason, instead of I18n.locale = you can use I18n.with_locale which does not have this leak
issue."* Puma is the default server and it is THREADED -- threads are reused, so a locale set and
never reset is inherited by whoever gets that thread next. It is invisible under single-threaded
local testing and surfaces in production as a page in the previous visitor's language.

SCOPED TO CONTROLLERS, deliberately. `I18n.locale = :en` in an initializer is correct -- it sets the
boot default. The same line inside a request cycle is the bug. Flagging both would fire on conforming
setup, which is the false positive that gets a gate switched off (#476).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

GEMFILE = Path("Gemfile")
CONTROLLERS = Path("app/controllers")
CONFIG = Path("config")

# Captures INSIDE the brackets. Capturing `%w[en]` whole and then tokenising yielded ["w", "en"] --
# the `w` of the array-literal prefix read as a locale, so a monolingual project looked multi-locale
# and got the full ruleset. Caught by the single-locale fixture.
LOCALES_DECL = re.compile(r"""\bconfig\.x\.locales\s*=\s*%?w?\[(?P<body>[^\]]*)\]""")
LOCALE_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
ASSIGNS_LOCALE = re.compile(r"\bI18n\.locale\s*=")
WITH_LOCALE = re.compile(r"\bI18n\.with_locale\b")
AROUND_ACTION = re.compile(r"\baround_action\b")
GEM = re.compile(r"""^\s*gem\s+(?P<q>['"])(?P<name>[A-Za-z0-9_\-]+)(?P=q)""")


def uncommented(text: str, pattern: re.Pattern) -> bool:
    return any(pattern.search(line) for line in text.splitlines()
               if not line.lstrip().startswith("#"))


def declared_locales(config_text: str) -> list[str] | None:
    """The locales this project declared, or None if it never did.

    None and `["en"]` are different answers and must stay so: one is "nobody decided", the other is
    "we decided one locale". Collapsing them would make the not-applicable state a guess.
    """
    for line in config_text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = LOCALES_DECL.search(line)
        if m:
            return LOCALE_TOKEN.findall(m.group("body"))
    return None


def declared_gems(gemfile: str) -> set[str]:
    return {m.group("name") for m in (GEM.match(l) for l in gemfile.splitlines()) if m}


def problems(controller_text: str, gemfile: str | None) -> list[str]:
    found: list[str] = []
    if uncommented(controller_text, ASSIGNS_LOCALE):
        found.append(
            "a controller assigns `I18n.locale = …`, which LEAKS across requests.\n"
            "    Puma is threaded and reuses threads, so a locale set and never reset is inherited "
            "by the next request on that thread — a page served in the previous visitor's "
            "language.\n"
            "    Rails' guide: \"instead of I18n.locale = you can use I18n.with_locale which does "
            "not have this leak issue.\"\n"
            "    Use:  around_action :switch_locale  →  I18n.with_locale(locale, &action)")
    elif not uncommented(controller_text, WITH_LOCALE):
        found.append(
            "no controller wraps the request in `I18n.with_locale`, so every request renders in "
            "the default locale.\n"
            "    An `around_action` is required rather than a `before_action`: `with_locale` "
            "restores the previous value when the block exits, which is what a wrapper does.\n"
            "    See skills/rails-8/references/i18n.md §2")
    elif not uncommented(controller_text, AROUND_ACTION):
        found.append(
            "`I18n.with_locale` is used but no `around_action` wraps the action, so it cannot be "
            "covering the whole request.\n"
            "    See skills/rails-8/references/i18n.md §2")
    if gemfile is not None and "rails-i18n" not in declared_gems(gemfile):
        found.append(
            "`rails-i18n` is not in the Gemfile. Rails ships English for its OWN strings only — "
            "validation messages, date and number formats — so those stay English while your copy "
            "translates.\n"
            "    Install:  bundle add rails-i18n")
    return found


def run(root: Path = Path(".")) -> tuple[int, str]:
    """(exit, message). 0 pass, 1 fail, 3 not-applicable."""
    cfg = root / CONFIG
    config_text = "\n".join(p.read_text(encoding="utf-8")
                            for p in cfg.glob("**/*.rb")) if cfg.is_dir() else ""
    locales = declared_locales(config_text)
    if locales is None:
        return 3, ("not applicable — this project has not declared `config.x.locales`, so there is "
                   "nothing to check against (NOT a pass).\n"
                   "  /rails-flow:setup-flow asks; declaring `%w[en]` records that one locale was "
                   "CHOSEN, which is different from nobody having decided.")
    if len(locales) < 2:
        return 3, (f"not applicable — this project declared a single locale ({locales[0]}), so the "
                   f"multi-locale rules do not apply (NOT a pass)")
    ctl = root / CONTROLLERS
    controller_text = "\n".join(p.read_text(encoding="utf-8")
                                for p in ctl.glob("**/*.rb")) if ctl.is_dir() else ""
    gemfile = root / GEMFILE
    found = problems(controller_text,
                     gemfile.read_text(encoding="utf-8") if gemfile.is_file() else None)
    if not found:
        return 0, f"i18n is wired for {len(locales)} locales ({', '.join(locales)})"
    return 1, f"{len(found)} finding(s):\n" + "\n".join(f"  - {f}" for f in found)


def selftest() -> int:
    import tempfile
    checks, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}{('  ' + detail) if detail else ''}")

    GOOD_CTL = ("class ApplicationController < ActionController::Base\n"
                "  around_action :switch_locale\n"
                "  def switch_locale(&action)\n"
                "    I18n.with_locale(params[:locale] || I18n.default_locale, &action)\n"
                "  end\nend\n")
    MULTI = 'Rails.application.configure do\n  config.x.locales = %w[en ar fr]\nend\n'
    GEMS = 'gem "rails"\ngem "rails-i18n"\n'

    def verdict(*, config: str | None = MULTI, controller: str | None = GOOD_CTL,
                gemfile: str | None = GEMS) -> tuple[int, str]:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            if config is not None:
                (root / "config" / "initializers").mkdir(parents=True)
                (root / "config" / "initializers" / "locales.rb").write_text(config, encoding="utf-8")
            if controller is not None:
                (root / "app" / "controllers").mkdir(parents=True)
                (root / "app" / "controllers" / "application_controller.rb").write_text(
                    controller, encoding="utf-8")
            if gemfile is not None:
                (root / "Gemfile").write_text(gemfile, encoding="utf-8")
            return run(root)

    # ---- THE DECLARATION decides whether anything applies -------------------------------------
    code, msg = verdict(config=None)
    check("no declaration is not-applicable, not a pass", code == 3, f"exit {code}")
    check("...and says a declaration is what setup-flow adds", "setup-flow asks" in msg, msg[:150])

    code, msg = verdict(config='Rails.application.configure do\n  config.x.locales = %w[en]\nend\n')
    check("a declared monolingual project is not-applicable", code == 3, f"exit {code}")
    check("...and says so rather than reporting clean", "NOT a pass" in msg, msg[:120])
    # NONE and ["en"] must stay DIFFERENT answers -- one is "nobody decided", the other is a choice.
    check("undeclared and single-locale give different reasons",
          "not declared" in verdict(config=None)[1] or "has not declared" in verdict(config=None)[1])

    # ---- THE LEAK, which is the clause that matters -------------------------------------------
    LEAKY = ("class ApplicationController < ActionController::Base\n"
             "  before_action :set_locale\n"
             "  def set_locale\n    I18n.locale = params[:locale]\n  end\nend\n")
    code, msg = verdict(controller=LEAKY)
    check("assigning I18n.locale in a controller FAILS", code == 1, f"exit {code}")
    check("...naming the cross-request leak", "LEAKS across requests" in msg, msg[:140])
    check("...and quoting the guide's remedy", "with_locale" in msg, msg[:200])

    # THE SAME LINE IN AN INITIALIZER IS CORRECT -- it sets the boot default. Flagging it would fire
    # on conforming setup, which is the false positive that gets a gate switched off.
    code, _ = verdict(config=MULTI + "I18n.locale = :en\n")
    check("I18n.locale = in config/ is NOT flagged", code == 0)

    # ---- THE PASS, or the clauses above could be "always fail" --------------------------------
    code, _ = verdict()
    check("a wrapped multi-locale app passes", code == 0)

    # ---- NO WRAPPER AT ALL --------------------------------------------------------------------
    code, msg = verdict(controller="class ApplicationController < ActionController::Base\nend\n")
    check("no with_locale anywhere FAILS", code == 1, f"exit {code}")
    check("...saying every request renders in the default", "default locale" in msg, msg[:150])

    # with_locale present but not wrapping the action is a half-done job, and its own message.
    code, msg = verdict(controller="class A\n  def x\n    I18n.with_locale(:fr) { y }\n  end\nend\n")
    check("with_locale with no around_action FAILS", code == 1, f"exit {code}")
    check("...with its own message, not the leak one", "cannot be covering" in msg, msg[:150])

    # ---- rails-i18n ---------------------------------------------------------------------------
    code, msg = verdict(gemfile='gem "rails"\n')
    check("a missing rails-i18n FAILS", code == 1, f"exit {code}")
    check("...saying Rails ships English for its own strings only",
          "its OWN strings only" in msg, msg[:160])
    code, _ = verdict(gemfile=None)
    check("no Gemfile at all is not a rails-i18n finding", code == 0)

    # A COMMENTED declaration is not a declaration.
    code, _ = verdict(config="# config.x.locales = %w[en ar]\n")
    check("a commented declaration does not count", code == 3)

    for f in failures:
        print(f"FAIL {f}")
    print(f"ran {checks} i18n-setup assertion(s)")
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
