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
supplied; an authentication, session or role change; a new personal-data column; a job fed by outside data; a secret or key; parsing of input from outside; raw HTML rendered from outside; a redirect to a supplied URL; an access rule or privacy filter. The pattern lists below
are the whole definition.

LIMITS. A keyword scan over prose and paths. The auth words only count after a change verb ("add a role", "let staff reset a password"), so a plan that
only mentions a login page or documents the roles stays quiet; "import" counts only with a file or data noun. It still over-fires on "parse the JSON
config we ship" and on prose about "credentials", and under-fires on a boundary the
plan never names. It says "owed", never "done", and cannot make the model that follows it honest. A reviewer who sees a boundary it
missed runs the command by hand.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# (boundary, what in the PLAN TEXT names it)
TEXT: tuple[tuple[str, re.Pattern], ...] = (
    ("public-route", re.compile(r"\b(?:public (?:route|page|endpoint|url|link)|unauthenticated|token (?:link|url|route)|magic link|signed (?:link|url)|allow_unauthenticated_access)\b", re.I)),
    ("upload-import", re.compile(r"\b(?:uploads?|csv|file input|attachments?|has_(?:one|many)_attached|multipart|(?:bulk |data )import|imports? (?:an? |the |their |that |this )?(?:files?|csv|spreadsheets?|data|records?|rows?))\b", re.I)),
    ("webhook", re.compile(r"\bwebhooks?\b|\bcallback (?:url|endpoint)\b", re.I)),
    ("mcp-tool", re.compile(r"\bmcp\b|\bmodel context protocol\b", re.I)),
    ("outbound-fetch", re.compile(r"\b(?:outbound (?:fetch|request|call)|fetch(?:es)? (?:a |the )?url|downloads? from (?:a )?url|net::http|faraday|open-uri|ssrf)\b", re.I)),
    ("auth-session-role", re.compile(r"\b(?:add|adds|adding|new|change|changes|changing|replace|remove|grant|revoke|let|lets|allow|allows|enable|rotate|reset|expire|invalidate|issue|implement|build|create|require|enforce|restrict|support|switch|migrate)\b[^.\n]{0,50}\b(?:sign[- ]?in|log[- ]?in|sessions?|passwords?|sso|oauth|omniauth|two[- ]factor|2fa|roles?|permissions?|authori[sz]ation|api (?:key|token))\b", re.I)),
    ("secrets", re.compile(r"\b(?:secrets?|credentials|(?:encryption|signing|private|master|secret) keys?|api[_ ]?keys?|encrypts|has_secure_password|(?:store|storing) (?:the |a )?tokens?)\b", re.I)),
    ("input-parsing", re.compile(r"\bparse[sd]?\b[^.\n]{0,40}\b(?:xml|json|yaml|html|payload|body|params|headers?|input)\b|\b(?:deserializ\w*|unmarshal\w*|yaml\.load|marshal\.load)", re.I)),
    ("raw-html", re.compile(r"\bhtml_safe\b|\braw\(|<%==?\s*raw\b|\b(?:skip|disable|turn off|without)\s+sanitiz\w*|\bsanitiz\w*\s+(?:off|disabled)\b|\brender\w*\s+(?:the |a |an )?(?:partner|user|customer|external|supplied|uploaded|third[- ]party)(?:'s|s')?\s+(?:raw )?html\b", re.I)),
    ("redirect-param", re.compile(r"\bredirect_to\s*\(?\s*params\b|\breturn[_ ]url\b|\bsend (?:them|the user|the person) back to (?:the |a )?(?:url|link|page) (?:in|from|they|the user)|\bredirects? (?:back )?to (?:a |the )?(?:param|url the user|url (?:in|from) the)", re.I)),
    ("access-rule", re.compile(r"\bonly [a-z ]{1,30} (?:can|may)\b|\b(?:hide|restrict|mask|redact|limit)\b[^.\n]{0,40}\b(?:field|column|attribute|salary|data|record)s?\b[^.\n]{0,30}\b(?:from|to|for)\b|\bnon-(?:admin|manager|staff|owner)s?\b", re.I)),
    ("personal-data", re.compile(r"\b(?:personal (?:data|information|field)s?|pii|date of birth|dob|phone number|email address|national id|bank (?:detail|account)s?|health data)\b", re.I)),
    ("outside-data-job", re.compile(r"\bjobs?\b[^.\n]{0,60}\b(?:from|fed by|reads?|processes?)\b[^.\n]{0,40}\b(?:webhook|upload|import|external|outside|api|csv)\b", re.I)),
)
# (boundary, which PLANNED PATH names it)
PATHS: tuple[tuple[str, re.Pattern], ...] = (
    ("public-route", re.compile(r"^app/controllers/(?:public|pages|home)_controller\.rb$")),
    ("webhook", re.compile(r"^app/controllers/(?:[^/]+/)*webhooks?/|_webhooks?_controller\.rb$")),
    ("mcp-tool", re.compile(r"^app/(?:[^/]+/)*mcp/")),
    ("auth-session-role", re.compile(r"^app/controllers/concerns/authentication\.rb$|^app/controllers/(?:sessions|passwords|registrations|omniauth_callbacks)_controller\.rb$|^app/(?:policies|abilities?)/|^app/models/(?:session|current|role)\.rb$")),
    ("upload-import", re.compile(r"^app/(?:[^/]+/)*uploads?/|^app/(?:models|services|jobs)/(?:[^/]+/)*[^/]*(?:import|intake|upload)[^/]*\.rb$")),
    ("api", re.compile(r"^app/controllers/api/")),
)


