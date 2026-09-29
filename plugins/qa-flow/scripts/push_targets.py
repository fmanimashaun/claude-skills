#!/usr/bin/env python3
"""Does this shell command `git push` to `main` or `master`? Decided the way git decides it.

Run:  printf '%s' "$cmd" | python3 push_targets.py    # exit 0 = targets main/master (named on
                                                       #   stdout), 1 = no push targets them,
                                                       #   3 = could not judge (the caller fails CLOSED)
      python3 push_targets.py --selftest

WHY THIS EXISTS (#1410). `release-gate.sh` matched `\\b(main|master)\\b` anywhere in a push segment,
and `\\b` counts `-` and `/` as boundaries: `git push -u origin fix/1010-one-main` and
`feat/983-pr2-master-detail` were both refused as promotions, twice in one day, and both authors
renamed their branch to get past it. A fail-closed gate that refuses correct work teaches people
its refusals are noise.

AND THE OTHER DIRECTION, found while fixing it. The regex read the NORMALISED segment, and the
normaliser strips quoted spans -- so `git push origin "main"` and `git push origin 'HEAD:main'`
arrived as `git push origin ` and were ALLOWED. This parser reads the RAW command with `shlex`, so a
quoted argument is an argument, and anything it cannot tokenise is exit 3, which the hook denies.

What counts as a destination, per `git help push`:
  * a refspec `<src>:<dst>` names `<dst>` (a leading `+` only forces); `:<dst>` deletes `<dst>`;
    `<ref>` alone names `<ref>`; `HEAD` / `@` alone names the current branch; `:` alone is the
    matching branches, which may include main -- treated as targeting it;
  * `--all`, `--branches`, `--mirror` push every branch, main included;
  * no refspec (`git push`, `git push origin`) pushes what `@{push}` resolves to -- which honours
    `push.default` and an upstream, so a branch tracking `origin/main` IS caught -- falling back to
    the current branch's name.
`refs/heads/main` is `main`. Anything unresolvable is exit 3, never "no".
"""
from __future__ import annotations

import shlex
import subprocess
import sys
from typing import Callable

PROTECTED = {"main", "master"}
SEPARATORS = {";", "&", "&&", "|", "||", "(", ")", "\n"}
PREFIXES = {"sudo", "env", "command", "exec", "time", "nohup"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}
PUSH_OPTS_WITH_VALUE = {"-o", "--push-option", "--receive-pack", "--exec", "--repo"}
EVERY_BRANCH = {"--all", "--branches", "--mirror"}


class Unjudgeable(Exception):
    """The command could not be read well enough to say no. The caller must deny."""


def tokens(cmd: str) -> list[str]:
    lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()\n")
    lex.whitespace = " \t\r"          # a newline separates commands; it is not mere whitespace
    lex.whitespace_split = True
    lex.commenters = "#"
    try:
        return list(lex)
    except ValueError as exc:         # unbalanced quote: nothing after it can be read
        raise Unjudgeable(str(exc)) from exc


def segments(toks: list[str]) -> list[list[str]]:
    out: list[list[str]] = [[]]
    for t in toks:
        if t in SEPARATORS or set(t) <= set(";&|()\n"):
            out.append([])
        else:
            out[-1].append(t)
    return [s for s in out if s]


def push_args(seg: list[str]) -> tuple[list[str], str | None] | None:
    """The arguments after `push`, and any `git -C <dir>`; None if this segment is not a git push."""
    i = 0
    while i < len(seg) and ("=" in seg[i] and not seg[i].startswith("-") or seg[i] in PREFIXES):
        i += 1
    if i >= len(seg) or seg[i] != "git":
        return None
    i += 1
    workdir = None
    while i < len(seg) and seg[i].startswith("-"):
        if seg[i] in GIT_OPTS_WITH_VALUE:
            if seg[i] == "-C" and i + 1 < len(seg):
                workdir = seg[i + 1]
            i += 2
        else:
            i += 1
    if i >= len(seg) or seg[i] != "push":
        return None
    return seg[i + 1:], workdir


def branch_of(dst: str) -> str:
    return dst[len("refs/heads/"):] if dst.startswith("refs/heads/") else dst


