#!/usr/bin/env python3
"""Every feature has an end-to-end path that a runner actually SELECTS (#1856, slice 2 of #1853).

WHY. The owner's rule (#1853): "every feature must have a way to test it end to end". Downstream, a `@real-signin` Playwright spec existed and passed on the
dev runner, but the image runner ran `--grep "@qa-image"`, which never selected it, so nothing flagged that the feature had no end-to-end path where it
mattered. A spec that no runner picks up is not a path: it counts as missing. Slice 1 (check_requirements.py) links a requirement to a manual case; this
links a requirement marked as a feature to a spec that is selected.

    python3 check_e2e_paths.py                    # the gate
    python3 check_e2e_paths.py --base origin/dev  # the base to compare the baseline with (default as in check_requirements.py)
    python3 check_e2e_paths.py --selftest

WHAT IT READS (Playwright only, today; any other `web_e2e` is exit 3, "could not check", never a pass):
  qa/requirements.yml        the registry of slice 1; an entry with `feature: true` (a JSON boolean) needs an end-to-end path (an owner-decision is exempt)
  qa/e2e/**/*.{spec,test}.*  the specs. A spec NAMES a requirement when its id is a whole token of a test title, a describe title, or a `tag` option, so
                             `test("@REQ-001 signs in", ...)`, `test.describe("REQ-001", ...)` and `test(..., { tag: "@REQ-001" }, ...)` all name it. A
                             skipped test (`test.skip`, `test.fixme`) names nothing.
  the runners                the files listed under `e2e_paths: runners:` in qa/qa.config.yml (a shell script, a package.json): every `playwright test ...`
                             command in them, with its `--grep`/`-g`, `--grep-invert`/`-G` and positional file filters. A project whose runners live in
                             other files lists those files.
  qa/playwright.config.ts    the top-level `grep` and `grepInvert`, when they are string or regex literals.
Paths and the runner list come from the `e2e_paths:` section of qa/qa.config.yml (`config`, `specs`, `baseline`, `runners`); defaults qa/playwright.config.ts,
qa/e2e, qa/e2e-unselected-baseline.txt.

THE SEMANTICS RELIED ON are Playwright's documented ones (verified 2026-10-11 against https://playwright.dev/docs/test-cli, /test-annotations and
/api/class-testconfig): `--grep` and `--grep-invert` are regular expressions; a positional argument is a regular expression matched against the full file
path; a tag is an `@` token in a title or a `tag` option and a describe's tag covers its group; the grep expression is tested against a string made of the
project name, the file name, the describe titles, the test title and the tags; `|` is OR. NOT documented, so NOT assumed: a repeated `--grep`, and a
command-line `--grep` combined with a config `grep`. A runner the check cannot read (a grep built from a shell variable, a repeated `--grep`, a pattern with
named groups or lookbehind, a config `testMatch`, `testIgnore` or a project-level `grep`) makes the verdict "could not check" for a requirement that would
otherwise be reported missing: exit 3, a skip, never a pass. A `--project` filter is not applied (a test is selected if some project runs it).

THE GATE FAILS WHEN
  1. a feature requirement is named by no active spec test, or is named only by tests that every readable runner leaves out, and is not on the baseline
     (`qa/e2e-unselected-baseline.txt`, a ratchet that may only shrink, with a `# size: N` header and `--base` as in slice 1);
  2. a baseline line names a requirement that is now selected, is not a feature, is an owner-decision, or is not in the registry, or the size header is wrong.

Exit codes: 0 clean, 1 findings, 2 could not read the registry or a path, 3 could not check (said, and why).
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_requirements as cr  # noqa: E402

E2E_BASELINE = "qa/e2e-unselected-baseline.txt"
DEFAULTS = {"config": "qa/playwright.config.ts", "specs": "qa/e2e", "baseline": E2E_BASELINE}
SPEC = re.compile(r"\.(?:spec|test)\.[cm]?[jt]sx?$")
VALUE_FLAGS = {"--workers", "--retries", "--shard", "--reporter", "--config", "-c", "--timeout", "--output", "--max-failures", "--repeat-each",
               "--browser", "--trace", "--global-timeout", "--tsconfig", "--ui-host", "--ui-port", "--pass-with-no-tests-regex"}
JS_ONLY = re.compile(r"\(\?<[=!A-Za-z]|\\p\{|\\P\{|\\k<|\[\^\]|\(\?[imsx]")      # named groups, lookbehind, unicode classes: not the same in Python


# ---- reading the specs --------------------------------------------------------------------------------------------------------------------------


def blank_comments(text: str) -> str:
    """`text` with every comment replaced by spaces (newlines kept), string and template literals left alone."""
    out, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            out.append(text[i:j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def close_of(text: str, open_at: int) -> int:
    """Index of the `}` that closes the `{` at `open_at`, skipping strings; len(text) when it never closes."""
    depth, i, n = 0, open_at, len(text)
    while i < n:
        ch = text[i]
        if ch in "\"'`":
            j = i + 1
            while j < n and text[j] != ch:
                j += 2 if text[j] == "\\" else 1
            i = j
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return n


CALL = re.compile(r"\b(test|it|describe)((?:\.\w+)*)\s*\(\s*(['\"`])")
BODY = re.compile(r"=>\s*\{|\bfunction\b[^{]*\{")
TAG_OPTION = re.compile(r"\btag\s*:\s*(\[[^\]]*\]|\"[^\"]*\"|'[^']*')")


def parse_tests(text: str, relpath: str) -> list[dict]:
    """The runnable tests in one spec: {titles: [describe titles..., test title], tags: [...], composite: str}. A skipped or fixme test is left out."""
    text = blank_comments(text)
    calls = []
    for m in CALL.finditer(text):
        head, mods, quote = m.group(1), [x for x in m.group(2).split(".") if x], m.group(3)
        start = m.end()
        end = start
        while end < len(text) and text[end] != quote:
            end += 2 if text[end] == "\\" else 1
        title = text[start:end]
        body = BODY.search(text, end)
        options = text[end + 1: body.start()] if body else text[end + 1: end + 200]
        tags = [t for raw in TAG_OPTION.findall(options) for t in re.findall(r"@[\w-]+", raw)]
        group = head == "describe" or "describe" in mods
        skipped = any(x in ("skip", "fixme") for x in mods)
        span = (body.end() - 1, close_of(text, body.end() - 1)) if (body and group) else None
        calls.append({"at": m.start(), "title": title, "tags": tags + re.findall(r"@[\w-]+", title), "group": group, "skipped": skipped, "span": span})
    tests = []
    for call in calls:
        if call["group"]:
            continue
        chain = [c for c in calls if c["group"] and c["span"] and c["span"][0] < call["at"] < c["span"][1]]
        if call["skipped"] or any(c["skipped"] for c in chain):
            continue
        titles = [c["title"] for c in chain] + [call["title"]]
        tags = [t for c in chain for t in c["tags"]] + call["tags"]
        tests.append({"titles": titles, "tags": tags, "file": relpath, "composite": " ".join([relpath, *titles, *tags])})
    return tests


def names(test: dict, rid: str) -> bool:
    """The requirement id is a whole token of a title or a tag (never of the file path)."""
    pattern = re.compile(r"(?<![A-Za-z0-9._-])" + re.escape(rid) + r"(?![A-Za-z0-9._-])")
    return any(pattern.search(piece) for piece in [*test["titles"], *test["tags"]])


# ---- reading the runners --------------------------------------------------------------------------------------------------------------------------


def js_regex(source: str, flags: str = "") -> tuple[re.Pattern | None, str | None]:
    """(compiled, None) or (None, why it cannot be read): only what Python's `re` reads the same way as JavaScript."""
    if JS_ONLY.search(source):
        return None, f"the pattern {source!r} uses syntax that JavaScript and Python read differently"
    if set(flags) - set("gi"):
        return None, f"the regex flags {flags!r} are not read"
    try:
        return re.compile(source, re.I if "i" in flags else 0), None
    except re.error as exc:
        return None, f"the pattern {source!r} is not a regular expression Python reads ({exc})"


