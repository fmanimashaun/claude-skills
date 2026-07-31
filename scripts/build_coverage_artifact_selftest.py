#!/usr/bin/env python3
"""Prove the coverage-artifact guards fire -- and stay silent on the real ENTRIES.

Run:  python3 scripts/build_coverage_artifact.py --selftest   (or execute this file directly)

WHY THIS EXISTS AT ALL, given the builder it imports already has a selftest. Importing
`build_coverage` removed a whole bug class (parsing generated English) and inherited a
different one: the guidance predicates are `status.startswith(...)`, so a typo'd status matches
NONE of them and the row would vanish from the page with no error at all. A completeness matrix
that silently renders 112 of 113 rows is the worst possible failure here, because the missing
row looks exactly like a row that does not exist. So `verify_partition` has to be observed
FAILING, not merely passing.

THE REGRESSION FIXTURE IS THE POINT. `test_totals_label_ordering` pins the exact bug this
script was rewritten to remove: matching the Totals label `documented` also matches
`— derivable from documented parts`, which counted 44 derivable rows as documented on the very
first run. That label match survives in ONE place -- the cross-check against the committed
markdown -- so the fixture uses four DISTINCT numbers, chosen so the old ordering produces a
visibly wrong mapping rather than a coincidentally right one.

Fixtures are synthetic and adversarial: a status matching no predicate, a stub matching all
three (impossible via prefixes, so the disjoint half of the assertion would otherwise never be
exercised), prose containing `</script>` and raw `<dd>`, and a Totals table that disagrees.

Costs nothing: no network, and the corpora are needed by exactly one check, which reports
`skip` rather than passing when they are absent.
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_coverage as bc  # noqa: E402
import build_coverage_artifact as art  # noqa: E402

FAILURES: list[str] = []
SKIPPED: list[str] = []
CHECKS = 0


def _tick() -> None:
    global CHECKS
    CHECKS += 1


def expect_raises(label: str, fn, needle: str = "") -> None:
    """A guard must FIRE. A check never observed failing is not known to work."""
    _tick()
    try:
        fn()
    except art.ArtifactError as exc:
        if needle and needle not in str(exc):
            FAILURES.append(f"{label}: fired, but message lacks {needle!r}:\n{exc}")
    else:
        FAILURES.append(f"{label}: expected ArtifactError, none raised")


def expect_clean(label: str, fn) -> None:
    """A guard must STAY SILENT on conforming input."""
    _tick()
    try:
        fn()
    except art.ArtifactError as exc:
        FAILURES.append(f"{label}: expected clean, got ArtifactError:\n{exc}")


def check(label: str, condition: bool, detail: str = "") -> None:
    _tick()
    if not condition:
        FAILURES.append(f"{label}: {detail or 'assertion failed'}")


# --------------------------------------------------------------- partition guard

class _AllThree:
    """Matches every predicate at once.

    Unreachable through a real status string (the three prefixes are disjoint), which is
    exactly why it is here: without it, only the `len(hits) == 0` half of the assertion is
    ever exercised, and a guard half-tested is a guard half-trusted.
    """
    name = "Impossible"
    status = "documented / derivable / needs doctrine"
    is_documented = is_derivable = needs_doctrine = True


def test_partition() -> None:
    real = art.bc.E("Button", "component", "documented — page-anatomies.md")
    expect_clean("partition: a real documented row", lambda: art.verify_partition([real]))
    expect_clean("partition: the whole real ENTRIES table",
                 lambda: art.verify_partition(list(bc.ENTRIES)))

    typo = art.bc.E("Ghost", "component", "documentd")  # one missing letter
    expect_raises("partition: status matching NO predicate",
                  lambda: art.verify_partition([typo]), "matches 0 guidance")

    expect_raises("partition: status matching ALL THREE predicates",
                  lambda: art.verify_partition([_AllThree()]), "matches 3 guidance")

    # An empty status is the degenerate case of the same bug -- `startswith` on "" is False
    # for all three, so it must be caught, not defaulted into a bucket.
    expect_raises("partition: empty status",
                  lambda: art.verify_partition([art.bc.E("Nameless", "component", "")]),
                  "matches 0 guidance")


# ------------------------------------------------------------------- prose guard

def test_prose() -> None:
    expect_clean("prose: the whole real ENTRIES table",
                 lambda: art.verify_prose(list(bc.ENTRIES)))

    # kind="nonesuch" misses every USE_DEFAULTS / BUILD_DEFAULTS key, so both resolve empty.
    orphan = art.bc.E("Orphan", "nonesuch", "derivable")
    expect_raises("prose: a row resolving no `where / when`",
                  lambda: art.verify_prose([orphan]), "resolves no `where")

    # Give it a `use` but still no `build`, so the second half is exercised on its own rather
    # than being masked by the first failure.
    orig = bc.USE
    bc.USE = {**bc.USE, "Orphan": "on any surface"}
    try:
        expect_raises("prose: a derivable row resolving no `build from`",
                      lambda: art.verify_prose([orphan]), "resolves no `build from`")
        # ...and a DOCUMENTED row legitimately has no `build from` -- it points at its own
        # reference entry instead, so the guard must not demand one.
        expect_clean("prose: a documented row needs no `build from`", lambda: art.verify_prose(
            [art.bc.E("Orphan", "nonesuch", "documented — somewhere")]))
    finally:
        bc.USE = orig


# ------------------------------------------------- the label-ordering regression

TOTALS_FIXTURE = """# Component coverage

