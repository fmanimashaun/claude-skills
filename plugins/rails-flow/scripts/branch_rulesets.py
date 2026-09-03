#!/usr/bin/env python3
"""branch_rulesets.py -- the release branch merges, never squashes: assert (and on request create) the
GitHub ruleset that makes the rule a mechanism (#895).

WHY. `gh pr merge --merge` is doctrine for a dev -> main promotion, but the Merge button's default is
whatever the repository allows. On 2026-09-03 a promotion was squash-merged from the UI: content
identical, ancestry gone, and the NEXT promotion would have conflicted on files nobody edited twice.
The doctor caught it after the fact; a ruleset prevents it. A rule a human can forget is advice; a
ruleset is a guarantee (docs/doctrine/harness-doctrine.md's test).

WHAT IT ASSERTS on the release branch (default `main`, else the repo's default branch):
  an ACTIVE branch ruleset whose conditions include the branch and whose rules carry
    - pull_request with allowed_merge_methods == ["merge"]     (no squash, no rebase)
    - deletion                                                  (the branch cannot be deleted)
    - non_fast_forward                                          (no force-push)

  --check          exit 0 when every piece is present; 1 with each missing piece named; 3 not applicable
  --apply          create the ruleset when NONE covers the branch (never edits someone else's ruleset:
                   a partial one is reported with the pieces to add, and left alone)
  --from FILE      read the rulesets JSON from FILE instead of the API (fixtures; the doctor's selftest)
  --repo O/N       override the slug derived from `origin`
  --branch B       override the release branch
  --json           the verdict as JSON
  --selftest

NOT APPLICABLE is exit 3 and never a pass: no `gh`, `gh` unauthenticated, no GitHub remote (a local or
non-GitHub `origin`), or the API unreachable. Stdlib + `gh`; no tokens handled here.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

REQUIRED_RULES = ("pull_request", "deletion", "non_fast_forward")
ALLOWED_METHODS = ["merge"]
RULESET_NAME = "{branch}: promotions merge, never squash"

Runner = Callable[[list[str]], tuple[int, str]]


def _gh(args: list[str]) -> tuple[int, str]:
    if shutil.which("gh") is None:
        return 127, "gh not installed"
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    return r.returncode, (r.stdout if r.returncode == 0 else (r.stderr or r.stdout))


def repo_slug(root: Path) -> str | None:
    """owner/name from `origin`, for github.com remotes only -- a local or non-GitHub origin is n/a."""
    r = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    m = re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", r.stdout.strip())
    return f"{m.group(1)}/{m.group(2)}" if m else None


def default_branch(slug: str, gh: Runner) -> str:
    code, out = gh(["api", f"repos/{slug}", "--jq", ".default_branch"])
    return out.strip() if code == 0 and out.strip() else "main"


# ----------------------------------------------------------------------------- the verdict

def covers(ruleset: dict, branch: str) -> bool:
    """Does this ruleset's condition include the branch? `~DEFAULT_BRANCH` and `~ALL` count; a name
    glob like `refs/heads/release/*` is matched with fnmatch."""
    import fnmatch
    if ruleset.get("target") != "branch" or ruleset.get("enforcement") != "active":
        return False
    ref = (ruleset.get("conditions") or {}).get("ref_name") or {}
    includes, excludes = ref.get("include") or [], ref.get("exclude") or []
    full = f"refs/heads/{branch}"
    def hit(pats): return any(p in ("~ALL",) or (p == "~DEFAULT_BRANCH" and branch in ("main", "master")) or fnmatch.fnmatch(full, p) for p in pats)
    return hit(includes) and not hit(excludes)


def verdict(rulesets: list[dict], branch: str) -> dict:
    """{ok, covering: [names], present: {rule: bool}, missing: [str], methods: [..]|None}."""
    covering = [r for r in rulesets if covers(r, branch)]
    present = {name: False for name in REQUIRED_RULES}
    methods = None
    for r in covering:
        for rule in r.get("rules") or []:
            t = rule.get("type")
            if t == "pull_request":
                methods = (rule.get("parameters") or {}).get("allowed_merge_methods")
                if methods is not None and sorted(methods) == sorted(ALLOWED_METHODS):
                    present["pull_request"] = True
            elif t in present:
                present[t] = True
    missing = []
    if not covering:
        missing.append(f"no active branch ruleset covers refs/heads/{branch}")
    else:
        if not present["pull_request"]:
            missing.append(f"pull_request rule allowing ONLY merge (found allowed_merge_methods={methods!r})")
        if not present["deletion"]:
            missing.append("deletion rule (the branch can be deleted)")
        if not present["non_fast_forward"]:
            missing.append("non_fast_forward rule (the branch can be force-pushed)")
    return {"ok": not missing, "branch": branch, "covering": [r.get("name", "?") for r in covering],
            "present": present, "missing": missing, "methods": methods}


def ruleset_body(branch: str) -> dict:
    return {"name": RULESET_NAME.format(branch=branch), "target": "branch", "enforcement": "active",
            "conditions": {"ref_name": {"include": [f"refs/heads/{branch}"], "exclude": []}},
            "rules": [{"type": "deletion"}, {"type": "non_fast_forward"},
                      {"type": "pull_request", "parameters": {"allowed_merge_methods": ALLOWED_METHODS,
                        "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": False,
                        "require_code_owner_review": False, "require_last_push_approval": False,
                        "required_review_thread_resolution": False}}]}


def fetch_rulesets(slug: str, gh: Runner) -> tuple[list[dict] | None, str]:
    """The full rulesets (the list endpoint omits rules; each is fetched by id). None + reason on n/a."""
    code, out = gh(["api", f"repos/{slug}/rulesets"])
    if code != 0:
        return None, out.strip()[:200] or "gh api failed"
    try:
        listing = json.loads(out or "[]")
    except json.JSONDecodeError:
        return None, "rulesets listing was not JSON"
    full = []
    for r in listing:
        code, detail = gh(["api", f"repos/{slug}/rulesets/{r['id']}"])
        if code != 0:
            return None, f"ruleset {r.get('id')} unreadable: {detail.strip()[:120]}"
        full.append(json.loads(detail))
    return full, ""


# ----------------------------------------------------------------------------- CLI

def main(argv: list[str], gh: Runner = _gh, post: Callable[[str, str, Runner], tuple[int, str]] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--apply", action="store_true", help="create the ruleset when none covers the branch")
    ap.add_argument("--from", dest="from_file", help="read rulesets JSON from a file instead of the API")
    ap.add_argument("--repo", help="owner/name (default: from origin)")
    ap.add_argument("--branch", help="release branch (default: main, else the repo's default branch)")
    ap.add_argument("--root", default=".")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    root = Path(a.root)
    slug = a.repo or repo_slug(root)
    if a.from_file:
        try:
            rulesets = json.loads(Path(a.from_file).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"cannot read {a.from_file}: {exc}", file=sys.stderr)
            return 2
        branch = a.branch or "main"
    else:
        if slug is None:
            print("n/a: `origin` is not a github.com remote (or there is none) — rulesets live on GitHub")
            return 3
        if shutil.which("gh") is None:
            print("n/a: `gh` is not installed — the ruleset cannot be read; install gh and `gh auth login`")
            return 3
        code, out = gh(["auth", "status"])
        if code != 0:
            print("n/a: `gh` is not authenticated — `gh auth login`")
            return 3
        branch = a.branch or ("main" if gh(["api", f"repos/{slug}/branches/main", "--jq", ".name"])[0] == 0 else default_branch(slug, gh))
        rulesets, why = fetch_rulesets(slug, gh)
        if rulesets is None:
            print(f"n/a: could not read rulesets for {slug}: {why}")
            return 3
    v = verdict(rulesets, branch)
    if a.apply and not v["ok"]:
        if v["covering"]:
            print(f"a ruleset already covers {branch} ({', '.join(v['covering'])}) but lacks: " + "; ".join(v["missing"]))
            print("not editing someone else's ruleset — add the missing rules to it in Settings → Rules, or delete it and re-run --apply")
            return 1
        if a.from_file:
            print("--apply needs the API, not --from")
            return 2
        body = json.dumps(ruleset_body(branch))
        code, out = (post or _post)(slug, body, gh)
        if code != 0:
            print(f"creating the ruleset failed: {out.strip()[:200]}", file=sys.stderr)
            return 2
        rulesets, why = fetch_rulesets(slug, gh)
        v = verdict(rulesets or [], branch)
        print(f"created ruleset {RULESET_NAME.format(branch=branch)!r} on {slug}")
    if a.json:
        print(json.dumps(v, indent=2))
        return 0 if v["ok"] else 1
    if v["ok"]:
        print(f"ok: {branch} is covered by {', '.join(v['covering'])} — PRs merge only, no deletion, no force-push")
        return 0
    for m in v["missing"]:
        print(f"- {m}")
    print(f"\n{len(v['missing'])} missing on {branch}. `--apply` creates the ruleset when none covers the branch; a squash-merged promotion breaks the next one.")
    return 1


def _post(slug: str, body: str, gh: Runner) -> tuple[int, str]:
    """POST through gh with the body on stdin -- kept separate so the selftest can stub it."""
    if shutil.which("gh") is None:
        return 127, "gh not installed"
    r = subprocess.run(["gh", "api", "-X", "POST", f"repos/{slug}/rulesets", "--input", "-"], input=body, capture_output=True, text=True)
    return r.returncode, r.stdout if r.returncode == 0 else (r.stderr or r.stdout)


# ----------------------------------------------------------------------------- selftest

def selftest() -> int:
    import tempfile
    n, failures = 0, []

    def check(label: str, ok: bool, detail: str = "") -> None:
        nonlocal n
        n += 1
        if not ok:
            failures.append(f"{label}{(' — ' + detail) if detail else ''}")

    good = ruleset_body("main"); good.update({"id": 1})
    check("the ruleset this tool creates satisfies its own check", verdict([good], "main")["ok"])
    check("no ruleset at all: one finding naming the branch", verdict([], "main")["missing"] == ["no active branch ruleset covers refs/heads/main"])
    squash = json.loads(json.dumps(good)); squash["rules"][2]["parameters"]["allowed_merge_methods"] = ["merge", "squash"]
    v = verdict([squash], "main")
    check("a ruleset that still allows squash is not ok, and says which methods it found",
          not v["ok"] and any("allowed_merge_methods=['merge', 'squash']" in m for m in v["missing"]) and v["present"]["deletion"], str(v))
    no_del = json.loads(json.dumps(good)); no_del["rules"] = [r for r in no_del["rules"] if r["type"] != "deletion"]
    check("a missing deletion rule is named", verdict([no_del], "main")["missing"] == ["deletion rule (the branch can be deleted)"])
    inactive = json.loads(json.dumps(good)); inactive["enforcement"] = "disabled"
    check("a disabled ruleset does not count", not verdict([inactive], "main")["ok"])
    other = json.loads(json.dumps(good)); other["conditions"]["ref_name"]["include"] = ["refs/heads/dev"]
    check("a ruleset on another branch does not count", not verdict([other], "main")["ok"])
    dflt = json.loads(json.dumps(good)); dflt["conditions"]["ref_name"]["include"] = ["~DEFAULT_BRANCH"]
    check("~DEFAULT_BRANCH covers main", verdict([dflt], "main")["ok"] and not verdict([dflt], "release")["ok"])
    excl = json.loads(json.dumps(good)); excl["conditions"]["ref_name"]["include"] = ["~ALL"]; excl["conditions"]["ref_name"]["exclude"] = ["refs/heads/main"]
    check("an exclude beats an include", not verdict([excl], "main")["ok"])
    check("slugs parse from ssh and https origins, and a local path is not a GitHub remote",
          re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", "git@github.com:o/n.git").group(2) == "n"
          and re.search(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?/?$", "https://github.com/o/n").group(1) == "o")

    with tempfile.TemporaryDirectory() as td:
        f = Path(td) / "rs.json"
        f.write_text(json.dumps([good]), encoding="utf-8")
        check("--check --from a conforming file exits 0", main(["--check", "--from", str(f)]) == 0)
        f.write_text("[]", encoding="utf-8")
        check("--check --from an empty list exits 1", main(["--check", "--from", str(f)]) == 1)
        check("--apply with --from is refused (exit 2): creation needs the API", main(["--apply", "--from", str(f)]) == 2)
        import contextlib, io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--check", "--from", str(f), "--json"])
        check("--json prints the verdict", rc == 1 and json.loads(buf.getvalue())["missing"])
        # a local origin is not GitHub: n/a, never a pass -- built as a real repo so repo_slug runs
        repo = Path(td) / "proj"; repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "remote", "add", "origin", str(Path(td) / "bare.git")], cwd=repo, check=True)
        def gh_any(args):
            if args[:2] == ["auth", "status"]: return (0, "ok")
            return (0, "[]") if args[1].endswith("/rulesets") else (0, "main")
        check("a non-GitHub origin is n/a (exit 3) before any gh call, not the exit-1 an API answer would give",
              main(["--check", "--root", str(repo)], gh=gh_any) == 3)
        # the API path with a stubbed gh: unauthenticated -> 3; authenticated with rulesets -> verdict
        calls: list[list[str]] = []
        def gh_unauth(args):
            calls.append(args)
            if args[:2] == ["auth", "status"]: return (1, "not logged in")
            if args[1].endswith("/branches/main"): return (0, "main")
            return (0, "[]")                                  # the API would answer -- only auth is the reason for n/a
        check("gh unauthenticated is n/a (exit 3), not the exit-1 the empty rulesets would give", main(["--check", "--repo", "o/n"], gh=gh_unauth) == 3)
        def gh_ok(args):
            calls.append(args)
            if args[:2] == ["auth", "status"]: return (0, "ok")
            if args[1].endswith("/branches/main"): return (0, "main")
            if args[1].endswith("/rulesets"): return (0, json.dumps([{"id": 7}]))
            if args[1].endswith("/rulesets/7"): return (0, json.dumps(good))
            return (1, "unexpected " + " ".join(args))
        check("the API path fetches each ruleset by id and passes on a conforming one", main(["--check", "--repo", "o/n"], gh=gh_ok) == 0
              and any(a[1].endswith("/rulesets/7") for a in calls))
        def gh_none(args):
            if args[:2] == ["auth", "status"]: return (0, "ok")
            if args[1].endswith("/branches/main"): return (0, "main")
            if args[1].endswith("/rulesets"): return (0, "[]")
            return (1, "unexpected")
        check("the API path with no rulesets fails (exit 1)", main(["--check", "--repo", "o/n"], gh=gh_none) == 1)
        def gh_partial(args):
            if args[:2] == ["auth", "status"]: return (0, "ok")
            if args[1].endswith("/branches/main"): return (0, "main")
            if args[1].endswith("/rulesets"): return (0, json.dumps([{"id": 9}]))
            if args[1].endswith("/rulesets/9"): return (0, json.dumps(squash))
            return (1, "unexpected")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--apply", "--repo", "o/n"], gh=gh_partial)
        check("--apply never edits someone else's ruleset: a partial one is reported, exit 1, nothing posted",
              rc == 1 and "not editing" in buf.getvalue())
        posted: list[str] = []
        state = {"rulesets": []}
        def gh_live(args):
            if args[:2] == ["auth", "status"]: return (0, "ok")
            if args[1].endswith("/branches/main"): return (0, "main")
            if args[1].endswith("/rulesets"): return (0, json.dumps([{"id": i + 1} for i in range(len(state["rulesets"]))]))
            m = re.search(r"/rulesets/(\d+)$", args[1])
            if m: return (0, json.dumps(state["rulesets"][int(m.group(1)) - 1]))
            return (1, "unexpected " + " ".join(args))
        def fake_post(slug, body, gh):
            posted.append(body); created = json.loads(body); created["id"] = 1; state["rulesets"].append(created); return (0, json.dumps(created))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["--apply", "--repo", "o/n"], gh=gh_live, post=fake_post)
        check("--apply with nothing covering the branch posts exactly one ruleset with the three rules, then re-reads and passes",
              rc == 0 and len(posted) == 1 and [r["type"] for r in json.loads(posted[0])["rules"]] == ["deletion", "non_fast_forward", "pull_request"]
              and json.loads(posted[0])["rules"][2]["parameters"]["allowed_merge_methods"] == ["merge"] and "created ruleset" in buf.getvalue(), buf.getvalue()[:200])

    for fl in failures:
        print(f"FAIL {fl}")
    print(f"branch_rulesets selftest: {n} checks, {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
