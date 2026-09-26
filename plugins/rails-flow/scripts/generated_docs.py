#!/usr/bin/env python3
"""Which branches must carry fresh generated docs, and which must not carry them at all (#1230).

THE PROBLEM, MEASURED DOWNSTREAM. A project commits its generated docs -- `docs/architecture/` from
`architecture_graph.py`, `docs/wiki/` from `build_project_wiki.py` -- and both drift checks failed
on EVERY branch. So every feature branch that moved a route, model or component regenerated them,
any two open PRs conflicted there whether or not their code overlapped, and each merge into `dev`
re-conflicted every other open PR. On one consumer, across ~15 PRs in two days, almost every
conflict was those ten files and exactly one was a real disagreement between authors (Retask #605).

THE POLICY, OPT-IN. A project that wants it declares `.rails-flow/generated-docs.json`:

    {"enforce_on": ["dev", "main", "chore/docs-refresh-*"]}

  * on an ENFORCING branch (matching a pattern) a stale graph or wiki FAILS, exactly as before;
  * on any other branch it is a NOTE and passes -- and `guard` FAILS the branch if its diff touches
    the generated paths at all, so feature branches stop carrying them;
  * the docs are refreshed after a merge batch, on an enforcing refresh branch.

NO FILE MEANS TODAY'S BEHAVIOUR: every branch enforces, and `guard` is not applicable. An UNKNOWN
branch (detached HEAD with no CI variable) also enforces -- a gate must not relax blind.

Optional keys: `generated` (default `["docs/architecture/", "docs/wiki/"]`) and `base`, the ref a
branch's changes are measured against (default `origin/dev`).

Which branch: `GENERATED_DOCS_BRANCH`, else `GITHUB_HEAD_REF` (a pull request), else
`GITHUB_REF_NAME` (a push), else `git branch --show-current`.

Run:  generated_docs.py mode [--root DIR]      # enforce/advisory, the branch, and why
      generated_docs.py guard [--root DIR]     # 0 clean · 1 touches generated paths · 2 cannot tell · 3 n/a
      generated_docs.py --selftest

`architecture_graph.py` and `build_project_wiki.py` import this when it sits beside them. A project
that vendored `architecture_graph.py` ALONE keeps today's behaviour until it vendors this file too.
"""
from __future__ import annotations

import fnmatch
import json
import os
import subprocess
import sys
from pathlib import Path

POLICY_FILE = Path(".rails-flow/generated-docs.json")
DEFAULT_GENERATED = ("docs/architecture/", "docs/wiki/")
DEFAULT_BASE = "origin/dev"


class PolicyError(Exception):
    """The policy file exists but cannot be read -- never guessed around."""


def load_policy(root: Path) -> dict | None:
    """The declared policy, or None when the project has declared none (today's behaviour)."""
    path = Path(root) / POLICY_FILE
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PolicyError(f"{POLICY_FILE} is not valid JSON: {exc}") from exc
    patterns = data.get("enforce_on") if isinstance(data, dict) else None
    if not (isinstance(patterns, list) and patterns and all(isinstance(p, str) and p for p in patterns)):
        raise PolicyError(f"{POLICY_FILE}: `enforce_on` must be a non-empty list of branch patterns")
    generated = data.get("generated", list(DEFAULT_GENERATED))
    if not (isinstance(generated, list) and generated and all(isinstance(g, str) and g for g in generated)):
        raise PolicyError(f"{POLICY_FILE}: `generated` must be a non-empty list of path prefixes")
    base = data.get("base", DEFAULT_BASE)
    if not isinstance(base, str) or not base:
        raise PolicyError(f"{POLICY_FILE}: `base` must be a ref name")
    return {"enforce_on": patterns, "generated": generated, "base": base}