def destinations(args: list[str], current: Callable[[bool], str | None]) -> list[str]:
    """Every branch this push writes, as far as it can be known. `current(push)` resolves the
    current branch (push=False) or its `@{push}` destination (push=True); None = unknown."""
    positional: list[str] = []
    repo_opt = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--":
            positional.extend(args[i + 1:])
            break
        if a in EVERY_BRANCH:
            return [f"every branch ({a})"]
        if a in PUSH_OPTS_WITH_VALUE:
            repo_opt = repo_opt or a == "--repo"
            i += 2
            continue
        if a.startswith("--repo="):
            repo_opt = True
        if a.startswith("-"):
            i += 1
            continue
        positional.append(a)
        i += 1
    refspecs = positional if repo_opt else positional[1:]
    if not refspecs:
        dst = current(True) or current(False)
        if not dst:
            raise Unjudgeable("a push with no refspec, and the current branch could not be resolved")
        return [dst]
    out = []
    for spec in refspecs:
        spec = spec.lstrip("+")
        if spec == ":":
            return ["the matching branches (:)"]
        src, sep, dst = spec.partition(":")
        target = dst if sep and dst else src
        if target in ("HEAD", "@"):
            target = current(False) or ""
            if not target:
                raise Unjudgeable("HEAD could not be resolved to a branch")
        out.append(branch_of(target))
    return out


def targets(cmd: str, current: Callable[[bool], str | None]) -> list[str]:
    hits = []
    for seg in segments(tokens(cmd)):
        parsed = push_args(seg)
        if parsed is None:
            continue
        for dst in destinations(parsed[0], lambda push, d=parsed[1]: current(push, d)):
            if dst in PROTECTED or dst.startswith(("every branch", "the matching")):
                hits.append(dst)
    return hits


def git_current(push: bool, workdir: str | None) -> str | None:
    rev = "@{push}" if push else "HEAD"
    cmd = ["git"] + (["-C", workdir] if workdir else []) + ["rev-parse", "--abbrev-ref", rev]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    if not out or out == "HEAD":      # detached, or no such ref
        return None
    return out.split("/", 1)[1] if push and "/" in out else out


def selftest() -> int:
    failures: list[str] = []

    def fake(branch: str | None, upstream: str | None = None):
        return lambda push, _d=None: (upstream if push else branch)

    on_feature = fake("fix/1010-one-main")
    cases = [
        # (#1410) the false refusals: `main`/`master` INSIDE a branch name is not a destination
        ("git push -u origin fix/1010-one-main", on_feature, False),
        ("git push origin feature/main-menu", on_feature, False),
        ("git push origin main-nav", on_feature, False),
        ("git push -u origin feat/983-pr2-master-detail", on_feature, False),
        ("git push origin maintenance", on_feature, False),
        ("git push", on_feature, False),
        ("git push origin HEAD", on_feature, False),
        ('git commit -m "push origin main" && git push origin feature/x', on_feature, False),
        ("git push origin --tags", on_feature, False),
        # the real promotions
        ("git push origin main", on_feature, True),
        ("git push origin HEAD:main", on_feature, True),
        ("git push origin dev:main", on_feature, True),
        ("git push origin refs/heads/main", on_feature, True),
        ("git push origin dev:refs/heads/master", on_feature, True),
        ("git push origin +main", on_feature, True),
        ("git push origin :main", on_feature, True),
        ("git push origin --delete main", on_feature, True),
        ("git push --all origin", on_feature, True),
        ("git push origin :", on_feature, True),
        ("git push --repo=origin main", on_feature, True),
        ("git -C repo push -o ci.skip origin main", on_feature, True),
        ("FOO=1 sudo git push origin main", on_feature, True),
        ("git status; git push origin main", on_feature, True),
        ("git status\ngit push origin main", on_feature, True),
        # the bypass the regex had: the normaliser strips quoted spans, the parser must not
        ('git push origin "main"', on_feature, True),
        ("git push origin 'HEAD:main'", on_feature, True),
        # a bare push FROM main, and from a branch whose @{push} is main (push.default=upstream)
        ("git push", fake("main"), True),
        ("git push origin HEAD", fake("main"), True),
        ("git push", fake("topic", "main"), True),
    ]
    for cmd, cur, want in cases:
        try:
            got = bool(targets(cmd, cur))
        except Unjudgeable as exc:
            got = f"unjudgeable: {exc}"
        if got is not want:
            failures.append(f"{cmd!r}: expected {'TARGETS main' if want else 'does not target main'}, got {got}")
    # Could not judge -> Unjudgeable, which the hook turns into a denial. Never a quiet "no".
    for cmd, cur in (('git push origin "main', on_feature), ("git push", fake(None))):
        try:
            targets(cmd, cur)
            failures.append(f"{cmd!r}: must be unjudgeable (the hook denies), not answered")
        except Unjudgeable:
            pass
    total = len(cases) + 2
    if failures:
        print(f"push_targets selftest FAILED -- {len(failures)} of {total}:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1
    print(f"push_targets selftest: {total} checks passed")
    return 0


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    try:
        hits = targets(sys.stdin.read(), git_current)
    except Unjudgeable as exc:
        print(f"could not judge the push destination: {exc}")
        return 3
    if hits:
        print(", ".join(sorted(set(hits))))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
