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
a correctly labelled issue, and asked for labels the other repo does not have. So a create written
`cd <literal path> && gh issue create …` is judged by that directory's git toplevel, which
supplies both the declaration and the "is this our repo" answer for `-R`. Any OTHER shape with a
`cd` in it is refused rather than guessed (see `issue_creates`), because a guess applies one repo's
rules to another's issue -- the defect itself, in a different direction.

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


HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")  # not <<< (a herestring)


def strip_heredocs(cmd: str) -> str:
    """Drop every heredoc BODY, keeping the line that opens it (#1336).

    Our own doctrine says to write issue bodies with a quoted heredoc and `--body-file`, never through
    double quotes. A body is prose, so it holds apostrophes and backticks, and shlex read those as an
    unterminated quote and refused a correctly labelled `gh issue create` in the same call. The body
    is data the shell never tokenises, so it is not ours to parse either.

    A heredoc whose closing tag never arrives raises ValueError -- a refusal -- when the lines it
    would swallow hold a `gh issue create`, because a create nobody sees is a create let through.
    Otherwise it is a quoted mention or arithmetic, and is left alone. `<<<` is a herestring, not a
    heredoc: it has no body to strip.
    """
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        out.append(line)
        i += 1
        for m in HEREDOC.finditer(line):
            tag, dash = m.group(3), m.group(1) == "-"
            start_of_swallow = i
            while i < len(lines) and (lines[i].lstrip("\t") if dash else lines[i]) != tag:
                i += 1
            if i >= len(lines):
                # Never closed. Usually a quoted mention (`--body 'a<<EOF'`) or arithmetic
                # (`$((1<<n))`), which is harmless -- UNLESS the lines it would swallow hold a
                # `gh issue create`, which would then go unchecked. Refuse only that.
                if re.search(r"\bgh\s+issue\s+create\b", "\n".join(lines[start_of_swallow:])):
                    raise ValueError(f"heredoc <<{tag} is never closed")
                break
            i += 1  # the closing tag line
    return "\n".join(out)


UNKNOWN = "\0unknown"   # a cd the create may or may not have followed
CD_WORDS = {"cd", "pushd", "popd"}


def _is_cd_word(tok: str) -> bool:
    """`cd`, and `cd` glued into an assignment or substitution (`x=\\`cd`, `$(cd`): any way to move."""
    return any(piece in CD_WORDS for piece in re.split(r"[`=$(){};]+", tok))


def issue_creates(cmd: str) -> list[tuple[list[str], str | None, str | None]]:
    """(argv, the directory it runs in, a GH_REPO prefix) for every `gh issue create` in the command.

    The directory is None (the session's), a literal `cd` operand, or UNKNOWN, which the caller
    refuses. It is an ALLOWLIST, and deliberately so (#1400). Three reviews of a shell model that
    tracked subshells, pipelines, conditionals and compound bodies each found a new way a guessed
    `cd` leaked -- a `case` pattern's `)`, a `time` prefix, a quoted `fi` -- because a blocklist over
    shell syntax never ends. So a `cd` is followed in exactly ONE shape:

        cd <literal path> && gh issue create …

    the command's FIRST word is `cd`, `&&` joins it DIRECTLY to the create, and the create is the
    segment's first word (a `GH_REPO=` prefix aside). A fourth review showed why nothing may sit in
    between: `export GH_REPO=`, `export GIT_DIR=`, `env -C <dir>` each send the create elsewhere. No cd word before the create: the session's own directory, as before.
    Any other shape with a cd in it: UNKNOWN, refused with the shape that works. The cost is a
    refusal of some valid commands, each fixable in one line; the benefit is that nothing leaks.
    """
    try:
        cmd = strip_heredocs(cmd)
    except ValueError:
        return [(["__unparseable__"], None, None)]
    cmd = cmd.replace("\\\n", " ").replace("\n", " ; ")
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return [(["__unparseable__"], None, None)]
    # shlex GLUES adjacent punctuation: `);` and `)&&` arrive as one token. Unsplit, such a token
    # read as a word, and the `gh issue create` after it vanished -- a create let through unseen.
    split: list[str] = []
    for tok in tokens:
        if tok and set(tok) <= set(";&|()"):
            i = 0
            while i < len(tok):
                two = tok[i:i + 2]
                if two in ("&&", "||"):
                    split.append(two)
                    i += 2
                else:
                    split.append(tok[i])
                    i += 1
        else:
            split.append(tok)
    # A newline right after `&&` / `||` / `|` continues that chain; drop the `;` it became.
    items: list[str] = []
    for tok in split:
        if tok == ";" and items and items[-1] in ("&&", "||", "|"):
            continue
        items.append(tok)

    out: list[tuple[list[str], str | None, str | None]] = []
    seg: list[str] = []
    start = 0                    # index in `items` where `seg` began
    for k, tok in enumerate(items + [";"]):
        if tok in ("(", ")") or (tok and set(tok) <= set(";&|")):
            words = list(seg)
            env = {}
            while words and "=" in words[0] and words[0].split("=", 1)[0].isidentifier():
                name, _, value = words.pop(0).partition("=")
                env[name] = value
            for i in range(len(words) - 2):
                if words[i] == "gh" and words[i + 1] == "issue" and words[i + 2] == "create":
                    cd = _cd_in_force(items[:start])
                    # After a followed cd, the create must BE the segment -- no `env -C`, no
                    # `command`, no GIT_DIR=: each sends the create somewhere the cd did not.
                    if cd not in (None, UNKNOWN) and (i != 0 or set(env) - {"GH_REPO"}):
                        cd = UNKNOWN
                    out.append((words[i + 3:], cd, env.get("GH_REPO")))
                    break
            seg, start = [], k + 1
        else:
            seg.append(tok)
    return out


