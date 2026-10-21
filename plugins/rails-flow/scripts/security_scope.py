#!/usr/bin/env python3
"""Say whether a PLANNED change adds a security boundary, so a threat model is owed before the acceptance criteria (#2117).

Run:  security_scope.py [--plan FILE] [--path P ...]
      security_scope.py --selftest
Exit: 0 no new boundary named: the plan records "no new boundary" and moves on
      1 a boundary is named: run /rails-flow:secure-design before writing criteria (reasons on stdout, one per line)
      2 nothing to classify (no --plan text and no --path): an unknown plan is not "no boundary"

WHY (#2117, decision D1 on #2115). A threat model on every unit becomes boilerplate nobody reads, so the step fires only when the plan
names something an attacker can reach or that changes who may do what. This is the PLANNING-time sibling of `risky_diff.py`, which reads
the DIFF after the code exists; this reads the plan, the spec or the issue text and the paths the unit will touch, before it does.

A BOUNDARY IS ONE OF: a public or token-link route; an upload or import; a webhook; an MCP tool; an outbound fetch of a URL somebody
supplied; an authentication, session or role change; a new personal-data column; a job fed by outside data; a secret or key; parsing of input from outside; raw HTML rendered from outside; a redirect to a supplied URL; an access rule or privacy filter. The plain-language
patterns below are stack-neutral; each detected stack adds its own spellings and paths from its descriptor (`security.boundary_text`,
`security.boundary_paths`), so this script names no stack.

LIMITS. A keyword scan over prose and paths: a PHRASE HEURISTIC, so a plan worded differently from every pattern ("let the caller pick where we land afterwards") is missed. The
raw-html and redirect-param categories in particular know a short list of spellings, not the idea. The auth words only count after a change verb ("add a role", "let staff reset a password"), so a plan that
only mentions a login page or documents the roles stays quiet; "import" counts only with a file or data noun. It still over-fires on "parse the JSON
config we ship" and on prose about "credentials", and under-fires on a boundary the
plan never names. It says "owed", never "done", and cannot make the model that follows it honest. A reviewer who sees a boundary it
missed runs the command by hand.
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path

# (boundary, what in the PLAN TEXT names it)
TEXT: tuple[tuple[str, re.Pattern], ...] = (
    ("public-route", re.compile(r"\b(?:public (?:route|page|endpoint|url|link)|unauthenticated|token (?:link|url|route)|magic link|signed (?:link|url)|sign(?:s|ing)?[- ]?in with|without (?:logging|signing) in)\b|\bmake\b[^.\n]{0,40}\bpublic\b", re.I)),
    ("upload-import", re.compile(r"\b(?:uploads?|csv|file input|attachments?|multipart|(?:bulk |data )import|imports? (?:an? |the |their |that |this )?(?:files?|csv|spreadsheets?|data|records?|rows?))\b", re.I)),
    ("webhook", re.compile(r"\bwebhooks?\b|\bcallback (?:url|endpoint)\b", re.I)),
    ("mcp-tool", re.compile(r"\bmcp\b|\bmodel context protocol\b", re.I)),
    ("outbound-fetch", re.compile(r"\b(?:outbound (?:fetch|request|call)|fetch(?:es)? (?:a |the )?url|downloads? from (?:a )?url|ssrf)\b", re.I)),
    ("auth-session-role", re.compile(r"\b(?:add|adds|adding|new|change|changes|changing|replace|remove|grant|revoke|let|lets|allow|allows|enable|rotate|reset|expire|invalidate|issue|implement|build|create|require|enforce|restrict|support|switch|migrate|skip|extend|generate|make)\b[^.\n]{0,50}\b(?:sign[- ]?in|log[- ]?in|sessions?|passwords?|sso|oauth|omniauth|two[- ]factor|2fa|roles?|permissions?|authori[sz]ation|authenticat\w*|(?:access|auth|bearer|refresh|reset|session|login|api|magic[- ]link) tokens?|impersonat\w*|remember[- ]me|api (?:key|token))\b", re.I)),
    ("secrets", re.compile(r"\b(?:secrets?|credentials|(?:encryption|signing|private|master|secret) keys?|api[_ ]?keys?|(?:store|storing) (?:the |a )?tokens?)\b", re.I)),
    ("input-parsing", re.compile(r"\bparse[sd]?\b[^.\n]{0,40}\b(?:xml|json|yaml|html|payload|body|params|headers?|input)\b|\b(?:deserializ\w*|unmarshal\w*)", re.I)),
    ("raw-html", re.compile(r"\braw\b[^.\n]{0,40}\bhtml\b|\bhtml\b[^.\n]{0,40}\braw\b|\b(?:skip|disable|turn off|without)\s+sanitiz\w*|\bsanitiz\w*\s+(?:off|disabled)\b|\brender\w*\s+(?:the |a |an )?(?:partner|user|customer|external|supplied|uploaded|third[- ]party)(?:'s|s')?\s+(?:raw )?html\b", re.I)),
    ("redirect-param", re.compile(r"\breturn[_ ]url\b|\b(?:return_to|redirect_url|redirect_uri|back_url|next_url|return_path)\b|\b(?:next|return|redirect|back)\s+param(?:eter)?s?\b|\bredirect\w*[^.\n]{0,40}\bparams?\b|\bsend (?:them|the user|the person) back to (?:the |a )?(?:url|link|page) (?:in|from|they|the user)|\bredirects? (?:back )?to (?:a |the )?(?:param|url the user|url (?:in|from) the)", re.I)),
    ("access-rule", re.compile(r"\bonly [a-z ]{1,30} (?:can|may)\b|\b(?:hide|restrict|mask|redact|limit)\b[^.\n]{0,40}\b(?:field|column|attribute|salary|data|record)s?\b[^.\n]{0,30}\b(?:from|to|for)\b|\bnon-(?:admin|manager|staff|owner)s?\b", re.I)),
    ("personal-data", re.compile(r"\b(?:personal (?:data|information|field)s?|pii|date of birth|dob|phone number|email address|national id|bank (?:detail|account)s?|health data)\b", re.I)),
    ("outside-data-job", re.compile(r"\bjobs?\b[^.\n]{0,60}\b(?:from|fed by|reads?|processes?)\b[^.\n]{0,40}\b(?:webhook|upload|import|external|outside|api|csv)\b", re.I)),
)


# A STACK ROW: (boundary, "text" or "path", pattern, the stack that declared it). The neutral TEXT above names a boundary in plain
# words; a stack's own spellings (a framework helper, a route file) come from its descriptor (`security.boundary_text` and
# `security.boundary_paths`, #2117), so this script names no stack and a new stack adds its patterns without editing it.
Row = tuple[str, str, "re.Pattern", str]


def stack_rows(project: Path, dirs: list[Path] | None = None) -> tuple[list[Row], list[str]]:
    """The detected stacks' boundary patterns for `project`, and any note on why there are none."""
    here = Path(__file__).resolve()
    sys.path.insert(0, str(here.parent))
    import detect_stack  # noqa: E402  (a sibling script; imported here so --selftest runs without a project)
    code, report = detect_stack.run(project, dirs if dirs is not None else detect_stack.manifest_dirs(here))
    rows: list[Row] = []
    for surface in report.get("security") or []:
        label = f"{surface.get('plugin')}:{surface.get('stack')}"
        for kind, key in (("text", "boundary_text"), ("path", "boundary_paths")):
            for entry in surface.get(key) or []:
                rows.append((entry["boundary"], kind, re.compile(entry["pattern"], re.I), label))
    notes = [] if code != 2 else [f"stack not judged ({'; '.join(report.get('problems') or [])}): neutral signals only"]
    if code != 2:
        labels = sorted({r[3] for r in rows})
        notes.append(f"stack rows: {len(rows)} from {', '.join(labels)}" if rows else
                     "stack rows: none loaded (no detected stack declares `security`, the project is a sub-directory, or its plugin was not found): neutral signals only")
    return rows, notes


