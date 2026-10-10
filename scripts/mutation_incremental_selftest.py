#!/usr/bin/env python3
"""Selftest for scripts/mutation_incremental.py (#1738, #1739). Every rule has a case that must fail when the rule is broken.

Run as `python3 scripts/mutation_incremental_selftest.py`. The guard `scripts/mutations/mutation_incremental.py` breaks the subject one
rule at a time and requires the case named in each mutation's `expects` to trip.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mutation_incremental as inc  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "rails-flow" / "scripts"))
import fixture_git as fg  # noqa: E402 -- hermetic temp repos, bound to themselves (#1588)

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


def git(root: Path, *args: str) -> str:
    return fg.run(root, *args, check=False).stdout.strip()


def commit(root: Path, message: str = "c") -> str:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


def populate(root: Path, g) -> None:
    for rel, body in ((f"scripts/mutations/{g.name}.py", "decl"), ("scripts/s.py", "subject"), ("scripts/s_selftest.py", "selftest"),
                      ("scripts/dep.py", "dep"), ("docs/need.md", "need"), ("docs/dir/a.txt", "a"), ("docs/dir/sub/n.txt", "n")):
        write(root, rel, body)
    for rel in (*inc.HARNESS_FILES, "scripts/mutation_check.py", "plugins/rails-flow/scripts/process_containment.py"):
        write(root, rel, "h")


def hashing() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        g = guard(deps=("scripts/dep.py",), needs=("docs/need.md", "docs/dir"))
        populate(root, g)
        base = inc.guard_hash(root, g)
        check("hash: the same files hash the same", inc.guard_hash(root, g) == base)
        for label, rel in (("the subject", "scripts/s.py"), ("the selftest", "scripts/s_selftest.py"), ("a dep", "scripts/dep.py"),
                           ("a needs file", "docs/need.md"), ("a file inside a needs directory", "docs/dir/a.txt"),
                           ("a file NESTED under a needs directory", "docs/dir/sub/n.txt"),
                           ("the guard's own mutation module", "scripts/mutations/g.py")):
            original = (root / rel).read_bytes()
            write(root, rel, original + b" changed")
            check(f"hash: a change to {label} changes the hash", inc.guard_hash(root, g) != base)
            write(root, rel, original)
        write(root, "docs/dir/c.txt", "new")
        check("hash: a NEW file inside a needs directory changes the hash", inc.guard_hash(root, g) != base)
        (root / "docs/dir/c.txt").unlink()
        write(root, "unrelated.txt", "x")
        check("hash: a file the guard does not stage does not change the hash", inc.guard_hash(root, g) == base)
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
        plug = guard(name="p", base="plugins/x")
        write(root, "plugins/x/scripts/mutations/p.py", "decl")
        write(root, "plugins/x/scripts/s.py", "one")
        write(root, "plugins/x/scripts/s_selftest.py", "t")
        first = inc.guard_hash(root, plug)
        write(root, "plugins/x/scripts/s.py", "two")
        check("hash: a plugin-based guard hashes the files under its base", inc.guard_hash(root, plug) != first)
        check("hash: a plugin-based guard also hashes its declaration under the plugin", "plugins/x/scripts/mutations/p.py" in inc.guard_files(plug))

        helper = "plugins/rails-flow/scripts/process_containment.py"
        h = inc.harness_hash(root)
        write(root, "scripts/mutation_check.py", "changed")
        check("harness: editing the runner changes the harness hash", inc.harness_hash(root) != h)
        write(root, "scripts/mutation_check.py", "h")
        write(root, helper, "changed")
        check("harness: editing a helper the runner leans on changes the harness hash", inc.harness_hash(root) != h)


def git_objects() -> None:
    """The proof commit's hashes are recomputed from its OWN objects, and agree with the working tree's for the same content."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fg.init(root)
        g = guard(deps=("scripts/dep.py",), needs=("docs/need.md", "docs/dir"))
        populate(root, g)
        c1 = commit(root)
        tree = inc.GitTree(root, c1)
        check("git: a commit's hash equals the working tree's for the same content", inc.guard_hash(tree, g) == inc.guard_hash(root, g))
        check("git: the harness hash of a commit equals the working tree's", inc.harness_hash(tree) == inc.harness_hash(root))
        write(root, "scripts/s.py", "edited after the commit, never committed")
        check("git: an uncommitted edit changes the working-tree hash", inc.guard_hash(root, g) != inc.guard_hash(tree, g))
        check("git: the commit's own hash does not move when the working tree does", inc.guard_hash(tree, g) == inc.guard_hash(inc.GitTree(root, c1), g))
        write(root, "docs/dir/sub/n.txt", "n2")
        check("git: a nested edit in a needs directory is seen against the commit", inc.guard_hash(root, g) != inc.guard_hash(tree, g))
        check("git: a file absent at the commit reads as missing, not as an error", tree.read("no/such/file") is None)
        check("git: a directory is recognised as one", tree.is_dir("docs/dir") and not tree.is_dir("docs/need.md"))
        check("git: a commit that does not exist reads nothing", inc.GitTree(root, "0" * 40).read("scripts/s.py") is None)


