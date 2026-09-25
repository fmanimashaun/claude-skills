#!/usr/bin/env python3
"""Refuse a `gh issue create` whose labels miss the project's declared groups (#1311).

WHY. Issue templates apply labels only through the GitHub web form. Agents file with
`gh issue create`, which bypasses the template, so issues arrived with no labels at all: 12 of 14
open in one consumer, and `type:`/`prio:` missing from most of a maintainer repo's recent issues.
A rule in prose changed nothing; this runs on the command itself.

THE DECLARATION: `.rails-flow/issue-labels.json` at the project root.
    {"groups": [
       {"one_of": ["bug", "feature", "enhancement"]},
       {"when": "bug", "one_of": ["severity:s1", "severity:s2", "severity:s3", "severity:s4"]}
    ]}
A value ending in `*` is a prefix (`comp:*`). A group with `when` applies only if that label is set.
Undeclared, or `-R/--repo` naming another repository (whose taxonomy is not ours): at least one label.

Called by guard-bash.sh with the RAW command on stdin (the normalised form strips quotes, and a label
value is usually quoted). Prints the refusal and exits 1; exits 0 to allow. The hook fails closed on
any other exit.

Run:  issue_labels.py [--root DIR] < command.txt
      issue_labels.py --selftest
"""
from __future__ import annotations

import json
import shlex
import subprocess
import sys
from pathlib import Path

CONFIG = Path(".rails-flow/issue-labels.json")


def issue_creates(cmd: str) -> list[list[str]]:
    """The argv of every `gh issue create` in the command, split on shell operators."""
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return [["__unparseable__"]]
    out, cur = [], []
    for tok in tokens + [";"]:
        if tok and set(tok) <= set(";&|"):
            for i in range(len(cur) - 2):
                if cur[i] == "gh" and cur[i + 1] == "issue" and cur[i + 2] == "create":
                    out.append(cur[i + 3:])
                    break
            cur = []
        else:
            cur.append(tok)
    return out


def parse_args(args: list[str]) -> tuple[list[str], str | None]:
    labels, repo = [], None
    i = 0
    while i < len(args):
        a = args[i]
        if a in ("--label", "-l") and i + 1 < len(args):
            labels += [x.strip() for x in args[i + 1].split(",") if x.strip()]
            i += 2
            continue
        if a.startswith("--label="):
            labels += [x.strip() for x in a.split("=", 1)[1].split(",") if x.strip()]
        elif a in ("--repo", "-R") and i + 1 < len(args):
            repo = args[i + 1]
            i += 2
            continue
        elif a.startswith("--repo="):
            repo = a.split("=", 1)[1]
        i += 1
    return labels, repo


def own_repo(root: Path) -> str | None:
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    url = url.removesuffix(".git")
    for sep in ("github.com/", "github.com:"):
        if sep in url:
            return url.split(sep, 1)[1]
    return None


def matches(label: str, pattern: str) -> bool:
    return label.startswith(pattern[:-1]) if pattern.endswith("*") else label == pattern


def verdict(cmd: str, root: Path) -> tuple[bool, str]:
    creates = issue_creates(cmd)
    if not creates:
        return True, ""
    config_path = root / CONFIG
    groups = None
    if config_path.is_file():
        try:
            groups = json.loads(config_path.read_text(encoding="utf-8"))["groups"]
        except (ValueError, KeyError, TypeError) as exc:
            return False, f"{CONFIG} is unreadable ({exc}); fix it so labels can be checked"
    mine = own_repo(root)
    for args in creates:
        if args == ["__unparseable__"]:
            return False, "the gh issue create command could not be parsed, so its labels cannot be checked"
        labels, repo = parse_args(args)
        foreign = repo is not None and repo != mine
        if not labels:
            where = f" (the declared groups are in {CONFIG})" if groups and not foreign else ""
            return False, f"`gh issue create` with no --label{where}. Label it when you file it; a template never applies here."
        if groups is None or foreign:
            continue
        for g in groups:
            if g.get("when") and not any(matches(l, g["when"]) for l in labels):
                continue
            allowed = g.get("one_of") or []
            if not any(matches(l, p) for l in labels for p in allowed):
                scope = f" (because it is `{g['when']}`)" if g.get("when") else ""
                return False, (f"`gh issue create` needs one of {', '.join(allowed)}{scope}; it has "
                               f"{', '.join(labels)}. Declared in {CONFIG}.")
    return True, ""