CASE_KEYS = {"name": str, "plan": str, "paths": list, "boundary": bool}


def case_shape_problems(cases: object) -> list[str]:
    """A stack's cases file in its one strict shape (#2210): a non-empty list of objects with exactly CASE_KEYS, typed, names unique.
    Anything else is refused, never read around: an extra key is a typo of a real one, and a case nobody can run proves nothing."""
    if not isinstance(cases, list) or not cases:
        return ["must be a non-empty JSON list of cases"]
    found, seen = [], set()
    for i, case in enumerate(cases):
        if not isinstance(case, dict):
            found.append(f"case {i} is not an object")
            continue
        if set(case) != set(CASE_KEYS):
            found.append(f"case {i} keys {sorted(case)} must be exactly {sorted(CASE_KEYS)}")
            continue
        wrong = [k for k, t in CASE_KEYS.items() if type(case[k]) is not t]
        if not wrong and not case["name"].strip():
            wrong = ["name"]
        if not wrong and not all(type(p) is str and p.strip() for p in case["paths"]):
            wrong = ["paths"]
        if wrong:
            found.append(f"case {i} has a wrong type or an empty value in {wrong}")
            continue
        if case["name"] in seen:
            found.append(f"case {i} repeats the name {case['name']!r}")
        seen.add(case["name"])
    return found