def runner_commands(relpath: str, text: str) -> list[dict]:
    """Every `playwright test ...` command in a runner file: {file, grep, invert, files, open, unreadable}."""
    sources = []
    if relpath.endswith(".json"):
        try:
            sources = [v for v in (json.loads(text).get("scripts") or {}).values() if isinstance(v, str)]
        except ValueError:
            return [{"file": relpath, "unreadable": "the file is not JSON", "grep": [], "invert": [], "files": [], "open": False}]
    else:
        sources = [strip_shell_comments(text).replace("\\\n", " ")]
    found = []
    for source in sources:
        for m in re.finditer(r"\bplaywright\s+test\b", source):
            found.append(_command(relpath, command_text(source, m.end())))
    return found


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


def _command(relpath: str, argument_text: str) -> dict:
    command = {"file": relpath, "grep": [], "invert": [], "files": [], "open": False, "unreadable": None}
    try:
        tokens = shlex.split(argument_text.rstrip(") "), posix=True)
    except ValueError as exc:
        command["unreadable"] = f"the command cannot be split ({exc})"
        return command
    i = 0
    while i < len(tokens):
        token = tokens[i]
        flag, equals, value = token.partition("=") if token.startswith("--") else (token, "", "")
        take = lambda: (tokens[i + 1] if i + 1 < len(tokens) else "")  # noqa: E731
        if token in ("$@", "$*"):
            command["open"] = True
        elif flag in ("--grep", "-g", "--grep-invert", "-G"):
            raw = value if equals else take()
            i += 0 if equals else 1
            if "$" in raw:
                command["unreadable"] = f"{flag} is built from a shell variable ({raw!r})"
            (command["grep"] if flag in ("--grep", "-g") else command["invert"]).append(raw)
        elif flag == "--project":
            i += 0 if equals else 1
        elif flag in VALUE_FLAGS:
            i += 0 if equals else 1
        elif token.startswith("-"):
            pass
        elif "$" in token:
            command["unreadable"] = f"a file filter is built from a shell variable ({token!r})"
        else:
            command["files"].append(token)
        i += 1
    if len(command["grep"]) > 1 or len(command["invert"]) > 1:
        command["unreadable"] = "a repeated --grep or --grep-invert (Playwright does not document how repeats combine)"
    return command