def _cd_in_force(prefix: list[str]) -> str | None:
    """The directory a create runs in, from everything before its own segment. See issue_creates."""
    if not any(_is_cd_word(t) for t in prefix):
        return None
    if len(prefix) < 3 or prefix[0] != "cd" or prefix[2] != "&&":
        return UNKNOWN
    target = prefix[1]
    if target in ("-", "--") or target.startswith("-") or "$" in target or "`" in target:
        return UNKNOWN
    # EXACTLY `cd <path> &&` and then the create. Any command in between -- `export GH_REPO=`,
    # `export GIT_DIR=`, `source`, a second cd -- can send the create elsewhere (#1406 review).
    if len(prefix) != 3:
        return UNKNOWN
    return target


def target_root(cd: str | None, root: Path) -> tuple[Path | None, str]:
    """The repository a create runs in: `root` without a `cd`, else the cd target's git toplevel."""
    if cd is None:
        return root, ""
    if cd == UNKNOWN:
        return None, ("cannot tell which directory this gh issue create runs in, so its label rules are "
                      "unknown. A cd is followed only as the command's first word, joined to the create "
                      "by && alone: `cd /literal/path && gh issue create ...`.")
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
    session_repo = own_repo(root)
    for args, cd, env_repo in creates:
        if args == ["__unparseable__"]:
            return False, "the gh issue create command could not be parsed, so its labels cannot be checked"
        labels, repo = parse_args(args)
        repo = repo or env_repo
        target, why = target_root(cd, root)
        if target is None:
            return False, why
        # A repo NAMED with -R / GH_REPO decides where the issue lands, whatever the cd says: if it is
        # the session's own, the session's rules apply even from inside another directory.
        if repo is not None and session_repo is not None and repo == session_repo:
            target, cd = root, None
        # A cd into ANOTHER CHECKOUT of the session's own repo (a clone, a worktree) files into the
        # session's repo, so the session's rules apply -- not the checkout's, which may declare none.
        elif cd is not None and session_repo is not None and own_repo(target) == session_repo:
            target, cd = root, None
        groups, why = load_groups(target)
        if why:
            return False, why
        mine = own_repo(target)
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
        # ---- #1400: the TARGET repository's declaration, in the one shape that is followed -------
        rt = "gh issue create -t X --label enhancement --label needs-decision"
        ok, why = verdict(rt, s)
        check("CONTROL: those labels fail the session's own declaration", not ok and "comp:*" in why, why)
        ok, why = verdict(f"cd {r} && {rt}", s)
        check("cd into another repo: that repo's declaration applies, and passes", ok, why)
        ok, why = verdict(f"cd {r} && gh issue create -t X --label bug", s)
        check("...and that repo's rules still refuse, naming its file",
              not ok and "severity:s1" in why and str(r) in why, why)
        check("a newline after && continues the chain", verdict(f"cd {r} &&\n{rt}", s)[0],
              verdict(f"cd {r} &&\n{rt}", s)[1])
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
        ok, why = verdict(f"cd {td}/nowhere && {rt}", s)
        check("a cd to a missing directory is refused", not ok and "names no directory" in why, why)
        check("CONTROL: a create with no cd still uses the session's declaration",
              not verdict(rt, s)[0] and not verdict(f"echo hi; {rt}", s)[0])

        # ---- every OTHER shape with a cd is refused, never guessed ---------------------------------
        # Each was a real leak in an earlier draft (three independent reviews), or is its near kin.
        # The labels pass the target repo, so a guess would let them through; UNKNOWN must refuse.
        subprocess.run(["git", "init", "-q", str(s)], check=True)
        subprocess.run(["git", "-C", str(s), "remote", "add", "origin", "https://github.com/me/skills.git"], check=True)
        u = Path(td) / "undeclared"
        u.mkdir()
        one = "gh issue create -t X --label comp:x"     # one label: passes an undeclared dir, fails skills
        def refused(name: str, cmd: str, needle: str = "cannot tell") -> None:
            ok, why = verdict(cmd, s)
            check(f"refused: {name}", not ok and needle in why, why)
        for name, shape in (
                ("a cd separated by ;", f"cd {r}; {rt}"),
                ("a cd inside a subshell", f"(cd {r}); {rt}"),
                ("a subshell cd before &&", f"(cd {r}) && {rt}"),
                ("a create inside the subshell", f"(cd {r} && {rt})"),
                ("a cd that is not the first command", f"true && cd {r} && {rt}"),
                ("a cd on a later line", f"echo hi\ncd {r} && {rt}"),
                ("a cd in a pipeline", f"cd {r} | cat && {rt}"),
                ("a cd sent to the background", f"cd {r} & {rt}"),
                ("a create after cd ||", f"cd {r} || {rt}"),
                ("a second cd", f"cd {r} && cd {u} && {rt}"),
                ("cd -", f"cd {u} && cd - && {rt}"),
                ("a cd to a variable", f"cd $OTHER && {rt}"),
                ("pushd", f"pushd {r} && {rt}"),
                ("builtin cd", f"builtin cd {r} && {rt}"),
                ("a cd inside $(...)", f"x=$(cd {r} && pwd) && {rt}"),
                ("a cd inside backticks", f"x=`cd {r}` && {rt}"),
                ("a cd inside an if body", f"if false; then\n cd {r}\nfi\n{rt}"),
                ("a cd behind time", f"time if false; then cd {r}; fi; {rt}"),
                ("a cd behind a case pattern's )", f"(case x in a) ;; esac; cd {r}); {rt}"),
                ("a cd behind a quoted fi", f"if false; then 'fi'; cd {r}; fi; {rt}"),
                ("a create after cd && exit;", f"cd {r} && exit; {rt}"),
                ("a command between the cd and the create", f"cd {r} && git status && {rt}"),
                ("export GH_REPO between the cd and the create", f"cd {r} && export GH_REPO=me/skills && {rt}"),
                ("export GIT_DIR between the cd and the create", f"cd {r} && export GIT_DIR={s}/.git && {rt}"),
                ("GIT_DIR on the create itself", f"cd {r} && GIT_DIR={s}/.git {rt}"),
                ("env -C redirecting the create", f"cd {r} && env -C {s} {rt}")):
            refused(name, shape)
        refused("-R naming the session's own repo keeps its rules", f"cd {u} && {one} -R me/skills", "type:*")
        refused("GH_REPO naming the session's own repo keeps its rules", f"cd {u} && GH_REPO=me/skills {one}", "type:*")
        ok, why = verdict("echo 'use <<EOF'\n" + one, s)
        check("an unterminated heredoc refuses rather than swallowing the create",
              not ok and "could not be parsed" in why, why)
        full = "gh issue create -t X --label comp:a --label type:b --label prio:P2"
        check("CONTROL: a quoted <<EOF on the create's own line is not a parse error",
              verdict(full + " --body 'a<<EOF'", s)[0], verdict(full + " --body 'a<<EOF'", s)[1])
        check("CONTROL: arithmetic << is not a parse error",
              verdict("echo $((1<<n)) && " + full, s)[0], verdict("echo $((1<<n)) && " + full, s)[1])
        ok, why = verdict("cat <<< hi\ngh issue create -t X\nhi", s)
        check("a <<< herestring is not a heredoc, so the unlabelled create after it is seen",
              not ok and "no --label" in why, why)
        # A cd into ANOTHER checkout of the session's own repo files into the session's repo.
        clone = Path(td) / "clone"
        clone.mkdir()
        subprocess.run(["git", "init", "-q", str(clone)], check=True)
        subprocess.run(["git", "-C", str(clone), "remote", "add", "origin", "https://github.com/me/skills.git"], check=True)
        ok, why = verdict(f"cd {clone} && {one}", s)
        check("a cd into a clone of the session's own repo keeps the session's rules", not ok and "type:*" in why, why)
        (r / CONFIG).write_text("{not json", encoding="utf-8")
        check("an unreadable declaration refuses rather than allowing",
              not verdict("gh issue create -t X --label feature", r)[0])

    for f in fails:
        print(f"FAIL {f}")
    print(f"issue_labels selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
