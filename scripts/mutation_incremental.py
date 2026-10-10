#!/usr/bin/env python3
"""What `mutation_check.py` decides BEFORE it runs a guard: skip it, or which shard owns it (#1738, #1739).

Pure functions plus a little injected I/O, so each rule can be driven by a selftest without running a guard.

INCREMENTAL PROOF (#1738). A full run costs about 64 minutes of runner time, and most guards are unchanged between two runs. A guard's
result is a function of the files the runner stages for it: its mutation module, subject, selftest, deps and `needs`. `guard_hash` hashes
exactly those, and `harness_hash` hashes the runner and its helpers. A guard is SKIPPED, reported `skip (unchanged since <sha>)` and never
counted as a pass, only when its hash NOW equals its hash AT A TRUSTED PROOF COMMIT, and the harness hash does too.

WHERE THE STATE LIVES, AND WHY IT IS NOT A FILE A PULL REQUEST CAN EDIT (decision, #1738; security review). The first design committed the
hashes in a JSON file. A pull request can edit that file: weaken a guard, write the weakened guard's new hash beside it, and the release
skips the guard it never ran. So the state is a COMMIT STATUS, `mutation-proof/<os>` = success, posted by CI on a commit of `main` after a
complete full run in which no guard was skipped (the weekly run, or a release). `trusted_skips` takes the newest `main` first-parent commit
that carries one, RECOMPUTES every hash from that commit's own git objects (`GitTree`), and compares them with the working tree's. Nothing a
pull request can write is consulted: its edits change the working-tree hash, and the proof commit's objects are immutable. No status, no
`gh`, no `origin/main`, a lookup error: nothing is skipped, which is the safe direction (a full run). The bytes are a function of the data.

SHARDS (#1739). `assign_shards` splits the guards over N jobs, largest recorded cost first onto the lightest shard: a pure function of the
guard names and the committed cost record, so the same inputs give the same split on every machine. `merge_shards` is what the summary job
runs: every shard present exactly once, for the commit and harness of THIS checkout, and together covering every guard exactly once. A
missing shard is a problem, never a pass.
"""
from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Mapping

HARNESS_FILES = (
    "scripts/mutation_check.py",
    "scripts/mutation_incremental.py",
    "scripts/mutation_types.py",
    "scripts/proc_group.py",
    "scripts/hermetic_git.py",
    "plugins/rails-flow/scripts/process_containment.py",
)

PROOF_CONTEXT = "mutation-proof"
LOOKBACK = 40            # main first-parent commits searched for a proof status
CI_HOST_PREFIX = "github-actions/"


def skip_allowed(env: Mapping[str, str]) -> bool:
    """True only in CI on `refs/heads/main`: a release, the weekly sweep, or a dispatch on main.

    WHERE THE DECIDING CODE RUNS IS PART OF THE TRUST (#1738, second security pass). `trusted_skips` compares hashes, but the comparison is made by
    the code in the checkout being run. On a pull request, a dispatch on a branch or a laptop that code is the branch's own, which its author can edit
    to skip any guard (or to print a green result for one) and no hash then proves anything. So off `main` nothing is skipped: every guard runs, the
    way it did before the incremental proof existed. The proof status itself is posted only from CI on `main` (`post_proof`), for the same reason."""
    return env.get("GITHUB_ACTIONS") == "true" and env.get("GITHUB_REF") == "refs/heads/main"


def os_key() -> str:
    return platform.system().lower() or "unknown"


def proof_context(system: str) -> str:
    return f"{PROOF_CONTEXT}/{system}"


# ---- reading files: the working tree, or a commit's own objects ---------------------------------------------------


