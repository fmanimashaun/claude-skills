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
            before = line[:m.start()]
            if before.count("'") % 2 or before.count('"') % 2:
                continue            # a quoted `<<X` is text, not a heredoc
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


def issue_creates(cmd: str) -> list[tuple[list[str], str | None, str | None]]:
    """(argv, the directory it runs in, a GH_REPO prefix) for every `gh issue create` in the command.

    The directory is None (the session's) or a literal `cd` operand, and a `cd` is followed in
    exactly ONE shape (#1400):

        cd <literal path> && gh issue create …

    `cd` is the command's first word, `&&` joins it DIRECTLY to the create, and the create is its
    segment's first word (a `GH_REPO=` prefix aside, which `verdict` treats as naming a repo).
    Every other shape -- no cd, or a cd anywhere else -- is None: the session's rules, exactly as
    before #1400. Why so narrow: five independent reviews of broader versions each found a shape
    where ANOTHER repo's rules were applied to a create that did not land there (a subshell `cd`,
    `cd -`, `||`, compound bodies, a `case` `)`, `time`, `export GIT_DIR=`, `env -C`). The session's
    rules are the check the same create gets with no cd at all, so falling back to them cannot let
    anything through that was refused before; `verdict` adds the remaining certainty checks.
    """
    try:
        cmd = strip_heredocs(cmd)
    except ValueError:
        return [(["__unparseable__"], None, None)]
    cmd = cmd.replace("\\\n", "").replace("\n", " ; ")   # a backslash-newline JOINS: `cre\\<nl>ate`
    # The followed cd shape is checked on the RAW text too (#1440): shlex drops quotes, so a quoted
    # `'&&'` would otherwise read as the separator. The operand may itself be quoted.
    raw_cd_shape = bool(re.match(r"""\s*cd\s+('[^']*'|"[^"]*"|[^\s'"&;|()]+)\s*&&""", cmd))
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return [(["__unparseable__"], None, None)]
    # shlex glues adjacent punctuation (`);`, `&&(`). A glued run is read as a word, which can only
    # keep the exact cd shape from matching -- and then the session's rules apply. It never hides a
    # create: `gh issue create` is found anywhere in its segment.
    split = tokens
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
                # Any path to gh is gh (`/usr/bin/gh issue create`, #1423).
                if os.path.basename(words[i]) == "gh" and words[i + 1] == "issue" and words[i + 2] == "create":
                    cd = _cd_in_force(items[:start]) if raw_cd_shape else None
                    # After a followed cd, the create must BE the segment -- no `env -C`, no
                    # `command`, no GIT_DIR=: each sends the create somewhere the cd did not.
                    if cd is not None and (i != 0 or set(env) - {"GH_REPO"}):
                        cd = None
                    out.append((words[i + 3:], cd, env.get("GH_REPO")))
                    break
            seg, start = [], k + 1
        else:
            seg.append(tok)
    return out


def _cd_in_force(prefix: list[str]) -> str | None:
    """The cd target when everything before the create's segment is EXACTLY `cd <literal> &&`.

    Anything else is None: judged in the session's directory, which is what the hook did before
    #1400 and is the one answer that cannot leak (see `verdict`).
    """
    # That the first word IS `cd`, with an unquoted `&&` after its operand, is checked on the raw text
    # (`raw_cd_shape`), which sees quotes; here only the token shape of the prefix remains.
    if len(prefix) != 3 or prefix[2] != "&&":
        return None
    # A `-`, `$VAR` or backtick operand names no directory the text can see, so target_root finds
    # nothing there and the session's rules apply -- no special case needed.
    return prefix[1]


CREATE_TEXT = re.compile(r"(?:^|[\s`(;&|])(?:\S*/)?gh\s+issue\s+create\b")
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}


