#!/usr/bin/env python3
"""setup-vs-doctrine cross-check — design-flow (#150).

The defect class this exists for: **doctrine references a runtime artefact the generator
never produces.** It is invisible to every other check we have — the brand-pack lint
validates a *pack*, `bash -n`/`py_compile` cover scripts, and the doctrine file and the
generator (`commands/setup.md`) are edited minutes apart with nothing comparing them. It
only surfaces at the first real `/design-flow:setup` run in a live Rails app — as a crash.

The canonical instance (#104): `Ui::Logo` was rewritten to read
`Rails.configuration.x.brand`, but `setup.md` had no step generating
`config/initializers/brand.rb`. Doctrine depended on a config object the generator never
produced, so the first run would raise `NoMethodError` on `nil`. Nobody's test, lint, or
review of the edited file caught it; it was caught by reading the *other* file. This makes
that reading mechanical.

WHAT IT CHECKS — and, deliberately, what it does not.

The unit of dependency is a **`Rails.configuration.x.<key>`** read. That choice is the whole
reason this check does not cry wolf:

  * It is self-scoping to what *raises at runtime*. A component reading a config key that
    was never set gets `nil` and blows up on the next method call — the #104 failure exactly.
    #150 calls this "the error direction ... the one that raises at runtime", and it is.
  * It correctly EXCLUDES artefacts other commands own. `config/initializers/simple_form.rb`
    is referenced all over the forms doctrine, but forms are authored by
    `/design-flow:component`, not by setup — so setup legitimately never generates it. A
    naive "every `config/initializers/*.rb` named in doctrine must be in setup.md" would flag
    it as a false error, and a check that cries wolf gets switched off. The config-key anchor
    scopes to setup's actual responsibility without a hand-maintained allowlist. (The
    `--selftest` proves this with an out-of-scope-initializer near-miss.)

So the enforced rule is narrow on purpose:

  ERROR (depended-on but not generated): a `Rails.configuration.x.<key>` is read somewhere in
      the doctrine and `setup.md` never names that key. This is #104 instance 1.
  ERROR (structural corollary): doctrine reads config but `setup.md` generates no
      `config/initializers/*.rb` at all, so nothing sets that config at boot. This one still
      fires when the key names in doctrine and generator have drifted apart.
  WARN  (generated but unreferenced): `setup.md` sets a config key no doctrine reads —
      probably dead scaffolding.

NOT covered, and why it would be dishonest to claim otherwise:
  * Bare initializer files / asset paths named in doctrine — see the simple_form reasoning
    above; they belong to other commands, and the pack's logo asset is already checked by
    `brand_pack_lint.py`. Enforcing them here would be false positives.
  * #104 instance 2 (setup wired font families *unconditionally* while `brand.md` made
    `fonts` an optional pack override) is a value-*conditionality* disagreement, not an
    artefact-presence one — it never raised at runtime, it rendered the wrong font. An
    artefact cross-check cannot reproduce it without becoming a prose-pattern matcher. That
    class is the LLM-tell detector's territory (a literal font family in generated output is
    a role-layer violation), tracked in #157.

REGRESSION PROOF, not an assertion that it works. #150 asks for the check to reproduce the
#104 defect at that PR's parent commit. It does, against the real trees in this repo's
history — `ced38c4` is the commit where doctrine began reading the key and `setup.md` still
generated nothing:

    for c in ced38c4 5902250; do
      d=$(mktemp -d); mkdir -p "$d/doctrine"
      git archive $c skills/design-system | tar -x -C "$d/doctrine" --strip-components=2
      git show $c:plugins/design-flow/commands/setup.md > "$d/setup.md"
      python3 plugins/design-flow/scripts/setup_doctrine_crosscheck.py \
        --setup "$d/setup.md" --doctrine "$d/doctrine"; echo "$c -> exit=$?"
    done
    # ced38c4 (defective, pre-fix) -> exit=1   5902250 (in-branch fix) -> exit=0

That needs full history; this repo is often cloned shallow, so `--selftest` carries the same
scenario as a self-contained fixture and is what the gates run.

Stdlib only, by design: it must run in any clone with nothing installed, like
`brand_pack_lint.py`. It boots no Rails and loads no gem.

Usage:
  python3 setup_doctrine_crosscheck.py                 # default repo paths
  python3 setup_doctrine_crosscheck.py --setup S --doctrine D
  python3 setup_doctrine_crosscheck.py --selftest      # prove the check can fail

Exit: 0 clean (warnings allowed) · 1 a depended-on config key is not generated ·
      2 usage/environment (a required input is missing, unreadable, or not valid UTF-8).

The 1/2 split is load-bearing: 1 means "doctrine drift a maintainer must fix", 2 means "this
check could not run". Anything that collapses the two sends someone hunting a defect that does
not exist, so every read is guarded and every partial scan aborts — see `InputError`.
"""

