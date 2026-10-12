#!/usr/bin/env python3
"""Every SessionStart hook's output is paid on EVERY COMPACTION. Ratchet it (#1085).

Run:  python3 scripts/check_hook_output_budget.py
      python3 scripts/check_hook_output_budget.py --update      # re-baseline deliberately
      python3 scripts/check_hook_output_budget.py --selftest

WHY THIS EXISTS. A `SessionStart` hook does not run once per session. It runs again after **every
compaction** -- which is precisely when the context window is scarce and the whole point of the
compaction was to reclaim it. Whatever these hooks print is charged again each time, so a hook that
looks cheap once is expensive exactly when it hurts.

Nobody was measuring it. Measured the first time, on this repository:

    plugins/rails-flow/hooks/scripts/session-start.sh   4451 bytes
      of which docs/brain/MEMORY.md dumped whole         3805 bytes  (85%)
      of THAT, `[slug](path)` markdown no model acts on  1828 bytes  (42% of the block)

The other three shipped SessionStart hooks printed 100, 0 and 0 bytes -- so one hook was 98% of the
cost and 85% of it was one file printed verbatim.

A RATCHET, NOT A THRESHOLD, and this repository has the scar for it. A fixed byte limit is either
inert (set above today's size, so it never fires) or red on day one (set below it). A ratchet
records what each hook costs TODAY and fails only on growth -- so the number starts honest, and the
only way past it is to raise the baseline in a commit somebody reviews.

MEASURED AGAINST A FIXTURE PROJECT, never this repository. A hook prints the branch name, the last
commit subject, an issue count -- all of which move. Measuring the live tree would produce a
baseline that drifts for reasons having nothing to do with the hook, and a gate that goes red on
its own is a gate that gets switched off. The fixture is a fixed git repo with fixed brain files,
so the same hook always produces the same byte count.

WHAT IT DELIBERATELY DOES NOT DO. It does not judge whether the content is WORTH its bytes -- that
is the `reference/context-budget.md` doctrine and a review question. This answers only "did it grow
without anyone deciding to let it".

AND WHAT IT CANNOT SEE, stated rather than left for someone to discover. The fixture pins every
input, which is what makes the ratchet trustworthy -- and it means a hook whose output comes
entirely from the network or from `gh` measures **0** here and its growth is invisible to this
check. `.claude/hooks/scripts/maintainer-status.sh` is exactly that shape: it prints an open-issue
count, so it is 100 bytes against the live repository and 0 against the fixture. The baseline is
honest about what it measured; it is not a claim that the hook is free.

Stdlib only. Exit 0 within budget, 1 over, 2 cannot measure.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BASELINE = REPO / "docs/evidence/hook-output-baseline.json"

# Growth under this many bytes is noise (a commit subject one word longer). Above it, somebody
# decided to print more and should say so in a review.
TOLERANCE = 64


# A value that moves on its own, with nothing having happened, rewrites the text a hook injects each time it runs and
# makes every compaction's copy differ from the last (#1886, slice 4 of #1683). A relative age ("14d ago") or a clock time
# ticks; a DATE a threshold was crossed on ("due since 2026-01-08") does not. Counters of real state (uncommitted files,
# open issues) change only when something changed, so they are not matched here.
# THE LIMITS, stated (a0's review of #1909): the patterns are tied to wording ("ago" for ages, `d:dd` times, ISO stamps, ten-digit
# epochs, "load averages"/"uptime"), so a hook printing `age: 14d`, `swept 14d`, `yesterday` or `just now` is not seen; and the scan reads
# ONE fixture state, so a hook that ticks only in another state (a held lock, a stale branch) is not covered either.
TICKING: tuple[tuple[str, re.Pattern], ...] = (
    ("a relative age", re.compile(r"\b\d+\s*(?:s|sec|secs|seconds?|m|min|mins|minutes?|h|hr|hrs|hours?|d|days?|w|weeks?|mo|months?|y|years?)\s+ago\b", re.I)),
    ("a time of day", re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")),
    ("an ISO timestamp", re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}")),
    ("an epoch", re.compile(r"\b1[5-9]\d{8}\b")),
    ("a load or uptime reading", re.compile(r"\b(?:load averages?|uptime)\b", re.I)),
)


def ticking(text: str) -> list[str]:
    """Each ticking value in `text`, as `<what>: <the line>` (one per line and kind)."""
    found = []
    for line in text.splitlines():
        for what, pattern in TICKING:
            if pattern.search(line):
                found.append(f"{what}: {line.strip()[:100]}")
    return found


def _declared(data: dict, label: str, script_dir: Path) -> list[tuple[str, Path]]:
    """SessionStart hook scripts a manifest declares, resolved under `script_dir`."""
    found = []
    for entry in data.get("hooks", {}).get("SessionStart", []):
        for hook in entry.get("hooks", []):
            for token in hook.get("command", "").split():
                # STRIP THE QUOTES FIRST. The maintainer hook is invoked as
                # `bash "$CLAUDE_PROJECT_DIR/.claude/hooks/scripts/maintainer-status.sh"`, so the
                # token ends with `.sh"` and a bare `endswith(".sh")` silently missed it -- the
                # gate reported 3 hooks and looked healthy while never measuring our own.
                token = token.strip('"\'')
                if token.endswith(".sh"):
                    path = script_dir / token.split("/")[-1]
                    if path.is_file():
                        found.append((label, path))
    return found


def session_start_hooks(root: Path = REPO) -> list[tuple[str, Path]]:
    """(owner, script path) for every SessionStart hook, SHIPPED AND OUR OWN.

    Read from each manifest rather than globbed off disk: a script that exists but is not wired
    costs nothing, and one wired under an unexpected name would be missed by a glob. The
    declaration is what the runtime acts on.

    `.claude/settings.json` IS INCLUDED, and leaving it out was the defect. The first version
    measured only `plugins/*/hooks/hooks.json` -- so the budget we ship to other people did not
    apply to the hook that fires in this repository, which is the shape of defect this repo has a
    whole lint rule for (`doctrine-we-ship-but-do-not-follow`). A maintainer's own session pays the
    same cost at every compaction as anyone else's.
    """
    found: list[tuple[str, Path]] = []
    for manifest in sorted(root.glob("plugins/*/hooks/hooks.json")):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        found += _declared(data, manifest.parent.parent.name, manifest.parent / "scripts")

    settings = root / ".claude/settings.json"
    if settings.is_file():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        found += _declared(data, "(this repo)", root / ".claude/hooks/scripts")
    return found


def _fixture(tmp: Path, lessons: int = 20) -> Path:
    """A fixed project tree, so the same hook always measures the same.

    Everything a SessionStart hook reads that could MOVE is pinned here: the branch, the commit
    subject, the brain files. Without that the baseline drifts on an unrelated commit and the gate
    goes red for a reason nobody can act on.
    """
    project = tmp / "fixture-project"
    (project / "docs/brain").mkdir(parents=True)
    (project / "docs/brain/STATUS.md").write_text(
        "# STATUS\n\n_Updated: 2026-01-01_\n\n**Phase:** fixture.\n" * 2, encoding="utf-8")
    (project / "docs/brain/MEMORY.md").write_text(
        "".join(f"- [lesson-{i}](memos/lesson-{i}.md) — a fixed lesson line number {i} that is "
                f"long enough to be representative of a real one\n" for i in range(lessons)),
        encoding="utf-8")
    (project / "GUARDRAILS.md").write_text("# GUARDRAILS\n", encoding="utf-8")
    # A sweep stamped long ago, so the "due" line prints: it is the line whose age used to tick (#1886).
    (project / "docs/brain/.last-review").write_text("1700000000\n", encoding="utf-8")
    env = dict(os.environ)
    import sys as _sys; _sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "plugins" / "rails-flow" / "scripts")); import fixture_git as _fg  # #1588
    _fg.init(project, "-b", "main")                             # bound to this temp repo (#1588)
    _fg.run(project, "add", "-A", check=False)
    _fg.run(project, "commit", "-q", "-m", "fixture", check=False)
    # A WORKED-IN CLONE HAS A WHERE-STOPPED FILE (#1639): rails-flow's Stop hook writes one every turn, so the measurement
    # includes what SessionStart prints with one on disk, rather than the empty case a brand-new clone is in (#1643 D1).
    stopped = REPO / "plugins/rails-flow/hooks/scripts/lib/where_stopped.py"
    if stopped.is_file():
        (project / "unsaved.txt").write_text("work in progress\n", encoding="utf-8")   # so the pointer prints (#1886)
        subprocess.run([sys.executable, str(stopped), "stop", "--cwd", str(project)], input="{}", env=env,
                       capture_output=True, text=True, timeout=30)
    return project


def measure(root: Path = REPO, lessons: int = 20) -> dict[str, int] | None:
    outputs = run_hooks(root, lessons)
    return None if outputs is None else {label: len(out) for label, out in outputs.items()}


def run_hooks(root: Path = REPO, lessons: int = 20) -> dict[str, bytes] | None:
    """What each SessionStart hook prints against the fixture project, by owner."""
    hooks = session_start_hooks(root)
    if not hooks:
        return None
    sizes: dict[str, bytes] = {}
    tmp = Path(tempfile.mkdtemp(prefix="hook-budget-"))
    try:
        project = _fixture(tmp, lessons)
        for plugin, path in hooks:
            env = {**os.environ,
                   "CLAUDE_PLUGIN_ROOT": str(path.parent.parent),
                   # The maintainer hook reads this; the plugin ones ignore it.
                   "CLAUDE_PROJECT_DIR": str(project),
                   "CLAUDE_PROJECT_DIR": str(project),
                   # Hooks that shell out to `gh` must not reach the network from a gate.
                   "GH_TOKEN": "", "PATH": os.environ.get("PATH", "")}
            proc = subprocess.run(["bash", str(path)], cwd=project, env=env,
                                  capture_output=True, timeout=30)
            sizes[plugin] = proc.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return sizes


def compare(sizes: dict[str, int], baseline: dict[str, int]) -> list[str]:
    findings = []
    for plugin, size in sorted(sizes.items()):
        recorded = baseline.get(plugin)
        if recorded is None:
            findings.append(
                f"{plugin}: prints {size} bytes at every session start and every compaction, and "
                f"has no recorded baseline. Run --update to record it deliberately.")
        elif size > recorded + TOLERANCE:
            findings.append(
                f"{plugin}: grew from {recorded} to {size} bytes (+{size - recorded}). "
                f"SessionStart fires again on EVERY COMPACTION, so this is charged each time the "
                f"context is reclaimed. Either trim it, or raise the baseline with --update in a "
                f"commit that says why.")
    for plugin in sorted(set(baseline) - set(sizes)):
        findings.append(
            f"{plugin}: has a recorded baseline and declares no SessionStart hook any more — "
            f"the measurement is stale. Run --update.")
    return findings


def _selftest() -> int:
    ok, bad = 0, []

    def expect(label: str, cond: bool) -> None:
        nonlocal ok
        if cond:
            ok += 1
        else:
            bad.append(label)

    # GROWTH IS THE FINDING, and it is the only one that matters day to day.
    expect("growth beyond the tolerance is reported",
           compare({"a": 5000}, {"a": 1000}))
    # MUST PASS: shrinking is the point of the exercise. A ratchet that fired on any change would
    # punish the fix as loudly as the regression, and nobody would trim anything.
    expect("shrinking is NOT reported", not compare({"a": 400}, {"a": 4000}))
    expect("staying the same is not reported", not compare({"a": 1000}, {"a": 1000}))
    # Noise must not fire it: a one-word-longer commit subject is not a decision.
    expect("growth inside the tolerance is noise, not a finding",
           not compare({"a": 1000 + TOLERANCE - 1}, {"a": 1000}))
    expect("growth just past the tolerance IS a finding",
           compare({"a": 1000 + TOLERANCE + 1}, {"a": 1000}))
    # An unbaselined hook is not silently fine -- that is how a new hook ships unmeasured.
    expect("a hook with no baseline is reported, not skipped",
           compare({"new": 900}, {}))
    # A stale baseline row is its own finding: it means we are ratcheting something that is gone.
    expect("a baseline for a hook that no longer exists is reported",
           compare({}, {"gone": 900}))

    hooks = session_start_hooks()
    expect("the shipped SessionStart hooks are discovered from hooks.json", len(hooks) >= 3)
    # THIS REPO'S OWN HOOK COUNTS. The first version globbed `plugins/*` only, so the budget we
    # ship did not apply to the hook that fires here -- and then a bare `endswith(".sh")` missed
    # it a second time, because the maintainer hook is invoked in quotes and the token ends `.sh"`.
    # The gate reported 3 hooks and looked healthy both times.
    expect("this repository's OWN SessionStart hook is measured, not just the shipped ones",
           any(label == "(this repo)" for label, _ in hooks))
    expect("...and a quoted command path is resolved, not skipped",
           any(p.name == "maintainer-status.sh" for _, p in hooks))
    expect("...and every discovered path exists", all(p.is_file() for _, p in hooks))

    sizes = measure()
    expect("measuring returns a size for every discovered hook",
           sizes is not None and len(sizes) == len(hooks))
    # DETERMINISM IS THE WHOLE BASIS OF THE RATCHET. If two runs disagree the baseline is noise,
    # and the gate would go red on its own -- which is how a gate gets switched off.
    expect("two runs of the same fixture measure the same bytes", sizes == measure())
    # ...AND THE FIXTURE MUST BE WHAT IS MEASURED. Determinism alone cannot show that: this
    # repository is stable within a run too, so a check that quietly measured the live tree would
    # satisfy the assertion above and drift the moment somebody commits. Two fixtures differing
    # only in how many lessons they hold must produce different byte counts; if they do not, the
    # hook is reading something other than the fixture.
    small, large = measure(lessons=2), measure(lessons=40)
    expect("a bigger fixture measures bigger — the hook reads the FIXTURE, not this repo",
           small is not None and large is not None
           and sum(small.values()) < sum(large.values()))

    # TICKING VALUES (#1886). Each row is a shape a hook printed or could print; the controls are the stable forms.
    for text in ("brain-review due: last swept 14d ago", "last swept 3 hours ago", "synced 5 minutes ago", "stopped (last turn, 2026-10-11T22:48Z)",
                 "measured at 14:03", "stamp 1700000000", "load averages: 24.30 24.52", "idle 2 weeks ago"):
        expect(f"a ticking value is reported: {text}", ticking(text))
    for text in ("brain-review due since 2026-01-08 (cadence 7d)", "uncommitted files: 12", "5 finished worktree(s)",
                 "- memory: 20 lesson(s) in docs/brain/MEMORY.md", "HEAD has moved (abc12345 -> def67890)", "wait 3 days before retrying"):
        expect(f"a stable value is not reported: {text}", not ticking(text))
    outputs = run_hooks()
    expect("every SessionStart hook's output, against the fixture, holds no ticking value",
           outputs is not None and not [t for out in outputs.values() for t in ticking(out.decode("utf-8", "replace"))],
           )
    expect("the fixture makes the aged review line and the where-stopped pointer print, so the scan reads them",
           outputs is not None and b"brain-review due" in outputs.get("rails-flow", b"")
           and b"where this worktree stopped" in outputs.get("rails-flow", b""))

    if bad:
        print(f"ran {ok + len(bad)} assertion(s)\n\n{len(bad)} FAILED:", file=sys.stderr)
        for b in bad:
            print(f"  - {b}", file=sys.stderr)
        return 1
    print(f"ran {ok} assertion(s)")
    print("growth is a finding, shrinking is not, and the fixture measures the same twice")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--update", action="store_true", help="re-record the baseline deliberately")
    ap.add_argument("--selftest", action="store_true", help="prove this check can fail")
    args = ap.parse_args()
    if args.selftest:
        return _selftest()

    sizes = measure()
    if sizes is None:
        # NOT a pass. Zero hooks measured reads exactly like zero hooks over budget.
        print("NOT APPLICABLE: no plugin declares a SessionStart hook — this check measured "
              "nothing.")
        return 2

    if args.update:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(sizes, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"baseline recorded for {len(sizes)} hook(s):")
        for plugin, size in sorted(sizes.items()):
            print(f"  {plugin}: {size} bytes")
        return 0

    baseline = {}
    if BASELINE.is_file():
        baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    findings = compare(sizes, baseline)
    for owner, out in sorted((run_hooks() or {}).items()):
        findings += [f"{owner}: injects {t} -- it changes with the clock, not with the work. State the date a threshold "
                     f"was crossed, not an age (#1886)" for t in ticking(out.decode("utf-8", "replace"))]
    for f in findings:
        print(f"  {f}")
    total = sum(sizes.values())
    print(f"\n{len(sizes)} SessionStart hook(s) measured, {total} bytes per session start "
          f"— and again after every compaction; {len(findings)} finding(s).")
    for plugin, size in sorted(sizes.items(), key=lambda kv: -kv[1]):
        print(f"    {size:>6} bytes  {plugin}")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
