#!/usr/bin/env python3
"""What `mutation_check.py` decides BEFORE it runs a guard: skip it, or which shard owns it (#1738, #1739).

Pure functions and one small file format, so each rule can be driven by a selftest without running a guard.

INCREMENTAL PROOF (#1738). A full run costs about 64 minutes of runner time, and most guards are unchanged between two runs.
A guard's result is a function of the files it STAGES: its mutation module, subject, selftest, deps and `needs` (the runner
copies exactly these into a tempdir, so nothing else can change a verdict). `guard_hash` hashes them. The proof file records,
per runner OS, the hash of every guard that passed a FULL run and the hash of the harness itself. A later run skips a guard
whose hash is unchanged and says `skip (unchanged since <sha>)`: a skip is NOT a pass, and it is never counted as one.
No skip happens when the harness changed, on `--full`, with `--guard`, for another OS, or for a guard with no record.
The weekly workflow passes `--full`, which is the forced re-proof.

WHERE THE STATE LIVES (decision, #1738). In a committed file, `docs/evidence/mutation-proof.json`, per runner OS, beside the
cost record. The bytes are a function of the data (sorted keys, no clock); a full run on the runner writes it and a person
commits the diff, exactly as with the cost record. A check-run or an Actions cache would be invisible in review and unreadable
without the API; a CI job that commits to `dev` would need a write token on a gate.

SHARDS (#1739). `assign_shards` splits the guards over N jobs, largest recorded cost first onto the lightest shard, so the
split follows cost, not count. It is a pure function of the guard names and the committed cost record: the same inputs give
the same split on every machine. `merge_shards` is what the summary job runs: every shard must be present exactly once, for
one commit and one harness, and together they must cover every guard exactly once. A missing shard is a problem, never a pass.
"""
from __future__ import annotations

import hashlib
import json
import platform
from pathlib import Path
from typing import Iterable, Mapping

HARNESS_FILES = (
    "scripts/mutation_check.py",
    "scripts/mutation_incremental.py",
    "scripts/mutation_types.py",
    "scripts/proc_group.py",
    "scripts/hermetic_git.py",
    "plugins/rails-flow/scripts/process_containment.py",
)

PROOF_NOTE = ("Per runner OS: the hash of every guard's staged files at the last FULL mutation run that passed, and the harness hash. "
              "A guard whose hash is unchanged is skipped (reported as a skip, never a pass). Written by `python3 scripts/mutation_check.py "
              "--full --record-hashes` or by the shard summary job; commit the diff (#1738)")


def os_key() -> str:
    return platform.system().lower() or "unknown"


def _digest(h, repo: Path, relative: str) -> None:
    """Fold one file (or directory, recursively, sorted) into `h`: its path, then its bytes with CRLF normalised."""
    path = repo / relative
    if path.is_dir():
        for child in sorted(p for p in path.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"):
            _digest(h, repo, str(child.relative_to(repo)))
        return
    h.update(relative.encode("utf-8") + b"\0")
    if not path.is_file():
        h.update(b"MISSING\0")
        return
    data = path.read_bytes()
    if b"\0" not in data[:8000]:                 # text only: a checkout's line endings are not a change
        data = data.replace(b"\r\n", b"\n")
    h.update(hashlib.sha256(data).digest())


def hash_paths(repo: Path, relatives: Iterable[str]) -> str:
    h = hashlib.sha256()
    for relative in sorted(set(relatives)):
        _digest(h, repo, relative)
    return h.hexdigest()


def guard_files(guard) -> list[str]:
    """Every repo-relative path the runner stages for `guard`, plus its own declaration module."""
    base = "" if guard.base in (".", "") else guard.base.rstrip("/") + "/"
    module = f"{base}scripts/mutations/{guard.name}.py"
    staged = [guard.subject, guard.selftest, *guard.deps, *guard.needs]
    return [module] + [f"{base}{p}" for p in staged]


def guard_hash(repo: Path, guard) -> str:
    return hash_paths(repo, guard_files(guard))


def harness_hash(repo: Path) -> str:
    return hash_paths(repo, HARNESS_FILES)


def load_proof(path: Path) -> dict | None:
    """The proof, or None when there is no file. A file that is not a proof RAISES: read as empty it would skip nothing, and read as full it would skip everything."""
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{path}: not valid JSON ({exc})") from exc
    systems = data.get("systems") if isinstance(data, dict) else None
    if not isinstance(systems, dict) or not all(
            isinstance(s, dict) and isinstance(s.get("guards"), dict) and isinstance(s.get("harness"), str)
            and isinstance(s.get("commit"), str) for s in systems.values()):
        raise ValueError(f"{path}: needs a 'systems' object mapping an OS to its commit, harness hash and guards")
    return data


def write_proof(path: Path, system: str, commit: str, harness: str, hashes: Mapping[str, str]) -> None:
    """Record `system`'s full run, keeping every other OS's entry. Sorted, no clock: the bytes are a function of the data."""
    current = load_proof(path) or {"systems": {}}
    current["systems"][system] = {"commit": commit, "harness": harness, "guards": dict(sorted(hashes.items()))}
    record = {"note": PROOF_NOTE, "systems": dict(sorted(current["systems"].items()))}
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def skipped_guards(hashes: Mapping[str, str], harness: str, proof: dict | None, system: str) -> dict[str, str]:
    """`{guard: commit}` for each guard whose staged files are unchanged since the recorded full run on `system`.

    Empty whenever the record cannot vouch for it: no proof, no entry for this OS, or a harness that changed (the
    runner, its types, the process helpers: any of them can change a verdict for every guard at once)."""
    entry = (proof or {}).get("systems", {}).get(system)
    if not entry or entry["harness"] != harness:
        return {}
    return {name: entry["commit"] for name, digest in hashes.items() if entry["guards"].get(name) == digest}


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


def select_guards(guards: list, hashes: Mapping[str, str], harness: str, proof: dict | None, system: str, *,
                  full: bool, named: bool, shard: tuple[int, int] | None, weights: Mapping[str, float],
                  default: float) -> tuple[list, dict[str, str]]:
    """`(guards to run, {skipped guard: commit})`. The shard is chosen over ALL guards, then the skip applies inside it,
    so a guard's shard never depends on which guards happen to be unchanged."""
    mine = list(guards)
    if shard is not None:
        index, count = shard
        owned = set(assign_shards([g.name for g in guards], weights, count, default)[index - 1])
        mine = [g for g in guards if g.name in owned]
    skipped: dict[str, str] = {}
    if not full and not named:
        skipped = skipped_guards({g.name: hashes[g.name] for g in mine}, harness, proof, system)
    return [g for g in mine if g.name not in skipped], skipped


def merge_shards(results: list[dict], expect: int, names: set[str]) -> tuple[dict | None, list[str]]:
    """The summary job's check: `(merged record, problems)`. The record is None whenever there is a problem.

    Every shard 1..expect present once, all for one OS, commit and harness, and between them every guard exactly once."""
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
              "jobs": first.get("jobs"), "full": all(r.get("full") for r in seen.values()),
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
    """`(label, refusal)` for `--rebaseline`: a cost record comes from the runner, or from a named host."""
    if host:
        return host, None
    if env.get("GITHUB_ACTIONS") == "true":
        return f"github-actions/{env.get('RUNNER_OS') or system}", None
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