from __future__ import annotations

import argparse
import os
import re
import sys

# --------------------------------------------------------------------------
# paths — resolved relative to this script so the default invocation needs no args,
# mirroring brand_pack_lint.py. Both are overridable for the selftest and for a
# non-standard checkout.
# --------------------------------------------------------------------------

_HERE = os.path.dirname(os.path.abspath(__file__))
# scripts -> design-flow -> plugins -> repo root
_REPO = os.path.normpath(os.path.join(_HERE, "..", "..", ".."))
DEFAULT_SETUP = os.path.join(_HERE, "..", "commands", "setup.md")
# RESOLVED, not counted. Four `..` hops reach the doctrine in a marketplace clone and land a
# directory short from an install, where the cache interposes `<bundle>/<version>/` — #617. The
# shared resolver knows both shapes; falling back to the clone path keeps the message honest when
# neither exists.
sys.path.insert(0, _HERE)
import doctrine_path                                    # noqa: E402 — same plugin, one resolver
_FOUND = doctrine_path.find(os.path.join(_HERE, "x.py"))
DEFAULT_DOCTRINE = str(_FOUND) if _FOUND else os.path.join(_REPO, "skills", "design-system")

# `Rails.configuration.x.<key>` or the equivalent `Rails.application.config.x.<key>`.
# Captures the FIRST segment after `.x.` — that is the config key. A chained
# `.x.brand.default_variant` yields `brand`; `.default_variant` is a method on the object
# the key holds, not a second key.
CONFIG_KEY = re.compile(
    r"Rails\.(?:configuration|application\.config)\.x\.([a-z_][a-z0-9_]*)"
)

# A generated initializer, e.g. `config/initializers/brand.rb`.
INITIALIZER = re.compile(r"config/initializers/([a-z0-9_]+)\.rb")

# A step boundary in setup.md: a markdown heading, or a top-level numbered step. Used to scope
# a config key to the step that generates it — see `setup_provides`.
STEP_BOUNDARY = re.compile(r"^(?:#{1,6} |\d+\. )", re.M)


class InputError(Exception):
    """A required input could not be read or decoded.

    Raised rather than skipped, deliberately. With one doctrine file unread the read-set is
    incomplete, so every verdict below it is unsound in BOTH directions: a key read only in the
    unread file looks ungenerated (invented finding), and the run can equally report clean over
    doctrine it never saw. A partial scan has no honest verdict, so this aborts to exit 2
    (environment) instead of returning a result indistinguishable from either.

    Without it an undecodable file exits **1** — the code reserved for "a depended-on config key
    is not generated" — sending a maintainer hunting a doctrine defect that does not exist.
    """


# --------------------------------------------------------------------------
# extraction
# --------------------------------------------------------------------------

def config_reads(doctrine_dir: str) -> tuple[dict[str, list[str]], int]:
    """(config keys the doctrine reads -> the `file:line` sites, count of files scanned).

    Scans every markdown file under the doctrine tree. The generator (`setup.md`) lives in
    the plugin's `commands/`, not here, so there is no risk of counting the generator's own
    mention as a doctrine read.

    The scanned count is returned because "no keys found" and "no files read" produce an
    identical clean verdict otherwise, and a check that reports clean over input it never
    read is worse than no check — see the caller.
    """
    reads: dict[str, list[str]] = {}
    scanned = 0
    for root, _dirs, files in os.walk(doctrine_dir):
        for name in sorted(files):
            if not name.endswith(".md"):
                continue
            path = os.path.join(root, name)
            rel = os.path.relpath(path, doctrine_dir)
            scanned += 1
            try:
                with open(path, encoding="utf-8") as handle:
                    for lineno, line in enumerate(handle, 1):
                        for key in CONFIG_KEY.findall(line):
                            reads.setdefault(key, []).append(f"{rel}:{lineno}")
            except (OSError, UnicodeDecodeError) as exc:
                raise InputError(f"cannot read doctrine file {rel}: {exc}") from exc
    return reads, scanned