def hidden_create(cmd: str) -> str | None:
    """A `gh issue create` the parser cannot label-check, named by its shape, or None (#1423).

    Owner decision (#1423): refuse, and say "run it directly". A create inside a command STRING runs
    as a create, but its labels are one quoted token here: `sh -c '…'`, `eval '…'`, backticks and
    `$( … )`. A plain mention -- `echo "gh issue create"`, a grep for it -- is text, not a command,
    and stays allowed: only a shell, `eval`, or a substitution EXECUTES the string.
    """
    try:
        body = strip_heredocs(cmd)
    except ValueError:
        return None                  # the caller already refuses an unparseable command
    # Backticks PAIR: the text between the 1st and 2nd is a substitution, the 2nd and 3rd is not.
    # An unclosed one runs to the end of the command.
    ticks = body.split("`")
    if any(CREATE_TEXT.search(" " + span) for span in ticks[1::2]):
        return "backticks"
    # `$( … )` to its OWN closing parenthesis, counted, so a create after it is not inside it.
    for m in re.finditer(r"\$\(", body):
        depth, j = 1, m.end()
        while j < len(body) and depth:
            depth += {"(": 1, ")": -1}.get(body[j], 0)
            j += 1
        if CREATE_TEXT.search(" " + body[m.end():j - (0 if depth else 1)]):
            return "a `$( … )` substitution"
    try:
        lexer = shlex.shlex(body.replace("\n", " ; "), posix=True, punctuation_chars=";&|()")
        lexer.whitespace_split = True
        tokens = list(lexer)
    except ValueError:
        return None
    seg: list[str] = []
    for tok in tokens + [";"]:
        if tok and set(tok) <= set(";&|()"):
            words = [w for w in seg if not ("=" in w and w.split("=", 1)[0].isidentifier())]
            head = os.path.basename(words[0]) if words else ""
            rest = " ".join(words[1:])
            # `-c` may be bundled with other short flags: `bash -lc '…'`.
            runs_string = any(w.startswith("-") and not w.startswith("--") and "c" in w for w in words[1:])
            if head in SHELLS and runs_string and CREATE_TEXT.search(rest):
                return f"`{head} -c`"
            if head == "eval" and CREATE_TEXT.search(rest):
                return "`eval`"
            seg = []
        else:
            seg.append(tok)
    return None


def target_root(cd: str | None, root: Path) -> tuple[Path | None, str]:
    """The repository a create runs in: `root` without a `cd`, else the cd target's git toplevel."""
    if cd is None:
        return root, ""
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
        elif a.startswith("-R") and len(a) > 2:
            repo = a[2:]            # gh accepts the value glued to the short flag
        i += 1
    return labels, repo


def norm_repo(s: str | None) -> str | None:
    """`owner/name`, lowercased, from ANY spelling of a repo: `owner/name`, a URL with or without
    userinfo (`https://token@github.com/…`), an ssh port (`ssh://git@github.com:22/…`), an ssh alias
    (`git@github-work:…`), an enterprise host, `.git`. The host is dropped on purpose: two remotes
    naming the same owner/name are treated as the same repo, which only ever means MORE fallback to
    the session's rules -- the safe direction."""
    if not s:
        return None
    m = re.search(r"([^/:@\s]+)/([^/:@\s]+?)(?:\.git)?/*$", s.strip().lower())
    return f"{m.group(1)}/{m.group(2)}" if m else None

def own_repo(root: Path) -> str | None:
    """The `origin` repo, normalised, or None."""
    try:
        url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None
    return norm_repo(url)