def stack_case_failures(dirs: list[Path]) -> tuple[list[str], int]:
    """Each discovered stack's own cases (`security.cases`, #2117) run through that stack's patterns: a stack proves its spellings."""
    here = Path(__file__).resolve()
    sys.path.insert(0, str(here.parent))
    import detect_stack  # noqa: E402
    manifests, _ = detect_stack.load_manifests(dirs)
    failures, ran = [], 0
    for manifest in manifests:
        for stack in manifest.get("stacks") or []:
            sec = ((stack or {}).get("descriptor") or {}).get("security") if isinstance(stack, dict) else None
            if not isinstance(sec, dict) or not isinstance(sec.get("cases"), str):
                continue
            label = f"{manifest['plugin']}:{stack.get('id')}"
            rows = [(e["boundary"], kind, re.compile(e["pattern"], re.I), label)
                    for kind, key in (("text", "boundary_text"), ("path", "boundary_paths")) for e in sec.get(key) or []]
            try:
                cases = json.loads((detect_stack.plugin_root(manifest) / sec["cases"]).read_text(encoding="utf-8"))
            except (OSError, ValueError) as err:
                failures.append(f"{label}: cannot read its cases {sec['cases']}: {err}")
                continue
            shape = case_shape_problems(cases)
            if shape:
                failures.extend(f"{label}: {sec['cases']}: {problem}" for problem in shape)
                continue
            for case in cases:
                ran += 1
                if bool(classify(case["plan"], case["paths"], rows)) != case["boundary"]:
                    failures.append(f"{label}: {case['name']}: expected {'a boundary' if case['boundary'] else 'none'}")
    return failures, ran


def normalise_path(path: str, project: Path | None = None) -> str:
    """A planned path as the stack patterns expect it: trimmed, posix, relative to the project, no `./` or diff `a/` `b/` prefix (#2117 adversary)."""
    p = path.strip().replace("\\", "/")
    if p.startswith("~/"):
        p = str(Path(p).expanduser()).replace("\\", "/")
    if project is not None and p.startswith("/"):
        root = str(project.resolve()).replace("\\", "/").rstrip("/") + "/"
        real = str(Path(p).resolve()).replace("\\", "/")
        for cand in (p, real):
            if cand.startswith(root):
                p = cand[len(root):]
                break
    p = re.sub(r"^[A-Za-z]:/", "", p)
    for _ in range(2):  # strip the prefixes, collapse `x/../` and `//`, then strip what the collapse exposed
        while True:
            for prefix in ("./", "../", "a/", "b/"):
                if p.startswith(prefix) and len(p) > len(prefix):
                    p = p[len(prefix):]
                    break
            else:
                break
        p = posixpath.normpath(p).lstrip("/") if p else p
    return p