def setup_steps(text: str) -> list[str]:
    """Split setup.md into step-sized chunks at headings and top-level numbered steps.

    Coarse on purpose. The unit only has to be small enough that a key and the initializer
    generating it must be *deliberately* placed together, and large enough that the real
    setup.md — where step 7 spans several wrapped lines — is one chunk rather than three.

    **Fenced code is never a boundary.** A shell comment (`# …`) at column 0 inside a ``` block
    matches the heading pattern exactly, and setup.md's own pack-resolution snippet contains two.
    Splitting there would cut a step in half, so a step that showed a code example *between* its
    initializer and its key read would be reported as unprovided — a false drift error on
    correct input, which is how a check earns being switched off. Fence content is still scanned
    for keys and initializers; it just cannot start a new chunk.
    """
    chunks: list[str] = []
    current: list[str] = []
    fence = ""   # the marker that opened the current fence; empty when outside one

    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if fence:
            if stripped.startswith(fence):
                fence = ""
            current.append(line)
            continue
        if stripped[:3] in ("```", "~~~"):
            fence = stripped[:3]
            current.append(line)
            continue
        if STEP_BOUNDARY.match(line) and current:
            chunks.append("".join(current))
            current = []
        current.append(line)

    if current:
        chunks.append("".join(current))
    return chunks or [text]


def setup_provides(setup_path: str) -> tuple[set[str], set[str], set[str]]:
    """(keys setup GENERATES, initializer basenames, keys setup merely MENTIONS).

    A key counts as *provided* only when some step names `Rails.configuration.x.<key>` **and**
    generates `config/initializers/<key>.rb` in that same step. Both halves are load-bearing:

    * **Same step**, because a mention is not a generation. Deriving `provided` from a
      whole-file scan let a stray prose mention stand in for a deleted generation step, so the
      check reported clean while the `NoMethodError` it exists to prevent shipped. That was a
      claims-vs-enforcement defect in this very function — the docstring asserted the
      association was structural while the code did whole-file set membership.
    * **Matching name**, because the error path already prescribes exactly one filename
      (*"Add a step generating `config/initializers/<key>.rb`"*). Enforcing the convention the
      tool prescribes keeps the two consistent; accepting any initializer in the step would let
      `telemetry.rb` vouch for `brand`.

    `mentioned` is returned so the caller can tell "setup never heard of this key" from "setup
    talks about it but generates nothing" — the same defect, but only the second is a near miss
    worth a distinct message.
    """
    try:
        with open(setup_path, encoding="utf-8") as handle:
            text = handle.read()
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"cannot read setup.md at {setup_path}: {exc}") from exc

    inits = set(INITIALIZER.findall(text))
    mentioned = set(CONFIG_KEY.findall(text))
    provided: set[str] = set()
    for chunk in setup_steps(text):
        provided |= set(CONFIG_KEY.findall(chunk)) & set(INITIALIZER.findall(chunk))
    return provided, inits, mentioned


# --------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------

class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.facts: list[str] = []
        # Set when the run examined nothing, so `main` can exit 2 (environment) rather than
        # 0 (clean). See the guard at the top of `cross_check`.
        self.no_input = False

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def fact(self, msg: str) -> None:
        self.facts.append(msg)

    @property
    def ok(self) -> bool:
        return not self.errors


