#!/usr/bin/env python3
"""Reconcile every path a plugin's `checks.json` waits on against the paths the plugin itself names.

Run:  python3 scripts/check_manifest_paths.py            # reconcile, fail on a phantom path
      python3 scripts/check_manifest_paths.py --selftest  # prove the rules fire AND stay silent

WHY (#423). `project_gates.py` decides applicability by asking whether an `applies_when` path
exists and whether a `{match:glob}` matches anything. Both answers are *reasons*, not verdicts:
absent path -> "not applicable", empty glob -> "not applicable". Never FAIL. So a gate aimed at a
directory nothing writes is **indistinguishable from a gate that correctly found nothing to do**,
and it stays that way forever. Three of qa-flow's seven and two of rails-flow's five were in
exactly that state -- `qa/routes.json` (the file is `qa/reports/routes.json`),
`qa/manual-tests/manifest.json` (it is `qa/reports/<run>/manifest.json`), `docs/guides/*.md` (the
artefact is `docs/GUIDE.md`), `docs/architecture.md` (it is `docs/architecture/graph.json`).

That is the `gate-that-cannot-fail` class, in the manifest that registers the gates.

WHAT THIS CHECKS, STATED HONESTLY. It does **not** prove a write happens -- most of these
artefacts are written by an agent following a fenced command in markdown, and no static analysis
can prove that. It proves **agreement**: every path the manifest waits on is a path the plugin's
own executable surfaces also name. A manifest path that appears nowhere else in the plugin is
either a typo or an artefact nobody produces, and both are the same permanent skip.

PROSE DOES NOT COUNT, AND THAT IS THE WHOLE DESIGN. `qa/routes.json` was named four times in
qa-flow -- in a docstring paragraph, in YAML frontmatter, and twice in prose -- while the file it
describes is `qa/reports/routes.json`. A corpus built from "anywhere the string appears" would
have read clean over the very bug this exists for. So the corpus is built from surfaces that
something actually RUNS:

    scripts/*.py          string constants, docstrings EXCLUDED (argparse defaults, path constants)
    scripts/*.js          string and template literals, `//` comments excluded
    commands|agents/*.md  fenced code blocks only -- the bash an agent executes, the contracts it writes
    hooks/scripts/*.sh    comment-stripped source

`*_selftest.py` is excluded: a fixture path is not a shipped writer, and including them would let a
test double vouch for a phantom.

COVERAGE IS COUNTED, because "no findings" over nothing examined is a pass that verified nothing.
A manifest declaring no paths at all, and a plugin whose surfaces name none, are both reported.

Exit codes:  0 every manifest path is named by its plugin · 1 at least one is not
             · 2 nothing was examined (no manifest found)

Stdlib only, no network.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from fnmatch import fnmatch
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGINS = "plugins"

# A path token, anchored on a root the manifest itself names (see `roots_of`). Anchoring on the
# manifest's own roots rather than on "anything with a slash" keeps URLs, python dotted paths and
# regex fragments out of the corpus without an exclusion list that would rot.
#
# The trailing lookahead is what stops the word `qa-lead` contributing a bare `qa`; the leading one
# stops a match starting mid-path.
SEGMENT = r"(?:/[A-Za-z0-9_.*<>${}-]+)*"
LEADING = r"(?<![A-Za-z0-9_./$-])"
TRAILING = r"(?![A-Za-z0-9_.-])"


class Unreadable(RuntimeError):
    """A manifest could not be parsed -- reported, never a silent pass."""


@dataclass(frozen=True)
class Entry:
    """One path a manifest waits on."""

    check: str
    kind: str      # "applies_when" or "{match:}"
    path: str      # normalised


@dataclass
class Report:
    plugin: str
    findings: list[str] = field(default_factory=list)
    examined: int = 0    # manifest paths reconciled
    corpus: int = 0      # distinct paths the plugin's own surfaces name


def normalise(raw: str) -> str:
    """One spelling for a path, so a writer and a manifest can be compared.

    `<run>` and `${slug}` are placeholders for a name chosen at run time. They are NOT the same
    thing: `<run>` stands for one concrete segment a writer will fill in, so it becomes a concrete
    placeholder that a manifest glob can match; `${slug}` is shell/JS interpolation of an unknown
    value, so it becomes a wildcard.
    """
    path = raw.strip().strip('"\'`,;')
    path = re.sub(r"\$\{[^}]*\}", "*", path)
    path = re.sub(r"<[^>/]*>", "X", path)
    path = re.sub(r"/{2,}", "/", path)
    return path.rstrip(".").rstrip("/")


def roots_of(entries: list[Entry]) -> list[str]:
    """The first segment of every manifest path -- the only prefixes worth scanning for."""
    return sorted({e.path.split("/", 1)[0] for e in entries if e.path})


def manifest_entries(text: str, source: str = "checks.json") -> list[Entry]:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Unreadable(f"{source}: {exc}") from exc
    out: list[Entry] = []
    for check in data.get("checks", []):
        cid = check.get("id", "<unnamed>")
        for path in check.get("applies_when", []):
            out.append(Entry(cid, "applies_when", normalise(path)))
        for token in check.get("command", []):
            if isinstance(token, str) and token.startswith("{match:") and token.endswith("}"):
                out.append(Entry(cid, "{match:}", normalise(token[len("{match:"):-1])))
    return out


def fenced(text: str) -> str:
    """Only what is inside ``` fences. Everything else in a command or agent file is prose."""
    kept, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if inside:
            kept.append(line)
    return "\n".join(kept)


def py_literals(source: str) -> list[str]:
    """Every string constant EXCEPT docstrings.

    The exclusion is the point. `link_audit.py`'s module docstring names `qa/routes.json` in a
    sentence explaining a bug; the file it actually reads is elsewhere. A docstring is prose that
    happens to live in a string, and treating it as a writer is how this check would go blind.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstrings.add(id(body[0].value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and id(n) not in docstrings]


def js_literals(source: str) -> list[str]:
    """Quoted and backticked literals, `//` comments removed.

    The `(?<!:)` keeps `http://` intact: stripping from the first `//` would eat the rest of any
    line carrying a URL, silently dropping real path literals that share it.
    """
    stripped = "\n".join(re.sub(r"(?<!:)//.*$", "", line) for line in source.splitlines())
    return re.findall(r"""['"`]([^'"`\n]*)['"`]""", stripped)


def sh_source(source: str) -> str:
    return "\n".join(line.split("#", 1)[0] for line in source.splitlines())


def surfaces(plugin: Path) -> list[tuple[Path, list[str]]]:
    """(file, texts) for every surface that something RUNS. Order is stable for reporting."""
    out: list[tuple[Path, list[str]]] = []
    for path in sorted((plugin / "scripts").glob("*.py")):
        if path.name.endswith("_selftest.py"):
            continue
        out.append((path, py_literals(path.read_text(encoding="utf-8"))))
    for path in sorted((plugin / "scripts").glob("*.js")):
        out.append((path, js_literals(path.read_text(encoding="utf-8"))))
    for sub in ("commands", "agents"):
        for path in sorted((plugin / sub).glob("*.md")):
            out.append((path, [fenced(path.read_text(encoding="utf-8"))]))
    for path in sorted((plugin / "hooks" / "scripts").glob("*.sh")):
        out.append((path, [sh_source(path.read_text(encoding="utf-8"))]))
    return out


def named_paths(plugin: Path, roots: list[str]) -> dict[str, set[str]]:
    """{normalised path: the surface files naming it}, restricted to the manifest's own roots."""
    patterns = [re.compile(LEADING + re.escape(root) + SEGMENT + TRAILING) for root in roots]
    found: dict[str, set[str]] = {}
    for path, texts in surfaces(plugin):
        for text in texts:
            for pattern in patterns:
                for hit in pattern.finditer(text):
                    token = normalise(hit.group(0))
                    # A bare `dir/*` says only that the directory is used, so it is recorded as the
                    # directory. Left as a glob it would vouch for every child name anyone invented,
                    # which is precisely the phantom this check exists to refuse.
                    while token.endswith("/*") or token.endswith("/**"):
                        token = token.rsplit("/", 1)[0]
                    if token:
                        found.setdefault(token, set()).add(path.name)
    return found


def agrees(entry: str, named: str) -> bool:
    """Does `named` (a path the plugin names) account for `entry` (a path the manifest waits on)?"""
    if entry == named:
        return True
    if fnmatch(named, entry):
        return True          # the writer produces an instance of the manifest's glob
    if fnmatch(entry, named):
        return True          # the manifest names an instance of the writer's pattern
    return named.startswith(entry + "/")   # the manifest waits on a directory written into


def hints(entry: str, corpus: dict[str, set[str]], limit: int = 3) -> list[str]:
    """The corpus paths most likely to be what the manifest meant.

    Shared prefix alone is not enough to be useful: every `docs/*` entry shares one segment with
    every other, so `docs/architecture.md` was pointed at `docs/reviews/`. The second term compares
    the entry's LAST segment against every segment of the candidate, which is what actually
    identifies `docs/architecture/graph.json` and `docs/GUIDE.md` as the intended artefacts.
    """
    want = entry.split("/")
    stem = want[-1].split(".")[0].lower()

    def score(candidate: str) -> tuple[int, int]:
        got = candidate.split("/")
        shared = 0
        for a, b in zip(want, got):
            if a != b:
                break
            shared += 1
        kin = 0
        for segment in got:
            other = segment.split(".")[0].lower()
            if stem and other and (other.startswith(stem) or stem.startswith(other)):
                kin = 1
                break
        if fnmatch(got[-1], want[-1]):
            kin = 1
        return (kin, shared)

    ranked = sorted(corpus, key=lambda c: (score(c), c), reverse=True)
    return [c for c in ranked[:limit] if any(score(c))]


def reconcile(plugin: Path, manifest_text: str | None = None) -> Report:
    """Findings for one plugin. `manifest_text` overrides the file, for fixtures."""
    report = Report(plugin=plugin.name)
    text = manifest_text if manifest_text is not None \
        else (plugin / "checks.json").read_text(encoding="utf-8")
    entries = manifest_entries(text, f"{plugin.name}/checks.json")
    corpus = named_paths(plugin, roots_of(entries))
    report.examined = len(entries)
    report.corpus = len(corpus)

    # THE VACUOUS PASS, both halves. A rule reporting "no findings" over zero examined paths has
    # verified nothing, and so has one whose corpus is empty -- the second is worse, because every
    # entry would then be reported and the run would look like a catastrophe rather than a bug in
    # the scan. Both are findings, so neither can read as clean.
    if not entries:
        report.findings.append(
            f"{plugin.name}/checks.json declares no applies_when path and no {{match:}} glob, so "
            "this reconciliation examined NOTHING. A check with no applicability condition always "
            "runs; if that is intended, say so in the manifest's `comment`.")
        return report
    if not corpus:
        report.findings.append(
            f"{plugin.name}: no shipped script, command, agent or hook names any path under "
            f"{', '.join(roots_of(entries))}/. Either the plugin's surfaces moved or the scan is "
            "broken -- reported rather than failing every entry, because an empty corpus is a "
            "defect in this check, not in the manifest.")
        return report

    for entry in entries:
        if any(agrees(entry.path, named) for named in corpus):
            continue
        near = hints(entry.path, corpus)
        suffix = f" Nearest paths the plugin names: {', '.join(near)}." if near else ""
        report.findings.append(
            f"{plugin.name}/{entry.check} waits on `{entry.path}` ({entry.kind}), which no shipped "
            f"script, command, agent or hook names. project_gates.py reports an absent path as NOT "
            f"APPLICABLE, never as a failure, so this check is a permanent silent skip.{suffix}")
    return report


def run(root: Path = REPO) -> int:
    manifests = sorted((root / PLUGINS).glob("*/checks.json")) if (root / PLUGINS).is_dir() else []
    if not manifests:
        print(f"no {PLUGINS}/*/checks.json found under {root} — nothing was examined, and that is "
              "not a pass.", file=sys.stderr)
        return 2

    reports: list[Report] = []
    for manifest in manifests:
        try:
            reports.append(reconcile(manifest.parent))
        except (OSError, Unreadable) as exc:
            bad = Report(plugin=manifest.parent.name)
            bad.findings.append(f"unreadable manifest: {exc}")
            reports.append(bad)

    findings = [f for r in reports for f in r.findings]
    examined = sum(r.examined for r in reports)
    for report in reports:
        mark = "FAIL" if report.findings else "ok  "
        print(f"  [{mark}] {report.plugin}: {report.examined} manifest path(s) against "
              f"{report.corpus} path(s) its own surfaces name")
    if findings:
        sys.stdout.flush()   # so the per-plugin lines above are read before their findings
        print(f"\n{len(findings)} manifest path(s) nothing produces:", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1
    print(f"\n{examined} manifest path(s) across {len(reports)} plugin(s); every one is named by "
          "the plugin that waits on it.")
    return 0


# --------------------------------------------------------------------------------------------
# Fixtures. Entirely synthetic: every one below must run with nothing but this module on disk,
# because that is the condition `mutation_check.py` stages it under. A fixture reaching for the
# real tree would die there on a missing corpus and read as a caught mutation -- and a crash is
# not a verdict.
# --------------------------------------------------------------------------------------------

_TOOL_PY = '''\
"""A tool.

Run:  python3 tool.py out/ghost.json

The docstring names `out/ghost.json`, which nothing reads. This is the `link_audit.py` shape.
"""
import argparse

TREND = "out/trend.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="out/report.json")
    return ap
'''

_RUN_MD = """\
# Run it

Everything lands under `out/prose-only.json`, which is a sentence, not a command.

```bash
python3 tool.py --out out/report.json
python3 judge.py out/live.csv
python3 judge.py "out/<date>-summary.csv"
```

Results go to `out/nowhere-else.json` in prose again.
"""


def _plugin(tmp: Path) -> Path:
    plugin = tmp / "demo"
    (plugin / "scripts").mkdir(parents=True, exist_ok=True)
    (plugin / "commands").mkdir(parents=True, exist_ok=True)
    (plugin / "scripts" / "tool.py").write_text(_TOOL_PY, encoding="utf-8")
    (plugin / "commands" / "run.md").write_text(_RUN_MD, encoding="utf-8")
    return plugin


def _manifest(*paths: tuple[str, list[str], list[str]]) -> str:
    checks = [{"id": cid, "why": "w", "command": ["python3", "{plugin}/scripts/tool.py"] +
               [f"{{match:{g}}}" for g in globs], "applies_when": applies}
              for cid, applies, globs in paths]
    return json.dumps({"plugin": "demo", "checks": checks})


def selftest() -> int:
    import tempfile

    failures: list[str] = []
    n = 0

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    with tempfile.TemporaryDirectory(prefix="manifest-paths-") as tmpdir:
        plugin = _plugin(Path(tmpdir))

        # ---- SILENCE. The half that matters: a checker firing on a correct manifest gets deleted.
        out = reconcile(plugin, _manifest(("c", ["out"], ["out/live.csv"])))
        check("a manifest agreeing with the plugin's own surfaces is silent",
              out.findings == [], f"{out.findings}")
        check("the corpus is non-empty for a real plugin", out.corpus >= 3, f"{out.corpus}")

        out = reconcile(plugin, _manifest(("c", ["out/report.json"], [])))
        check("an argparse default counts as agreement", out.findings == [], f"{out.findings}")

        out = reconcile(plugin, _manifest(("c", [], ["out/*.csv"])))
        check("a `<placeholder>` instance satisfies a glob", out.findings == [], f"{out.findings}")

        out = reconcile(plugin, _manifest(("c", ["out/trend.jsonl"], [])))
        check("a module-level path constant counts as agreement",
              out.findings == [], f"{out.findings}")

        # ---- FIRES.
        out = reconcile(plugin, _manifest(("c", ["out/nowhere"], [])))
        check("a phantom applies_when path is reported",
              any("out/nowhere" in f and "permanent silent skip" in f for f in out.findings),
              f"{out.findings}")

        out = reconcile(plugin, _manifest(("c", ["out"], ["out/nothing.json"])))
        check("a phantom match glob is reported",
              any("out/nothing.json" in f and "{match:}" in f for f in out.findings),
              f"{out.findings}")

        # The exact #423 shape, twice over: a path that IS named, but only where nothing runs it.
        out = reconcile(plugin, _manifest(("c", ["out/prose-only.json"], [])))
        check("a path named only in prose does not count as agreement",
              any("out/prose-only.json" in f for f in out.findings), f"{out.findings}")

        out = reconcile(plugin, _manifest(("c", ["out/ghost.json"], [])))
        check("a path named only in a docstring does not count as agreement",
              any("out/ghost.json" in f for f in out.findings), f"{out.findings}")

        # A finding must point somewhere. A bare "wrong" is what makes a gate get ignored.
        out = reconcile(plugin, _manifest(("c", ["out/report.jsonl"], [])))
        check("a finding names the nearest real path",
              any("out/report.json" in f for f in out.findings), f"{out.findings}")

        # ---- COVERAGE. "No findings" over nothing examined is the vacuous pass.
        out = reconcile(plugin, _manifest(("c", [], [])))
        check("a manifest declaring no paths is reported, not passed",
              out.examined == 0 and any("examined NOTHING" in f for f in out.findings),
              f"{out.examined} {out.findings}")

        bare = Path(tmpdir) / "bare"
        (bare / "scripts").mkdir(parents=True, exist_ok=True)
        (bare / "scripts" / "x.py").write_text("Y = 1\n", encoding="utf-8")
        out = reconcile(bare, _manifest(("c", ["out"], [])))
        # Asserted on wording UNIQUE to the empty-corpus branch. "no shipped script ... names" also
        # appears in the per-entry finding, so the obvious assertion passed with this branch deleted
        # -- the mutation checker caught it surviving, which is the whole reason that gate exists.
        check("a plugin whose surfaces name no paths is reported",
              out.corpus == 0 and any("empty corpus is a defect" in f for f in out.findings),
              f"{out.corpus} {out.findings}")

        # ---- A directory-only corpus entry must NOT vouch for children.
        # `out/*` in a writer says the directory is used, nothing more. Left as a glob it would
        # satisfy every name anyone invented, which is the phantom this refuses.
        dirs = Path(tmpdir) / "dirs"
        (dirs / "scripts").mkdir(parents=True, exist_ok=True)
        (dirs / "scripts" / "x.py").write_text('D = "out/*"\n', encoding="utf-8")
        out = reconcile(dirs, _manifest(("c", ["out/invented.json"], [])))
        check("a bare `dir/*` writer does not vouch for an invented child",
              any("out/invented.json" in f for f in out.findings), f"{out.findings}")

    # An unparseable manifest RAISES rather than reconciling zero entries and reporting clean.
    n += 1
    try:
        manifest_entries("{not json", "x")
        failures.append("an unparseable manifest parsed instead of raising")
    except Unreadable:
        pass

    # `run()` over a tree with no manifests is exit 2, never 0. A sweep that found nothing to
    # reconcile must not report the same green as one that reconciled everything.
    import tempfile as _tf
    with _tf.TemporaryDirectory(prefix="manifest-empty-") as empty:
        check("a tree with no manifests exits 2, not 0", run(Path(empty)) == 2)

    if failures:
        print(f"SELFTEST FAILED -- {len(failures)} of {n} checks:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1
    print(f"check_manifest_paths selftest: {n} checks passed")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reconcile every checks.json path against the paths its plugin names.")
    ap.add_argument("--selftest", action="store_true", help="prove the rules fire AND stay silent")
    args = ap.parse_args(argv)
    return selftest() if args.selftest else run()


if __name__ == "__main__":
    sys.exit(main())
