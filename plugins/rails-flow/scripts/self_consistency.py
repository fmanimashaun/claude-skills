#!/usr/bin/env python3
"""Catch code in THIS project that does not do what the project claims it does.

WHY
---
Ordinary review asks "is this code correct?". The defects that survive review came
from a different question:

    Does this code do what its own docs, config, comments and project rules claim?

Correct-looking code passes the first and fails the second, and the author cannot
see it -- they read the claim and the code as one intention. The `code-review`
skill (bundled in rails-stack) names the classes; this script mechanises the four
that need no judgement, because a rule left in prose gets violated again.

RULES
-----
  swallowed-exception   `rescue nil` / an empty rescue -- failure becomes silence
  swallowed-verdict     `|| true` on a verification command -- the gate cannot fail
  assertion-free-spec   an example that runs code but asserts nothing
  dead-env-var          a key in .env.example that nothing reads   (--all only)

Deliberately narrow. Every rule is mechanical, so a finding is always real. A
linter that false-positives gets disabled and then catches nothing, so classes
needing judgement (`unenforced-documented-step`,
`carve-out-without-negative-test`) stay with the reviewer, not here.

USAGE
-----
    python3 self_consistency.py --file app/models/user.rb   # per-file (hook)
    python3 self_consistency.py --all                       # whole repo
    python3 self_consistency.py --selftest                  # prove the rules work

Exit 0 clean, 1 findings, 2 usage error. Stdlib only -- a Rails repo must not need
a pip install to review itself.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

SKIP_DIRS = {
    ".git", "node_modules", "tmp", "log", "coverage", "public", "vendor",
    ".bundle", "storage", ".venv", "venv", "__pycache__", ".yarn", "dist",
}

# Commands whose verdict is load-bearing. Softening one of these is what made a
# release gate unable to block upstream (#151), which is why the pattern is here.
VERIFY = (
    r"(?:rspec|rubocop|brakeman|bundler-audit|bundle\s+exec|rake\s|rails\s+test"
    r"|npm\s+(?:test|run\s+lint)|yarn\s+(?:test|lint)|pytest|erblint|erb_lint"
    r"|standardrb|zeitwerk:check|importmap\s+audit)"
)


@dataclass(frozen=True)
class Finding:
    rule: str
    path: str
    line: int
    message: str

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"[{self.rule}] {where} -- {self.message}"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def walk(root: Path, suffixes: tuple[str, ...]) -> list[Path]:
    """Files under root, pruning SKIP_DIRS during traversal (not after)."""
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if name.endswith(suffixes):
                out.append(Path(dirpath) / name)
    return sorted(out)


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def strip_ruby_comment(line: str) -> str:
    """Blank a trailing `#` comment, ignoring `#` inside a string literal.

    Not `line.split('#')[0]`: `"#{interp}"` and `"#hash"` are string content, and
    cutting there would both miss real code and mangle it.
    """
    in_s = in_d = False
    i = 0
    while i < len(line):
        c = line[i]
        if c == "\\" and (in_s or in_d):
            i += 2
            continue
        if c == "'" and not in_d:
            in_s = not in_s
        elif c == '"' and not in_s:
            in_d = not in_d
        elif c == "#" and not in_s and not in_d:
            return line[:i]
        i += 1
    return line


# --------------------------------------------------------------------------
# swallowed-exception   (code-review class: gate-that-cannot-fail)
# --------------------------------------------------------------------------

_RESCUE_NIL = re.compile(r"\brescue\s+nil\b")
_RESCUE_OPEN = re.compile(r"^\s*rescue\b[^#]*$")


def check_swallowed_exception(path: Path, text: str, root: Path) -> list[Finding]:
    if path.suffix != ".rb":
        return []
    findings: list[Finding] = []
    where = rel(path, root)
    lines = text.splitlines()

    for i, raw in enumerate(lines, start=1):
        code = strip_ruby_comment(raw)
        if _RESCUE_NIL.search(code):
            findings.append(Finding(
                "swallowed-exception", where, i,
                "`rescue nil` turns every failure into silence -- rescue the specific "
                "error and handle it, or let it raise",
            ))
            continue
        # `rescue` on its own line whose block body is empty -> swallows.
        if _RESCUE_OPEN.match(code) and "=>" not in code and "rescue nil" not in code:
            body_is_empty = True
            for follow in lines[i:]:
                stripped = strip_ruby_comment(follow).strip()
                if not stripped:
                    continue
                body_is_empty = stripped in {"end", "}"}
                break
            if body_is_empty:
                findings.append(Finding(
                    "swallowed-exception", where, i,
                    "empty `rescue` body -- the error is discarded with no handling, "
                    "log or re-raise",
                ))
    return findings


# --------------------------------------------------------------------------
# swallowed-verdict   (code-review class: gate-that-cannot-fail)
# --------------------------------------------------------------------------

_SOFTENED = re.compile(VERIFY + r"[^\n|&]*(?:\|\|\s*(?:true|:|echo\b)|;\s*true\b)")


def check_swallowed_verdict(path: Path, text: str, root: Path) -> list[Finding]:
    if not path.name.endswith((".sh", ".bash", ".yml", ".yaml")) and path.suffix != "":
        return []
    findings: list[Finding] = []
    where = rel(path, root)
    for i, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0] if raw.lstrip().startswith("#") else raw
        match = _SOFTENED.search(line)
        if match:
            findings.append(Finding(
                "swallowed-verdict", where, i,
                f"`{match.group(0).strip()}` -- a verification command whose failure "
                f"cannot fail the build. A guard decides whether to RUN a check; it "
                f"must never soften the verdict",
            ))
    return findings


# --------------------------------------------------------------------------
# assertion-free-spec   (code-review class: gate-that-cannot-fail)
# --------------------------------------------------------------------------

_EXAMPLE_OPEN = re.compile(r"^(\s*)(?:it|specify|example)\b[^#]*\bdo\b")
_ASSERTS = re.compile(
    r"\b(?:expect|is_expected|should|should_not|assert\w*|refute\w*|"
    r"raise_error|have_\w+|be_\w+|match_array|change\s*[({]|"
    r"it_behaves_like|include_examples|satisfy|throw_symbol|"
    r"have_enqueued_job|have_broadcasted_to)\b"
)
# A body doing nothing yet is a deliberate placeholder, not a false claim.
_PENDING = re.compile(r"\b(?:pending|skip|xit)\b")


def check_assertion_free_spec(path: Path, text: str, root: Path) -> list[Finding]:
    name = path.name
    if not name.endswith("_spec.rb") and not name.endswith("_test.rb"):
        return []
    findings: list[Finding] = []
    where = rel(path, root)
    lines = text.splitlines()

    for i, raw in enumerate(lines):
        opened = _EXAMPLE_OPEN.match(strip_ruby_comment(raw))
        if not opened:
            continue
        indent = len(opened.group(1))
        body: list[str] = []
        for follow in lines[i + 1:]:
            code = strip_ruby_comment(follow)
            stripped = code.strip()
            if stripped in {"end", "end)"} and (len(code) - len(code.lstrip())) <= indent:
                break
            body.append(code)
        blob = "\n".join(body)
        if not blob.strip():
            continue  # `it "..." do end` -- an empty placeholder, not a false claim
        if _PENDING.search(blob) or _ASSERTS.search(blob):
            continue
        findings.append(Finding(
            "assertion-free-spec", where, i + 1,
            "this example runs code but asserts nothing -- it passes whatever the code "
            "does, so it proves nothing and cannot fail",
        ))
    return findings


# --------------------------------------------------------------------------
# dead-env-var   (code-review class: dead-declaration)   -- repo-wide
# --------------------------------------------------------------------------

_ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Z][A-Z0-9_]{2,})\s*=")


def check_dead_env_vars(root: Path) -> tuple[list[Finding], int]:
    """A key documented in .env.example that nothing in the repo reads."""
    samples = [p for p in walk(root, (".env.example", ".env.sample", ".env.template"))]
    samples += [root / name for name in (".env.example", ".env.sample")
                if (root / name).is_file()]
    samples = sorted({p for p in samples if p.is_file()})
    if not samples:
        return [], 0

    # Search every text file, not just Ruby: a key may be read by a Dockerfile,
    # a Kamal deploy.yml, a JS bundle, or a shell script. Narrowing the haystack
    # is how this rule would produce false positives.
    haystack: list[str] = []
    for path in walk(root, (".rb", ".erb", ".yml", ".yaml", ".sh", ".bash", ".js",
                            ".ts", ".jsx", ".tsx", ".json", ".rake", ".ru", ".md",
                            ".env", ".tf", ".conf", "Dockerfile", "Procfile",
                            "Gemfile", "Rakefile", ".gemspec")):
        if path in samples:
            continue
        haystack.append(read(path))
    blob = "\n".join(haystack)

    findings: list[Finding] = []
    examined = 0
    for sample in samples:
        where = rel(sample, root)
        for i, raw in enumerate(read(sample).splitlines(), start=1):
            if raw.lstrip().startswith("#"):
                continue
            match = _ENV_KEY.match(raw)
            if not match:
                continue
            key = match.group(1)
            examined += 1
            if re.search(rf"\b{re.escape(key)}\b", blob):
                continue
            findings.append(Finding(
                "dead-env-var", where, i,
                f"{key} is documented here but nothing in the project reads it -- "
                f"wire it up or delete it; a documented setting that does nothing "
                f"gets copied into deploys and read as fact",
            ))
    return findings, examined


# --------------------------------------------------------------------------
# drivers
# --------------------------------------------------------------------------

PER_FILE = (check_swallowed_exception, check_swallowed_verdict, check_assertion_free_spec)

FILE_SUFFIXES = (".rb", ".erb", ".sh", ".bash", ".yml", ".yaml", ".rake")


def check_file(path: Path, root: Path) -> list[Finding]:
    if not path.is_file():
        return []
    text = read(path)
    out: list[Finding] = []
    for rule in PER_FILE:
        out.extend(rule(path, text, root))
    return out


def check_all(root: Path) -> tuple[list[Finding], dict[str, int]]:
    files = walk(root, FILE_SUFFIXES)
    findings: list[Finding] = []
    for path in files:
        findings.extend(check_file(path, root))
    env_findings, env_keys = check_dead_env_vars(root)
    findings.extend(env_findings)
    return findings, {"files": len(files), "env keys": env_keys}


def report(findings: list[Finding], coverage: dict[str, int], *, as_json: bool) -> int:
    if as_json:
        print(json.dumps({"findings": [asdict(f) for f in findings],
                          "coverage": coverage}, indent=2))
        return 1 if findings else 0

    # Print coverage even when clean: "no findings" over input never read is worse
    # than no check at all, because it reads as a pass.
    if coverage:
        parts = [f"{v} {k if v != 1 else k.rstrip('s')}" for k, v in coverage.items()]
        print("examined " + ", ".join(parts))
    for finding in findings:
        print(str(finding), file=sys.stderr)
    if findings:
        print(f"\n{len(findings)} self-consistency finding(s).", file=sys.stderr)
        return 1
    print("no self-consistency findings.")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="check one file (per-file rules only)")
    group.add_argument("--all", action="store_true", help="check the whole project")
    group.add_argument("--selftest", action="store_true",
                       help="prove every rule fires AND stays silent")
    parser.add_argument("--root", default=".", help="project root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args(argv[1:])

    if args.selftest:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        try:
            from self_consistency_selftest import run_selftest  # type: ignore
        except ImportError:
            print("self_consistency_selftest.py is not beside this script; the "
                  "selftest ships with the plugin and should be.", file=sys.stderr)
            return 2
        return run_selftest()

    root = Path(args.root).resolve()
    if not root.is_dir():
        parser.error(f"--root is not a directory: {root}")

    if args.file:
        target = Path(args.file)
        if not target.is_absolute():
            target = root / target
        findings = check_file(target, root)
        return report(findings, {"files": 1 if target.is_file() else 0},
                      as_json=args.json)

    findings, coverage = check_all(root)
    return report(findings, coverage, as_json=args.json)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