def cross_check(setup_path: str, doctrine_dir: str) -> Report:
    report = Report()
    reads, scanned = config_reads(doctrine_dir)
    provided, inits, mentioned = setup_provides(setup_path)

    # A pointed-at-the-wrong-place run finds no keys and would otherwise print "setup
    # generates every config key the doctrine reads" — clean, over nothing. That reads
    # exactly like a pass and is how a check goes quiet without anyone noticing.
    if not scanned:
        report.no_input = True
        report.error(
            f"scanned 0 markdown file(s) under {doctrine_dir} — this check examined nothing, "
            "which is NOT a pass. Point --doctrine at the design-system tree."
        )
        return report

    report.fact(
        f"scanned {scanned} doctrine file(s); {len(reads)} config key(s) read: "
        f"{', '.join(sorted(reads)) or '(none)'}"
    )
    report.fact(
        f"setup generates initializer(s): "
        f"{', '.join(sorted(f'{i}.rb' for i in inits)) or '(none)'}"
    )

    for key in sorted(reads):
        if key in provided:
            continue
        sites = reads[key]
        shown = ", ".join(sites[:4]) + (" …" if len(sites) > 4 else "")
        # Mentioned but not generated is the near miss: setup talks about the key while the step
        # that created it is gone. It reads as "handled" to a human skimming setup.md, which is
        # exactly why it needs its own message rather than the generic one.
        if key in mentioned:
            report.error(
                f"doctrine reads `Rails.configuration.x.{key}` ({shown}) and setup.md mentions "
                f"the key, but no step both names it and generates "
                f"`config/initializers/{key}.rb` — a mention is not a generation, so nothing "
                f"sets it at boot and the first `/design-flow:setup` run raises NoMethodError "
                f"on nil."
            )
        else:
            report.error(
                f"doctrine reads `Rails.configuration.x.{key}` ({shown}) but setup.md never "
                f"generates it — the first `/design-flow:setup` run raises NoMethodError on nil. "
                f"Add a step generating `config/initializers/{key}.rb`."
            )

    # Structural corollary: config is read but setup creates no initializer at all. This
    # would have caught #104 even if the key name in doctrine and generator had drifted.
    if reads and not inits:
        report.error(
            "doctrine reads config under `Rails.configuration.x.*` but setup.md generates no "
            "`config/initializers/*.rb` at all — nothing sets that config at boot."
        )

    for key in sorted(provided - set(reads)):
        report.warn(
            f"setup.md sets `Rails.configuration.x.{key}` but no doctrine reads it — "
            "probably dead scaffolding (or a doctrine reference was removed)."
        )

    return report


# --------------------------------------------------------------------------
# selftest — near-miss fixtures. Each writes a throwaway doctrine tree + setup.md and
# asserts the check's verdict. The failure phrase per fixture is unique and appears ONLY
# on failure, so scripts/mutation_check.py can prove the RIGHT fixture tripped.
# --------------------------------------------------------------------------