class WorkTree:
    """The files as they are on disk now."""

    def __init__(self, repo: Path):
        self.repo = Path(repo)

    def is_dir(self, relative: str) -> bool:
        return (self.repo / relative).is_dir()

    def files_under(self, relative: str) -> list[str]:
        base = self.repo / relative
        found = [str(p.relative_to(self.repo)) for p in base.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"]
        return sorted(found)

    def read(self, relative: str) -> bytes | None:
        path = self.repo / relative
        return path.read_bytes() if path.is_file() else None


class GitTree:
    """The files as they were at `commit`, read from git's objects. Immutable: nothing in the working tree or the index can change them.

    One `ls-tree` lists the whole commit; each distinct file is read once. A hash over every guard would otherwise cost thousands of processes."""

    def __init__(self, repo: Path, commit: str):
        self.repo, self.commit = Path(repo), commit
        self._listing: dict[str, str] | None = None
        self._blobs: dict[str, bytes | None] = {}

    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-c", "gc.auto=0", "-C", str(self.repo), *args], capture_output=True, timeout=120,
                              stdin=subprocess.DEVNULL)

    def _files(self) -> dict[str, str]:
        if self._listing is None:
            out = self._git("ls-tree", "-r", "-z", self.commit)
            listing: dict[str, str] = {}
            for entry in (out.stdout.split(b"\0") if out.returncode == 0 else []):
                meta, _, name = entry.partition(b"\t")
                fields = meta.split()
                if len(fields) == 3 and fields[1] == b"blob":
                    listing[name.decode("utf-8")] = fields[2].decode("ascii")
            self._listing = listing
        return self._listing

    def is_dir(self, relative: str) -> bool:
        prefix = relative.rstrip("/") + "/"
        return any(name.startswith(prefix) for name in self._files())

    def files_under(self, relative: str) -> list[str]:
        prefix = relative.rstrip("/") + "/"
        return sorted(n for n in self._files() if n.startswith(prefix) and "__pycache__" not in n.split("/") and not n.endswith(".pyc"))

    def read(self, relative: str) -> bytes | None:
        blob = self._files().get(relative)
        if blob is None:
            return None
        if blob not in self._blobs:
            out = self._git("cat-file", "blob", blob)
            self._blobs[blob] = out.stdout if out.returncode == 0 else None
        return self._blobs[blob]


def _digest(h, source, relative: str) -> None:
    """Fold one file (or directory, recursively, sorted) into `h`: its path, then its bytes with CRLF normalised."""
    if source.is_dir(relative):
        for child in source.files_under(relative):
            _digest(h, source, child)
        return
    h.update(relative.encode("utf-8") + b"\0")
    data = source.read(relative)
    if data is None:
        h.update(b"MISSING\0")
        return
    if b"\0" not in data[:8000]:                 # text only: a checkout's line endings are not a change
        data = data.replace(b"\r\n", b"\n")
    h.update(hashlib.sha256(data).digest())


def hash_paths(source, relatives: Iterable[str]) -> str:
    """`source` is a WorkTree or a GitTree; a bare Path means the working tree."""
    if isinstance(source, (str, Path)):
        source = WorkTree(Path(source))
    h = hashlib.sha256()
    for relative in sorted(set(relatives)):
        _digest(h, source, relative)
    return h.hexdigest()


def guard_files(guard) -> list[str]:
    """Every repo-relative path the runner stages for `guard`, plus its own declaration module."""
    base = "" if guard.base in (".", "") else guard.base.rstrip("/") + "/"
    module = f"{base}scripts/mutations/{guard.name}.py"
    staged = [guard.subject, guard.selftest, *guard.deps, *guard.needs]
    return [module] + [f"{base}{p}" for p in staged]


def guard_hash(source, guard) -> str:
    return hash_paths(source, guard_files(guard))


def harness_hash(source) -> str:
    return hash_paths(source, HARNESS_FILES)


# ---- the trusted proof ----------------------------------------------------------------------------------------------


def trusted_skips(guards: list, hashes: Mapping[str, str], harness: str, candidates: list[str],
                  has_proof: Callable[[str], bool], tree_at: Callable[[str], object]) -> dict[str, str]:
    """`{guard: proof commit}` for each guard whose staged files are byte-identical to what they were at the newest TRUSTED proof commit.

    `candidates` are `main` first-parent commits, newest first; `has_proof(sha)` is true only for a commit carrying a success status posted
    by CI; `tree_at(sha)` reads that commit's own objects. Every hash is recomputed from those objects, so no file a pull request edits
    is consulted. Any failure to read means nothing is skipped."""
    for sha in candidates:
        try:
            if not has_proof(sha):
                continue
            tree = tree_at(sha)
            if harness_hash(tree) != harness:
                return {}                         # a harness change since the proof forces a full run
            return {g.name: sha for g in guards if guard_hash(tree, g) == hashes[g.name]}
        except Exception:                         # noqa: BLE001 -- unreadable evidence is no evidence: run everything
            return {}
    return {}


def select_guards(guards: list, hashes: Mapping[str, str], *, skips: Mapping[str, str], full: bool, named: bool,
                  shard: tuple[int, int] | None, weights: Mapping[str, float], default: float) -> tuple[list, dict[str, str]]:
    """`(guards to run, {skipped guard: commit})`. The shard is chosen over ALL guards, then the skip applies inside it,
    so a guard's shard never depends on which guards happen to be unchanged. `--full` and `--guard` skip nothing."""
    mine = list(guards)
    if shard is not None:
        index, count = shard
        owned = set(assign_shards([g.name for g in guards], weights, count, default)[index - 1])
        mine = [g for g in guards if g.name in owned]
    skipped: dict[str, str] = {}
    if not full and not named:
        skipped = {g.name: skips[g.name] for g in mine if g.name in skips}
    return [g for g in mine if g.name not in skipped], skipped