def main(argv: list[str]) -> int:
    if argv[1:] == ["--selftest"]:
        return selftest()
    root = Path(argv[argv.index("--root") + 1]) if "--root" in argv else Path(".")
    ok, why = verdict(sys.stdin.read(), root.resolve())
    if not ok:
        print(why)
        return 1
    return 0


def selftest() -> int:
    import tempfile

    fails: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            fails.append(f"{label} {detail}".rstrip())

    retask = {"groups": [{"one_of": ["bug", "feature", "enhancement"]},
                         {"when": "bug", "one_of": ["severity:s1", "severity:s2", "severity:s3", "severity:s4"]}]}
    skills = {"groups": [{"one_of": ["comp:*"]}, {"one_of": ["type:*"]}, {"one_of": ["prio:*"]}]}
    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / "retask"
        (r / ".rails-flow").mkdir(parents=True)
        (r / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
        s = Path(td) / "skills"
        (s / ".rails-flow").mkdir(parents=True)
        (s / CONFIG).write_text(json.dumps(skills), encoding="utf-8")
        bare = Path(td) / "bare"
        bare.mkdir()

        check("not a gh issue create: allowed", verdict("gh issue list --label bug", r)[0])
        check("CONTROL: a feature is allowed", verdict('gh issue create -t X --label "feature" --body-file b.md', r)[0])
        ok, why = verdict("gh issue create -t X --body-file b.md", r)
        check("no label: refused", not ok and "no --label" in why, why)
        ok, why = verdict('gh issue create -t X --label "phase-3-recruitment"', r)
        check("labels outside the type group: refused, naming the group", not ok and "bug, feature, enhancement" in why, why)
        ok, why = verdict("gh issue create -t X --label bug", r)
        check("a bug without a severity: refused, saying why", not ok and "severity:s1" in why and "`bug`" in why, why)
        check("CONTROL: a bug with a severity is allowed",
              verdict("gh issue create -t X --label bug --label severity:s2", r)[0])
        check("comma-joined labels are split", verdict('gh issue create -t X -l "bug,severity:s3"', r)[0])
        check("--label=value is read", verdict("gh issue create -t X --label=feature", r)[0])

        check("prefix groups: comp/type/prio all present is allowed",
              verdict('gh issue create -t X --label "comp:rails-flow" --label type:bug --label prio:P2', s)[0])
        ok, why = verdict('gh issue create -t X --label "comp:rails-flow"', s)
        check("prefix groups: a missing type is refused", not ok and "type:*" in why, why)

        check("undeclared project: one label is enough", verdict("gh issue create -t X --label anything", bare)[0])
        check("undeclared project: no label is refused", not verdict("gh issue create -t X", bare)[0])
        check("another repo: one label is enough",
              verdict("gh issue create -R someone/else -t X --label bug", r)[0])
        check("another repo: no label is still refused", not verdict("gh issue create -R someone/else -t X", r)[0])

        check("a create later in a compound command is checked",
              not verdict('cd x && gh issue create -t X --body-file b.md', r)[0])
        check("a quoted mention is not a command", verdict('echo "gh issue create"', r)[0])
        (r / CONFIG).write_text("{not json", encoding="utf-8")
        check("an unreadable declaration refuses rather than allowing",
              not verdict("gh issue create -t X --label feature", r)[0])

    for f in fails:
        print(f"FAIL {f}")
    print(f"issue_labels selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
