#!/usr/bin/env python3
"""Every feature has an end-to-end path that a runner actually SELECTS (#1856, slice 2 of #1853).

WHY. The owner's rule (#1853): "every feature must have a way to test it end to end". Downstream, a `@real-signin` Playwright spec existed and passed on the
dev runner, but the image runner ran `--grep "@qa-image"`, which never selected it, so nothing flagged that the feature had no end-to-end path where it
mattered. A spec that no runner picks up is not a path: it counts as missing. Slice 1 (check_requirements.py) links a requirement to a manual case; this
links a requirement marked as a feature to a spec that is selected.

    python3 check_e2e_paths.py                    # the gate
    python3 check_e2e_paths.py --base origin/dev  # the base to compare the baseline with (default as in check_requirements.py)
    python3 check_e2e_paths.py --selftest         # the plumbing, against canned listings and stub executables
    python3 check_e2e_paths.py --selftest --real DIR   # also run the attack battery against a REAL Playwright (DIR holds its node_modules)

THE AUTHORITY IS PLAYWRIGHT ITSELF. The first version of this check re-implemented Playwright's argument parsing (`--grep`, `--grep-invert`, positional filters,
`--config`, `testDir`) and an independent review found six ways it disagreed with the real thing (attached `-g@tag` values, a case-insensitive CLI grep, a config
that is not at the default path, a `testDir` elsewhere, positional filters that are OR'd, `--list`). Patching each one is a loop that never ends, so this version
asks Playwright: for each runner command it runs the same command with `--list --reporter=json` and reads which tests Playwright says it would run. A feature
passes only if a listed, non-skipped test names it. The text of a runner file is read for ONE thing: to FIND the `playwright test` commands, and to refuse the
ones it cannot execute safely.

THIS IS A PROJECT GATE, run in the project's own CI or on its developer's machine, never a PreToolUse hook: running the project's own `npx --no-install playwright`
(which loads the project's playwright config and spec files, as its own test run does) is in scope. It never installs anything. The arguments are passed as an
argument list (no shell), and only `playwright test` is ever run.

WHAT IT READS (Playwright only; any other `web_e2e` is exit 2, never a pass):
  qa/requirements.yml        the registry of slice 1; an entry with `feature: true` (a JSON boolean) needs an end-to-end path (an owner-decision is exempt)
  the runners                the files listed under `e2e_paths: runners:` in qa/qa.config.yml (a shell script, a package.json)
  the listings               `playwright test --list --reporter=json`, once with no filter (every test Playwright finds) and once per runner command
A requirement NAMES a test when its id is a whole token of a describe title, a test title or a tag (Playwright reports tags without the `@`). A test Playwright
marks skipped (`test.skip`, `test.fixme`) names nothing. Paths and the runner list come from the `e2e_paths:` section of qa/qa.config.yml (`config`, `baseline`,
`cwd`, `runners`); defaults qa/playwright.config.ts and qa/e2e-unselected-baseline.txt. The listings run from the directory of the playwright config (`qa/`), or
from `cwd` when it is set; a runner file that `cd`s somewhere else needs `cwd` to say so.

WHAT IT REFUSES TO EXECUTE (exit 2, with the reason, never a pass): a command whose arguments are built from a shell variable or a substitution; one that sits in
shell control flow (`if`, `for`, `while`, `case`, a function body); one with anything else on its line before it (`[ ... ] && cmd`, `a || cmd`, `x | cmd`); one after
a heredoc, an `exit` or a `return`; one after a `cd` unless `cwd` is set; a package.json script that pipes or uses `||`. A runner command that is only a listing
(`--list`) runs nothing and is not a runner. If Playwright cannot be run (not installed, a config error, a timeout, no JSON on stdout) the verdict is "could not check" (exit 2).
A `--project` filter is passed through, so Playwright applies it.

THE GATE FAILS WHEN
  1. a feature requirement is named by no active test in the unfiltered listing, or is named only by tests that every runner command leaves out, and is not on the
     baseline (`qa/e2e-unselected-baseline.txt`, a ratchet that may only shrink, with a `# size: N` header and `--base` as in slice 1);
  2. a baseline line names a requirement that is now selected, is not a feature, is an owner-decision, or is not in the registry, or the size header is wrong.

EXIT CODES. 0 clean; 1 findings; 2 COULD NOT CHECK (a registry or path that cannot be read, no runner declared, a non-Playwright runner, a Playwright that cannot be run,
a command refused as unsafe to execute): the project gate runner (project_gates.py) grades 2 as ERROR and 3 as "not applicable", which never fails a run, so a check that
could not look must not say 3; 3 only when the DEFAULT base ref is missing (a project on `main`) and nothing else is wrong, the #1029 precedent where the project chooses.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_requirements as cr  # noqa: E402

E2E_BASELINE = "qa/e2e-unselected-baseline.txt"
DEFAULTS = {"config": "qa/playwright.config.ts", "baseline": E2E_BASELINE}
TIMEOUT = 180
DROP_FLAGS = {"--list", "--ui", "--debug", "--headed", "--last-failed", "--only-changed"}
DROP_WITH_VALUE = {"--reporter"}


# ---- Playwright's own answer -------------------------------------------------------------------------------------------------------------------------


def flatten(data: dict) -> list[dict]:
    """The specs of a `--list --reporter=json` document: {titles: [describe titles..., test title], tags: [...], file, active}. `active` is False for a test
    Playwright marks skipped."""
    found: list[dict] = []

    def walk(suite: dict, chain: list[str], top: bool) -> None:
        title = suite.get("title") or ""
        # the file's own suite is titled with the file name; it is not a describe
        inner = chain if (top and title == os.path.basename(suite.get("file") or title)) else [*chain, title] if title else chain
        for spec in suite.get("specs", []):
            tests = spec.get("tests", [])
            found.append({"titles": [*inner, spec.get("title", "")], "tags": [str(t) for t in spec.get("tags", [])], "file": spec.get("file") or suite.get("file") or "",
                          "active": any(t.get("expectedStatus") != "skipped" for t in tests)})
        for child in suite.get("suites", []):
            walk(child, inner, False)

    for suite in data.get("suites", []):
        walk(suite, [], True)
    return found


class Lister:
    """Runs `npx --no-install playwright test <args> --list --reporter=json` and returns its specs. Subclassed by the selftest, never mocked at the subprocess."""

    def list(self, cwd: Path, args: list[str]) -> tuple[list[dict] | None, str | None]:
        argv = ["npx", "--no-install", "playwright", "test", *args, "--list", "--reporter=json"]
        try:
            done = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            return None, "`npx` is not installed, so Playwright could not be run"
        except subprocess.TimeoutExpired:
            return None, f"Playwright did not finish listing in {TIMEOUT}s"
        try:
            data = json.loads(done.stdout)
        except ValueError:
            return None, f"Playwright printed no JSON listing (exit {done.returncode}): {(done.stderr or done.stdout).strip()[:160]!r}"
        if not isinstance(data, dict):
            return None, f"Playwright printed JSON that is not a listing: {str(data)[:120]!r}"
        # a filter that matches nothing is reported as the error "No tests found" (exit 1) with an empty suite list: that is an empty listing, not a failure
        errors = [e for e in data.get("errors") or [] if "No tests found" not in str(e.get("message", "") if isinstance(e, dict) else e)]
        if errors:
            return None, f"Playwright reported errors: {json.dumps(errors)[:160]}"
        return flatten(data), None


# ---- finding the runner commands ---------------------------------------------------------------------------------------------------------------------


def strip_shell_comments(text: str) -> str:
    """`text` without shell comments: a `#` at the start of a word, outside quotes, ends the line. A comment that says `playwright test` is not a runner."""
    lines = []
    for line in text.split("\n"):
        quote, cut = "", len(line)
        for i, ch in enumerate(line):
            if quote:
                if ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
            elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
                cut = i
                break
        lines.append(line[:cut])
    return "\n".join(lines)


def command_text(source: str, start: int) -> str:
    """The rest of a shell command from `start`: up to a newline, `;`, `&&`, `||` or `|` that is NOT inside a quote (a grep pattern holds `|`)."""
    quote, i, n = "", start, len(source)
    while i < n:
        ch = source[i]
        if quote:
            if ch == "\\" and quote == '"':
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "\n;|" or source.startswith("&&", i):
            break
        i += 1
    return source[start:i]


CLEAN_PREFIX = re.compile(r"^\s*(?:[A-Za-z_][A-Za-z0-9_]*=\S*\s+)*(?:exec\s+)?(?:npx(?:\s+(?:--no-install|-y|--yes))*\s+|pnpm\s+(?:exec\s+)?|yarn\s+(?:run\s+)?|bunx\s+|npm\s+exec\s+(?:--\s+)?)?$")
OPENERS = re.compile(r"(?:^|[;&|(]|\bthen\b|\bdo\b|\belse\b|\bin\b)\s*(if|for|while|until|case|select)\b", re.M)
CLOSERS = re.compile(r"\b(fi|done|esac)\b")


def shell_refusal(prior: str, prefix: str, allow_cd: bool) -> str | None:
    """Why a command found in a shell script cannot be executed safely, or None. `prior` is the text before its line, `prefix` the text before it on its line."""
    if not CLEAN_PREFIX.match(prefix):
        return f"something else runs on the same line before it ({prefix.strip()[:40]!r}): a condition, a pipe or another command"
    if re.search(r"<<-?\s*['\"]?\w", prior):
        return "a heredoc comes before it"
    if re.search(r"(?:^|[;&|(\s])(?:exit|return)\b", prior):
        return "an `exit` or `return` comes before it"
    if len(OPENERS.findall(prior)) - len(CLOSERS.findall(prior)) > 0 or prior.count("{") - prior.count("}") > 0:
        return "it sits inside shell control flow (an `if`, `for`, `while`, `case` or a function body)"
    if not allow_cd and re.search(r"(?:^|[;&|(\s])cd\s", prior):
        return "a `cd` comes before it, so the directory it runs in is unknown (set `cwd` under `e2e_paths:` to say which)"
    return None


def script_refusal(prefix: str, allow_cd: bool) -> str | None:
    """The same for a package.json script string: `a && playwright test` and `a; playwright test` are fine, `||` and a pipe are not."""
    if "||" in prefix or re.search(r"(?<!\|)\|(?!\|)", prefix):
        return "a `||` or a pipe comes before it"
    if re.search(r"(?:^|[;&|(\s])(?:exit|return)\b", prefix):
        return "an `exit` comes before it"
    if not allow_cd and re.search(r"(?:^|[;&|(\s])cd\s", prefix):
        return "a `cd` comes before it, so the directory it runs in is unknown (set `cwd` under `e2e_paths:` to say which)"
    return None


def runner_commands(relpath: str, text: str, allow_cd: bool = False) -> list[dict]:
    """Every `playwright test ...` command in a runner file: {file, args, listing_only, unsafe}. `args` are what to hand Playwright to list the same selection."""
    found = []
    if relpath.endswith(".json"):
        try:
            scripts = [v for v in (json.loads(text).get("scripts") or {}).values() if isinstance(v, str)]
        except ValueError:
            return [{"file": relpath, "args": [], "listing_only": False, "unsafe": "the file is not JSON"}]
        for source in scripts:
            for m in re.finditer(r"\bplaywright\s+test\b", source):
                found.append(_command(relpath, command_text(source, m.end()), script_refusal(source[:m.start()], allow_cd)))
        return found
    source = strip_shell_comments(text).replace("\\\n", " ")
    for m in re.finditer(r"\bplaywright\s+test\b", source):
        line_start = source.rfind("\n", 0, m.start()) + 1
        found.append(_command(relpath, command_text(source, m.end()), shell_refusal(source[:line_start], source[line_start:m.start()], allow_cd)))
    return found


def _command(relpath: str, argument_text: str, refusal: str | None) -> dict:
    command = {"file": relpath, "args": [], "listing_only": False, "unsafe": refusal}
    try:
        tokens = shlex.split(argument_text.rstrip(") "), posix=True)
    except ValueError as exc:
        command["unsafe"] = command["unsafe"] or f"the command cannot be split ({exc})"
        return command
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if token in ("$@", "$*"):
            pass                                   # the runner's own extra arguments: not part of its default selection
        elif "$" in token or "`" in token:
            command["unsafe"] = command["unsafe"] or f"an argument is built from a shell variable or substitution ({token!r})"
        elif token == "--list":
            command["listing_only"] = True
        elif token in DROP_FLAGS:
            pass
        elif token in DROP_WITH_VALUE:
            i += 1
        elif token.startswith("--reporter="):
            pass
        else:
            command["args"].append(token)
        i += 1
    return command


# ---- the gate ----------------------------------------------------------------------------------------------------------------------------------------


def names(spec: dict, rid: str) -> bool:
    """The requirement id is a whole token of a describe title, the test title or a tag (never of the file path)."""
    pattern = re.compile(r"(?<![A-Za-z0-9._-])" + re.escape(rid) + r"(?![A-Za-z0-9._-])")
    return any(pattern.search(piece) for piece in [*spec["titles"], *spec["tags"]])


def settings(root: Path) -> dict:
    config = root / "qa" / "qa.config.yml"
    values: dict = {}
    if config.is_file():
        import qa_config
        values = qa_config.load_section(config, "e2e_paths")
    chosen: dict = {}
    for key, default in DEFAULTS.items():
        value = str(values[key]) if values.get(key) else default
        if not (root / value).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"e2e_paths.{key} {value!r} must be a path inside the project")
        chosen[key] = value
    cwd = str(values["cwd"]) if values.get("cwd") else ""
    chosen["cwd_set"] = bool(cwd)
    chosen["cwd"] = cwd or str(Path(chosen["config"]).parent)
    if not (root / chosen["cwd"]).resolve().is_relative_to(root.resolve()):
        raise ValueError(f"e2e_paths.cwd {chosen['cwd']!r} must be a path inside the project")
    runners = values.get("runners") or []
    runners = [runners] if isinstance(runners, str) else list(runners)
    for value in runners:
        if not (root / str(value)).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"e2e_paths.runners {value!r} must be a path inside the project")
    chosen["runners"] = [str(v) for v in runners]
    return chosen


def check(root: Path, base: list[str] | None = None, lister: Lister | None = None) -> tuple[int, list[str], list[str]]:
    """(exit code, findings, notes). Notes are the reasons a verdict could not be reached."""
    lister = lister or Lister()
    try:
        conf = settings(root)
        registry, _, _ = cr.paths(root)
    except ValueError as exc:
        return 2, [str(exc)], []
    entries, problems = cr.load(root, registry)
    if problems:
        return 2, problems, []
    by_id = {e["id"]: e for e in entries if isinstance(e.get("id"), str)}
    features = [rid for rid, e in by_id.items() if e.get("feature") is True and e.get("status") != "owner-decision"]
    findings: list[str] = []
    notes: list[str] = []
    baseline_path = root / conf["baseline"]
    base_text = baseline_path.read_text(encoding="utf-8-sig") if baseline_path.is_file() else ""
    listed = cr.baseline_lines(base_text)
    size = cr.header_number(base_text, "size")
    if (listed or size is not None) and size != len(listed):
        findings.append(f"{conf['baseline']}: the header says `# size: {size}` but it holds {len(listed)} line(s); edit the number on purpose, where a reviewer sees it")
    if not features and not listed:
        return (1 if findings else 0), findings, notes
    if features and not conf["runners"]:
        return 2, findings, ["no runner files are declared: list them under `e2e_paths: runners:` in qa/qa.config.yml (a shell script or a package.json that runs `playwright test`)"]
    config_yml = root / "qa" / "qa.config.yml"
    declared = re.search(r"^web_e2e:\s*([A-Za-z][A-Za-z0-9-]*)", config_yml.read_text(encoding="utf-8-sig"), re.M) if config_yml.is_file() else None
    if features and declared and declared.group(1) not in ("playwright", "none"):
        return 2, findings, [f"web_e2e is {declared.group(1)}: only Playwright is read (could not check, never a pass)"]
    commands: list[dict] = []
    for runner in (conf["runners"] if features else []):
        path = root / runner
        if not path.is_file():
            return 2, findings + [f"{runner}: listed under e2e_paths: runners but missing"], notes
        found = runner_commands(runner, path.read_text(encoding="utf-8-sig"), allow_cd=conf["cwd_set"])
        if not found:
            notes.append(f"{runner}: no `playwright test` command found in it")
        commands += found
    cwd = root / conf["cwd"]
    everything, why = lister.list(cwd, []) if features else ([], None)      # no feature, nothing to list
    if everything is None:
        return 2, findings, notes + [f"could not list the tests Playwright finds: {why}"]
    selections: list[list[dict]] = []
    uncertain: list[str] = []
    for command in commands:
        if command["listing_only"]:
            notes.append(f"{command['file']}: a `--list` command only lists tests and runs none, so it is not a runner")
        elif command["unsafe"]:
            uncertain.append(f"{command['file']}: not executed, {command['unsafe']}")
        else:
            specs, why = lister.list(cwd, command["args"])
            if specs is None:
                uncertain.append(f"{command['file']}: could not list `{' '.join(command['args'])}`: {why}")
            else:
                selections.append(specs)
    selected_ids: set[str] = set()
    undecided: dict[str, str] = {}
    for rid in features:
        named = [s for s in everything if s["active"] and names(s, rid)]
        if not named:
            if rid not in listed:
                findings.append(f"{rid}: a feature, but no active test names it (an id in a test title, a describe title or a tag): add an end-to-end spec")
            continue
        if any(s["active"] and names(s, rid) for specs in selections for s in specs):
            selected_ids.add(rid)
        elif uncertain:
            undecided[rid] = "; ".join(uncertain)
        elif rid not in listed:
            where = ", ".join(sorted({s["file"] for s in named}))
            findings.append(f"{rid}: named by {len(named)} test(s) in {where}, but no runner selects any of them (Playwright lists none of them for any runner command)")
    for rid in listed:
        entry = by_id.get(rid)
        if entry is None:
            findings.append(f"{conf['baseline']}: {rid} is not in the registry (the list only shrinks: drop it)")
        elif entry.get("feature") is not True or entry.get("status") == "owner-decision":
            findings.append(f"{conf['baseline']}: {rid} is not a feature that needs an end-to-end path (drop it)")
        elif rid in selected_ids:
            findings.append(f"{conf['baseline']}: {rid} is now selected by a runner; drop it from the baseline (the list only shrinks)")
    if base is not None:
        for rid in listed:
            if rid not in base:
                findings.append(f"{conf['baseline']}: {rid} is not in the base branch's baseline; a feature without an end-to-end path cannot be added to it (add the spec)")
    more = [f"{rid}: could not decide ({why})" for rid, why in sorted(undecided.items())]
    if findings:
        return 1, findings, notes + more
    if undecided:
        return 2, findings, notes + more
    return 0, findings, notes


# ---- selftest ---------------------------------------------------------------------------------------------------------------------------------------


def spec(*titles: str, tags: tuple[str, ...] = (), active: bool = True, file: str = "e2e/auth.spec.ts") -> dict:
    return {"titles": list(titles), "tags": list(tags), "file": file, "active": active}


class FakeLister(Lister):
    """Answers a listing from a table keyed by the argument list, and records every call: the plumbing is tested, Playwright's selection is not re-implemented."""

    def __init__(self, table: dict[tuple, list[dict] | str]):
        self.table, self.calls = table, []

    def list(self, cwd: Path, args: list[str]):
        self.calls.append((cwd.name, tuple(args)))
        answer = self.table.get(tuple(args), f"no canned listing for {tuple(args)}")
        return (None, answer) if isinstance(answer, str) else (answer, None)


