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

THE DECLARATION IS THE TARGET REPOSITORY'S, not the session's (#1400). A coordinator working from one
checkout runs `cd /path/to/other-repo && gh issue create ...`; the issue lands in the other repo, so
its labels answer to the other repo's declaration. The hook used to read the session's file, refused
a correctly labelled issue, and asked for labels the other repo does not have. So each create is
tied to the directory it runs in: a `cd` earlier in the same command moves it, and that directory's
git toplevel supplies both the declaration and the "is this our repo" answer for `-R`. A `cd` whose
target cannot be resolved here (a `$VAR`, a missing path) is refused and named, because guessing
would apply one repo's rules to another's issue -- the defect itself, in a different direction.

Called by guard-bash.sh with the RAW command on stdin (the normalised form strips quotes, and a label
value is usually quoted). Prints the refusal and exits 1; exits 0 to allow. The hook fails closed on
any other exit.

Run:  issue_labels.py [--root DIR] < command.txt
      issue_labels.py --selftest
"""
from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

CONFIG = Path(".rails-flow/issue-labels.json")


HEREDOC = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def strip_heredocs(cmd: str) -> str:
    """Drop every heredoc BODY, keeping the line that opens it (#1336).

    Our own doctrine says to write issue bodies with a quoted heredoc and `--body-file`, never through
    double quotes. A body is prose, so it holds apostrophes and backticks, and shlex read those as an
    unterminated quote and refused a correctly labelled `gh issue create` in the same call. The body
    is data the shell never tokenises, so it is not ours to parse either.
    """
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            tag, dash = m.group(3), m.group(1) == "-"
            while i < len(lines) and (lines[i].lstrip("\t") if dash else lines[i]) != tag:
                i += 1
            i += 1  # the closing tag line
    return "\n".join(out)


def issue_creates(cmd: str) -> list[tuple[list[str], str | None]]:
    """(argv, the `cd` target in force) for every `gh issue create`, split on shell operators.

    The `cd` target is the raw operand of the last `cd` before the create, or None when there was
    none. Subshell parentheses are peeled off, so `(cd x && gh issue create ...)` reads the same.
    """
    cmd = strip_heredocs(cmd)
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return [(["__unparseable__"], None)]
    out, cur, cd = [], [], None
    for tok in tokens + [";"]:
        if tok and set(tok) <= set(";&|"):
            seg = [x.strip("()") for x in cur]
            seg = [x for x in seg if x]
            if seg and seg[0] == "cd":
                target = next((x for x in seg[1:] if not x.startswith("-")), "~")
                cd = target if cd is None or target.startswith(("/", "~", "$")) else f"{cd}/{target}"
            for i in range(len(seg) - 2):
                if seg[i] == "gh" and seg[i + 1] == "issue" and seg[i + 2] == "create":
                    out.append((seg[i + 3:], cd))
                    break
            cur = []
        else:
            cur.append(tok)
    return out


def target_root(cd: str | None, root: Path) -> tuple[Path | None, str]:
    """The repository a create runs in: `root` without a `cd`, else the cd target's git toplevel."""
    if cd is None:
        return root, ""
    if "$" in cd or "`" in cd:
        return None, (f"cannot tell which repository `cd {cd}` enters, so its label rules are unknown. "
                      "Use a literal path.")
    path = Path(os.path.expanduser(cd))
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_dir():
        return None, f"`cd {cd}` names no directory, so its label rules are unknown."
    try:
        top = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        top = ""
    return (Path(top) if top else path.resolve()), ""


def load_groups(target: Path) -> tuple[list | None, str]:
    config_path = target / CONFIG
    if not config_path.is_file():
        return None, ""
    try:
        return json.loads(config_path.read_text(encoding="utf-8"))["groups"], ""
    except (ValueError, KeyError, TypeError) as exc:
        where = CONFIG if target == Path(".").resolve() else target / CONFIG
        return None, f"{where} is unreadable ({exc}); fix it so labels can be checked"


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
    for args, cd in creates:
        if args == ["__unparseable__"]:
            return False, "the gh issue create command could not be parsed, so its labels cannot be checked"
        target, why = target_root(cd, root)
        if target is None:
            return False, why
        groups, why = load_groups(target)
        if why:
            return False, why
        mine = own_repo(target)
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
                decl = CONFIG if cd is None else target / CONFIG
                return False, (f"`gh issue create` needs one of {', '.join(allowed)}{scope}; it has "
                               f"{', '.join(labels)}. Declared in {decl}.")
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
        # #1336: a quoted heredoc body in the same call is prose, not shell to tokenise.
        body = "cat > b.md <<'EOF'\nThe validator's warning: `x` is \"quoted\"\nEOF\n"  # ONE apostrophe: odd, so shlex cannot pair it
        check("a heredoc body with apostrophes does not break a labelled create",
              verdict(body + 'gh issue create -t X --label "feature" --body-file b.md', r)[0],
              verdict(body + 'gh issue create -t X --label "feature" --body-file b.md', r)[1])
        ok, why = verdict(body + "gh issue create -t X --body-file b.md", r)
        check("...and an unlabelled create after the heredoc is still refused", not ok and "no --label" in why, why)
        ok, why = verdict("cat <<-EOF > b.md\n\tit's\n\tEOF\ngh issue create -t X", r)
        check("a <<- heredoc (tab-indented close) is stripped too", not ok and "no --label" in why, why)
        ok, why = verdict("gh issue create -t \"X --label feature", r)
        check("CONTROL: a genuinely unparseable create still refuses", not ok and "could not be parsed" in why, why)
        # ---- #1400: the TARGET repository's declaration, not the session's ------------------------
        # The reported case: a skills session files a correctly labelled Retask issue.
        rt = "gh issue create -t X --label enhancement --label needs-decision"
        ok, why = verdict(rt, s)
        check("CONTROL: those labels fail the session's own declaration", not ok and "comp:*" in why, why)
        ok, why = verdict(f"cd {r} && {rt}", s)
        check("cd into another repo: that repo's declaration applies, and passes", ok, why)
        ok, why = verdict(f"cd {r} && gh issue create -t X --label bug", s)
        check("...and that repo's rules still refuse, naming its file",
              not ok and "severity:s1" in why and str(r) in why, why)
        check("a subshell cd reads the same", verdict(f"(cd {r} && {rt})", s)[0])
        check("a cd separated by ; reads the same", verdict(f"cd {r}; {rt}", s)[0])
        subprocess.run(["git", "init", "-q", str(r)], check=True)
        (r / "app" / "models").mkdir(parents=True)
        # Discriminating on purpose: a subdirectory with no declaration of its own would read as
        # UNDECLARED, where one label passes -- so the fixture must be one only the toplevel refuses.
        ok, why = verdict(f"cd {r}/app/models && gh issue create -t X --label bug", s)
        check("a cd into a SUBDIRECTORY finds the repo's toplevel declaration",
              not ok and "severity:s1" in why, why)
        check("...and passes what the toplevel allows", verdict(f"cd {r}/app/models && {rt}", s)[0])
        here = Path.cwd()
        try:
            os.chdir(td)
            check("a relative cd resolves from where the command runs", verdict(f"cd retask && {rt}", s)[0],
                  verdict(f"cd retask && {rt}", s)[1])
        finally:
            os.chdir(here)
        ok, why = verdict(f"cd $OTHER && {rt}", s)
        check("a cd to a variable is refused, not guessed", not ok and "cannot tell" in why, why)
        ok, why = verdict(f"cd {td}/nowhere && {rt}", s)
        check("a cd to a missing directory is refused", not ok and "names no directory" in why, why)
        check("CONTROL: a create with no cd still uses the session's declaration",
              not verdict(rt, s)[0] and verdict(f"cd {r} && {rt}", s)[0])

        (r / CONFIG).write_text("{not json", encoding="utf-8")
        check("an unreadable declaration refuses rather than allowing",
              not verdict("gh issue create -t X --label feature", r)[0])

    for f in fails:
        print(f"FAIL {f}")
    print(f"issue_labels selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