def classify(text: str, paths: list[str], stack: list[Row] | tuple = ()) -> list[str]:
    """One line per boundary named, `<boundary>: <what named it>`; empty when none."""
    seen: dict[str, str] = {}
    for name, rx in TEXT:
        m = rx.search(text)
        if m and name not in seen:
            seen[name] = f"plan names `{m.group(0).strip()}`"
    for name, kind, rx, label in stack:
        if kind == "text" and name not in seen and (m := rx.search(text)):
            seen[name] = f"plan names `{m.group(0).strip()}` ({label})"
    for path in (normalise_path(p) for p in paths):
        for name, kind, rx, label in stack:
            if kind == "path" and name not in seen and (rx.search(path) or rx.search(path.rstrip("/") + "/")):
                seen[name] = f"planned path `{path}` ({label})"
    return [f"{name}: {why}" for name, why in seen.items()]


def selftest() -> int:
    cases = [
        ("a plain CRUD plan names nothing", "Add a notes field to the project page and show it in the list.", [], 0),
        ("an upload is a boundary", "Let the requester upload a spreadsheet of enrollees.", [], 1),
        ("a webhook is a boundary", "Receive the Zoho Sign webhook and mark the contract signed.", [], 1),
        ("an MCP tool is a boundary", "Add an MCP tool that lists open requests.", [], 1),
        ("a role change is a boundary", "Staff can now change another user's role.", [], 1),
        ("a token link is a boundary", "Email a magic link that signs the person in.", [], 1),
        ("an outbound fetch of a supplied url is a boundary", "The job fetches the url the user pasted.", [], 1),
        ("a personal column is a boundary", "Store the applicant's date of birth.", [], 1),
        ("a secret is a boundary", "Add the Stripe secret key to the app's credentials.", [], 1),
        ("an encryption key is a boundary", "Store the encryption key for the vault.", [], 1),
        ("parsing partner xml is a boundary", "Parse the XML the partner sends.", [], 1),
        ("parsing a json body into params is a boundary", "Accept a JSON body and parse it into params.", [], 1),
        ("a privacy filter is a boundary", "Hide the salary field from non-managers.", [], 1),
        ("hiding a field from everyone else is a boundary", "Hide the salary field from everyone but HR.", [], 1),
        ("raw html from a partner is a boundary", "Render the partner's HTML in the preview pane.", [], 1),
        ("turning sanitizing off is a boundary", "Disable sanitizing on the comment field.", [], 1),
        ("rendering our own markdown with the sanitizer on is not a boundary", "Render the help page markdown with the sanitizer on.", [], 0),
        ("sending them back to the return url is a boundary", "Send them back to the return URL after payment.", [], 1),
        ("a redirect to a fixed page is not a boundary", "Redirect to the dashboard after save.", [], 0),
        ("raw as a word beside html is a boundary", "Render the comment body as HTML with raw.", [], 1),
        ("a return_to param is a boundary", "Redirect to the return_to param after login.", [], 1),
        ("a next param is a boundary", "Go to the next param once the form saves.", [], 1),
        ("raw totals with no html is not a boundary", "Render the raw totals in a table.", [], 0),
        ("importing a helper module is not a boundary", "Import the shared helper module in the form controller.", [], 0),
        ("a login page css tweak is not a boundary", "Adjust the spacing of the login page button.", [], 0),
        ("documenting the roles is not a boundary", "Document the roles in the README.", [], 0),
        ("importing a spreadsheet is a boundary", "Import the spreadsheet of enrollees.", [], 1),
        ("a word inside another word is not a match", "Add the rolesque helper.", [], 0),
        ("skipping authentication is a boundary", "Skip authentication on the status endpoint.", [], 1),
        ("extending a session is a boundary", "Extend the session to thirty days.", [], 1),
        ("generating an access token is a boundary", "Generate an access token for each partner.", [], 1),
        ("making a page public is a boundary", "Make the report page public.", [], 1),
        ("impersonation is a boundary", "Let support impersonate a user.", [], 1),
        ("design tokens are not a boundary", "Add the spacing tokens from the design system.", [], 0),
        ("remember me is a boundary", "Add a remember-me checkbox.", [], 1),
        ("sign in with a provider is a boundary", "Users sign in with Google.", [], 1),
        ("without logging in is a boundary", "Visitors see the report without logging in.", [], 1),
    ]
    bad = 0
    # STACK-NEUTRAL (#2117): with no stack detected, plain words still fire and a stack's own spelling does not.
    for name, text, paths, want in (
            ("with no stack, a plain-language boundary still fires", "Receive the partner webhook.", [], 1),
            ("with no stack, a stack-only spelling is not named", "Use zap_html here.", [], 0),
            ("with no stack, a stack-only path is not named", "Tidy.", ["hooks/in.py"], 0)):
        got = 1 if classify(text, paths) else 0
        if got != want:
            bad += 1
            print(f"FAIL {name}: expected exit {want}, got {got}")
    # The rows really load from a stack plugin's stacks.json through the detector.
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        plug, proj = Path(td) / "plugins" / "stk", Path(td) / "proj"
        (plug / ".claude-plugin").mkdir(parents=True)
        (plug / ".claude-plugin" / "plugin.json").write_text('{"name": "stk", "version": "1.0.0"}', encoding="utf-8")
        (plug / "sec.md").write_text("# checklist\n", encoding="utf-8")
        (plug / "stacks.json").write_text(
            '{"plugin": "stk", "stacks": [{"id": "s", "name": "S", "all": [{"file": "marker.txt"}], "descriptor": '
            '{"security": {"checklist": "sec.md", "scanners": ["x"], "cases": "cases.json", "boundary_text": [{"boundary": "raw-html", "pattern": "\\\\bzap_html\\\\b"}], '
            '"boundary_paths": [{"boundary": "webhook", "pattern": "^hooks/"}]}}}]}', encoding="utf-8")
        (plug / "cases.json").write_text('[{"name": "an upper-case path is matched by its own stack", "plan": "Tidy.", "paths": ["HOOKS/in.py"], "boundary": true}]', encoding="utf-8")
        own_failures, own_ran = stack_case_failures([plug])
        if own_failures or own_ran != 1:
            bad += 1
            print(f"FAIL a stack's own cases run case-insensitively: ran {own_ran}, {own_failures}")
        good = {"name": "n", "plan": "Tidy.", "paths": [], "boundary": False}
        for name, cases_value, want in (
                ("a well-formed cases file has no shape problem", [good], 0),
                ("an empty cases list is refused", [], 1),
                ("a cases object instead of a list is refused", {"cases": [good]}, 1),
                ("a case with an extra key is refused", [{**good, "note": "x"}], 1),
                ("a case missing a key is refused", [{k: v for k, v in good.items() if k != "plan"}], 1),
                ("a string boundary is refused", [{**good, "boundary": "true"}], 1),
                ("an integer boundary is refused", [{**good, "boundary": 1}], 1),
                ("a string paths is refused", [{**good, "paths": "app/x.ts"}], 1),
                ("a non-string path is refused", [{**good, "paths": [3]}], 1),
                ("an empty path is refused", [{**good, "paths": [" "]}], 1),
                ("a blank name is refused", [{**good, "name": " "}], 1),
                ("a repeated name is refused", [good, dict(good)], 1)):
            got = 1 if case_shape_problems(cases_value) else 0
            if got != want:
                bad += 1
                print(f"FAIL {name}: expected {want}, got {case_shape_problems(cases_value)}")
        (plug / "cases.json").write_text('[{"name": "x", "plan": "Tidy.", "paths": [], "boundary": false, "extra": 1}]', encoding="utf-8")
        shaped, shaped_ran = stack_case_failures([plug])
        if shaped_ran != 0 or not any("must be exactly" in f for f in shaped):
            bad += 1
            print(f"FAIL a stack whose cases break the shape fails without running them: ran {shaped_ran}, {shaped}")
        proj.mkdir()
        (proj / "marker.txt").write_text("x", encoding="utf-8")
        rows, notes = stack_rows(proj, [plug])
        link = Path(td) / "link"
        link.symlink_to(proj, target_is_directory=True)
        for name, ok in (("a stack's boundary_text loads and fires", bool(classify("Use zap_html here.", [], rows))),
                         ("a stack's boundary_paths loads and fires", bool(classify("Tidy.", ["hooks/in.py"], rows))),
                         ("and nothing fires without them", not classify("Use zap_html here.", ["hooks/in.py"])),
                         ("the note names the rows used", notes == ["stack rows: 2 from stk:s"]),
                         ("a ./ path is matched", bool(classify("Tidy.", ["./hooks/in.py"], rows))),
                         ("a diff b/ path is matched", bool(classify("Tidy.", ["b/hooks/in.py"], rows))),
                         ("a backslash path is matched", bool(classify("Tidy.", ["hooks\\in.py"], rows))),
                         ("an unresolved absolute path (a symlinked temp root) is matched",
                          bool(classify("Tidy.", [normalise_path(str(link / "hooks" / "in.py"), proj)], rows))),
                         ("a ../ path is matched", bool(classify("Tidy.", ["../hooks/in.py"], rows))),
                         ("a drive-letter path is matched", bool(classify("Tidy.", ["C:\\hooks\\in.py"], rows))),
                         ("a path in another case is matched", bool(classify("Tidy.", ["Hooks/in.py"], rows))),
                         ("a dot-dot inside a path is collapsed", bool(classify("Tidy.", ["docs/../hooks/in.py"], rows))),
                         ("a leading double slash is matched", bool(classify("Tidy.", ["//hooks/in.py"], rows))),
                         ("a directory without its slash is matched", bool(classify("Tidy.", ["hooks"], rows))),
                         ("a padded path is matched", bool(classify("Tidy.", ["  hooks/in.py\n"], rows))),
                         ("an absolute path inside the project is matched", bool(classify("Tidy.", [normalise_path(str(proj.resolve() / "hooks/in.py"), proj)], rows)))):
            if not ok:
                bad += 1
                print(f"FAIL {name}: rows={rows} notes={notes}")
    for name, text, paths, want in cases:
        got = 1 if classify(text, paths) else 0
        if got != want:
            bad += 1
            print(f"FAIL {name}: expected exit {want}, got {got}")
    # The exit codes of main(): 2 is "could not classify", never 0 (an unknown plan is not "no boundary").
    for name, argv, want in (("no input at all is exit 2", [], 2), ("an unreadable plan is exit 2", ["--plan", "/nonexistent/plan.md"], 2),
                             ("a path alone is classified", ["--path", "docs/notes.md"], 0)):
        got = main(argv)
        if got != want:
            bad += 1
            print(f"FAIL {name}: expected exit {want}, got {got}")
    # Every stack this script can see proves its own spellings with its own cases (none in a tree with no stack plugin).
    stack_failures, stack_ran = stack_case_failures(__import__("detect_stack").manifest_dirs(Path(__file__).resolve()))
    for failure in stack_failures:
        bad += 1
        print(f"FAIL {failure}")
    if bad == 0:
        print(f"security_scope selftest: {len(cases)} cases, {stack_ran} stack case(s) and the exit codes pass")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan")
    ap.add_argument("--path", action="append", default=[])
    ap.add_argument("--project", default=".", help="the project whose stacks add their boundary patterns (default: .)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    text = ""
    if args.plan:
        try:
            text = Path(args.plan).read_text(encoding="utf-8")
        except OSError as e:
            print(f"cannot read --plan {args.plan}: {e}", file=sys.stderr)
            return 2
    if not text.strip() and not args.path:
        print("nothing to classify: give --plan FILE and/or --path P", file=sys.stderr)
        return 2
    rows, notes = stack_rows(Path(args.project))
    for note in notes:
        print(note, file=sys.stderr)
    found = classify(text, [normalise_path(p, Path(args.project)) for p in args.path], rows)
    if found:
        print("\n".join(found))
        return 1
    print("no new boundary named")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
