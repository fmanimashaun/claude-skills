#!/usr/bin/env python3
"""A change a user can see is built only after the owner approved a clickable mock-up (#1376).

Run:  check_mockup_gate.py --base dev [--root DIR]            # the branch's diff, before merge
      check_mockup_gate.py --paths app/views/a.html.erb ...   # the plan's files, at Phase 1
      check_mockup_gate.py --selftest
      optional on either: --record docs/product/mockups/<slug>.md

Exit: 0 no user-visible change, or an approved mock-up is recorded, or the project declared the
gate off · 1 user-visible change with no approved mock-up recorded · 2 cannot classify.

WHY. On a downstream app's first production day the owner reported about 14 screens built unlike
what had been agreed in conversation: tables for cards, page forms for modals, a link for a
dropdown. Each cost a PR, specs, screenshots and a redeploy. The one screen whose clickable mock-up
was approved FIRST was right in one round, because the build had a target. So the owner's rule: a
user-visible change waits for an approved mock-up, whatever the issue's label says.

UI SCOPE IS A PATH RULE, not a judgement. A change touches what a user sees when it touches
UI_PATHS: views (not JSON/XML templates, which API clients read), components, JavaScript,
stylesheets, helpers, and locale files (visible copy). Everything else is backend. A mixed change is
UI scope.

THE RECORD is `docs/product/mockups/<slug>.md`, carrying one `Key: value` line for each of RECORD_KEYS.
It must name the mock-up (a URL, or a repo file that exists), the issue, who approved it, the
approval itself as a link to the comment where they said so, and the widths (a phone width ≤ 480
and a desktop width ≥ 1024) and states it covers. The branch must add or change the record, or name
it with --record. An approval with no link is a sentence anyone can type.

WHAT IT DOES NOT: prove the linked comment says "approved", or that the build matches the mock-up.
The first is the reviewer's click; the second is the screenshot comparison before merge.

OPT-OUT. A project without a design reviewer declares `mockup-gate: off` on its own line in
GUARDRAILS.md (setup-flow asks). Undeclared means ON: the owner set the default.

Stdlib only; git is read like classify_door.py reads it, through the same helper.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classify_door import Unusable, diff  # noqa: E402  -- one diff reader, never a second

UI_PATHS = (re.compile(r"^app/views/"), re.compile(r"^app/components/"), re.compile(r"^app/javascript/"),
            re.compile(r"^app/assets/(stylesheets|tailwind|images)/"), re.compile(r"^app/helpers/"),
            re.compile(r"^config/locales/"),
            # What Rails 8 generates for a user to see outside app/views: the error pages, the icon,
            # the favicon (pre-release review of #1381).
            re.compile(r"^public/[^/]+\.(html|png|svg|ico|webmanifest)$"))
# An API template is read by a client, not seen by a person -- except the PWA manifest, which holds
# the installed app's name and icons.
NOT_UI = re.compile(r"\.(json|xml)(\.[a-z]+)?$")
SEEN_ANYWAY = re.compile(r"^app/views/pwa/")
RECORD_DIR = "docs/product/mockups/"
RECORD_KEYS = ("Mock-up", "Issue", "Approved-by", "Approval", "Widths", "States")
APPROVAL_URL = re.compile(r"^https://github\.com/[^/\s]+/[^/\s]+/(issues|pull)/\d+"
                          r"#(issuecomment-\d+|discussion_r\d+|pullrequestreview-\d+)$")
MOCK_FILE = re.compile(r"\.(html?|png|jpe?g|webp|pdf|svg)$", re.I)
ISSUE_REF = re.compile(r"^(#\d+|https://github\.com/[^/\s]+/[^/\s]+/issues/\d+)\b")
OPT_OUT = re.compile(r"^\s*(?:[-*]\s*)?`?mockup-gate:\s*off`?\s*$", re.M | re.I)


def ui_paths(paths: list[str]) -> list[str]:
    return sorted(p for p in paths if any(r.match(p) for r in UI_PATHS)
                  and (SEEN_ANYWAY.match(p) or not NOT_UI.search(p)))


def declared_off(root: Path) -> bool:
    g = root / "GUARDRAILS.md"
    if not g.is_file():
        return False
    # A fenced example of the line documents the opt-out; it does not declare it (review of #1381).
    # An UNTERMINATED fence runs to the end of the file (#1430) -- stricter than a renderer, which
    # ends one at the close of its list item; list-scoped fences are not modelled here. The
    # regex this replaces removed only closed fences, so an opt-out after a stray ``` still counted.
    return bool(OPT_OUT.search(unfenced(g.read_text(encoding="utf-8"))))



def unfenced(text: str) -> str:
    """The lines outside fenced code blocks. A fence closes on the same character, at least as long."""
    out, fence = [], ""
    for line in text.splitlines():
        # Any indentation: in GUARDRAILS.md a fence usually sits inside a list item (review of PR #1478).
        # A BACKTICK opener may not contain another backtick (CommonMark), so "```x``` inline" is a
        # code span, not a fence -- read as one it swallowed a real opt-out below it (final review).
        m = re.match(r"^\s*(`{3,})(?=[^`]*$)|^\s*(~{3,})", line)
        run = (m.group(1) or m.group(2)) if m else ""
        if fence:
            if run and run[0] == fence[0] and len(run) >= len(fence) and not line.strip()[len(run):].strip():
                fence = ""
            continue
        if run:
            fence = run
            continue
        out.append(line)
    return "\n".join(out)


def record_problems(root: Path, rel: str) -> list[str]:
    path = root / rel
    if not path.is_file():
        return [f"{rel}: no such mock-up record"]
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\s*(?:[-*]\s*)?\**([A-Za-z-]+)\**:\s*(.*?)\s*$", line)
        if m and m.group(1) in RECORD_KEYS:
            fields[m.group(1)] = m.group(2)
    out = [f"{rel}: no `{k}:` line" for k in RECORD_KEYS if not fields.get(k)]
    mock = fields.get("Mock-up", "")
    if mock.startswith("https://"):
        if not re.match(r"^https://[^/\s]+\.[^/\s]+", mock):
            out.append(f"{rel}: Mock-up {mock!r} is not a link to anything")
    elif mock and ((root / mock).resolve() == path.resolve()
                   or ((root / mock).exists() and (root / mock).samefile(path))):
        # `samefile` too: a hard link is the record under another name, and resolve() keeps names (#1479).
        # A record naming itself satisfied "a file under docs/product/mockups/" (#1430).
        out.append(f"{rel}: Mock-up names this record itself; name the mock-up it records")
    elif mock and (root / mock).resolve().suffix.lower() == ".md":
        # ...and so did naming another record. A record is not a mock-up, whatever a symlink calls it
        # -- the RESOLVED target is judged. Any other committed file under the folder is still a
        # mock-up (.gif, .avif, .html.erb): an allow-list refused real ones (review of PR #1478).
        out.append(f"{rel}: Mock-up {mock!r} is a Markdown record, not a mock-up file")
    elif mock and not ((root / mock).is_file() and (mock.startswith(RECORD_DIR) or MOCK_FILE.search(mock))):
        out.append(f"{rel}: Mock-up {mock!r} is neither an https link nor a mock-up file in the repo "
                   f"(under {RECORD_DIR}, or an .html/.png/.jpg/.webp/.pdf/.svg)")
    issue = fields.get("Issue", "")
    if issue and not ISSUE_REF.match(issue):
        out.append(f"{rel}: Issue {issue!r} must name the issue this mock-up answers (#n, or its URL)")
    approval = fields.get("Approval", "")
    if approval and not APPROVAL_URL.match(approval):
        out.append(f"{rel}: Approval must link the comment where the owner approved "
                   f"(…/issues/N#issuecomment-M), got {approval!r}")
    widths = [int(w) for w in re.findall(r"\d+", fields.get("Widths", ""))]
    if fields.get("Widths") and not (any(w <= 480 for w in widths) and any(w >= 1024 for w in widths)):
        out.append(f"{rel}: Widths {fields['Widths']!r} must include a phone width (≤ 480) and a desktop width (≥ 1024)")
    return out


def run(root: Path, changed: list[str], record: str | None) -> tuple[int, list[str]]:
    """The whole decision. main() and the selftest both come through here."""
    ui = ui_paths(changed)
    if not ui:
        return 0, ["no user-visible change: no mock-up needed"]
    if declared_off(root):
        return 0, [f"{len(ui)} user-visible file(s), and GUARDRAILS.md declares `mockup-gate: off`"]
    records = [record] if record else sorted(p for p in changed if p.startswith(RECORD_DIR) and p.endswith(".md")
                                             and Path(p).name.lower() != "readme.md")
    if not records:
        return 1, [f"{len(ui)} user-visible file(s) ({', '.join(ui[:5])}{' …' if len(ui) > 5 else ''}) and no "
                   f"approved mock-up: publish one, stop for the owner's approval, then record it in "
                   f"{RECORD_DIR}<slug>.md"]
    problems = [p for r in records for p in record_problems(root, r)]
    if problems:
        return 1, problems
    return 0, [f"{len(ui)} user-visible file(s); approved mock-up recorded in {', '.join(records)}"]


# --------------------------------------------------------------------------- selftest

GOOD = """# Mock-up — invoice bell
Mock-up: https://example.com/mockups/bell
Issue: #12
Approved-by: @owner
Approval: https://github.com/acme/app/issues/12#issuecomment-99
Widths: 1280, 390
States: default, empty, error
"""


def selftest() -> int:
    failures: list[str] = []

    def check_that(label: str, ok: bool, detail: object = "") -> None:
        if not ok:
            failures.append(f"{label}{(' — ' + str(detail)) if detail != '' else ''}")

    check_that("a view is UI scope", ui_paths(["app/views/invoices/index.html.erb"]) != [])
    check_that("a component is UI scope", ui_paths(["app/components/bell_component.rb"]) != [])
    check_that("a Stimulus controller is UI scope", ui_paths(["app/javascript/controllers/bell_controller.js"]) != [])
    check_that("a locale file (visible copy) is UI scope", ui_paths(["config/locales/en.yml"]) != [])
    check_that("CONTROL: a model, migration, job and spec are not UI scope",
               ui_paths(["app/models/invoice.rb", "db/migrate/1_x.rb", "app/jobs/sync_job.rb",
                         "spec/models/invoice_spec.rb"]) == [])
    check_that("CONTROL: a JSON template is read by a client, not seen",
               ui_paths(["app/views/api/invoices/show.json.jbuilder"]) == [])
    # Pre-release review of #1381: what Rails 8 generates for a user to see outside app/views.
    check_that("a public error page is UI scope", ui_paths(["public/404.html"]) == ["public/404.html"])
    check_that("the app icon is UI scope", ui_paths(["public/icon.png"]) == ["public/icon.png"])
    check_that("an image asset is UI scope", ui_paths(["app/assets/images/logo.svg"]) != [])
    check_that("the PWA manifest is UI scope although it is JSON",
               ui_paths(["app/views/pwa/manifest.json.erb"]) == ["app/views/pwa/manifest.json.erb"])
    check_that("CONTROL: robots.txt and a public subdirectory file are not UI scope",
               ui_paths(["public/robots.txt", "public/assets/app-1.css"]) == [])
    check_that("a mixed change is UI scope",
               ui_paths(["app/models/invoice.rb", "app/views/invoices/_row.html.erb"]) == ["app/views/invoices/_row.html.erb"])

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        rec = root / "docs/product/mockups"
        rec.mkdir(parents=True)
        view = ["app/views/invoices/index.html.erb"]

        code, _ = run(root, ["app/models/invoice.rb"], None)
        check_that("CONTROL: a backend-only change passes with no record", code == 0)
        code, msg = run(root, view, None)
        check_that("a UI change with no mock-up record is held", code == 1, msg)

        (rec / "bell.md").write_text(GOOD)
        code, msg = run(root, view + ["docs/product/mockups/bell.md"], None)
        check_that("CONTROL: a UI change with a complete, approved record passes", code == 0, msg)
        code, msg = run(root, view, "docs/product/mockups/bell.md")
        check_that("CONTROL: --record names a record the branch did not touch", code == 0, msg)

        def with_record(text: str) -> tuple[int, list[str]]:
            (rec / "r.md").write_text(text)
            return run(root, view + ["docs/product/mockups/r.md"], None)

        code, msg = with_record(GOOD.replace("Approval: https://github.com/acme/app/issues/12#issuecomment-99\n", ""))
        check_that("a record with no approval line is held", code == 1 and any("Approval" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("https://github.com/acme/app/issues/12#issuecomment-99", "approved in chat"))
        check_that("an approval that is not a comment link is held", code == 1 and any("link the comment" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("Widths: 1280, 390", "Widths: 1280"))
        check_that("a mock-up with no phone width is held", code == 1 and any("phone width" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("Widths: 1280, 390", "Widths: 390"))
        check_that("a mock-up with no desktop width is held", code == 1 and any("phone width" in m for m in msg), msg)
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/missing.html"))
        check_that("a mock-up file that does not exist is held", code == 1 and any("neither" in m for m in msg), msg)
        (root / "docs/product/mockups/bell.html").write_text("<html></html>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.html"))
        check_that("CONTROL: a committed mock-up file passes", code == 0, msg)

        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "https://"))
        check_that("a bare https:// is not a mock-up", code == 1 and any("not a link" in m for m in msg), msg)
        (root / "GUARDRAILS.md").write_text("x\n")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "GUARDRAILS.md"))
        check_that("an arbitrary repo file is not a mock-up", code == 1 and any("mock-up file" in m for m in msg), msg)
        (root / "notes.txt").write_text("x\n")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "notes.txt"))
        check_that("an arbitrary NON-Markdown repo file outside the folder is not a mock-up",
                   code == 1 and any("neither" in m for m in msg), msg)
        (root / "GUARDRAILS.md").unlink()
        code, msg = with_record(GOOD.replace("Issue: #12", "Issue: the bell one"))
        check_that("a record that names no issue is held", code == 1 and any("Issue" in m for m in msg), msg)
        (rec / "README.md").write_text("# How mock-up records work\n")
        code, msg = run(root, view + ["docs/product/mockups/README.md", "docs/product/mockups/bell.md"], None)
        check_that("CONTROL: a README in the records folder is not a record", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nTo opt out, add:\n\n```markdown\n- mockup-gate: off\n```\n")
        code, msg = run(root, view, None)
        check_that("a fenced example of the opt-out line is not a declaration", code == 1, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("a project that declared the gate off is not held", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nWe might set mockup-gate: off one day.\n")
        code, msg = run(root, view, None)
        check_that("CONTROL: prose mentioning the key is not a declaration", code == 1, msg)
        # #1430: an opt-out inside an UNTERMINATED fence is still inside a fence.
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\nExample:\n\n```\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("#1430: an opt-out inside an unterminated fence is not a declaration", code == 1, msg)
        (root / "GUARDRAILS.md").write_text("# Guardrails\n\n```\nexample\n```\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("#1430 CONTROL: an opt-out AFTER a closed fence still declares", code == 0, msg)
        (root / "GUARDRAILS.md").unlink()
        # #1430: a record may not name itself, or another record, as its mock-up.
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/r.md"))
        check_that("#1430: a record naming itself is held", code == 1 and any("itself" in m for m in msg), msg)
        # #1479: a HARD LINK is the record under another name; resolve() keeps the name, samefile
        # does not. Named .html so the Markdown-record rule cannot be what holds it. Portable to Linux.
        (rec / "r.md").write_text(GOOD)
        alias = rec / "r-alias.html"
        alias.unlink(missing_ok=True)
        os.link(rec / "r.md", alias)
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/r-alias.html"))
        check_that("#1479: a record naming itself by another name is held",
                   code == 1 and any("itself" in m for m in msg), msg)
        alias.unlink()
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.md"))
        check_that("#1430: a record naming another record is held", code == 1 and any("Markdown record" in m for m in msg), msg)
        (root / "docs/product/mockups/bell.svg").write_text("<svg/>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/bell.svg"))
        check_that("#1430 CONTROL: a committed .svg mock-up passes", code == 0, msg)
        (root / "design").mkdir(exist_ok=True)
        (root / "design/bell.svg").write_text("<svg/>")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "design/bell.svg"))
        check_that("#1430: an .svg mock-up OUTSIDE the records folder is a mock-up file", code == 0, msg)
        # Review of PR #1478: an allow-list refused real mock-ups committed under the folder.
        for name in ("bell.gif", "bell.avif", "bell.html.erb"):
            (root / "docs/product/mockups" / name).write_text("x")
            code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", f"docs/product/mockups/{name}"))
            check_that(f"PR #1478 review: a committed {name} under the folder is a mock-up", code == 0, msg)
        # ...and a symlink is judged by its TARGET: o.html -> bell.md is a record, not a mock-up.
        (root / "docs/product/mockups/o.html").symlink_to("bell.md")
        code, msg = with_record(GOOD.replace("https://example.com/mockups/bell", "docs/product/mockups/o.html"))
        check_that("PR #1478 review: a symlink onto a record is held", code == 1 and any("Markdown record" in m for m in msg), msg)
        # An example opt-out in an INDENTED fence (inside a list item) is still an example.
        (root / "GUARDRAILS.md").write_text("# G\n\n- Example:\n\n    ```\n    - mockup-gate: off\n    ```\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 review: an opt-out in an indented fence is not a declaration", code == 1, msg)
        # Final review: a line OPENING with an inline code span is not a fence.
        (root / "GUARDRAILS.md").write_text("# G\n\n```x``` inline\n\n- mockup-gate: off\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 final review: a code span at line start does not fence the opt-out", code == 0, msg)
        (root / "GUARDRAILS.md").write_text("# G\n\n```sh\n- mockup-gate: off\n```\n")
        code, msg = run(root, view, None)
        check_that("PR #1478 final review CONTROL: an info-string fence still fences", code == 1, msg)
        (root / "GUARDRAILS.md").unlink()

    # The git path main() takes: a new, untracked view must count (the #1341 blind spot). A FRESH
    # directory: the one above holds untracked records, which would rightly count as on the branch.
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        def git(*a: str) -> None:
            subprocess.run(("git",) + a, cwd=root, check=True, capture_output=True)
        git("init", "-q", "-b", "dev"); git("config", "user.email", "t@example.com"); git("config", "user.name", "t")
        (root / "README.md").write_text("x\n"); git("add", "README.md"); git("commit", "-qm", "base")
        git("checkout", "-q", "-b", "feature")
        (root / "app/views/invoices").mkdir(parents=True)
        (root / "app/views/invoices/index.html.erb").write_text("<table></table>\n")   # untracked
        code, msg = run(root, list(diff(root, "dev")), None)
        check_that("an untracked new view, read through the diff, is held", code == 1, msg)
        try:
            diff(root, "no-such-base")
            check_that("an unresolvable base is unusable", False)
        except Unusable:
            pass

    for f in failures:
        print(f"selftest FAIL: {f}")
    print(f"check_mockup_gate selftest: {'FAILED' if failures else 'ok'} ({len(failures)} failure(s))")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="check_mockup_gate.py", description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="dev")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--paths", nargs="+", help="the plan's files, instead of the branch's diff")
    ap.add_argument("--record", help=f"the mock-up record, when the branch does not touch one ({RECORD_DIR}<slug>.md)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        changed = a.paths if a.paths else list(diff(a.root, a.base))
    except Unusable as exc:
        print(f"UNUSABLE: {exc} -- an unclassified change is not exempt; ask the owner", file=sys.stderr)
        return 2
    code, lines = run(a.root, changed, a.record)
    print(("MOCK-UP GATE: HOLD -- " if code else "MOCK-UP GATE: ok -- ") + lines[0])
    for line in lines[1:]:
        print(f"  {line}")
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