def stub_npx(directory: Path, body: str) -> None:
    (directory / "npx").write_text("#!/bin/sh\n" + body + "\n")
    (directory / "npx").chmod(0o755)


def selftest(match: str | None = None, real: str | None = None) -> int:
    """`match` runs only the rows whose label contains it (the mutation harness runs each mutant on the one row it names)."""
    failures: list[str] = []

    def entry(rid: str, extra: str = "  feature: true\n", status: str = "done") -> str:
        return f'- id: "{rid}"\n  area: "A"\n  requirement: "text of {rid}"\n  status: "{status}"\n{extra}'

    def project(*entries: str) -> str:
        return f"# rows: {len(entries)}\n" + "".join(entries)

    CONFIG = "e2e_paths:\n  runners:\n    - bin/e2e\n"
    RUN = '#!/bin/sh\nexec npx playwright test --project=chromium --grep "@REQ-001|@smoke" --workers=1 "$@"\n'
    ARGS = ("--project=chromium", "--grep", "@REQ-001|@smoke", "--workers=1")
    NAMED = spec("@REQ-001 signs in", tags=("REQ-001",))
    OTHER = spec("something else")

    def row(label: str, files: dict, table: dict, want_code: int, want: str | None, base: list[str] | None = None) -> FakeLister | None:
        if match and match not in label:
            return None
        files = {"qa/requirements.yml": project(entry("REQ-001")), "qa/test-cases.csv": "Test ID,Status,Source\n", "qa/qa.config.yml": CONFIG, "bin/e2e": RUN,
                 "qa/playwright.config.ts": "export default {};\n", **files}
        lister = FakeLister(table)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, text in files.items():
                if text is None:
                    continue
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding="utf-8")
            code, found, notes = check(root, base, lister)
        joined = "\n".join([*found, *notes])
        if code != want_code or (want is None and found) or (want is not None and want not in joined):
            failures.append(f"{label}: wanted exit {want_code} {want!r}, got exit {code}: {joined[:260]!r}")
        return lister

    ALL = {(): [NAMED, OTHER]}
    selected = {**ALL, ARGS: [NAMED]}
    row("a feature that a runner's listing selects is clean", {}, selected, 0, None)
    row("the @real-signin shape: named in the unfiltered listing, left out of every runner's", {}, {**ALL, ARGS: [OTHER]}, 1, "no runner selects")
    row("a feature that no test names is a finding", {}, {(): [OTHER], ARGS: [OTHER]}, 1, "no active test names it")
    row("a test Playwright marks skipped names nothing", {}, {(): [spec("@REQ-001 signs in", active=False)], ARGS: [OTHER]}, 1, "no active test names it")
    row("a skipped test in a runner's listing does not select the feature", {}, {(): [NAMED], ARGS: [spec("@REQ-001 signs in", active=False)]}, 1, "no runner selects")
    row("a tag names the requirement", {}, {(): [spec("signs in", tags=("REQ-001",))], ARGS: [spec("signs in", tags=("REQ-001",))]}, 0, None)
    row("a describe title names the requirement", {}, {(): [spec("@REQ-001 sign in", "works")], ARGS: [spec("@REQ-001 sign in", "works")]}, 0, None)
    row("an id inside a longer token is not named (REQ-0011 is not REQ-001)", {}, {(): [spec("@REQ-0011 other")], ARGS: [spec("@REQ-0011 other")]}, 1, "no active test names it")
    row("an id only in the file path is not named", {}, {(): [spec("works", file="e2e/REQ-001/login.spec.ts")], ARGS: [OTHER]}, 1, "no active test names it")
    row("the listing arguments are the runner's own, minus --list, --reporter and the runner's extra arguments",
        {"bin/e2e": '#!/bin/sh\nnpx playwright test --reporter=list --grep "@REQ-001" --list-x "$@" --reporter html\n'},
        {(): [NAMED], ("--grep", "@REQ-001", "--list-x"): [NAMED]}, 0, None)
    row("an attached short value is forwarded as written, never re-parsed", {"bin/e2e": "#!/bin/sh\nnpx playwright test -g@qa-image\n"}, {(): [NAMED], ("-g@qa-image",): [OTHER]}, 1,
        "no runner selects")
    row("a --config argument is forwarded for Playwright to read", {"bin/e2e": "#!/bin/sh\nnpx playwright test --config=qa/ci.config.ts\n"}, {(): [NAMED], ("--config=qa/ci.config.ts",): [OTHER]}, 1,
        "no runner selects")
    row("two positional filters are forwarded as written", {"bin/e2e": "#!/bin/sh\nnpx playwright test auth.spec.ts other.spec.ts\n"}, {(): [NAMED], ("auth.spec.ts", "other.spec.ts"): [NAMED]}, 0, None)
    row("a runner that only lists is not a runner", {"bin/e2e": '#!/bin/sh\nnpx playwright test --list --grep "@REQ-001"\n'}, {(): [NAMED]}, 1, "no runner selects")
    row("a comment that says playwright test is not a runner", {"bin/e2e": '#!/bin/sh\n# npx playwright test\nnpx playwright test --grep "@qa-image"   # not @REQ-001\n'},
        {(): [NAMED], ("--grep", "@qa-image"): [OTHER]}, 1, "no runner selects")
    row("a package.json script is a runner", {"qa/package.json": json.dumps({"scripts": {"smoke": "playwright test --grep @qa-image"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"},
        {(): [NAMED], ("--grep", "@qa-image"): [OTHER]}, 1, "no runner selects")
    row("a package.json script after && is fine", {"qa/package.json": json.dumps({"scripts": {"e2e": "npm run build && playwright test --grep @REQ-001"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"},
        {(): [NAMED], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    row("a second runner that selects the feature is enough", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "@qa-image"\nnpx playwright test --grep @REQ-001\n'},
        {(): [NAMED], ("--grep", "@qa-image"): [OTHER], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    # what is refused, with the reason, and never executed
    for label, script, reason in (
        ("a grep built from a shell variable is not executed", '#!/bin/sh\nnpx playwright test --grep "$TAGS"\n', "built from a shell variable"),
        ("a command substitution in an argument is not executed", '#!/bin/sh\nnpx playwright test --grep "$(cat tags)"\n', "built from a shell variable or substitution"),
        ("a command inside an if is not executed", '#!/bin/sh\nif false; then\n  npx playwright test --grep @REQ-001\nfi\n', "shell control flow"),
        ("a command in a function body is not executed", '#!/bin/sh\nrun() {\n  npx playwright test --grep @REQ-001\n}\n', "shell control flow"),
        ("a command after a heredoc is not executed", '#!/bin/sh\ncat <<EOF\nx\nEOF\nnpx playwright test --grep @REQ-001\n', "a heredoc comes before it"),
        ("a command after an exit is not executed", '#!/bin/sh\nexit 0\nnpx playwright test --grep @REQ-001\n', "an `exit` or `return` comes before it"),
        ("a command guarded by && on its line is not executed", '#!/bin/sh\n[ -n "$CI" ] && npx playwright test --grep @REQ-001\n', "something else runs on the same line"),
        ("a command after || on its line is not executed", '#!/bin/sh\ntrue || npx playwright test --grep @REQ-001\n', "something else runs on the same line"),
        ("a command piped into is not executed", '#!/bin/sh\necho x | npx playwright test --grep @REQ-001\n', "something else runs on the same line"),
        ("a command after a cd is not executed unless cwd is set", '#!/bin/sh\ncd somewhere\nnpx playwright test --grep @REQ-001\n', "a `cd` comes before it"),
    ):
        lister = row(label, {"bin/e2e": script}, {(): [NAMED]}, 2, reason)
        if lister is not None and any(call[1] for call in lister.calls):
            failures.append(f"{label}: Playwright was run for a command that must not be executed: {lister.calls}")
    row("a command after a cd is executed when cwd is set", {"bin/e2e": "#!/bin/sh\ncd somewhere\nnpx playwright test --grep @REQ-001\n", "qa/qa.config.yml": "e2e_paths:\n  cwd: qa/e2e\n  runners:\n    - bin/e2e\n"},
        {(): [NAMED], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    row("a package.json script with || before it is not executed", {"qa/package.json": json.dumps({"scripts": {"e2e": "a || playwright test --grep @REQ-001"}}), "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - qa/package.json\n"},
        {(): [NAMED]}, 2, "a `||` or a pipe comes before it")
    row("a refused command does not hide a runner that selects the feature", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "$X"\nnpx playwright test --grep @REQ-001\n'},
        {(): [NAMED], ("--grep", "@REQ-001"): [NAMED]}, 0, None)
    row("a finding is still reported when another feature cannot be decided", {"qa/requirements.yml": project(entry("REQ-001"), entry("REQ-002")), "bin/e2e": '#!/bin/sh\nnpx playwright test --grep "$X"\n'},
        {(): [NAMED]}, 1, "REQ-002: a feature, but no active test names it")
    row("a listing that fails for a runner is exit 2, never a pass", {}, {(): [NAMED], ARGS: "boom"}, 2, "could not list")
    row("the unfiltered listing failing is exit 2, never a pass", {}, {(): "no JSON"}, 2, "could not list the tests Playwright finds")
    lister = row("the cwd of a listing is the config's directory", {}, selected, 0, None)
    if lister is not None and {call[0] for call in lister.calls} != {"qa"}:
        failures.append(f"the cwd of a listing is the config's directory: {lister.calls}")
    row("no runner files declared is exit 2, not a pass", {"qa/qa.config.yml": ""}, {}, 2, "no runner files are declared")
    row("a web_e2e other than playwright is exit 2, not a pass", {"qa/qa.config.yml": "web_e2e: cypress-cucumber\ne2e_paths:\n  runners:\n    - bin/e2e\n"}, {}, 2, "only Playwright is read")
    row("a runner file that is missing is exit 2", {"qa/qa.config.yml": "e2e_paths:\n  runners:\n    - bin/gone\n"}, {}, 2, "listed under e2e_paths: runners but missing")
    row("a runner path outside the project is exit 2", {"qa/qa.config.yml": "e2e_paths:\n  runners:\n    - ../outside\n"}, {}, 2, "inside the project")
    row("a registry with no features lists nothing and needs no runners", {"qa/requirements.yml": project(entry("REQ-001", extra="")), "qa/qa.config.yml": ""}, {}, 0, None)
    row("a runner file with no playwright command says so", {"bin/e2e": "#!/bin/sh\necho hi\n"}, {(): [NAMED]}, 1, "no `playwright test` command found")
    # the baseline ratchet
    base_files = {"qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-001\n"}
    row("a baselined feature that is named nowhere is clean", base_files, {(): [OTHER], ARGS: [OTHER]}, 0, None)
    row("a baseline line for a feature that is now selected is a finding", base_files, selected, 1, "now selected by a runner")
    row("a baseline line for a non-feature is a finding", {"qa/requirements.yml": project(entry("REQ-001", extra="")), **base_files}, {}, 1, "not a feature that needs an end-to-end path")
    row("a baseline line for an unknown requirement is a finding", {"qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-404\n"}, selected, 1, "not in the registry")
    row("a baseline whose size header is wrong is a finding", {"qa/e2e-unselected-baseline.txt": "# size: 4\nREQ-001\n"}, {(): [OTHER], ARGS: [OTHER]}, 1, "header says `# size: 4`")
    row("--base: a baseline line not in the base's baseline is refused", base_files, {(): [OTHER], ARGS: [OTHER]}, 1, "not in the base branch's baseline", base=[])
    row("a requirement that is not a feature needs no spec", {"qa/requirements.yml": project(entry("REQ-001", extra=""))}, {(): [OTHER]}, 0, None)
    row("an owner-decision feature needs no spec", {"qa/requirements.yml": project(entry("REQ-001", status="owner-decision"))}, {(): [OTHER]}, 0, None)

    # the real Lister, against stub executables: what Playwright's output and failures turn into
    def real_lister(label: str, body: str, want_specs: bool, want: str | None) -> None:
        if match and match not in label:
            return
        with tempfile.TemporaryDirectory() as td:
            stub_npx(Path(td), body)
            old = os.environ["PATH"]
            os.environ["PATH"] = td + os.pathsep + old
            try:
                specs, why = Lister().list(Path(td), ["--grep", "x"])
            finally:
                os.environ["PATH"] = old
        if (specs is not None) != want_specs or (want is not None and want not in (why or "")):
            failures.append(f"{label}: wanted specs={want_specs} {want!r}, got {specs!r} {why!r}")

    if not match or "no npx on PATH" in match:
        with tempfile.TemporaryDirectory() as td:
            old = os.environ["PATH"]
            os.environ["PATH"] = td
            try:
                specs, why = Lister().list(Path(td), [])
            finally:
                os.environ["PATH"] = old
        if specs is not None or "`npx` is not installed" not in (why or ""):
            failures.append(f"no npx on PATH is a reason, not a pass: got {specs!r} {why!r}")
    DOC = {"config": {}, "suites": [{"title": "auth.spec.ts", "file": "auth.spec.ts", "specs": [{"title": "@REQ-1 a", "tags": ["REQ-1"], "file": "auth.spec.ts",
           "tests": [{"projectName": "c", "expectedStatus": "passed"}]}], "suites": [{"title": "grp", "specs": [{"title": "b", "tags": [], "file": "auth.spec.ts",
           "tests": [{"projectName": "c", "expectedStatus": "skipped"}]}]}]}], "errors": []}
    real_lister("a real listing is flattened: the file suite is not a describe, a nested describe is, a skipped test is inactive", f"cat <<'JSON'\n{json.dumps(DOC)}\nJSON", True, None)
    real_lister("npx missing is a reason, not a pass", "exit 127", False, "printed no JSON listing")
    real_lister("output that is not JSON is a reason, not a pass", "echo not json; exit 1", False, "printed no JSON listing")
    real_lister("a JSON document with errors is a reason, not a pass", "echo '{\"errors\":[{\"message\":\"bad config\"}],\"suites\":[]}'; exit 1", False, "reported errors")
    real_lister("a listing that matches nothing (error No tests found, exit 1) is an empty listing, not a failure",
                "echo '{\"errors\":[{\"message\":\"Error: No tests found\"}],\"suites\":[]}'; exit 1", True, None)
    real_lister("No tests found next to a real error is still an error", "echo '{\"errors\":[{\"message\":\"Error: No tests found\"},{\"message\":\"bad config\"}],\"suites\":[]}'; exit 1", False,
                "reported errors")
    if not match or "a real listing is flattened" in match:
        got = flatten(DOC)
        want = [{"titles": ["@REQ-1 a"], "tags": ["REQ-1"], "file": "auth.spec.ts", "active": True}, {"titles": ["grp", "b"], "tags": [], "file": "auth.spec.ts", "active": False}]
        if got != want:
            failures.append(f"a real listing is flattened: got {got!r}")
    if real:
        failures += real_battery(Path(real))
    if failures:
        print("check_e2e_paths selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
        return 1
    print("check_e2e_paths selftest: ok (0 failure(s))" + (f"; the real-Playwright battery ran against {real}" if real else ""))
    return 0


def real_battery(modules: Path) -> list[str]:
    """0d's attack battery (#1864 review) against a REAL Playwright: `modules` is a directory that holds node_modules with `playwright` (and `@playwright/test`)."""
    failures: list[str] = []
    entry = lambda rid: f'- id: "{rid}"\n  area: "A"\n  requirement: "t"\n  status: "done"\n  feature: true\n'  # noqa: E731
    SPEC = 'import { test } from "@playwright/test";\ntest("@REQ-001 signs in", async ({ page }) => {});\n'
    BASE = {"qa/requirements.yml": "# rows: 1\n" + entry("REQ-001"), "qa/test-cases.csv": "Test ID,Status,Source\n", "qa/qa.config.yml": "e2e_paths:\n  runners:\n    - bin/e2e\n",
            "bin/e2e": '#!/bin/sh\nnpx playwright test --grep "@REQ-001"\n', "qa/e2e/auth.spec.ts": SPEC, "qa/playwright.config.ts": "export default { testDir: './e2e' };\n"}
    sh = lambda c: "#!/bin/sh\n" + c + "\n"  # noqa: E731
    battery = [
        ("CLI --grep-invert is case-insensitive: @req-001 excludes the @REQ-001 test", 1, {"bin/e2e": sh('npx playwright test --grep-invert "@req-001"')}),
        ("CLI --grep is case-insensitive: @req-001 selects the @REQ-001 test", 0, {"bin/e2e": sh('npx playwright test --grep "@req-001"')}),
        ("two positional files are OR'd", 0, {"bin/e2e": sh("npx playwright test auth.spec.ts other.spec.ts")}),
        ("-g@qa-image (attached value)", 1, {"bin/e2e": sh("npx playwright test -g@qa-image")}),
        ("--config with a grepInvert", 1, {"bin/e2e": sh("npx playwright test --config=ci.config.ts"), "qa/ci.config.ts": "export default { testDir: './e2e', grepInvert: /@REQ-001/ };\n"}),
        ("the only config is playwright.config.js with a grepInvert", 1, {"qa/playwright.config.ts": None, "qa/playwright.config.js": "module.exports = { testDir: './e2e', grepInvert: /@REQ-001/ };\n"}),
        ("config testDir points elsewhere: the spec is never loaded", 1, {"qa/playwright.config.ts": "export default { testDir: './elsewhere' };\n"}),
        ("--list only runs nothing", 1, {"bin/e2e": sh('npx playwright test --list --grep "@REQ-001"')}),
        ("a command after an unconditional exit is refused, not executed: exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "@qa-image"\nexit 0\nnpx playwright test --grep "@REQ-001"')}),
        ("a command in a branch that is never taken is refused, not executed: exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "@qa-image"\nif false; then\n  npx playwright test --grep "@REQ-001"\nfi')}),
        ("a command inside a heredoc is refused, not executed: exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "@qa-image"\ncat <<EOF\nnpx playwright test --grep "@REQ-001"\nEOF')}),
        ("control: a grep that leaves it out", 1, {"bin/e2e": sh('npx playwright test --grep "@qa-image"')}),
        ("control: a grep from a shell variable is exit 2", 2, {"bin/e2e": sh('npx playwright test --grep "$TAGS"')}),
        ("control: a skipped test names nothing", 1, {"qa/e2e/auth.spec.ts": 'import { test } from "@playwright/test";\ntest.skip("@REQ-001 signs in", async () => {});\n'}),
        ("control: a lookbehind grep is Playwright's to read", 1, {"bin/e2e": sh('npx playwright test --grep "(?<=@)qa-image"')}),
    ]
    for label, want, over in battery:
        files = {**BASE, **over}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, text in files.items():
                if text is None:
                    continue
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text)
            (root / "node_modules").symlink_to((modules / "node_modules").resolve())
            code, found, notes = check(root)
        if code != want:
            failures.append(f"real Playwright, {label}: wanted exit {want}, got {code}: {(found + notes)[:2]!r}")
        else:
            print(f"  real ok: {label}")
    return failures


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Every feature requirement has a test that a runner selects, by Playwright's own listing (#1856).")
    parser.add_argument("--root", default=".", help="the project root (default: the current directory)")
    parser.add_argument("--base", metavar="REF", help="refuse a baseline line not in REF's baseline (default: `requirements: base:` in qa/qa.config.yml, else origin/dev)")
    parser.add_argument("--selftest", action="store_true", help="prove each rule fires on a violation and stays silent on conforming input")
    parser.add_argument("--match", metavar="TEXT", help="with --selftest: run only the rows whose label contains TEXT (the mutation harness)")
    parser.add_argument("--real", metavar="DIR", help="with --selftest: also run the attack battery against a real Playwright (DIR holds node_modules)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(args.match, args.real)
    root = Path(args.root).resolve()
    base, unchecked = None, False
    try:
        conf = settings(root)
        ref, explicit = cr.base_ref(root, args.base)
        state, lines = cr.base_baseline(ref, root, baseline=conf["baseline"], default_baseline=E2E_BASELINE)
        if state == "unreadable":
            if explicit:
                print(f"check_e2e_paths: cannot read {ref} (exit 2, not a pass)", file=sys.stderr)
                return 2
            print(f"check_e2e_paths: note: the default base {ref} cannot be read, so growth was not checked; set `base:` under `requirements:` in qa/qa.config.yml")
            unchecked = True
        elif state == "none":
            print(f"check_e2e_paths: note: {ref} holds no registry or baseline, so growth against it was not checked (first adoption)")
        else:
            base = lines
    except ValueError as exc:
        print(f"check_e2e_paths: {exc} (exit 2, not a pass)", file=sys.stderr)
        return 2
    code, found, notes = check(root, base)
    for line in found:
        print(line)
    for note in notes:
        print(f"note: {note}")
    if code == 0 and unchecked:
        print("check_e2e_paths: nothing found, but growth was not checked: exit 3 (a skip, not a pass)")
        return 3
    print(f"check_e2e_paths: {'ok' if code == 0 else 'could not check (exit 2, not a pass)' if code == 2 else str(len(found)) + ' finding(s)'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
