#!/usr/bin/env python3
"""Selftest for scripts/mutation_incremental.py (#1738, #1739). Every rule has a case that must fail when the rule is broken.

Run as `python3 scripts/mutation_incremental_selftest.py`. The guard `scripts/mutations/mutation_incremental.py` breaks the
subject one rule at a time and requires the case named in each mutation's `expects` to trip.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutation_incremental as inc  # noqa: E402

FAILURES: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILURES.append(f"{label}{': ' + detail if detail else ''}")


def guard(name="g", base=".", subject="scripts/s.py", selftest="scripts/s_selftest.py", deps=(), needs=()):
    return SimpleNamespace(name=name, base=base, subject=subject, selftest=selftest, deps=tuple(deps), needs=tuple(needs))


def write(root: Path, relative: str, text: str | bytes) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))


def hashing() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        g = guard(deps=("scripts/dep.py",), needs=("docs/need.md", "docs/dir"))
        for rel, body in (("scripts/mutations/g.py", "decl"), ("scripts/s.py", "subject"), ("scripts/s_selftest.py", "selftest"),
                          ("scripts/dep.py", "dep"), ("docs/need.md", "need"), ("docs/dir/a.txt", "a"), ("docs/dir/b.txt", "b")):
            write(root, rel, body)
        base = inc.guard_hash(root, g)
        check("hash: the same files hash the same", inc.guard_hash(root, g) == base)
        for label, rel in (("the subject", "scripts/s.py"), ("the selftest", "scripts/s_selftest.py"), ("a dep", "scripts/dep.py"),
                           ("a needs file", "docs/need.md"), ("a file inside a needs directory", "docs/dir/b.txt"),
                           ("the guard's own mutation module", "scripts/mutations/g.py")):
            original = (root / rel).read_bytes()
            write(root, rel, original + b" changed")
            check(f"hash: a change to {label} changes the hash", inc.guard_hash(root, g) != base)
            write(root, rel, original)
        write(root, "docs/dir/sub/n.txt", "n")
        nested = inc.guard_hash(root, g)
        check("hash: a file NESTED under a needs directory is part of the hash", nested != base)
        (root / "docs/dir/sub/n.txt").unlink()
        (root / "docs/dir/sub").rmdir()
        write(root, "docs/dir/c.txt", "new")
        check("hash: a NEW file inside a needs directory changes the hash", inc.guard_hash(root, g) != base)
        (root / "docs/dir/c.txt").unlink()
        write(root, "unrelated.txt", "x")
        check("hash: a file the guard does not stage does not change the hash", inc.guard_hash(root, g) == base)
        write(root, "scripts/s.py", b"subject")
        write(root, "docs/need.md", b"nee" + b"d")
        crlf = guard(needs=("docs/crlf.md",))
        write(root, "docs/crlf.md", b"a\nb\n")
        lf_hash = inc.guard_hash(root, crlf)
        write(root, "docs/crlf.md", b"a\r\nb\r\n")
        check("hash: a CRLF checkout of the same text is not a change", inc.guard_hash(root, crlf) == lf_hash)
        write(root, "docs/bin.dat", b"\0a\r\nb")
        binary = guard(needs=("docs/bin.dat",))
        before = inc.guard_hash(root, binary)
        write(root, "docs/bin.dat", b"\0a\nb")
        check("hash: a binary file is hashed byte for byte, CRLF included", inc.guard_hash(root, binary) != before)
        gone = guard(needs=("docs/absent.md",))
        missing = inc.guard_hash(root, gone)
        write(root, "docs/absent.md", "")
        check("hash: a needs file that appears changes the hash (missing is not empty)", inc.guard_hash(root, gone) != missing)
        # A guard shipped inside a plugin resolves from its base, and a different base is a different file.
        plug = guard(name="p", base="plugins/x")
        write(root, "plugins/x/scripts/mutations/p.py", "decl")
        write(root, "plugins/x/scripts/s.py", "one")
        write(root, "plugins/x/scripts/s_selftest.py", "t")
        first = inc.guard_hash(root, plug)
        write(root, "plugins/x/scripts/s.py", "two")
        check("hash: a plugin-based guard hashes the files under its base", inc.guard_hash(root, plug) != first)
        check("hash: a plugin-based guard also hashes its declaration under the plugin", "plugins/x/scripts/mutations/p.py" in inc.guard_files(plug))

        helper = "plugins/rails-flow/scripts/process_containment.py"
        for rel in (*inc.HARNESS_FILES, "scripts/mutation_check.py", helper):
            write(root, rel, "h")
        h = inc.harness_hash(root)
        write(root, "scripts/mutation_check.py", "changed")
        check("harness: editing the runner changes the harness hash", inc.harness_hash(root) != h)
        write(root, "scripts/mutation_check.py", "h")
        write(root, helper, "changed")
        check("harness: editing a helper the runner leans on changes the harness hash", inc.harness_hash(root) != h)


def proof() -> None:
    hashes = {"a": "1", "b": "2"}
    record = {"systems": {"linux": {"commit": "c0ffee1234567890", "harness": "H", "guards": dict(hashes)}}}
    got = inc.skipped_guards(hashes, "H", record, "linux")
    check("skip: an unchanged guard on the same OS is skipped, with the commit it was recorded at",
          got == {"a": "c0ffee1234567890", "b": "c0ffee1234567890"}, str(got))
    got = inc.skipped_guards({"a": "1", "b": "CHANGED"}, "H", record, "linux")
    check("skip: a guard whose hash changed is NOT skipped, and its neighbour still is", set(got) == {"a"}, str(got))
    check("skip: a harness change forces a full run (nothing is skipped)", inc.skipped_guards(hashes, "H2", record, "linux") == {})
    check("skip: a record for another OS skips nothing", inc.skipped_guards(hashes, "H", record, "darwin") == {})
    check("skip: no record at all skips nothing", inc.skipped_guards(hashes, "H", None, "linux") == {})
    check("skip: a guard with no recorded hash runs", set(inc.skipped_guards({"a": "1", "new": "9"}, "H", record, "linux")) == {"a"})

    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "proof.json"
        check("proof: an absent file loads as None", inc.load_proof(path) is None)
        inc.write_proof(path, "linux", "c1", "H", {"b": "2", "a": "1"})
        first = path.read_bytes()
        inc.write_proof(path, "darwin", "c2", "H2", {"a": "x"})
        loaded = inc.load_proof(path)
        check("proof: writing one OS keeps another OS's entry", set(loaded["systems"]) == {"linux", "darwin"}, str(loaded))
        before = path.read_bytes()
        inc.write_proof(path, "darwin", "c2", "H2", {"a": "x"})
        check("proof: a second write of the same data is byte-identical", path.read_bytes() == before)
        inc.write_proof(path, "linux", "c1", "H", {"a": "1", "b": "2"})
        check("proof: the bytes are a function of the data (key order of the input does not matter)",
              json.loads(first)["systems"]["linux"] == json.loads(path.read_text())["systems"]["linux"])
        text = path.read_text()
        check("proof: keys are sorted and the file ends in one newline", text.endswith("}\n") and text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n")
        for label, body in (("not JSON", "{nope"), ("no systems object", '{"x": 1}'), ("a system without a harness", '{"systems": {"linux": {"guards": {}, "commit": "c"}}}')):
            path.write_text(body, encoding="utf-8")
            try:
                inc.load_proof(path)
            except ValueError:
                continue
            check(f"proof: a malformed record ({label}) raises, never reads as empty", False)


def sharding() -> None:
    for text, want in (("1/4", (1, 4)), ("4/4", (4, 4)), ("1/1", (1, 1))):
        check(f"shard: {text} parses", _try(inc.parse_shard, text) == want)
    for text in ("0/4", "5/4", "2", "a/b", "1/0", "1/2/3", ""):
        check(f"shard: {text!r} is refused", _try(inc.parse_shard, text) == "refused")

    # Real-shaped weights: a few heavy guards, a long tail.
    weights = {f"heavy{i}": 2800.0 - 150 * i for i in range(8)}
    weights.update({f"mid{i}": 400.0 - 15 * i for i in range(20)})
    names = list(weights) + [f"light{i}" for i in range(60)]
    for count in (2, 3, 4, 6):
        shards = inc.assign_shards(names, weights, count, 60.0)
        flat = [n for s in shards for n in s]
        check(f"shard N={count}: every guard is in exactly one shard", sorted(flat) == sorted(names) and len(flat) == len(set(flat)))
        loads = [sum(weights.get(n, 60.0) for n in s) for s in shards]
        mean = sum(loads) / count
        check(f"shard N={count}: no shard is over 1.5x the mean cost", max(loads) <= 1.5 * mean, str([round(x) for x in loads]))
        check(f"shard N={count}: no shard is empty", all(shards))
    a = inc.assign_shards(names, weights, 4, 60.0)
    b = inc.assign_shards(list(reversed(names)), weights, 4, 60.0)
    check("shard: the assignment is stable (the same inputs, in any order, give the same split)", a == b)
    check("shard: the split follows cost, not count (the two heaviest guards are not together)",
          not any({"heavy0", "heavy1"} <= set(s) for s in a))
    # A heavy guard alone balances nine light ones: only cost-aware placement gets this exactly even (a count-based or in-turn
    # deal leaves 1300 against 500).
    skew = {"big": 900.0, **{f"s{i}": 100.0 for i in range(9)}}
    even = inc.assign_shards(list(skew), skew, 2, 60.0)
    check("shard: the split follows cost, not count (one heavy guard against nine light ones is exactly even)",
          sorted(sum(skew[n] for n in s) for s in even) == [900.0, 900.0], str(even))
    count_only = inc.assign_shards(names, {}, 4, 60.0)
    check("shard: with no cost record the split is by count and still covers every guard once",
          sorted(n for s in count_only for n in s) == sorted(names) and max(map(len, count_only)) - min(map(len, count_only)) <= 1)

    # select_guards: the shard is chosen over ALL guards, then the skip applies inside it.
    gs = [SimpleNamespace(name=n) for n in ("a", "b", "c", "d")]
    hashes = {n.name: "h" for n in gs}
    record = {"systems": {"linux": {"commit": "cccccccccccc", "harness": "H", "guards": {"a": "h", "b": "h", "c": "stale", "d": "h"}}}}
    run, skipped = inc.select_guards(gs, hashes, "H", record, "linux", full=False, named=False, shard=None, weights={}, default=1.0)
    check("select: an incremental run skips what is unchanged and runs what changed",
          [g.name for g in run] == ["c"] and set(skipped) == {"a", "b", "d"}, f"{[g.name for g in run]} {skipped}")
    run, skipped = inc.select_guards(gs, hashes, "H", record, "linux", full=True, named=False, shard=None, weights={}, default=1.0)
    check("select: --full skips nothing", len(run) == 4 and not skipped)
    run, skipped = inc.select_guards(gs, hashes, "H", record, "linux", full=False, named=True, shard=None, weights={}, default=1.0)
    check("select: a guard named with --guard is run, not skipped", len(run) == 4 and not skipped)
    run, skipped = inc.select_guards(gs, hashes, "H2", record, "linux", full=False, named=False, shard=None, weights={}, default=1.0)
    check("select: a changed harness runs every guard", len(run) == 4 and not skipped)
    seen: set[str] = set()
    for index in (1, 2):
        run, skipped = inc.select_guards(gs, hashes, "H", None, "linux", full=False, named=False, shard=(index, 2), weights={}, default=1.0)
        names_in = {g.name for g in run} | set(skipped)
        check(f"select: shard {index}/2 holds only its own guards", names_in.isdisjoint(seen) and names_in, str(names_in))
        seen |= names_in
    check("select: the two shards together cover every guard once", seen == {"a", "b", "c", "d"})
    s1, k1 = inc.select_guards(gs, hashes, "H", record, "linux", full=False, named=False, shard=(1, 2), weights={}, default=1.0)
    s2, k2 = inc.select_guards(gs, hashes, "H", None, "linux", full=False, named=False, shard=(1, 2), weights={}, default=1.0)
    check("select: which shard owns a guard does not depend on which guards are skipped",
          {g.name for g in s1} | set(k1) == {g.name for g in s2} | set(k2))


def merging() -> None:
    names = {"a", "b", "c"}

    def shard(i, n=2, guards=(), skipped=(), **over):
        base = {"shard": i, "of": n, "os": "linux", "commit": "c1", "harness": "H", "jobs": 4, "full": True,
                "guards": {g: "h" for g in guards}, "skipped": {g: "old" for g in skipped}, "cost": {g: 10.0 for g in guards}}
        base.update(over)
        return base

    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c",))], 2, names)
    check("merge: every shard present and every guard covered once is accepted",
          not problems and merged and set(merged["guards"]) == names and merged["full"] is True, str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b"))], 2, names)
    check("merge: a MISSING shard is a problem, not a pass", merged is None and any("MISSING" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([], 2, names)
    check("merge: no shard reported at all is a problem", merged is None and len(problems) >= 2, str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(1, guards=("c",))], 2, names)
    check("merge: the same shard twice is a problem, and the missing one is named",
          merged is None and any("twice" in p for p in problems) and any("2/2 is MISSING" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c",), commit="c2")], 2, names)
    check("merge: shards for different commits are refused", merged is None and any("commit" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c",), harness="H2")], 2, names)
    check("merge: shards for different harnesses are refused", merged is None and any("harness" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a",)), shard(2, guards=("c",))], 2, names)
    check("merge: a guard no shard ran is a problem", merged is None and any("b: no shard" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("b", "c"))], 2, names)
    check("merge: a guard two shards ran is a problem", merged is None and any("b: more than one" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c", "ghost"))], 2, names)
    check("merge: a guard that no longer exists is a problem", merged is None and any("ghost" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, n=3, guards=("c",))], 2, names)
    check("merge: a shard run as one of a different N is a problem", merged is None and bool(problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a",), skipped=("b",), full=False), shard(2, guards=("c",))], 2, names)
    check("merge: a skipped guard counts as covered, and the set is then NOT full",
          merged is not None and merged["full"] is False, str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c",))], 2, names)
    check("merge: the merged cost holds every guard", merged is not None and set(merged["cost"]) == names)

    for result, fast, want in (("success", False, True), ("failure", False, False), ("cancelled", False, False),
                               ("skipped", False, False), ("", False, False), ("skipped", True, True), ("success", True, True),
                               ("failure", True, False), ("cancelled", True, False)):
        got, message = inc.summary_verdict(result, fast)
        check(f"summary: result {result!r} in {'fast' if fast else 'full'} mode is {'accepted' if want else 'refused'}", got is want, message)


def verdict_cli() -> None:
    import contextlib
    import io
    for argv, want, label in ((["verdict", "success", "full"], 0, "a successful full run exits 0"),
                              (["verdict", "failure", "full"], 1, "a failed shard exits 1"),
                              (["verdict", "cancelled", "full"], 1, "a cancelled shard exits 1"),
                              (["verdict", "skipped", "full"], 1, "a shard that never ran exits 1 in full mode"),
                              (["verdict", "skipped", "fast"], 0, "a fast run with no shards exits 0"),
                              (["verdict", "failure", "fast"], 1, "a failed shard exits 1 even in fast mode"),
                              (["verdict", "success"], 2, "a missing mode is misuse (2)"),
                              (["verdict", "success", "maybe"], 2, "an unknown mode is misuse (2)"),
                              (["nonsense", "success", "full"], 2, "an unknown command is misuse (2)")):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            got = inc.main(argv)
        check(f"verdict CLI: {label}", got == want, f"exit {got}")


def hosts() -> None:
    label, refusal = inc.record_host({}, None, "darwin")
    check("rebaseline: refused outside CI without --host", label is None and refusal and "--host" in refusal, str((label, refusal)))
    label, refusal = inc.record_host({}, "my-laptop", "darwin")
    check("rebaseline: an explicit --host is accepted and is the label", (label, refusal) == ("my-laptop", None))
    label, refusal = inc.record_host({"GITHUB_ACTIONS": "true", "RUNNER_OS": "Linux"}, None, "linux")
    check("rebaseline: CI is accepted, labelled with the runner", refusal is None and label == "github-actions/Linux", str((label, refusal)))
    label, refusal = inc.record_host({"GITHUB_ACTIONS": "false"}, None, "linux")
    check("rebaseline: only GITHUB_ACTIONS=true counts as CI", label is None and refusal is not None)


def _try(fn, *args):
    try:
        return fn(*args)
    except ValueError:
        return "refused"


def run() -> int:
    hashing()
    proof()
    sharding()
    merging()
    hosts()
    verdict_cli()
    for failure in FAILURES:
        print(f"FAIL: {failure}")
    print(f"mutation_incremental selftest: {'FAILED' if FAILURES else 'ok'} ({len(FAILURES)} failure(s))")
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(run())