def config_filters(text: str) -> dict:
    """{grep, invert, unreadable}: the top-level `grep`/`grepInvert` of a playwright.config, when they are literals."""
    text = blank_comments(text)
    out: dict = {"grep": None, "invert": None, "unreadable": []}
    projects = re.search(r"\bprojects\s*:\s*\[", text)
    inside = ""
    if projects:
        depth, i = 0, projects.end() - 1
        while i < len(text):
            depth += (text[i] == "[") - (text[i] == "]")
            if depth == 0:
                break
            i += 1
        inside, text = text[projects.end(): i], text[:projects.start()] + text[i + 1:]
    if re.search(r"\b(grep|grepInvert|testMatch|testIgnore)\s*:", inside):
        out["unreadable"].append("a project in the config sets grep, grepInvert, testMatch or testIgnore, which is not read")
    if re.search(r"\b(testMatch|testIgnore)\s*:", text):
        out["unreadable"].append("the config sets testMatch or testIgnore, which is not read")
    for key, slot in (("grepInvert", "invert"), ("grep", "grep")):
        m = re.search(r"\b" + key + r"\s*:\s*(.+)", text)
        if not m:
            continue
        value = m.group(1).strip()
        regex = re.match(r"/((?:[^/\\\n]|\\.)+)/([a-z]*)(?=\s*(?:[,}\]]|$))", value)
        string = re.match(r"([\"'])((?:[^\\\n]|\\.)*?)\1(?=\s*(?:[,}\]]|$))", value)
        if regex:
            out[slot] = (regex.group(1), regex.group(2))
        elif string:
            out[slot] = (string.group(2), "")
        else:
            out["unreadable"].append(f"the config's {key} ({value[:40]!r}) is not a string or regex literal")
    return out