def current_branch(root: Path, env=os.environ) -> str:
    for var in ("GENERATED_DOCS_BRANCH", "GITHUB_HEAD_REF", "GITHUB_REF_NAME"):
        value = (env.get(var) or "").strip()
        if value:
            return value
    try:
        done = subprocess.run(["git", "-C", str(root), "branch", "--show-current"],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip() if done.returncode == 0 else ""


def decide(policy: dict | None, branch: str) -> tuple[bool, str]:
    """(enforcing?, why). No policy, or an unknown branch, enforces."""
    if policy is None:
        return True, f"no {POLICY_FILE}: every branch enforces"
    if not branch:
        return True, "the branch is unknown (detached HEAD, no CI variable), so it enforces"
    for pattern in policy["enforce_on"]:
        if fnmatch.fnmatchcase(branch, pattern):
            return True, f"{branch} matches enforce_on {pattern!r}"
    return False, f"{branch} matches no enforce_on pattern"


def enforcing(root: Path, env=os.environ) -> tuple[bool, str]:
    return decide(load_policy(root), current_branch(root, env))


def advisory_note(what: str, why: str) -> str:
    """The line a drift check prints instead of failing on a non-enforcing branch."""
    return (f"NOTE: {what} is stale, and on this branch that does not fail ({why}). Feature branches "
            f"do not carry the generated docs; they are refreshed on an enforcing branch "
            f"({POLICY_FILE}, #1230).")


def changed_paths(root: Path, base: str) -> list[str] | None:
    """Paths the branch changes relative to its merge base with `base`, or None if `base` is unknown."""
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
    if git("rev-parse", "--verify", "--quiet", base + "^{commit}").returncode != 0:
        return None
    done = git("diff", "--name-only", f"{base}...HEAD")
    return [ln for ln in done.stdout.splitlines() if ln.strip()] if done.returncode == 0 else None


def guard(root: Path, env=os.environ) -> tuple[int, str]:
    """(exit code, message). 3 not applicable, 0 clean, 1 touches generated paths, 2 cannot tell."""
    policy = load_policy(root)
    if policy is None:
        return 3, f"not applicable — no {POLICY_FILE}, so feature branches may carry generated docs"
    ok, why = decide(policy, current_branch(root, env))
    if ok:
        return 0, f"generated paths may change here ({why})"
    paths = changed_paths(root, policy["base"])
    if paths is None:
        return 2, (f"cannot resolve `{policy['base']}`, so cannot tell what this branch changes — "
                   f"fetch it rather than reading this as clean")
    touched = sorted(p for p in paths if p.startswith(tuple(policy["generated"])))
    if not touched:
        return 0, f"this branch changes no generated docs relative to {policy['base']}"
    lines = [f"{len(touched)} finding(s): this branch modifies generated docs, which a non-enforcing "
             f"branch must not carry ({why}):"] + [f"  - {p}" for p in touched]
    lines.append(f"Fix: git restore --source {policy['base']} --staged --worktree -- {' '.join(policy['generated'])} "
                 f"&& git commit -m 'Drop generated docs'")
    return 1, "\n".join(lines)


def selftest() -> int:
    import tempfile
    checks, fails = 0, []

    def expect(label: str, ok: bool) -> None:
        nonlocal checks
        checks += 1
        if not ok:
            fails.append(label)

    policy = {"enforce_on": ["dev", "main", "chore/docs-refresh-*"], "generated": list(DEFAULT_GENERATED),
              "base": "dev"}
    expect("no policy enforces on a feature branch (today's behaviour)", decide(None, "fix/x")[0] is True)
    for name, want in (("dev", True), ("main", True), ("chore/docs-refresh-1", True), ("fix/1", False),
                       ("chore/other", False), ("develop", False), ("", True)):
        expect(f"decide({name!r}) enforces={want}", decide(policy, name)[0] is want)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        g = ["git", "-C", tmp, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess.run(["git", "init", "-q", "-b", "dev", tmp], check=True)
        (root / "docs/architecture").mkdir(parents=True)
        (root / "docs/architecture/graph.json").write_text("{}\n")
        (root / "app.rb").write_text("x\n")
        subprocess.run(g + ["add", "."], check=True)
        subprocess.run(g + ["commit", "-qm", "base"], check=True)
        feature = {"GENERATED_DOCS_BRANCH": "fix/1"}
        expect("guard is n/a without a policy file", guard(root, feature)[0] == 3)
        (root / ".rails-flow").mkdir()
        (root / POLICY_FILE).write_text(json.dumps({"enforce_on": ["dev"], "base": "dev"}))
        subprocess.run(g + ["checkout", "-qb", "fix/1"], check=True)
        (root / "app.rb").write_text("y\n")
        subprocess.run(g + ["commit", "-qam", "code"], check=True)
        expect("guard: a feature branch changing only code is clean", guard(root, feature)[0] == 0)
        (root / "docs/architecture/graph.json").write_text('{"a":1}\n')
        subprocess.run(g + ["commit", "-qam", "regen"], check=True)
        code, msg = guard(root, feature)
        expect("guard: a feature branch changing graph.json FAILS", code == 1 and "graph.json" in msg)
        expect("guard: an enforcing branch may change it", guard(root, {"GENERATED_DOCS_BRANCH": "dev"})[0] == 0)
        (root / POLICY_FILE).write_text(json.dumps({"enforce_on": ["dev"], "base": "no-such-ref"}))
        expect("guard: an unresolvable base is exit 2, never clean", guard(root, feature)[0] == 2)
        (root / POLICY_FILE).write_text("{not json")
        try:
            load_policy(root)
            expect("an unreadable policy raises", False)
        except PolicyError:
            expect("an unreadable policy raises", True)
        (root / POLICY_FILE).write_text(json.dumps({"enforce_on": []}))
        try:
            load_policy(root)
            expect("an empty enforce_on raises", False)
        except PolicyError:
            expect("an empty enforce_on raises", True)
        expect("the branch is read from the environment first",
               current_branch(root, {"GITHUB_HEAD_REF": "fix/pr"}) == "fix/pr")

    for label in fails:
        print(f"FAIL {label}")
    print(f"generated_docs selftest: {checks} checks, {len(fails)} failure(s)")
    return 1 if fails else 0


def main(argv: list[str]) -> int:
    if argv == ["--selftest"]:
        return selftest()
    if argv[:1] in (["-h"], ["--help"]):
        print(__doc__)
        return 0
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path.cwd()
    try:
        if argv[:1] == ["mode"]:
            ok, why = enforcing(root)
            print(f"{'enforce' if ok else 'advisory'}: {why}")
            return 0
        if argv[:1] == ["guard"]:
            code, msg = guard(root)
            print(msg)
            return code
    except PolicyError as exc:
        print(f"generated_docs: {exc}", file=sys.stderr)
        return 2
    print("usage: generated_docs.py mode|guard [--root DIR] | --selftest", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