def _write(base: str, rel: str, body: str) -> None:
    path = os.path.join(base, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(body)


def selftest() -> int:
    import tempfile

    passed = 0
    failed = 0

    def check(name: str, condition: bool, fail_phrase: str) -> None:
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}: {fail_phrase}")

    with tempfile.TemporaryDirectory() as tmp:
        # --- Fixture A: #104 instance 1 — key read, setup generates nothing → ERROR ---
        doc = os.path.join(tmp, "a-doctrine")
        setup = os.path.join(tmp, "a-setup.md")
        _write(doc, "component-implementations.md",
               "class Ui::Logo\n  brand = Rails.configuration.x.brand  # read at render\n")
        _write(tmp, "a-setup.md",
               "# setup\n1. application.css @theme\n2. base ViewComponents incl. Ui::Logo\n")
        rep = cross_check(setup, doc)
        check("instance-1 regression fires",
              any("Rails.configuration.x.brand" in e for e in rep.errors) and not rep.ok,
              "expected an error for the ungenerated config key, got none")

        # --- Fixture B: fixed state — key read AND generated → CLEAN ---
        doc = os.path.join(tmp, "b-doctrine")
        _write(doc, "component-implementations.md",
               "brand = Rails.configuration.x.brand\n")
        _write(tmp, "b-setup.md",
               "# setup\n7. generate `config/initializers/brand.rb` so "
               "`Rails.configuration.x.brand` exposes variants.\n")
        rep = cross_check(os.path.join(tmp, "b-setup.md"), doc)
        check("fixed state is clean",
              rep.ok and not rep.errors,
              f"expected no errors once generated, got: {rep.errors}")

        # --- Fixture C: setup sets a key nothing reads → WARN, still exit 0 ---
        doc = os.path.join(tmp, "c-doctrine")
        _write(doc, "components.md", "no config here, just prose about Ui::Card\n")
        _write(tmp, "c-setup.md",
               "# setup\ngenerate `config/initializers/telemetry.rb` setting "
               "`Rails.configuration.x.telemetry`.\n")
        rep = cross_check(os.path.join(tmp, "c-setup.md"), doc)
        check("unreferenced config warns without failing",
              rep.ok and any("telemetry" in w for w in rep.warnings),
              "expected a warning (not an error) for generated-but-unreferenced config")

        # --- Near-miss: an out-of-scope initializer (simple_form) must NOT error ---
        # This is the real #150 false-positive trap: forms doctrine references
        # config/initializers/simple_form.rb, but forms are authored by /component, not
        # setup. Because it backs no Rails.configuration.x.* read, it is correctly ignored.
        doc = os.path.join(tmp, "d-doctrine")
        _write(doc, "forms.md",
               "Configure simple_form in `config/initializers/simple_form.rb`.\n")
        _write(tmp, "d-setup.md", "# setup\nno forms here — those come from /component\n")
        rep = cross_check(os.path.join(tmp, "d-setup.md"), doc)
        check("out-of-scope initializer is not flagged",
              rep.ok and not rep.errors,
              "an out-of-scope initializer was wrongly flagged — the check has over-widened "
              "beyond Rails.configuration.x.* reads and will cry wolf")

        # --- Fixture E: an empty doctrine tree must NOT read as clean ---
        # "No findings" over zero inputs is the gate-that-cannot-fail shape: it is
        # indistinguishable from a pass, so it is an environment error (exit 2) instead.
        doc = os.path.join(tmp, "e-doctrine")
        os.makedirs(doc, exist_ok=True)
        _write(tmp, "e-setup.md", "# setup\nnothing here\n")
        rep = cross_check(os.path.join(tmp, "e-setup.md"), doc)
        check("empty doctrine tree is an error, not a pass",
              rep.no_input and not rep.ok,
              "a run that scanned zero files reported clean — the check can go quiet "
              "without anyone noticing")
        check("empty doctrine tree exits 2, not 0",
              main(["--setup", os.path.join(tmp, "e-setup.md"), "--doctrine", doc,
                    "--quiet"]) == 2,
              "expected exit 2 (environment) for a run that examined nothing")

        # --- Fixture F: a mention is not a generation ---
        # The regression proof for the whole-file-membership defect. setup.md still mentions the
        # key in prose, and still generates SOME initializer (so the structural corollary stays
        # quiet), but the step that generated `brand.rb` is gone. Pre-fix this reported clean and
        # the NoMethodError shipped.
        doc = os.path.join(tmp, "f-doctrine")
        _write(doc, "component-implementations.md",
               "brand = Rails.configuration.x.brand\n")
        _write(tmp, "f-setup.md",
               "# setup\n"
               "1. **Theme**: generate `config/initializers/telemetry.rb`.\n"
               "2. **Report**: mention that `Rails.configuration.x.brand` drives Ui::Logo.\n")
        rep = cross_check(os.path.join(tmp, "f-setup.md"), doc)
        check("a stray key mention does not count as generated",
              not rep.ok and any("mention is not a generation" in e for e in rep.errors),
              "setup.md merely MENTIONS the key while generating no matching initializer, and "
              "the check passed — `provided` is being inferred from a whole-file scan again")

        # --- Fixture G: the safe direction — co-location across a realistic multi-step file ---
        # Guards the fix from over-correcting. If step-scoping were too tight (say, per-line),
        # the real setup.md — whose step 7 wraps across several lines — would fail, and a check
        # that flags the correct shape gets switched off.
        doc = os.path.join(tmp, "g-doctrine")
        _write(doc, "component-implementations.md",
               "brand = Rails.configuration.x.brand\n")
        _write(tmp, "g-setup.md",
               "# setup\n"
               "1. **application.css** — the full `@theme`.\n"
               "2. **Layout recipes** — stack, cluster, center.\n"
               "7. **Brand config for `Ui::Logo`**: generate `config/initializers/brand.rb`\n"
               "   from the pack's `brand.json` so `Rails.configuration.x.brand` exposes\n"
               "   `default_variant` and `variants`.\n")
        rep = cross_check(os.path.join(tmp, "g-setup.md"), doc)
        check("a key generated in its own multi-line step stays clean",
              rep.ok and not rep.errors,
              f"the real setup.md shape was flagged — step scoping is too tight and the check "
              f"will cry wolf on correct input. Got: {rep.errors}")

        # --- Fixture H: an unreadable doctrine file is environment (2), never drift (1) ---
        # Pre-fix this escaped as a UnicodeDecodeError traceback, which exits 1 — the code that
        # means "a depended-on config key is not generated". An environment fault was therefore
        # indistinguishable from a real finding.
        doc = os.path.join(tmp, "h-doctrine")
        os.makedirs(doc, exist_ok=True)
        _write(doc, "fine.md", "brand = Rails.configuration.x.brand\n")
        with open(os.path.join(doc, "broken.md"), "wb") as handle:
            handle.write(b"\xff\xfe not valid utf-8\n")
        _write(tmp, "h-setup.md",
               "# setup\n7. generate `config/initializers/brand.rb` setting "
               "`Rails.configuration.x.brand`.\n")
        code = main(["--setup", os.path.join(tmp, "h-setup.md"), "--doctrine", doc, "--quiet"])
        check("an undecodable doctrine file exits 2, not 1",
              code == 2,
              f"expected exit 2 (environment) for an unreadable input, got {code} — an "
              "environment fault is being reported as doctrine drift")

        # --- Fixture I: a fenced code example must not split a step ---
        # A shell comment at column 0 inside ``` matches the heading pattern exactly. setup.md's
        # own pack-resolution snippet contains two. If a fence could start a chunk, this step —
        # which generates the initializer, shows a snippet, THEN names the key — would be split
        # and reported as unprovided: a false drift error on correct input.
        doc = os.path.join(tmp, "i-doctrine")
        _write(doc, "component-implementations.md",
               "brand = Rails.configuration.x.brand\n")
        # The fence and its comments sit at COLUMN 0, mirroring setup.md. Indenting them would
        # make this fixture vacuous: `^#` cannot match a leading-space line, so it would pass
        # whether or not the splitter tracked fences at all.
        _write(tmp, "i-setup.md",
               "# setup\n"
               "7. **Brand config**: generate `config/initializers/brand.rb`.\n"
               "\n"
               "```bash\n"
               "# resolve the pack directory before generating\n"
               "# (fidara, _template) live inside the plugin\n"
               "python3 \"$LINT\" \"$PACK\"\n"
               "```\n"
               "\n"
               "so `Rails.configuration.x.brand` exposes `variants`.\n")
        rep = cross_check(os.path.join(tmp, "i-setup.md"), doc)
        check("a fenced code example does not split a step",
              rep.ok and not rep.errors,
              f"a `# ` comment inside a fence split the step, so the key and its initializer "
              f"landed in different chunks — the check now cries wolf on correct input. "
              f"Got: {rep.errors}")

    total = passed + failed
    if failed:
        print(f"\nselftest: {failed} of {total} FAILED")
        return 1
    print(f"\nselftest: {total} checks passed")
    return 0


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        prog="setup_doctrine_crosscheck.py",
        description="Verify /design-flow:setup generates the config the doctrine reads.",
    )
    parser.add_argument("--setup", default=DEFAULT_SETUP,
                        help="path to commands/setup.md")
    parser.add_argument("--doctrine", default=DEFAULT_DOCTRINE,
                        help="path to the design-system doctrine tree")
    parser.add_argument("--selftest", action="store_true",
                        help="run the near-miss fixtures and exit")
    parser.add_argument("--quiet", action="store_true", help="only print problems")
    args = parser.parse_args(argv)

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass

    if args.selftest:
        return selftest()

    if not os.path.isfile(args.setup):
        print(f"setup_doctrine_crosscheck: setup.md not found at {args.setup}",
              file=sys.stderr)
        return 2
    if not os.path.isdir(args.doctrine):
        print(f"setup_doctrine_crosscheck: doctrine tree not found at {args.doctrine}",
              file=sys.stderr)
        return 2

    try:
        report = cross_check(args.setup, args.doctrine)
    except InputError as exc:
        # Environment, not a finding. Letting this escape as a traceback exits 1 — the code
        # reserved for real drift — so an unreadable file would read as a doctrine defect.
        print(f"setup_doctrine_crosscheck: {exc}", file=sys.stderr)
        return 2

    if not args.quiet:
        for fact in report.facts:
            print(f"        {fact}")
    for msg in report.errors:
        print(f"  error: {msg}")
    for msg in report.warnings:
        print(f"  warn:  {msg}")

    if report.no_input:
        return 2   # examined nothing: an environment fault, never a clean bill of health
    if not report.ok:
        print(f"\n{len(report.errors)} unmet runtime dependency(ies). Doctrine reads config "
              "that setup never generates — this raises NoMethodError at the first setup run, "
              "not in any test.")
        return 1
    if not args.quiet:
        print("\nsetup generates every config key the doctrine reads.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