def selects(command: dict, config: dict, test: dict, root: Path) -> tuple[bool, str | None]:
    """(selected, why it could not be decided). The CLI filter and the config filter of the same kind are not combined (undocumented)."""
    if command["unreadable"]:
        return False, command["unreadable"]
    if command["grep"] and config["grep"]:
        return False, "a command-line --grep with a config grep (Playwright does not document how they combine)"
    if command["invert"] and config["invert"]:
        return False, "a command-line --grep-invert with a config grepInvert (Playwright does not document how they combine)"
    absolute = str((root / test["file"]).resolve())
    for pattern in command["files"]:
        compiled, why = js_regex(pattern)
        if compiled is None:
            return False, why
        if not compiled.search(absolute):
            return False, None
    filters = []
    for raw, config_value, invert in ((command["grep"], config["grep"], False), (command["invert"], config["invert"], True)):
        source = (raw[0], "") if raw else config_value
        if source:
            filters.append((source, invert))
    for (source, flags), invert in filters:
        compiled, why = js_regex(source, flags)
        if compiled is None:
            return False, why
        if bool(compiled.search(test["composite"])) == invert:
            return False, None
    return True, None


# ---- the gate ----------------------------------------------------------------------------------------------------------------------------------------


def settings(root: Path) -> dict:
    config = root / "qa" / "qa.config.yml"
    values: dict = {}
    if config.is_file():
        import qa_config
        values = qa_config.load_section(config, "e2e_paths")
    chosen = {}
    for key, default in DEFAULTS.items():
        value = str(values[key]) if values.get(key) else default
        if not (root / value).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"e2e_paths.{key} {value!r} must be a path inside the project")
        chosen[key] = value
    runners = values.get("runners") or []
    runners = [runners] if isinstance(runners, str) else list(runners)
    for value in runners:
        if not (root / str(value)).resolve().is_relative_to(root.resolve()):
            raise ValueError(f"e2e_paths.runners {value!r} must be a path inside the project")
    chosen["runners"] = [str(v) for v in runners]
    return chosen


def check(root: Path, base: list[str] | None = None) -> tuple[int, list[str], list[str]]:
    """(exit code, findings, notes). Notes are the reasons a verdict could not be reached."""
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
    if not conf["runners"]:
        return 3, findings, ["no runner files are declared: list them under `e2e_paths: runners:` in qa/qa.config.yml (a shell script or a package.json that runs `playwright test`)"]
    config_yml = root / "qa" / "qa.config.yml"
    declared = re.search(r"^web_e2e:\s*([A-Za-z][A-Za-z0-9-]*)", config_yml.read_text(encoding="utf-8-sig"), re.M) if config_yml.is_file() else None
    if declared and declared.group(1) not in ("playwright", "none"):
        return 3, findings, [f"web_e2e is {declared.group(1)}: only Playwright's runner filters are read (could not check, never a pass)"]
    tests: list[dict] = []
    for spec in sorted((root / conf["specs"]).rglob("*")):
        if spec.is_file() and SPEC.search(spec.name):
            tests += parse_tests(spec.read_text(encoding="utf-8-sig"), str(spec.relative_to(root)))
    config_file = root / conf["config"]
    config = config_filters(config_file.read_text(encoding="utf-8-sig")) if config_file.is_file() else {"grep": None, "invert": None, "unreadable": []}
    commands: list[dict] = []
    for runner in conf["runners"]:
        path = root / runner
        if not path.is_file():
            return 2, findings + [f"{runner}: listed under e2e_paths: runners but missing"], notes
        found = runner_commands(runner, path.read_text(encoding="utf-8-sig"))
        if not found:
            notes.append(f"{runner}: no `playwright test` command found in it")
        commands += found
    uncertain: dict[str, str] = {}
    selected_ids: set[str] = set()
    for rid in features:
        named = [t for t in tests if names(t, rid)]
        if not named:
            if rid not in listed:
                findings.append(f"{rid}: a feature, but no active spec test names it (an id in a test title, a describe title or a `tag` option): add an end-to-end spec")
            continue
        why_not: list[str] = []
        picked = False
        for test in named:
            for command in commands:
                ok, why = selects(command, config, test, root)
                if ok:
                    picked = True
                elif why:
                    why_not.append(f"{command['file']}: {why}")
        for reason in config["unreadable"]:
            why_not.append(f"{conf['config']}: {reason}")
        if picked:
            selected_ids.add(rid)
        elif why_not:
            uncertain[rid] = "; ".join(sorted(set(why_not)))
        elif rid not in listed:
            where = ", ".join(sorted({t["file"] for t in named}))
            findings.append(f"{rid}: named by {len(named)} spec test(s) in {where}, but no runner selects any of them (the runners' --grep/--grep-invert and file filters leave them out)")
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
    if findings:
        return 1, findings, notes + [f"{rid}: could not decide ({why})" for rid, why in sorted(uncertain.items())]
    if uncertain:
        return 3, findings, notes + [f"{rid}: could not decide ({why})" for rid, why in sorted(uncertain.items())]
    return 0, findings, notes