def remotes(root: Path) -> set[str]:
    """EVERY remote's repo, normalised. gh picks among them (`upstream` before `origin`), so a
    checkout any of whose remotes is the session's repo may file there."""
    try:
        out = subprocess.run(["git", "-C", str(root), "remote", "-v"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return {r for line in out.splitlines() if len(line.split()) >= 2
            for r in [norm_repo(line.split()[1])] if r}


def matches(label: str, pattern: str) -> bool:
    return label.startswith(pattern[:-1]) if pattern.endswith("*") else label == pattern


def verdict(cmd: str, root: Path) -> tuple[bool, str]:
    shape = hidden_create(cmd)
    if shape:
        return False, (f"a `gh issue create` inside {shape} cannot be label-checked (its labels are one "
                       "quoted string here). Run it directly, with its --label flags (#1423).")
    creates = issue_creates(cmd)
    if not creates:
        return True, ""
    for args, cd, env_repo in creates:
        if args == ["__unparseable__"]:
            return False, "the gh issue create command could not be parsed, so its labels cannot be checked"
        labels, repo = parse_args(args)
        # THE SAFE DEFAULT IS THE SESSION'S RULES -- exactly what the hook did before #1400. Another
        # repo's rules apply only when the create CERTAINLY files there: the allowlisted cd shape,
        # no repo named on the create (-R, --repo, GH_REPO), a target with remotes, and none of them
        # the session's repo (gh may pick `upstream` over `origin`). Every leak five reviews found
        # was another repo's rules applied without that certainty; this default cannot leak,
        # because it is the check the same create gets with no cd at all.
        target = root
        # GH_REPO in the hook's own environment (settings `env`) redirects gh too. One set only via
        # CLAUDE_ENV_FILE is invisible here -- a known limit, recorded in #1400.
        if cd is not None and repo is None and env_repo is None and not os.environ.get("GH_REPO"):
            found, _ = target_root(cd, root)
            if found is not None:
                theirs, ours = remotes(found), remotes(root)
                # Certain only when BOTH sides have remotes and they share none: gh may file into
                # any remote (`upstream` first), so one shared repo means the session's rules.
                if theirs and ours and ours.isdisjoint(theirs):
                    target = found
        followed = target != root
        groups, why = load_groups(target)
        if why:
            return False, why
        mine = own_repo(target)
        foreign = repo is not None and norm_repo(repo) != mine
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
                decl = target / CONFIG if followed else CONFIG
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
        # Both sides need remotes for the cd to be certain: the session is me/skills, the target
        # a git checkout whose only remote is someone else's.
        subprocess.run(["git", "init", "-q", str(s)], check=True)
        subprocess.run(["git", "-C", str(s), "remote", "add", "origin", "https://github.com/me/skills.git"], check=True)
        subprocess.run(["git", "init", "-q", str(r)], check=True)
        subprocess.run(["git", "-C", str(r), "remote", "add", "origin", "https://github.com/other/retask.git"], check=True)
        rt = "gh issue create -t X --label enhancement --label needs-decision"
        ok, why = verdict(rt, s)
        check("CONTROL: those labels fail the session's own declaration", not ok and "comp:*" in why, why)
        ok, why = verdict(f"cd {r} && {rt}", s)
        check("cd into another repo: that repo's declaration applies, and passes", ok, why)
        ok, why = verdict(f"cd {r} && gh issue create -t X --label bug", s)
        check("...and that repo's rules still refuse, naming its file",
              not ok and "severity:s1" in why and str(r) in why, why)
        ok, why = verdict("(true);gh issue create -t X", s)
        check("a create right after a glued `);` is seen, and its missing label refused", not ok and "no --label" in why, why)
        check("a newline after && continues the chain", verdict(f"cd {r} &&\n{rt}", s)[0],
              verdict(f"cd {r} &&\n{rt}", s)[1])
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
        check("a cd to a missing directory keeps the session's rules", not ok and "comp:*" in why, why)
        bare_target = Path(td) / "noremote"
        bare_target.mkdir()
        (bare_target / ".rails-flow").mkdir()
        (bare_target / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
        ok, why = verdict(f"cd {bare_target} && {rt}", s)
        check("a target with no remote keeps the session's rules: gh's destination is unknown",
              not ok and "comp:*" in why, why)
        check("CONTROL: a create with no cd still uses the session's declaration",
              not verdict(rt, s)[0] and not verdict(f"echo hi; {rt}", s)[0])

        # ---- every OTHER shape with a cd is refused, never guessed ---------------------------------
        # Each was a real leak in an earlier draft (three independent reviews), or is its near kin.
        # The labels pass the target repo, so a guess would let them through; the session must judge.
        u = Path(td) / "undeclared"
        u.mkdir()
        one = "gh issue create -t X --label comp:x"     # one label: passes an undeclared dir, fails skills
        # "Refused" here means judged by the SESSION's rules: the labels pass the target's rules and
        # fail the session's, so a refusal proves the cd was NOT followed -- the safe default.
        def refused(name: str, cmd: str, needle: str = "comp:*") -> None:
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
                ("env -C redirecting the create", f"cd {r} && env -C {s} {rt}"),
                ("a repo named with -R after the cd", f"cd {r} && {rt} -R me/skills"),
                ("GH_REPO on the create after the cd", f"cd {r} && GH_REPO=someone/else {rt}")):
            refused(name, shape)
        refused("-R naming the session's own repo keeps its rules", f"cd {u} && {one} -R me/skills", "type:*")
        refused("GH_REPO naming the session's own repo keeps its rules", f"cd {u} && GH_REPO=me/skills {one}", "type:*")
        ok, why = verdict("cat <<EOF\n" + one, s)
        check("an unterminated heredoc refuses rather than swallowing the create",
              not ok and "could not be parsed" in why, why)
        ok, why = verdict("echo '<<X'\ngh issue create -t t\nX", s)
        check("a quoted <<X is text, so the unlabelled create after it is seen", not ok and "no --label" in why, why)
        ok, why = verdict("gh issue cre\\\nate -t t", s)
        check("a backslash-newline joins, so `cre\\<nl>ate` is still a create", not ok and "no --label" in why, why)
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
        up = Path(td) / "upstream-only"
        up.mkdir()
        (up / ".rails-flow").mkdir()
        (up / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(up)], check=True)
        subprocess.run(["git", "-C", str(up), "remote", "add", "upstream", "git@github.com:Me/Skills.git"], check=True)
        ok, why = verdict(f"cd {up} && {rt}", s)
        check("a target whose UPSTREAM is the session's repo keeps the session's rules", not ok and "comp:*" in why, why)
        subprocess.run(["git", "-C", str(up), "remote", "add", "origin", "https://github.com/someone/fork.git"], check=True)
        ok, why = verdict(f"cd {up} && {rt}", s)
        check("...and so does a fork origin with the session repo as upstream", not ok and "comp:*" in why, why)
        # The session's repo in every URL spelling a clone might carry (#1406 sixth review).
        for n, (kind, url) in enumerate((("userinfo", "https://x-access-token:secret@github.com/me/skills.git"),
                                         ("an ssh port", "ssh://git@github.com:22/me/skills.git"),
                                         ("an ssh alias", "git@github-work:me/skills.git"),
                                         ("an enterprise host", "https://github.example.com/Me/Skills"))):
            c = Path(td) / f"spelling{n}"
            (c / ".rails-flow").mkdir(parents=True)
            (c / CONFIG).write_text(json.dumps(retask), encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(c)], check=True)
            subprocess.run(["git", "-C", str(c), "remote", "add", "origin", url], check=True)
            ok, why = verdict(f"cd {c} && {rt}", s)
            check(f"a clone whose origin uses {kind} is the session's repo",
                  not ok and "comp:*" in why, why)
        # GH_REPO in the hook's environment redirects gh, so the cd is not certain.
        saved = os.environ.get("GH_REPO")
        os.environ["GH_REPO"] = "me/skills"
        try:
            ok, why = verdict(f"cd {r} && {rt}", s)
            check("GH_REPO in the environment keeps the session's rules", not ok and "comp:*" in why, why)
        finally:
            if saved is None:
                os.environ.pop("GH_REPO", None)
            else:
                os.environ["GH_REPO"] = saved
        # A session whose origin is a fork and whose UPSTREAM is the real repo: gh files upstream.
        s2 = Path(td) / "session-fork"
        (s2 / ".rails-flow").mkdir(parents=True)
        (s2 / CONFIG).write_text(json.dumps(skills), encoding="utf-8")
        subprocess.run(["git", "init", "-q", str(s2)], check=True)
        subprocess.run(["git", "-C", str(s2), "remote", "add", "origin", "https://github.com/someone/fork.git"], check=True)
        subprocess.run(["git", "-C", str(s2), "remote", "add", "upstream", "https://github.com/me/skills.git"], check=True)
        ok, why = verdict(f"cd {clone} && {rt}", s2)
        check("a session whose upstream is the target's repo keeps its own rules", not ok and "comp:*" in why, why)
        # A session with NO remote cannot be told apart from anything: never follow.
        s3 = Path(td) / "session-bare"
        (s3 / ".rails-flow").mkdir(parents=True)
        (s3 / CONFIG).write_text(json.dumps(skills), encoding="utf-8")
        ok, why = verdict(f"cd {r} && {rt}", s3)
        check("a session with no remote keeps its own rules", not ok and "comp:*" in why, why)
        # Repo names in every spelling gh accepts.
        for spelling in ("-Rme/skills", "-R Me/Skills", "-R https://github.com/me/skills", "--repo=github.com/me/skills.git"):
            ok, why = verdict(f"{one} {spelling}", s)
            check(f"-R spelled `{spelling}` is the session's repo", not ok and "type:*" in why, why)
        check("CONTROL: a glued -R naming another repo needs one label, like the spaced form",
              verdict(f"{one} -Rsomeone/else", s)[0])
        ok, why = verdict(f"GH_REPO=https://github.com/other/x {one}", s)
        check("GH_REPO with no cd changes nothing, as before #1400", not ok and "type:*" in why, why)
        # The reverse direction: a correctly labelled create with no followed cd is ALLOWED, as on dev.
        for name, shape in (("echo cd", f"echo cd; {full}"), ("a subshell cd", f"(cd {u} && true); {full}"),
                            ("popd", f"popd; {full}"), ("grep cd", f"grep -rn cd docs; {full}")):
            check(f"CONTROL: `{name}` before a fully labelled create is allowed, as on dev",
                  verdict(shape, s)[0], verdict(shape, s)[1])
        # ---- #1440: a QUOTED `&&` is an argument, not the separator ----------------------------
        ok, why = verdict(f"cd {r} '&&' {rt}", s)
        check("a quoted '&&' does not make the followed cd shape", not ok and "comp:*" in why, why)
        check("CONTROL: a quoted cd OPERAND still makes it", verdict(f"cd '{r}' && {rt}", s)[0],
              verdict(f"cd '{r}' && {rt}", s)[1])

        # ---- #1423: a create the parser cannot label-check is refused, named -----------------------
        # `bare` is undeclared, so ONE label passes a create it can see: a refusal here is the shape.
        lab = "gh issue create -t X --label anything"
        for shape, cmd in (("`sh -c`", f"sh -c '{lab}'"), ("`bash -c`", f'bash -lc "{lab}"'),
                           ("`eval`", f"eval '{lab}'"), ("backticks", f"x=`{lab}`"),
                           ("a `$( … )` substitution", f"y=$({lab})")):
            ok, why = verdict(cmd, bare)
            check(f"a create inside {shape} is refused and named", not ok and shape in why and "directly" in why, why)
        for name, cmd in (("echo of the text", 'echo "gh issue create"'), ("grep for the text", "grep -rn 'gh issue create' docs"),
                          ("a backtick BEFORE the create", f"x=`date` && {lab}"), ("$( ) BEFORE the create", f"echo $(date) && {lab}")):
            check(f"CONTROL: {name} is not a hidden create", verdict(cmd, bare)[0], verdict(cmd, bare)[1])
        ok, why = verdict("/usr/bin/gh issue create -t X", bare)
        check("a path to gh is gh: its missing label is refused", not ok and "no --label" in why, why)
        check("CONTROL: ...and a labelled one passes", verdict("/usr/bin/gh issue create -t X --label a", bare)[0])

        (r / CONFIG).write_text("{not json", encoding="utf-8")
        check("an unreadable declaration refuses rather than allowing",
              not verdict("gh issue create -t X --label feature", r)[0])

    for f in fails:
        print(f"FAIL {f}")
    print(f"issue_labels selftest: {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