def first_parents() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fg.init(root, "-b", "main")
        write(root, "a.txt", "1")
        base = commit(root, "base")
        git(root, "checkout", "-q", "-b", "side")
        write(root, "b.txt", "2")
        side = commit(root, "side-only")
        git(root, "checkout", "-q", "main")
        git(root, "merge", "-q", "--no-ff", "-m", "merge side", "side")
        tip = git(root, "rev-parse", "HEAD")
        check("first-parent: with no origin/main nothing is trusted", inc.main_first_parents(root) == [])
        git(root, "update-ref", "refs/remotes/origin/main", tip)
        got = inc.main_first_parents(root)
        check("first-parent: the merge commit and the main line are listed, newest first", got == [tip, base], str(got))
        check("first-parent: a commit that only lives on a side branch is NOT a candidate", side not in got, str(got))
        check("first-parent: the lookback bounds the list", inc.main_first_parents(root, 1) == [tip])


def trust() -> None:
    """THE FORGERY CASES (security review of #1738). A pull request can write anything in the tree it proposes; none of it may skip a guard."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        fg.init(root)
        g = guard(needs=("docs/need.md",))
        h = guard(name="h", subject="scripts/h.py", selftest="scripts/h_selftest.py")
        populate(root, g)
        write(root, "scripts/mutations/h.py", "decl")
        write(root, "scripts/h.py", "h subject")
        write(root, "scripts/h_selftest.py", "h selftest")
        proven = commit(root, "proven by a full run")
        guards = [g, h]

        def skips(*, candidates, has_proof=lambda sha: True, tree_at=None, harness=None, hashes=None):
            now = hashes if hashes is not None else {x.name: inc.guard_hash(root, x) for x in guards}
            return inc.trusted_skips(guards, now, harness if harness is not None else inc.harness_hash(root), candidates, has_proof,
                                     tree_at or (lambda sha: inc.GitTree(root, sha)))

        got = skips(candidates=[proven])
        check("trust: unchanged guards are skipped, with the proof commit", got == {"g": proven, "h": proven}, str(got))
        check("trust: no candidate commit skips nothing", skips(candidates=[]) == {})
        check("trust: a commit with no CI proof skips nothing", skips(candidates=[proven], has_proof=lambda sha: False) == {})

        # The attack: weaken a guard in the PR AND write whatever hashes the PR likes into any file it commits.
        write(root, "scripts/s.py", "WEAKENED subject")
        write(root, "docs/evidence/mutation-proof.json", json.dumps({"systems": {"linux": {"guards": {"g": inc.guard_hash(root, g)}}}}))
        got = skips(candidates=[proven])
        check("trust: a guard the pull request changed is NOT skipped, whatever hash file the pull request wrote", "g" not in got and "h" in got, str(got))
        write(root, "scripts/s.py", "subject")
        os.remove(root / "docs/evidence/mutation-proof.json")

        write(root, "scripts/mutation_check.py", "a harness edit")
        check("trust: a harness change since the proof forces a full run", skips(candidates=[proven]) == {})
        write(root, "scripts/mutation_check.py", "h")

        newer = commit(root, "newer, no proof")
        check("trust: the newest commit WITH a proof is used, a newer one without is passed over",
              skips(candidates=[newer, proven], has_proof=lambda sha: sha == proven) == {"g": proven, "h": proven})
        write(root, "scripts/s.py", "changed and committed, no proof")
        weakened = commit(root, "a weakened guard, committed but never proven")
        got = skips(candidates=[weakened, proven], has_proof=lambda sha: sha == proven)
        check("trust: a guard committed after the proof and never proven is NOT skipped", "g" not in got, str(got))
        got = skips(candidates=[weakened], has_proof=lambda sha: True)
        check("trust: a proof posted ON a commit vouches for that commit's own files (CI posts it only after a full run)",
              got.get("g") == weakened)

        def exploding(sha):
            raise OSError("cannot read")

        def safely(**kw):
            try:
                return skips(**kw)
            except Exception as exc:        # noqa: BLE001 -- the check below fails by name
                return f"raised {exc!r}"

        check("trust: an unreadable proof commit skips nothing (fail to a full run)", safely(candidates=[proven], tree_at=exploding) == {})
        check("trust: a lookup that raises skips nothing", safely(candidates=[proven], has_proof=lambda sha: 1 / 0) == {})
        check("trust: a guard missing at the proof commit is not skipped",
              "new" not in inc.trusted_skips([guard(name="new", subject="scripts/new.py")], {"new": "x"}, inc.harness_hash(root), [proven],
                                             lambda sha: True, lambda sha: inc.GitTree(root, sha)))

    status = json.dumps([{"context": "mutation-proof/linux", "state": "success"}, {"context": "other", "state": "failure"}])
    check("status: a success on mutation-proof/<os> is a proof", inc.status_has_proof(status, "linux") is True)
    check("status: a proof for another OS is not", inc.status_has_proof(status, "darwin") is False)
    check("status: the NEWEST state of the context counts (a later failure withdraws it)",
          inc.status_has_proof(json.dumps([{"context": "mutation-proof/linux", "state": "failure"},
                                           {"context": "mutation-proof/linux", "state": "success"}]), "linux") is False)
    check("status: a success that is not on the proof context is not a proof",
          inc.status_has_proof(json.dumps([{"context": "full-sweep", "state": "success"}]), "linux") is False)
    check("status: unparseable output is no proof", inc.status_has_proof("not json", "linux") is False)
    check("status: a non-list payload is no proof", inc.status_has_proof(json.dumps({"message": "Not Found"}), "linux") is False)

    def stub(returncode, stdout="", stderr=""):
        calls: list[list[str]] = []

        def run(argv, **kw):
            calls.append(list(argv))
            return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)
        return run, calls

    saved = os.environ.get("GITHUB_REPOSITORY")
    os.environ["GITHUB_REPOSITORY"] = "o/r"
    try:
        run, calls = stub(0, status)
        lookup = inc.github_proof_lookup(Path("."), "linux", run=run)
        check("lookup: a commit whose statuses hold the proof reads as proven", lookup("abc") is True)
        check("lookup: it asks the statuses endpoint of that commit", any("repos/o/r/commits/abc/statuses" in a for a in calls[0]), str(calls))
        run, _ = stub(1, status, "HTTP 403")
        check("lookup: an API error reads as NO proof, never as proof", inc.github_proof_lookup(Path("."), "linux", run=run)("abc") is False)

        def missing_gh(argv, **kw):
            raise FileNotFoundError("gh")
        check("lookup: no `gh` on the machine reads as NO proof", inc.github_proof_lookup(Path("."), "linux", run=missing_gh)("abc") is False)
    finally:
        if saved is None:
            os.environ.pop("GITHUB_REPOSITORY", None)
        else:
            os.environ["GITHUB_REPOSITORY"] = saved

    main_env = {"GITHUB_ACTIONS": "true", "GITHUB_REF": "refs/heads/main", "GITHUB_REPOSITORY": "o/r"}
    check("skip_allowed: CI on main may skip a proven, unchanged guard", inc.skip_allowed(main_env) is True)
    for label, env in (("a pull request run", dict(main_env, GITHUB_REF="refs/pull/9/merge")),
                       ("a dispatch on a branch", dict(main_env, GITHUB_REF="refs/heads/feature/x")),
                       ("CI on dev", dict(main_env, GITHUB_REF="refs/heads/dev")),
                       ("a tag", dict(main_env, GITHUB_REF="refs/tags/v1.0.0")),
                       ("a ref that merely starts like main", dict(main_env, GITHUB_REF="refs/heads/main-evil")),
                       ("a laptop with the ref set", {"GITHUB_REF": "refs/heads/main"}),
                       ("a laptop", {}),
                       ("GITHUB_ACTIONS that is not exactly true", dict(main_env, GITHUB_ACTIONS="1"))):
        check(f"skip_allowed: {label} never skips (the branch's own code decides the skip there)", inc.skip_allowed(env) is False)
    for label, env in (("a pull request run", dict(main_env, GITHUB_REF="refs/pull/9/merge")),
                       ("a dispatch on a branch", dict(main_env, GITHUB_REF="refs/heads/feature/x")),
                       ("a laptop", {"GITHUB_REF": "refs/heads/main", "GITHUB_REPOSITORY": "o/r"}),
                       ("CI on dev", dict(main_env, GITHUB_REF="refs/heads/dev"))):
        run, calls = stub(0)
        posted, why = inc.post_proof(env, "linux", "a" * 40, run=run)
        check(f"post: {label} never posts a proof", posted is False and not calls, why)
    run, calls = stub(0)
    posted, why = inc.post_proof(main_env, "linux", "a" * 40, run=run)
    check("post: CI on main posts mutation-proof/<os> = success on the commit",
          posted and any("repos/o/r/statuses/" + "a" * 40 in a for a in calls[0]) and "context=mutation-proof/linux" in calls[0] and "state=success" in calls[0],
          str(calls))
    run, calls = stub(1, "", "denied")
    posted, why = inc.post_proof(main_env, "linux", "a" * 40, run=run)
    check("post: a failed post says so and is not reported as posted", posted is False and "could not post" in why, why)
    run, calls = stub(0)
    check("post: no commit, no post", inc.post_proof(main_env, "linux", "", run=run)[0] is False and not calls)


def selection() -> None:
    gs = [SimpleNamespace(name=n) for n in ("a", "b", "c", "d")]
    hashes = {g.name: "h" for g in gs}
    skips = {"a": "p1", "b": "p1", "d": "p1"}
    run, skipped = inc.select_guards(gs, hashes, skips=skips, full=False, named=False, shard=None, weights={}, default=1.0)
    check("select: an incremental run skips what is trusted-unchanged and runs what changed",
          [g.name for g in run] == ["c"] and set(skipped) == {"a", "b", "d"}, f"{[g.name for g in run]} {skipped}")
    run, skipped = inc.select_guards(gs, hashes, skips=skips, full=True, named=False, shard=None, weights={}, default=1.0)
    check("select: --full skips nothing", len(run) == 4 and not skipped)
    run, skipped = inc.select_guards(gs, hashes, skips=skips, full=False, named=True, shard=None, weights={}, default=1.0)
    check("select: a guard named with --guard is run, not skipped", len(run) == 4 and not skipped)
    run, skipped = inc.select_guards(gs, hashes, skips={}, full=False, named=False, shard=None, weights={}, default=1.0)
    check("select: with no trusted proof every guard runs", len(run) == 4 and not skipped)
    seen: set[str] = set()
    for index in (1, 2):
        run, skipped = inc.select_guards(gs, hashes, skips={}, full=False, named=False, shard=(index, 2), weights={}, default=1.0)
        names_in = {g.name for g in run} | set(skipped)
        check(f"select: shard {index}/2 holds only its own guards", names_in.isdisjoint(seen) and names_in, str(names_in))
        seen |= names_in
    check("select: the two shards together cover every guard once", seen == {"a", "b", "c", "d"})
    s1, k1 = inc.select_guards(gs, hashes, skips=skips, full=False, named=False, shard=(1, 2), weights={}, default=1.0)
    s2, k2 = inc.select_guards(gs, hashes, skips={}, full=False, named=False, shard=(1, 2), weights={}, default=1.0)
    check("select: which shard owns a guard does not depend on which guards are skipped",
          {g.name for g in s1} | set(k1) == {g.name for g in s2} | set(k2))


def sharding() -> None:
    for text, want in (("1/4", (1, 4)), ("4/4", (4, 4)), ("1/1", (1, 1))):
        check(f"shard: {text} parses", _try(inc.parse_shard, text) == want)
    for text in ("0/4", "5/4", "2", "a/b", "1/0", "1/2/3", ""):
        check(f"shard: {text!r} is refused", _try(inc.parse_shard, text) == "refused")

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
    check("shard: the split follows cost, not count (the two heaviest guards are not together)", not any({"heavy0", "heavy1"} <= set(s) for s in a))
    skew = {"big": 900.0, **{f"s{i}": 100.0 for i in range(9)}}
    even = inc.assign_shards(list(skew), skew, 2, 60.0)
    check("shard: the split follows cost, not count (one heavy guard against nine light ones is exactly even)",
          sorted(sum(skew[n] for n in s) for s in even) == [900.0, 900.0], str(even))
    count_only = inc.assign_shards(names, {}, 4, 60.0)
    check("shard: with no cost record the split is by count and still covers every guard once",
          sorted(n for s in count_only for n in s) == sorted(names) and max(map(len, count_only)) - min(map(len, count_only)) <= 1)


def merging() -> None:
    names = {"a", "b", "c"}

    def shard(i, n=2, guards=(), skipped=(), **over):
        base = {"shard": i, "of": n, "os": "linux", "commit": "c1", "harness": "H", "jobs": 4,
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
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c",))], 2, names, commit="OTHER")
    check("merge: shard results for another commit than this checkout's are refused (stale or foreign artifacts)",
          merged is None and any("another commit" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c",))], 2, names, harness="OTHER")
    check("merge: shard results for another harness than this checkout's are refused", merged is None and any("another harness" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c",))], 2, names, commit="c1", harness="H")
    check("merge: results for this checkout's own commit and harness are accepted", merged is not None and not problems, str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a",)), shard(2, guards=("c",))], 2, names)
    check("merge: a guard no shard ran is a problem", merged is None and any("b: no shard" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("b", "c"))], 2, names)
    check("merge: a guard two shards ran is a problem", merged is None and any("b: more than one" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, guards=("c", "ghost"))], 2, names)
    check("merge: a guard that no longer exists is a problem", merged is None and any("ghost" in p for p in problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a", "b")), shard(2, n=3, guards=("c",))], 2, names)
    check("merge: a shard run as one of a different N is a problem", merged is None and bool(problems), str(problems))
    merged, problems = inc.merge_shards([shard(1, guards=("a",), skipped=("b",)), shard(2, guards=("c",))], 2, names)
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
    check("rebaseline: an explicit --host outside CI is accepted and is the label", (label, refusal) == ("my-laptop", None))
    label, refusal = inc.record_host({}, "github-actions/Linux", "darwin")
    check("rebaseline: outside CI a --host may not impersonate the CI runner", label is None and refusal and "claims to be the CI runner" in refusal, str((label, refusal)))
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
    git_objects()
    first_parents()
    trust()
    selection()
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