# ---- selftest ---------------------------------------------------------------------------------------------------------------------------------------


def selftest(match: str | None = None) -> int:
    """`match` runs only the scenario rows whose label contains it (the mutation harness runs each mutant on the one row it names)."""
    failures: list[str] = []

    def entry(rid: str, extra: str = '  feature: true\n', status: str = "done") -> str:
        return f'- id: "{rid}"\n  area: "A"\n  requirement: "text of {rid}"\n  status: "{status}"\n{extra}'

    def project(*entries: str) -> str:
        return f"# rows: {len(entries)}\n" + "".join(entries)

    CONFIG = 'e2e_paths:\n  runners:\n    - bin/e2e\n'
    SPEC_OK = 'import { test } from "@playwright/test";\ntest("@REQ-001 signs in", async ({ page }) => {\n  await page.goto("/");\n});\n'
    RUN = '#!/bin/sh\nexec npx playwright test --project=chromium --grep "@REQ-001|@smoke" --workers=1 "$@"\n'

    def scenario(label: str, files: dict[str, str], want_code: int, want: str | None, base: list[str] | None = None) -> None:
        if match and match not in label:
            return
        files = {"qa/requirements.yml": project(entry("REQ-001")), "qa/test-cases.csv": "Test ID,Status,Source\n", "qa/qa.config.yml": CONFIG, "bin/e2e": RUN,
                 "qa/e2e/auth.spec.ts": SPEC_OK, "qa/playwright.config.ts": "export default defineConfig({ testDir: './e2e' });\n", **files}
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for name, text in files.items():
                if text is None:
                    continue
                (root / name).parent.mkdir(parents=True, exist_ok=True)
                (root / name).write_text(text, encoding="utf-8")
            code, found, notes = check(root, base)
        joined = "\n".join([*found, *notes])
        ok = code == want_code and (not found if want is None else want in joined)
        if not ok:
            failures.append(f"{label}: wanted exit {want_code} {want!r}, got exit {code}: {joined[:240]!r}")

    scenario("a feature whose tagged spec is selected by a runner is clean", {}, 0, None)
    scenario("a feature with no spec naming it is a finding", {"qa/e2e/auth.spec.ts": 'test("@REQ-009 other", async () => {});\n'}, 1, "no active spec test names it")
    scenario("the @real-signin shape: the spec is tagged, the runner's grep leaves it out", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "@qa-image"\n'}, 1,
             "no runner selects any of them")
    scenario("a --grep-invert that excludes the tag leaves the spec out", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep-invert "@REQ-001"\n'}, 1, "no runner selects")
    scenario("a --grep-invert for another tag leaves it selected", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep-invert "@root"\n'}, 0, None)
    scenario("no --grep at all selects everything", {"bin/e2e": '#!/bin/sh\nnpx playwright test\n'}, 0, None)
    scenario("OR in the grep selects either tag", {"bin/e2e": '#!/bin/sh\nnpx playwright test -g "@x|@REQ-001"\n'}, 0, None)
    scenario("a positional file filter that does not match the spec leaves it out", {"bin/e2e": '#!/bin/sh\nnpx playwright test billing\n'}, 1, "no runner selects")
    scenario("a positional file filter that matches the spec file selects it", {"bin/e2e": '#!/bin/sh\nnpx playwright test auth\n'}, 0, None)
    scenario("a second runner that selects the spec is enough", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "@qa-image"\nnpx playwright test --grep @REQ-001\n'}, 0, None)
    scenario("a comment that says playwright test is not a runner (it would select everything)", {"bin/e2e": '#!/bin/sh\n# npx playwright test\nnpx playwright test --grep "@qa-image"   # not @REQ-001\n'}, 1,
             "no runner selects")
    scenario("a # inside a quoted grep is part of the pattern, not a comment", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "#x|@REQ-001"\n'}, 0, None)
    scenario("a line continuation joins the command", {"bin/e2e": '#!/bin/sh\nnpx playwright test \\\n  --grep "@REQ-001"\n'}, 0, None)
    scenario("a package.json script is a runner", {"qa/package.json": json.dumps({"scripts": {"smoke": "playwright test --grep @qa-image"}}),
             "qa/qa.config.yml": 'e2e_paths:\n  runners:\n    - qa/package.json\n'}, 1, "no runner selects")
    scenario("a grep built from a shell variable cannot be read: exit 3, not a pass and not a finding", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep "$FILTER"\n'}, 3,
             "built from a shell variable")
    scenario("a repeated --grep cannot be read (undocumented)", {"bin/e2e": '#!/bin/sh\nnpx playwright test --grep @a --grep @b\n'}, 3, "repeated --grep")
    scenario("a config grep with a command-line grep cannot be combined (undocumented)", {"qa/playwright.config.ts": "export default defineConfig({ grep: /@x/ });\n"}, 3,
             "does not document how they combine")
    scenario("a config grep alone is applied: it leaves the spec out", {"qa/playwright.config.ts": "export default defineConfig({ grep: /@x/ });\n",
             "bin/e2e": '#!/bin/sh\nnpx playwright test\n'}, 1, "no runner selects")
    scenario("a config grepInvert alone is applied", {"qa/playwright.config.ts": "export default defineConfig({ grepInvert: /@REQ-001/ });\n",
             "bin/e2e": '#!/bin/sh\nnpx playwright test\n'}, 1, "no runner selects")
    scenario("a project-level grep in the config cannot be read", {"qa/playwright.config.ts": "export default defineConfig({ projects: [{ name: 'a', grep: /@x/ }] });\n",
             "bin/e2e": '#!/bin/sh\nnpx playwright test --grep "@qa-image"\n'}, 3, "project in the config")
    scenario("a finding is still reported when another runner cannot be read", {"qa/e2e/auth.spec.ts": 'test("@REQ-009 other", async () => {});\n',
             "bin/e2e": '#!/bin/sh\nnpx playwright test --grep "$X"\n'}, 1, "no active spec test names it")
    scenario("a skipped test names nothing", {"qa/e2e/auth.spec.ts": 'test.skip("@REQ-001 signs in", async () => {});\n'}, 1, "no active spec test names it")
    scenario("a fixme test names nothing", {"qa/e2e/auth.spec.ts": 'test.fixme("@REQ-001 signs in", async () => {});\n'}, 1, "no active spec test names it")
    scenario("a skipped describe skips every test inside it", {"qa/e2e/auth.spec.ts": 'test.describe.skip("group", () => {\n test("@REQ-001 in", async () => {});\n});\n'}, 1,
             "no active spec test names it")
    scenario("a describe title tag covers the tests inside it", {"qa/e2e/auth.spec.ts": 'test.describe("@REQ-001 sign in", () => {\n test("works", async () => {});\n});\n'}, 0, None)
    scenario("a describe tag option covers the tests inside it", {"qa/e2e/auth.spec.ts": 'test.describe("sign in", { tag: "@REQ-001" }, () => {\n test("works", async () => {});\n});\n'}, 0, None)
    scenario("a tag option array on a test names it", {"qa/e2e/auth.spec.ts": 'test("works", { tag: ["@a", "@REQ-001"] }, async ({ page }) => {});\n'}, 0, None)
    scenario("an id inside a longer token is not named (REQ-0011 is not REQ-001)", {"qa/e2e/auth.spec.ts": 'test("@REQ-0011 other", async () => {});\n'}, 1,
             "no active spec test names it")
    scenario("the id in a comment names nothing", {"qa/e2e/auth.spec.ts": '// @REQ-001 todo\ntest("other", async () => {});\n'}, 1, "no active spec test names it")
    scenario("an id only in the file path is not named", {"qa/e2e/REQ-001.spec.ts": 'test("works", async () => {});\n', "qa/e2e/auth.spec.ts": 'test("x", async () => {});\n'}, 1,
             "no active spec test names it")
    scenario("a requirement that is not a feature needs no spec", {"qa/requirements.yml": project(entry("REQ-001", extra=""))}, 0, None)
    scenario("an owner-decision feature needs no spec", {"qa/requirements.yml": project(entry("REQ-001", status="owner-decision"))}, 0, None)
    scenario("a baselined feature with no spec is clean", {"qa/e2e/auth.spec.ts": 'test("x", async () => {});\n', "qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-001\n"}, 0, None)
    scenario("a baseline line for a feature that is now selected is a finding", {"qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-001\n"}, 1, "now selected by a runner")
    scenario("a baseline line for a non-feature is a finding", {"qa/requirements.yml": project(entry("REQ-001", extra="")), "qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-001\n"}, 1,
             "not a feature that needs an end-to-end path")
    scenario("a baseline line for an unknown requirement is a finding", {"qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-404\n"}, 1, "not in the registry")
    scenario("a baseline whose size header is wrong is a finding", {"qa/e2e/auth.spec.ts": 'test("x", async () => {});\n', "qa/e2e-unselected-baseline.txt": "# size: 4\nREQ-001\n"}, 1,
             "header says `# size: 4`")
    scenario("--base: a baseline line not in the base's baseline is refused", {"qa/e2e/auth.spec.ts": 'test("x", async () => {});\n',
             "qa/e2e-unselected-baseline.txt": "# size: 1\nREQ-001\n"}, 1, "not in the base branch's baseline", base=[])
    scenario("no runner files declared is exit 3, not a pass", {"qa/qa.config.yml": ""}, 3, "no runner files are declared")
    scenario("a runner file that is missing is exit 2", {"qa/qa.config.yml": 'e2e_paths:\n  runners:\n    - bin/gone\n'}, 2, "listed under e2e_paths: runners but missing")
    scenario("a runner path outside the project is exit 2", {"qa/qa.config.yml": 'e2e_paths:\n  runners:\n    - ../outside\n'}, 2, "inside the project")
    scenario("a registry with no features needs no runners", {"qa/requirements.yml": project(entry("REQ-001", extra="")), "qa/qa.config.yml": ""}, 0, None)
    scenario("a web_e2e other than playwright is exit 3, not a pass", {"qa/qa.config.yml": "web_e2e: cypress-cucumber\ne2e_paths:\n  runners:\n    - bin/e2e\n"}, 3,
             "only Playwright's runner filters are read")
    scenario("a runner file with no playwright command says so", {"bin/e2e": "#!/bin/sh\necho hi\n"}, 1, "no `playwright test` command found")
    scenario("a skipped title mentioned only in a template string still parses the rest", {"qa/e2e/auth.spec.ts": 'const a = `x // not a comment`;\ntest("@REQ-001 ok", async () => {});\n'}, 0, None)
    if failures:
        print("check_e2e_paths selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
        return 1
    print("check_e2e_paths selftest: ok (0 failure(s))")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Every feature requirement has a spec that a runner selects (#1856).")
    parser.add_argument("--root", default=".", help="the project root (default: the current directory)")
    parser.add_argument("--base", metavar="REF", help="refuse a baseline line not in REF's baseline (default: `requirements: base:` in qa/qa.config.yml, else origin/dev)")
    parser.add_argument("--selftest", action="store_true", help="prove each rule fires on a violation and stays silent on conforming input")
    parser.add_argument("--match", metavar="TEXT", help="with --selftest: run only the scenario rows whose label contains TEXT (the mutation harness)")
    args = parser.parse_args(argv)
    if args.selftest:
        return selftest(args.match)
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
    print(f"check_e2e_paths: {'ok' if code == 0 else 'could not check (exit 3, not a pass)' if code == 3 else 'could not read an input' if code == 2 else str(len(found)) + ' finding(s)'}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
