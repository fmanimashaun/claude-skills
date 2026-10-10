#!/usr/bin/env python3
"""Record which examples are already red on the integration branch, and say whether that record can still be trusted (#1567).

Run:  python3 dev_baseline.py record --run "bundle exec rspec --no-color" --expect-ref origin/dev
      python3 dev_baseline.py record --from rspec-output.txt            # a run you already have
      python3 dev_baseline.py check  --ref origin/dev                   # fresh, or stale and why
      python3 dev_baseline.py --selftest

WHY THIS EXISTS. A red suite does not say whose red it is. The branch's own, dev's already, or a flake
that passes on a second go all print the same `rspec ./spec/foo_spec.rb:12`, and each one costs a manual
investigation (Retask-platform#1197, an e2e flake under load, read as a regression). Answering that needs
a record of what was failing on dev BEFORE the branch, and `triage_failures.py` reads it.

THE BASELINE IS A RATCHET, NOT A THRESHOLD. It is the exact list of failing example ids at ONE commit. It
is never "N failures are acceptable". A number lets a new failure hide behind an old one; a list does not.

A BASELINE AT THE WRONG COMMIT IS STALE, NOT TRUSTED. It is only evidence about the commit it was
measured at. A branch's merge base with the integration ref is the commit its failures should be compared
against, so `check` compares the recorded commit with that merge base. When they differ it says STALE and
exits 3; `triage_failures.py` then claims no PREEXISTING at all, because "it was red on some other
commit" proves nothing about this one.

WHAT THIS DELIBERATELY DOES NOT DO. It does not schedule itself: the refresh job is the project's choice
(cron, launchd, CI), and this ships the script, not a scheduler. It does not assume a database, a
framework or a layout: the suite command is whatever you pass, and the only thing read from the output is
the standard `rspec ./path:line` rows of RSpec's "Failed examples:" list (or its `--format json`).

EXIT CODES:  0 recorded / fresh   1 the suite could not be read   2 bad usage   3 STALE

Stdlib only. `--selftest` never touches a real repository except the temporary one it builds.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fixture_git  # noqa: E402

DEFAULT_BASELINE = ".rails-flow/dev-baseline.json"
VERSION = 1

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
# `rspec ./spec/a_spec.rb:12` and `rspec ./spec/a_spec.rb[1:2:3]`, anchored to the start of the line: RSpec
# prints this list from column 0, and a description that happens to contain "rspec ./x" must not count.
FAILED_ROW = re.compile(r"^rspec (\./\S+)", re.MULTILINE)
# "1 error occurred outside of examples": a spec file failed to LOAD, so its examples never ran and appear in no
# failure list. A run with that line has examples nobody counted, however clean the rest of it reads.
OUTSIDE_ERRORS = re.compile(r"\b[1-9]\d* errors? occurred outside of examples\b")


def normalise(example_id: str) -> str:
    """The one spelling every comparison uses: a leading `./`, no surrounding space."""
    example_id = example_id.strip()
    return example_id if example_id.startswith("./") else "./" + example_id


def has_outside_errors(output: str) -> bool:
    """True when the run reports errors outside of examples (text summary or json summary)."""
    text = ANSI.sub("", output)
    if OUTSIDE_ERRORS.search(text):
        return True
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError:
            return False
        if isinstance(data, dict) and isinstance(data.get("summary"), dict):
            return (data["summary"].get("errors_outside_of_examples_count") or 0) > 0
    return False


def parse_failures(output: str) -> list[str] | None:
    """The failing example ids in an RSpec run, sorted and de-duplicated; None when it cannot tell.

    None is not the same as an empty list. A suite that printed nothing we can read would otherwise record
    "no failures", which is the flattering answer to a question the output never answered. A run with errors
    outside of examples is None for the same reason (#1567 review): a dev that fails to LOAD has no failed
    examples to list, and would read as clean.
    """
    if has_outside_errors(output):
        return None
    text = ANSI.sub("", output)
    stripped = text.lstrip()
    if stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except ValueError:
            data = None
        if isinstance(data, dict) and isinstance(data.get("examples"), list):
            ids = set()
            for example in data["examples"]:
                if example.get("status") != "failed":
                    continue
                path, line = example.get("file_path"), example.get("line_number")
                if path and line:
                    ids.add(normalise(f"{path}:{line}"))
            return sorted(ids)
    rows = FAILED_ROW.findall(text)
    if rows:
        return sorted({normalise(r) for r in rows})
    # A passing run has no "Failed examples:" list; it has a summary that says so. Anything else is unreadable.
    if re.search(r"\b\d+ examples?, 0 failures?\b", text):
        return []
    return None


def git(*args: str, cwd: str | None = None) -> str:
    env = None
    if cwd is not None:
        # The caller NAMED the repository, so a GIT_DIR inherited from a hook must not redirect git to another one.
        env = {k: v for k, v in os.environ.items() if k not in fixture_git.REPO_LOCATORS}
    done = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env)
    if done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {done.stderr.strip() or 'failed'}")
    return done.stdout.strip()


def file_of(example_id: str) -> str:
    """The spec file an example id names: `./spec/a_spec.rb:12` and `./spec/a_spec.rb[1:2]` are both `./spec/a_spec.rb`."""
    return re.split(r"[:\[]", normalise(example_id), maxsplit=1)[0]


def touched_files(ref: str, cwd: str | None = None) -> set[str] | None:
    """Files this branch changed since its merge base with `ref`, committed or not, as `./path`; None when unknown.

    None is conservative on purpose: a baseline entry is only evidence about a spec this branch did not edit, so
    when the changed set cannot be read nothing is called PREEXISTING (#1567 review).
    """
    try:
        base = git("merge-base", "HEAD", ref, cwd=cwd)
        names = git("diff", "--name-only", base, cwd=cwd)
    except RuntimeError:
        return None
    return {normalise(n) for n in names.splitlines() if n.strip()}


def write_baseline(path: Path, commit: str, failures: list[str], command: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "version": VERSION,
        "commit": commit,
        "measured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "command": command,
        "failures": failures,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(body, indent=2) + "\n")
    tmp.replace(path)


def read_baseline(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("version") != VERSION:
        return None
    if not isinstance(data.get("commit"), str) or not isinstance(data.get("failures"), list):
        return None
    return data


def freshness(baseline: dict, ref: str, cwd: str | None = None) -> tuple[bool, str]:
    """(fresh, why). Fresh means measured at the merge base of HEAD and `ref`, and at nothing else."""
    base = git("merge-base", "HEAD", ref, cwd=cwd)
    recorded = baseline["commit"]
    if recorded == base:
        return True, f"measured at the merge base {base[:8]}"
    return False, f"measured at {recorded[:8]}, but the merge base with {ref} is {base[:8]}"


def cmd_record(args: argparse.Namespace) -> int:
    cwd = args.cwd
    try:
        head = git("rev-parse", "HEAD", cwd=cwd)
        if args.expect_ref:
            want = git("rev-parse", args.expect_ref, cwd=cwd)
            if head != want:
                print(f"dev_baseline: HEAD is {head[:8]} but {args.expect_ref} is {want[:8]}: "
                      "a baseline must be measured AT the ref it claims. Check it out first.", file=sys.stderr)
                return 2
    except RuntimeError as err:
        print(f"dev_baseline: {err}", file=sys.stderr)
        return 2
    if args.from_file:
        try:
            output, command = Path(args.from_file).read_text(), f"--from {args.from_file}"
        except OSError as err:
            print(f"dev_baseline: {err}", file=sys.stderr)
            return 2
    else:
        # Foreground, one run, the whole output kept. The suite's own exit status is NOT the verdict: a red
        # suite is the case this exists for.
        done = subprocess.run(shlex.split(args.run), cwd=cwd, capture_output=True, text=True)
        output, command = done.stdout + "\n" + done.stderr, args.run
    failures = parse_failures(output)
    if failures is None:
        print("dev_baseline: could not read an RSpec result from that output (no 'Failed examples:' rows, "
              "no '0 failures' summary, no JSON). Nothing recorded.", file=sys.stderr)
        return 1
    write_baseline(Path(args.baseline), head, failures, command)
    print(f"dev_baseline: recorded {len(failures)} failing example(s) at {head[:8]} -> {args.baseline}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    baseline = read_baseline(Path(args.baseline))
    if baseline is None:
        print(f"dev_baseline: no readable baseline at {args.baseline}", file=sys.stderr)
        return 2
    try:
        fresh, why = freshness(baseline, args.ref, cwd=args.cwd)
    except RuntimeError as err:
        print(f"dev_baseline: {err}", file=sys.stderr)
        return 2
    print(("FRESH" if fresh else "STALE") + ": " + why)
    return 0 if fresh else 3


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    text = ("Failed examples:\n\nrspec ./spec/a_spec.rb:1 # a\nrspec ./spec/a_spec.rb:12 # b\n"
            "rspec ./spec/a_spec.rb:1 # a again\n")
    expect("failed rows are read, sorted, de-duplicated",
           parse_failures(text) == ["./spec/a_spec.rb:1", "./spec/a_spec.rb:12"])
    expect("an id that is a prefix of another stays a different id",
           "./spec/a_spec.rb:1" in parse_failures(text) and "./spec/a_spec.rb:12" in parse_failures(text))
    expect("colour codes do not hide a row",
           parse_failures("\x1b[31mrspec ./spec/c_spec.rb:3\x1b[0m # c\n") == ["./spec/c_spec.rb:3"])
    expect("a passing run reads as no failures, not as unreadable",
           parse_failures("Finished in 1s\n12 examples, 0 failures\n") == [])
    expect("unreadable output is None, never an empty baseline", parse_failures("Segmentation fault\n") is None)
    expect("a description that mentions rspec is not a row",
           parse_failures("  1) x\n     # rspec ./spec/z_spec.rb:9\n3 examples, 1 failure\n") is None)
    as_json = json.dumps({"examples": [
        {"status": "failed", "file_path": "./spec/j_spec.rb", "line_number": 7},
        {"status": "passed", "file_path": "./spec/j_spec.rb", "line_number": 8}]})
    expect("a json run reads the failed examples only", parse_failures(as_json) == ["./spec/j_spec.rb:7"])
    expect("ids are normalised to a leading ./", normalise("spec/a_spec.rb:1") == "./spec/a_spec.rb:1")
    # #1567 review: a dev that fails to LOAD prints no failed examples at all.
    load_error = ("An error occurred while loading ./spec/x_spec.rb.\n\nFinished in 0.01 seconds\n"
                  "0 examples, 0 failures, 1 error occurred outside of examples\n")
    expect("a run with errors outside of examples is unreadable, never an empty baseline",
           parse_failures(load_error) is None)
    expect("...even when it also lists failed examples",
           parse_failures("rspec ./spec/a_spec.rb:1 # a\n2 examples, 1 failure, 2 errors occurred outside of examples\n") is None)
    json_load_error = json.dumps({"examples": [], "summary": {"errors_outside_of_examples_count": 1}})
    expect("a json run with errors_outside_of_examples_count > 0 is unreadable",
           parse_failures(json_load_error) is None)
    expect("a json run with a zero count is read normally",
           parse_failures(json.dumps({"examples": [], "summary": {"errors_outside_of_examples_count": 0}})) == [])
    expect("a spec file is the part of an id before the line or the group path",
           file_of("./spec/a_spec.rb:12") == "./spec/a_spec.rb" and file_of("spec/a_spec.rb[1:2]") == "./spec/a_spec.rb")

    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp)

        def run(*a: str) -> str:
            return fixture_git.run(repo, *a).stdout.strip()

        fixture_git.init(repo, "-b", "main")
        (repo / "f").write_text("1")
        run("add", "f")
        run("commit", "-q", "-m", "one")
        first = run("rev-parse", "HEAD")
        (repo / "f").write_text("2")
        run("commit", "-q", "-am", "two")
        second = run("rev-parse", "HEAD")
        out = repo / "rspec.txt"
        out.write_text("rspec ./spec/a_spec.rb:1 # a\n")
        base = repo / "baseline.json"
        argv = ["record", "--from", str(out), "--baseline", str(base), "--cwd", str(repo)]
        ns = build_parser().parse_args(argv)
        expect("a recorded baseline exits 0", cmd_record(ns) == 0)
        data = read_baseline(base)
        expect("it carries the commit and the failing ids",
               data is not None and data["commit"] == second and data["failures"] == ["./spec/a_spec.rb:1"])
        expect("measured at the merge base is fresh", freshness(data, "main", cwd=str(repo))[0])
        run("checkout", "-q", "-b", "feature", first)
        (repo / "g").write_text("x")
        run("add", "g")
        run("commit", "-q", "-m", "branch")
        (repo / "spec_touched.rb").write_text("y")
        run("add", "spec_touched.rb")
        run("commit", "-q", "-m", "branch two")
        (repo / "f").write_text("dirty")
        touched = touched_files("main", cwd=str(repo))
        expect("the files this branch changed since the merge base are read, committed or not",
               touched is not None and {"./g", "./spec_touched.rb", "./f"} <= touched)
        expect("a ref that does not exist leaves the changed set unknown, not empty",
               touched_files("no-such-ref", cwd=str(repo)) is None)
        run("checkout", "-q", "--", "f")
        fresh, why = freshness(data, "main", cwd=str(repo))
        expect("a baseline at a commit that is not the merge base is stale", not fresh and "merge base" in why)
        nsc = build_parser().parse_args(["check", "--baseline", str(base), "--ref", "main", "--cwd", str(repo)])
        expect("check exits 3 on a stale baseline", cmd_check(nsc) == 3)
        bad_ref = build_parser().parse_args(argv + ["--expect-ref", "main"])
        expect("record refuses to measure a ref that is not checked out", cmd_record(bad_ref) == 2)
        junk = repo / "junk.txt"
        junk.write_text("nothing here\n")
        unreadable = build_parser().parse_args(["record", "--from", str(junk), "--baseline", str(repo / "b2.json"),
                                                "--cwd", str(repo)])
        expect("unreadable output records nothing and exits 1",
               cmd_record(unreadable) == 1 and not (repo / "b2.json").exists())

    if bad:
        print(f"dev_baseline selftest FAILED ({len(bad)} of {ok + len(bad)}):", file=sys.stderr)
        for label in bad:
            print(f"  - {label}", file=sys.stderr)
        return 1
    print(f"dev_baseline selftest ok: {ok} checks")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    sub = ap.add_subparsers(dest="cmd")
    rec = sub.add_parser("record", help="record the failing example ids at the current commit")
    src = rec.add_mutually_exclusive_group(required=True)
    src.add_argument("--run", help="the suite command to run, in --cwd (foreground, once)")
    src.add_argument("--from", dest="from_file", help="a saved RSpec output instead of running it")
    rec.add_argument("--expect-ref", help="refuse unless HEAD is this ref (e.g. origin/dev)")
    chk = sub.add_parser("check", help="say whether the baseline is fresh for HEAD against --ref")
    chk.add_argument("--ref", default="origin/dev")
    for p in (rec, chk):
        p.add_argument("--baseline", default=DEFAULT_BASELINE)
        p.add_argument("--cwd", default=None)
    return ap


def main(argv: list[str] | None = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.cmd == "record":
        return cmd_record(args)
    if args.cmd == "check":
        return cmd_check(args)
    ap.print_usage(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