def main_first_parents(repo: Path, count: int = LOOKBACK) -> list[str]:
    """Newest-first first-parent commits of `origin/main`; empty when there is no such ref (nothing is then trusted)."""
    out = subprocess.run(["git", "-C", str(repo), "rev-list", "--first-parent", f"--max-count={count}", "origin/main"],
                         capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    return out.stdout.split() if out.returncode == 0 else []


def status_has_proof(statuses_json: str, system: str) -> bool:
    """True when the statuses of a commit hold a `mutation-proof/<system>` whose LATEST state is success."""
    try:
        statuses = json.loads(statuses_json)
    except ValueError:
        return False
    if not isinstance(statuses, list):
        return False
    for status in statuses:                       # the API lists newest first; the newest state of a context is the one that counts
        if isinstance(status, dict) and status.get("context") == proof_context(system):
            return status.get("state") == "success"
    return False


def github_proof_lookup(repo: Path, system: str, run=subprocess.run) -> Callable[[str], bool]:
    """`has_proof(sha)` backed by `gh api`; any error (no gh, no token, no network) reads as 'no proof'."""
    import os
    slug = os.environ.get("GITHUB_REPOSITORY", "")

    def has_proof(sha: str) -> bool:
        nonlocal slug
        try:
            if not slug:
                got = run(["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=str(repo),
                          capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
                slug = got.stdout.strip() if got.returncode == 0 else ""
            if not slug:
                return False
            got = run(["gh", "api", f"repos/{slug}/commits/{sha}/statuses?per_page=100"], capture_output=True, text=True, timeout=60,
                      stdin=subprocess.DEVNULL)
            return got.returncode == 0 and status_has_proof(got.stdout, system)
        except (OSError, subprocess.SubprocessError):
            return False
    return has_proof


def post_proof(env: Mapping[str, str], system: str, sha: str, run=subprocess.run) -> tuple[bool, str]:
    """Post `mutation-proof/<system>` = success on `sha`, from CI on `refs/heads/main` only. `(posted, why or where)`.

    A pull request run, a dispatch on a branch and a laptop never post: the status is the one thing a skip trusts."""
    if env.get("GITHUB_ACTIONS") != "true" or env.get("GITHUB_REF") != "refs/heads/main":
        return False, "not posted: only CI on refs/heads/main posts a proof (a branch, a pull request or a laptop never does)"
    slug = env.get("GITHUB_REPOSITORY", "")
    if not slug or not sha:
        return False, "not posted: no repository or commit"
    got = run(["gh", "api", "-X", "POST", f"repos/{slug}/statuses/{sha}", "-f", "state=success", "-f", f"context={proof_context(system)}",
               "-f", "description=full mutation run passed, no guard skipped"], capture_output=True, text=True, timeout=60,
              stdin=subprocess.DEVNULL)
    if got.returncode != 0:
        return False, f"could not post: {got.stderr.strip()[:200]}"
    return True, f"posted {proof_context(system)} on {sha[:12]}"


# ---- shards -----------------------------------------------------------------------------------------------------------


def parse_shard(text: str) -> tuple[int, int]:
    """`I/N` with 1 <= I <= N; anything else raises ValueError."""
    try:
        left, right = text.split("/")
        index, count = int(left), int(right)
    except ValueError:
        raise ValueError(f"--shard wants I/N, such as 2/4; got {text!r}") from None
    if not 1 <= index <= count:
        raise ValueError(f"--shard {text}: I must be between 1 and N")
    return index, count


def assign_shards(names: Iterable[str], weights: Mapping[str, float], count: int, default: float) -> list[list[str]]:
    """Split `names` into `count` shards: heaviest first onto the currently lightest shard, ties by name and then by index.

    A guard missing from `weights` weighs `default`. A pure function of its arguments, so one guard is always in the same
    shard for the same names, record and N."""
    shards: list[list[str]] = [[] for _ in range(count)]
    load = [0.0] * count
    for name in sorted(names, key=lambda n: (-weights.get(n, default), n)):
        lightest = min(range(count), key=lambda i: (load[i], i))
        shards[lightest].append(name)
        load[lightest] += weights.get(name, default)
    return [sorted(s) for s in shards]


def merge_shards(results: list[dict], expect: int, names: set[str], commit: str | None = None,
                 harness: str | None = None) -> tuple[dict | None, list[str]]:
    """The summary job's check: `(merged record, problems)`. The record is None whenever there is a problem.

    Every shard 1..expect present once, all for one OS and for THIS checkout's commit and harness (a result from another run or another
    tree is not evidence about this one), and between them every guard exactly once."""
    problems: list[str] = []
    seen: dict[int, dict] = {}
    for result in results:
        index = result.get("shard")
        if result.get("of") != expect:
            problems.append(f"shard {index} was run as one of {result.get('of')}, not {expect}")
        elif index in seen:
            problems.append(f"shard {index}/{expect} appears twice")
        elif not isinstance(index, int) or not 1 <= index <= expect:
            problems.append(f"shard {index!r} is not in 1..{expect}")
        else:
            seen[index] = result
    for index in range(1, expect + 1):
        if index not in seen:
            problems.append(f"shard {index}/{expect} is MISSING: a shard that did not report is a failure, not a pass")
    for key in ("os", "commit", "harness"):
        values = sorted({str(r.get(key)) for r in seen.values()})
        if len(values) > 1:
            problems.append(f"the shards disagree on {key}: {values}")
    for key, want in (("commit", commit), ("harness", harness)):
        if want is not None and any(r.get(key) != want for r in seen.values()):
            problems.append(f"a shard result is for another {key} than this checkout's ({want[:12]}): it is not evidence about this tree")
    covered: dict[str, int] = {}
    for result in seen.values():
        for name in list(result.get("guards", {})) + list(result.get("skipped", {})):
            covered[name] = covered.get(name, 0) + 1
    for name in sorted(names - set(covered)):
        problems.append(f"{name}: no shard ran or skipped it")
    for name in sorted(n for n, c in covered.items() if c > 1):
        problems.append(f"{name}: more than one shard ran it")
    for name in sorted(set(covered) - names):
        problems.append(f"{name}: a shard reports a guard that no longer exists")
    if problems:
        return None, problems
    first = seen[1]
    merged = {"os": first["os"], "commit": first["commit"], "harness": first["harness"],
              "jobs": first.get("jobs"), "full": all(not r.get("skipped") for r in seen.values()),
              "guards": {}, "cost": {}}
    for result in seen.values():
        merged["guards"].update(result.get("guards", {}))
        merged["cost"].update(result.get("cost", {}))
    return merged, []


def summary_verdict(result: str, fast: bool) -> tuple[bool, str]:
    """The summary job's verdict from `needs.<shards>.result`. Full mode passes only on `success`: failed, cancelled and
    skipped (a shard that never ran) are all failures. Fast mode runs no shards on purpose and says so."""
    if result == "success":
        return True, "every shard passed"
    if fast and result in ("skipped", ""):
        return True, "fast mode: the mutation shards are not run here (a skip, not a pass)"
    return False, f"the mutation shards finished as {result or 'unknown'!r}; every shard must succeed"


def record_host(env: Mapping[str, str], host: str | None, system: str) -> tuple[str | None, str | None]:
    """`(label, refusal)` for `--rebaseline`: a cost record comes from the runner, or from a machine that says what it is.

    Outside CI a `--host` label is accepted (the record is a reviewed diff and names its host) but may not impersonate the runner."""
    in_ci = env.get("GITHUB_ACTIONS") == "true"
    if host and not in_ci:
        if host.startswith(CI_HOST_PREFIX):
            return None, f"--host {host!r} claims to be the CI runner; outside CI name the machine yourself (not {CI_HOST_PREFIX}...)"
        return host, None
    if in_ci:
        return host or f"{CI_HOST_PREFIX}{env.get('RUNNER_OS') or system}", None
    return None, ("--rebaseline refuses outside CI: a record measured on a laptop under other sessions' load is what tripped the "
                  "ratchet three times (#1738). Take the record from a CI run, or name the machine with --host LABEL")


def main(argv: list[str] | None = None) -> int:
    """`verdict <needs.shards.result> <fast|full>`: the summary job's first step. Exit 0 to pass, 1 to fail, 2 on misuse."""
    import sys
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 3 or args[0] != "verdict" or args[2] not in ("fast", "full"):
        print("usage: mutation_incremental.py verdict <shards result> <fast|full>", file=sys.stderr)
        return 2
    ok, message = summary_verdict(args[1], args[2] == "fast")
    print(f"mutation coverage: {message}", file=sys.stdout if ok else sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