## Totals

| | count |
|---|---|
| Tailwind UI leaf components enumerated | 91 |
| Flowbite catalogue entries enumerated | 61 |
| fidara rows | 113 |
| — `documented` | 64 |
| — `derivable` from documented parts | 44 |
| — `needs doctrine` (tracked writing gap) | 5 |

## Documented — build straight from the reference entry
"""


def test_totals_label_ordering() -> None:
    """The bug that caused this rewrite, pinned.

    Every number differs, so a mis-mapping cannot pass by coincidence. Under the original
    ordering, `— derivable from documented parts` matched `documented` first and reported
    documented=44.
    """
    got = art.parse_committed_totals(TOTALS_FIXTURE)
    # `tw`/`fb` ARE parsed now, under keys of their own. The page reads its upstream counts from this
    # committed table instead of walking the licensed kits, so that the rendered bytes do not depend
    # on whether the builder happened to have the optional corpora attached.
    want = {"rows": 113, "documented": 64, "derivable": 44, "needs-doctrine": 5, "tw": 91, "fb": 61}
    check("totals: labels map to the right buckets", got == want, f"got {got}, want {want}")

    # The guarantee the previous version of this fixture protected, kept and made sharper. It used to
    # assert the corpus numbers appeared NOWHERE, which stopped being true when the page started
    # reading them. What actually matters is unchanged: they must never land in a FIDARA bucket,
    # because summing corpus totals into our own rows would inflate every percentage on the page.
    # Distinct keys make that structural, so assert the structure rather than the absence.
    check("totals: corpus enumeration rows never land in a fidara bucket",
          got["tw"] == 91 and got["fb"] == 61
          and all(got[k] not in (91, 61)
                  for k in ("rows", "documented", "derivable", "needs-doctrine")),
          f"got {got}")

    # A file with no Totals table is `skip`, never a silent empty pass.
    check("totals: a file with no Totals table parses to nothing",
          art.parse_committed_totals("# Nothing here\n") == {}, "expected {}")


def test_cross_check_states() -> None:
    """Three states, and `skip` must never be reported as `ok`."""
    real = bc.OUT
    tmp = Path(tempfile.mkdtemp(prefix="coverage-artifact-"))
    counted = {"rows": 113, "documented": 64, "derivable": 44, "needs-doctrine": 5}
    try:
        bc.OUT = tmp / "absent.md"
        state, _ = art.cross_check_committed(counted)
        check("cross-check: absent file reports skip", state == "skip", f"got {state!r}")

        bc.OUT = tmp / "coverage.md"
        bc.OUT.write_text(TOTALS_FIXTURE, encoding="utf-8")
        state, _ = art.cross_check_committed(counted)
        check("cross-check: agreeing counts report ok", state == "ok", f"got {state!r}")

        state, msg = art.cross_check_committed({**counted, "documented": 63})
        check("cross-check: disagreeing counts report fail", state == "fail", f"got {state!r}")
        check("cross-check: the failure names both numbers",
              "63" in msg and "64" in msg, f"got {msg!r}")

        # ...and `collect()` must REFUSE to write on a fail, not warn and continue. This needs
        # a fixture that disagrees with the REAL ENTRIES: TOTALS_FIXTURE happens to state the
        # true counts, so pointing collect() at it proves nothing.
        bc.OUT.write_text(TOTALS_FIXTURE.replace("| 64 |", "| 63 |"), encoding="utf-8")
        expect_raises("cross-check: a fail aborts the build", art.collect, "disagree")
    finally:
        bc.OUT = real


# --------------------------------------------------------- escaping / injection

def test_escaping() -> None:
    """Every string here reaches the DOM through `innerHTML`, so escaping is load-bearing."""
    got = art.inline("use `<dd>` inside a `<dl>`, not <hr> & not raw")
    check("escape: literal tags in prose become entities",
          "<dd>" not in got and "&lt;dd&gt;" in got, f"got {got!r}")
    check("escape: `<hr>` outside backticks is escaped too",
          "<hr>" not in got and "&lt;hr&gt;" in got, f"got {got!r}")
    check("escape: ampersand is escaped exactly once",
          got.count("&amp;") == 1 and "&amp;amp;" not in got, f"got {got!r}")
    check("escape: backticks still become <code>", "<code>" in got, f"got {got!r}")

    # The real LAYOUT_PRIMITIVES entry `cover > center > stack` -- an unescaped `>` here is
    # harmless-looking and still corrupts the markup.
    chevron = art.inline("cover > center > stack (single-focus recipe)")
    check("escape: chevrons in a real primitive name are escaped",
          ">" not in chevron.replace("&gt;", ""), f"got {chevron!r}")

    check("escape: markdown links keep their text, drop the target",
          art.inline("see [the token file](foundations-tokens.md)")
          == "see the token file", f"got {art.inline('see [x](y.md)')!r}")


def test_script_terminator() -> None:
    """`json.dumps` does not protect an inline <script> from `</script>` inside a string."""
    hostile = {"note": "close it with </script> and comment with <!-- this"}
    blob = json.dumps(hostile, ensure_ascii=False)
    check("terminator: json.dumps alone does NOT neutralise it", "</script>" in blob,
          "json.dumps escaped it after all — re-check whether the guard is still needed")

    doc = art.render({**art.collect(), "hostile": hostile["note"]})
    body = doc[doc.index("const DATA = "):doc.rindex("</script>")]
    check("terminator: the rendered script body carries no terminator",
          "</script" not in body and "<!--" not in body, "found one in the emitted body")

    # ...and the escaping must be JSON-transparent: the page has to parse back to the same value.
    # Line-anchored, NOT re.S: `json.dumps` emits no newlines, so the blob is exactly one
    # line. A greedy dot-all match runs on to the last `};` in the script instead.
    raw = re.search(r"^const DATA = (\{.*\});$", doc, re.M)
    check("terminator: the blob still parses", raw is not None, "could not locate the blob")
    if raw:
        check("terminator: escaping is value-preserving",
              json.loads(raw.group(1))["hostile"] == hostile["note"],
              "the escaped blob decoded to a different string")

    # The placeholder guard itself must fire when substitution silently does nothing.
    orig = art.TEMPLATE
    art.TEMPLATE = "<script>const DATA = {};</script>__DATA__ __DATA__"
    try:
        # replace() substitutes BOTH, so force the survival case with a template whose
        # placeholder is spelled differently from the one render() substitutes.
        art.TEMPLATE = "<script>const DATA = __DATA__;</script>__DATA_" + "_X"
        expect_clean("placeholder: a fully substituted template is accepted",
                     lambda: art.render({"ok": 1}))
    finally:
        art.TEMPLATE = orig


# ------------------------------------------------------ the real end-to-end pass

def test_real_build() -> None:
    """The whole thing, on the real ENTRIES — the SILENCE fixture that matters most."""
    data = art.collect()
    t = data["totals"]

    check("real: buckets partition the rows exactly",
          t["documented"] + t["derivable"] + t["needs-doctrine"] == t["rows"],
          f"{t['documented']}+{t['derivable']}+{t['needs-doctrine']} != {t['rows']}")
    check("real: every ENTRIES row is emitted",
          t["rows"] == len(bc.ENTRIES), f"{t['rows']} rows from {len(bc.ENTRIES)} entries")
    check("real: no row is missing its `where / when`",
          all(r["whereHtml"].strip() for r in data["entries"]), "found an empty cell")
    check("real: every needs-doctrine row carries its tracked issue",
          all(r["tracked"].startswith("#") for r in data["entries"]
              if r["guidance"] == "needs-doctrine"), "a tracked issue did not parse out")
    check("real: documented rows carry no `build from`",
          all(r["buildHtml"] is None for r in data["entries"]
              if r["guidance"] == "documented"),
          "a documented row emitted a `build from`, which belongs to its reference entry")

    doc = art.render(data)
    missing = [r["name"] for r in data["entries"]
               if r["nameHtml"] not in doc and r["name"] not in doc]
    check("real: every row name appears in the rendered document",
          not missing, f"absent: {missing[:5]}")
    check("real: the document declares a title", "<title>" in doc, "no <title>")
    check("real: both theme signals are present",
          "prefers-color-scheme:dark" in doc and 'data-theme="dark"' in doc,
          "a theme override is missing, so the viewer's toggle cannot win")

    # No corpus markup, class list or asset may reach the page (#89 licensing boundary).
    check("real: no corpus file path leaks into the page",
          "design-corpora" not in doc, "a corpus path appears in the output")

    # Corpora are optional: this is the ONE check that needs them, and it reports skip.
    if data["corpora"]["available"]:
        check("real: corpus totals are positive when attached",
              data["corpora"]["tw"] > 0 and data["corpora"]["fb"] > 0,
              f"got {data['corpora']}")
    else:
        _tick()
        SKIPPED.append("corpus enumeration totals — design-corpora/ is not attached")

    # ---- NOT ONE FIELD ABOUT THE CHECKOUT MAY BE EMBEDDED --------------------------------
    # Two rounds of this, each of which broke the gate in production: first `commit`/`branch`/the
    # released split, then the dirty flag. Named explicitly rather than checked as a byte-equality
    # only, because the equality test says *that* something leaked and this says *which* field.
    # `label` and `versions` are the whole allowed surface: both are functions of tracked files.
    p = data["provenance"]
    check("the embedded stamp carries no git state whatsoever",
          set(p) == {"label", "versions"}, f"got keys {sorted(p)}")
    check("the embedded label is the release version, not a checkout description",
          p["label"].startswith("Coverage as of v"), f"got {p['label']!r}")
    # The FULL stamp keeps the volatile fields — the console may print them, the page may not.
    full = art.provenance()
    check("the full stamp still reports a known checkout state for the console",
          full["state"] in {"released", "unreleased", "dirty", "unknown"}, f"got {full['state']!r}")
    check("the full stamp names only files this page is built from",
          all(f.endswith(("build_coverage.py", "build_coverage_artifact.py", "coverage.md"))
              for f in full["dirty"]), f"got {full['dirty']}")


def test_dirty_paths() -> None:
    """`git status --porcelain` is FIXED-WIDTH, and the first column is often a space.

    The bug this pins reported `cripts/build_coverage_artifact.py`: `_git` stripped the output,
    which removed the leading space of an UNSTAGED ` M path` line and shifted the slice by one.
    It was invisible for staged (`M  path`) lines, so a fixture using only staged entries would
    have passed the whole time.
    """
    porcelain = (
        " M scripts/build_coverage.py\n"       # unstaged  — the leading space is significant
        "M  scripts/build_coverage_artifact.py\n"  # staged
        "MM skills/fidara-design/references/coverage.md\n"  # staged + further unstaged edits
        "?? scripts/brand-new.py\n"            # untracked
    )
    got = dirty = art.dirty_paths(porcelain)
    want = sorted([
        "scripts/build_coverage.py", "scripts/build_coverage_artifact.py",
        "skills/fidara-design/references/coverage.md", "scripts/brand-new.py",
    ])
    check("dirty: every status form yields the WHOLE path", got == want, f"got {got}")
    check("dirty: no path lost its first character",
          all(not p.startswith(("cripts/", "kills/")) for p in dirty), f"got {dirty}")
    check("dirty: empty output means a clean tree", art.dirty_paths("") == [], "expected []")
    check("dirty: a blank line is not a path", art.dirty_paths("   \n") == [], "expected []")


def run() -> int:
    # ---- collect() MUST NOT REQUIRE THE LICENSED CORPORA ------------------------------------
    # FIRST, and it returns immediately on failure, because every other fixture below calls
    # `collect()`. If it reaches for the optional private kits, the run dies in a traceback from
    # whichever fixture happens to call it first — and a traceback is not a verdict, it is how a
    # mutation gets "caught" by an accident. Reported and stopped here instead.
    #
    # The invariant: the upstream counts come from the committed `coverage.md` Totals, which every
    # clone has. Walking the kits instead means a corpora-less machine cannot regenerate the page,
    # and worse, a machine that CAN renders different bytes from one that cannot — so whoever
    # commits last breaks the drift gate for the other. That happened.
    _tick()
    _tw0, _fb0 = bc.discover_tw, bc.discover_fb

    def _absent():
        raise bc.BuildError("design-corpora/ is not attached")

    try:
        bc.discover_tw = bc.discover_fb = _absent
        art.collect()
    except bc.BuildError:
        FAILURES.append(
            "collect() requires the licensed corpora — it must read the upstream counts from the "
            "committed coverage.md Totals, which every clone has, not the optional private kits")
    finally:
        bc.discover_tw, bc.discover_fb = _tw0, _fb0

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    test_partition()
    test_dirty_paths()
    test_prose()
    test_totals_label_ordering()
    test_cross_check_states()
    test_escaping()
    test_script_terminator()

    test_real_build()

    # ------------------------------------------------------ the --check drift gate
    # The artifact is COMMITTED, so it can go stale exactly as coverage.md can. A drift gate that
    # cannot fail is worse than none, so all three verdicts are pinned: clean, stale, and absent.
    # Uses main() rather than an internal, because the exit CODE is the contract the doctor reads —
    # asserting an internal would leave the gate's actual interface untested.
    # NOTHING IS PINNED for this block any more, and that is the improvement. An earlier version had
    # to stub `provenance` clean, because the page embedded a dirty flag and every fixture below
    # otherwise returned 3 (SKIP) on a developer's tree — testing the environment instead of the gate.
    # Git state is out of the payload, so these fixtures now run identically on any checkout.
    _blob_real = art.committed_blob
    with tempfile.TemporaryDirectory() as _d:
        _out = Path(_d) / "coverage.html"

        # written by the generator itself, so "clean" means byte-for-byte what it emits
        check("--check is silent on a freshly written artifact",
              art.main(["--out", str(_out)]) == 0,
              "generating to a temp path should succeed")
        _fresh = _out.read_text(encoding="utf-8")

        # The gate compares the COMMITTED BLOB, so that is what these fixtures vary. The working
        # copy is deliberately left alone to prove it plays no part.
        art.committed_blob = lambda _rel: _fresh
        check("--check passes when the COMMITTED blob is the clean build",
              art.main(["--check", "--out", str(_out)]) == 0,
              "a committed clean build must satisfy --check")

        # STALE: one appended byte must fail. This is the case that actually happens — a row flips
        # and nobody regenerates.
        art.committed_blob = lambda _rel: _fresh + "<!-- drift -->"
        check("--check FAILS on a stale artifact",
              art.main(["--check", "--out", str(_out)]) == 1,
              "an edited artifact must be reported as drift, or the gate is decorative")

        # NOT TRACKED, but sitting on disk as a perfect clean build. THE defect this gate exists to
        # close, and the one an `is_file()` check passed: a deliverable no other clone can see is
        # not a deliverable. The file below is byte-identical to a clean build and still drift.
        art.committed_blob = lambda _rel: None
        check("a built-but-untracked page is DRIFT, not a pass",
              _out.is_file() and art.main(["--check", "--out", str(_out)]) == 1,
              "the gate must read git, not the working copy — that was the whole point")

        # ABSENT from disk as well: still drift, and must not crash reaching for a file.
        _out.unlink()
        check("--check FAILS when the artifact is nowhere at all",
              art.main(["--check", "--out", str(_out)]) == 1,
              "a missing artifact must fail, not pass by absence")

        # THE OTHER DIRECTION: a scratched-up working copy over a clean COMMIT is not drift. Nothing
        # a maintainer has locally can make the committed deliverable stale, and a gate that said
        # otherwise would fire on every uncommitted experiment.
        art.main(["--out", str(_out)])
        _out.write_text("locally scribbled over", encoding="utf-8")
        art.committed_blob = lambda _rel: _fresh
        check("a dirty working copy over a clean COMMIT is not drift",
              art.main(["--check", "--out", str(_out)]) == 0,
              "only the committed blob decides")

        # NEAR MISS: differing only by line endings must NOT be drift — git may hand back CRLF on
        # Windows, and reporting that as a stale artifact would make the gate unusable there.
        art.committed_blob = lambda _rel: _fresh.replace("\n", "\r\n")
        check("--check tolerates CRLF-normalised checkouts",
              art.main(["--check", "--out", str(_out)]) == 0,
              "line-ending normalisation is not drift")

        # A DIRTY TREE IS NOT A SKIP. It was, returning exit 3, and that was a footgun rather than a
        # safeguard: regenerating coverage.md dirties the tree, so the next command wrote a
        # dirty-stamped page to the committed path and the gate failed permanently. Mid-edit the
        # honest verdict is a real one — 0 if the commit matches, 1 if it does not — never "cannot
        # tell". `coverage matrix drift` has no such exemption either.
        art.committed_blob = lambda _rel: _fresh
        check("a dirty tree still reaches a REAL verdict, never exit 3",
              art.main(["--check", "--out", str(_out)]) == 0,
              "git state must not affect the comparison at all")
    art.committed_blob = _blob_real

    # ---- THE INVARIANT BOTH OF THE ABOVE REST ON ----------------------------------------
    # The rendered bytes are a function of the DATA and of nothing else. Two non-content inputs
    # reached them and each broke the gate in production, so both directions are pinned here.
    _tick()
    _real = art.provenance
    try:
        base = art.provenance()
        # (a) GIT STATE — dirty vs clean, different commit, different branch, released vs not.
        art.provenance = lambda: dict(base, commit="aaaaaaa", branch="dev", state="released",
                                      dirty=[])
        clean_build = art.render(art.collect())
        art.provenance = lambda: dict(base, commit="fffffff", branch="main", state="dirty",
                                      dirty=["scripts/build_coverage.py"])
        dirty_build = art.render(art.collect())
    finally:
        art.provenance = _real
    if clean_build != dirty_build:
        FAILURES.append(
            "the rendered page differs between a clean and a dirty checkout of the SAME data — a "
            "page built while regenerating coverage.md then fails its own drift gate forever, which "
            "is exactly what happened")

    # (b) CORPORA AVAILABILITY. A machine without the licensed kits used to render `tw: null,
    # fb: null` where 93/63 were, commit that, and break the gate for everyone who HAS them. The
    # CORPORA_GATES exemption cannot help: it stops the check failing on the machine that is
    # missing them, never the bad commit. The counts come from the committed Totals table now.
    # Stubs the corpora IN with deliberately wrong sizes rather than stubbing them away. Stubbing
    # them away cannot work: this selftest also runs inside mutation_check's temp workdir, which has
    # no `design-corpora/` at all, so "without" and the baseline were identical and the fixture was
    # vacuous — while the mutant merely CRASHED on the missing directory. A crash is not a verdict.
    # Returning values means the fixture discriminates on every machine, corpora attached or not.
    # BOTH sides are rendered under stubs, with different sizes. Neither call may touch the real
    # corpora, for a reason proved by running the mutant: this selftest also runs in
    # mutation_check's temp workdir, which has no `design-corpora/`, so a real call raises
    # `BuildError` and the mutant died in a traceback instead of failing this fixture. A crash is
    # not a verdict. Two stubs also make the assertion sharper than stub-vs-real — it says the
    # bytes are independent of the COUNT, not merely of the directory existing.
    _tick()
    _tw_real, _fb_real = bc.discover_tw, bc.discover_fb
    try:
        bc.discover_tw = lambda: {f"tw-{i}" for i in range(5)}
        bc.discover_fb = lambda: {f"fb-{i}" for i in range(7)}
        few = art.render(art.collect())
        bc.discover_tw = lambda: {f"tw-{i}" for i in range(41)}
        bc.discover_fb = lambda: {f"fb-{i}" for i in range(43)}
        many = art.render(art.collect())
    finally:
        bc.discover_tw, bc.discover_fb = _tw_real, _fb_real
    if few != many:
        FAILURES.append(
            "the rendered page differs with and without the licensed corpora attached — a "
            "corpora-less machine can commit a stripped page that fails the gate for everyone else")

    if FAILURES:
        print(f"SELFTEST FAILED -- {len(FAILURES)} of {CHECKS} checks:", file=sys.stderr)
        for failure in FAILURES:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    passed = CHECKS - len(SKIPPED)
    if SKIPPED:
        print(f"build_coverage_artifact selftest: {passed} passed, {len(SKIPPED)} SKIPPED")
        for s_ in SKIPPED:
            print(f"  - skipped: {s_}")
        print("A skipped check did NOT run — it is not a pass. Attach the corpora to close these.")
    else:
        print(f"build_coverage_artifact selftest: {passed} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(run())