def classify(text: str, paths: list[str]) -> list[str]:
    """One line per boundary named, `<boundary>: <what named it>`; empty when none."""
    seen: dict[str, str] = {}
    for name, rx in TEXT:
        m = rx.search(text)
        if m and name not in seen:
            seen[name] = f"plan names `{m.group(0).strip()}`"
    for path in paths:
        for name, rx in PATHS:
            if rx.search(path) and name not in seen:
                seen[name] = f"planned path `{path}`"
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
        ("a planned auth path is a boundary even when the prose is silent", "Tidy the controller.", ["app/controllers/sessions_controller.rb"], 1),
        ("a planned webhook path is a boundary", "Tidy.", ["app/controllers/webhooks/zoho_sign_controller.rb"], 1),
        ("a spec path is not a boundary", "Tidy.", ["spec/requests/sessions_spec.rb"], 0),
        ("a secret is a boundary", "Add the Stripe secret key to Rails credentials.", [], 1),
        ("an encryption key is a boundary", "Store the encryption key for the vault.", [], 1),
        ("encrypts is a boundary", "Encrypt the notes column with encrypts.", [], 1),
        ("parsing partner xml is a boundary", "Parse the XML the partner sends.", [], 1),
        ("parsing a json body into params is a boundary", "Accept a JSON body and parse it into params.", [], 1),
        ("a privacy filter is a boundary", "Hide the salary field from non-managers.", [], 1),
        ("hiding a field from everyone else is a boundary", "Hide the salary field from everyone but HR.", [], 1),
        ("raw html from a partner is a boundary", "Render the partner's HTML in the preview pane.", [], 1),
        ("html_safe is a boundary", "Mark the note body html_safe so links work.", [], 1),
        ("turning sanitizing off is a boundary", "Disable sanitizing on the comment field.", [], 1),
        ("rendering our own markdown with the sanitizer on is not a boundary", "Render the help page markdown with the sanitizer on.", [], 0),
        ("a redirect to a param is a boundary", "After sign-out, redirect_to params[:next].", [], 1),
        ("sending them back to the return url is a boundary", "Send them back to the return URL after payment.", [], 1),
        ("a redirect to a fixed page is not a boundary", "Redirect to the dashboard after save.", [], 0),
        ("importing a helper module is not a boundary", "Import the shared helper module in the form controller.", [], 0),
        ("a login page css tweak is not a boundary", "Adjust the spacing of the login page button.", [], 0),
        ("documenting the roles is not a boundary", "Document the roles in the README.", [], 0),
        ("importing a spreadsheet is a boundary", "Import the spreadsheet of enrollees.", [], 1),
        ("a word inside another word is not a match", "Add the rolesque helper.", [], 0),
    ]
    bad = 0
    for name, text, paths, want in cases:
        got = 1 if classify(text, paths) else 0
        if got != want:
            bad += 1
            print(f"FAIL {name}: expected exit {want}, got {got}")
    # The exit codes of main(): 2 is "could not classify", never 0 (an unknown plan is not "no boundary").
    for name, argv, want in (("no input at all is exit 2", [], 2), ("an unreadable plan is exit 2", ["--plan", "/nonexistent/plan.md"], 2),
                             ("a path alone is classified", ["--path", "spec/x_spec.rb"], 0)):
        got = main(argv)
        if got != want:
            bad += 1
            print(f"FAIL {name}: expected exit {want}, got {got}")
    if bad == 0:
        print(f"security_scope selftest: {len(cases)} cases and the exit codes pass")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan")
    ap.add_argument("--path", action="append", default=[])
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
    found = classify(text, args.path)
    if found:
        print("\n".join(found))
        return 1
    print("no new boundary named")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
