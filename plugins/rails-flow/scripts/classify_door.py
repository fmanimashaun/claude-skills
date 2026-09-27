#!/usr/bin/env python3
"""Classify a branch's diff as a one-way door (a human merges it) or a two-way door (#1338).

Run:  classify_door.py [--base dev] [--root DIR]    # 0 two-way · 1 one-way · 2 cannot classify
      classify_door.py --selftest

WHY. On a CLEAN review, a PR into `dev` merges without a human. That is right for a change you can
undo with a revert. It is wrong for one you cannot: a dropped column's data does not come back with
`git revert`, and a permission loosened on dev is live on every staging deploy until someone notices.
A human was only ever asked at `dev -> main`, after the irreversible part had already happened.

DETERMINISTIC ON PURPOSE. "Does this look reversible?" is the judgement a model gets wrong
differently every run. Each trigger below is a pattern over the diff, stated so a reviewer can see
exactly why a PR was held:
  * migration     a db/migrate file adding remove_column, drop_table, rename_column, change_column,
                  remove_reference, change_column_null false, execute, or a data backfill
                  (update_all / update_columns / in_batches)
  * access        a change to the authentication concern, app/policies/, or an authorization
                  initializer
  * contract      a route removed from config/routes.rb, or a line removed from a serializer or a
                  .json.jbuilder view (a field an API client may read)
  * outbound      a new call to an outside service: Net::HTTP, Faraday, HTTParty, RestClient, Excon,
                  URI.open, or a webhook deliverer
Everything else is two-way. A trigger is not a veto: it moves the merge decision to a human.

Exit 2 is never two-way. If the base cannot be resolved the diff is unknown, and an unknown change
does not merge by itself.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

# The trailing \b is what keeps `change_column_default` / `change_column_comment` (reversible) out: `_`
# is a word character, so `change_column\b` cannot match inside them. The CONTROL fixture pins it.
MIGRATION = re.compile(r"\b(remove_column|drop_table|rename_column|change_column|"
                       r"remove_reference|remove_belongs_to|execute|update_all|update_columns|in_batches)\b"
                       r"|change_column_null\s*\(?[^)\n]*,\s*false")
ACCESS_PATHS = (re.compile(r"^app/controllers/concerns/authentication\.rb$"), re.compile(r"^app/policies/"),
                re.compile(r"^config/initializers/[^/]*(auth|devise|pundit|rack_attack|permission)[^/]*\.rb$"))
ROUTE_LINE = re.compile(r"^\s*(get|post|patch|put|delete|match|resources?|namespace|scope|mount|root)\b")
CONTRACT_PATHS = (re.compile(r"^app/serializers/"), re.compile(r"\.json\.jbuilder$"))
OUTBOUND = re.compile(r"\b(Net::HTTP|Faraday|HTTParty|RestClient|Excon|URI\.open)\b|Webhook\w*\.(deliver|post)")


class Unusable(RuntimeError):
    pass


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise Unusable(f"git {' '.join(args)}: {proc.stderr.strip() or 'failed'}")
    return proc.stdout


def diff(root: Path, base: str) -> dict[str, tuple[list[str], list[str]]]:
    """path -> (added lines, removed lines) for base...HEAD, including uncommitted and untracked work."""
    _git(root, "rev-parse", "--verify", "-q", f"{base}^{{commit}}")
    merge_base = _git(root, "merge-base", base, "HEAD").strip()
    out: dict[str, tuple[list[str], list[str]]] = {}
    path = None
    for line in _git(root, "diff", "--no-color", "-U0", merge_base).splitlines():
        if line.startswith("diff --git "):
            path = line.split(" b/", 1)[1] if " b/" in line else None
            if path is not None:
                out.setdefault(path, ([], []))
        elif path is None or line.startswith(("+++", "---", "@@", "index ", "new file", "deleted file")):
            continue
        elif line.startswith("+"):
            out[path][0].append(line[1:])
        elif line.startswith("-"):
            out[path][1].append(line[1:])
    # A new, not-yet-added file is in no `git diff` output at all (the #1341 blind spot): a fresh
    # migration or policy would read as two-way. Every untracked, not-ignored file counts as added.
    for rel in _git(root, "ls-files", "--others", "--exclude-standard").splitlines():
        try:
            out[rel] = ((root / rel).read_text(encoding="utf-8").splitlines(), [])
        except (OSError, UnicodeDecodeError):
            out[rel] = ([], [])
    return out


def classify(changes: dict[str, tuple[list[str], list[str]]]) -> list[str]:
    reasons = []
    for path, (added, removed) in sorted(changes.items()):
        if path.startswith("db/migrate/"):
            hits = sorted({m.group(0).split("(")[0].strip() for line in added for m in [MIGRATION.search(line)] if m})
            if hits:
                reasons.append(f"migration  {path}: {', '.join(hits)}")
        if any(p.search(path) for p in ACCESS_PATHS):
            reasons.append(f"access     {path}: authentication or authorization changed")
        if path == "config/routes.rb":
            gone = [l.strip() for l in removed if ROUTE_LINE.match(l)]
            if gone:
                reasons.append(f"contract   {path}: route removed ({gone[0][:60]})")
        if any(p.search(path) for p in CONTRACT_PATHS) and any(l.strip() for l in removed):
            reasons.append(f"contract   {path}: a field an API client may read was removed or changed")
        if path.endswith(".rb") and not path.startswith(("spec/", "test/")):
            if any(OUTBOUND.search(l) for l in added):
                reasons.append(f"outbound   {path}: a new call to an outside service")
    return reasons


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="classify_door.py", description=__doc__.splitlines()[0])
    ap.add_argument("--base", default="dev")
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    try:
        reasons = classify(diff(a.root, a.base))
    except Unusable as exc:
        print(f"UNUSABLE: {exc} -- an unclassified change is not two-way; hand the merge to a human", file=sys.stderr)
        return 2
    if reasons:
        print(f"ONE-WAY DOOR ({len(reasons)} reason(s)) -- stop after CLEAN and hand the merge to a human:")
        print("\n".join(f"  {r}" for r in reasons))
        return 1
    print(f"TWO-WAY DOOR -- nothing in {a.base}...HEAD is irreversible by these rules")
    return 0


def selftest() -> int:
    import tempfile

    failures: list[str] = []

    def expect(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        g = lambda *a: subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", *a], cwd=root,
                                      check=True, capture_output=True, text=True)
        g("init", "-q", "-b", "dev")
        (root / "config").mkdir()
        (root / "config/routes.rb").write_text("Rails.application.routes.draw do\n  resources :invoices\n  get :health\nend\n")
        (root / "app/serializers").mkdir(parents=True)
        (root / "app/serializers/invoice_serializer.rb").write_text("attributes :id, :total\n")
        (root / "app/services").mkdir(parents=True)
        (root / "app/services/pay.rb").write_text("class Pay\nend\n")
        g("add", "."); g("commit", "-q", "-m", "base")
        g("checkout", "-q", "-b", "feature/x")

        def case(files: dict[str, str], label: str, want: str | None) -> None:
            for rel, body in files.items():
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(body)
            reasons = classify(diff(root, "dev"))
            ok = (not reasons) if want is None else any(r.startswith(want) for r in reasons)
            expect(label, ok, str(reasons))
            # Reset the throwaway repo between cases (it lives in a tempdir; nothing here touches a real tree).
            g("add", "."); g("reset", "-q", "--hard", "HEAD")

        case({"db/migrate/20260926_add_x.rb": "add_column :invoices, :x, :string\n"},
             "CONTROL: an add_column migration is two-way", None)
        case({"db/migrate/20260926_drop_x.rb": "remove_column :invoices, :total\n"}, "remove_column is one-way", "migration")
        case({"db/migrate/20260926_ren.rb": "rename_column :invoices, :a, :b\n"}, "rename_column is one-way", "migration")
        case({"db/migrate/20260926_null.rb": "change_column_null :invoices, :x, false\n"},
             "change_column_null to false is one-way", "migration")
        case({"db/migrate/20260926_def.rb": "change_column_default :invoices, :x, from: nil, to: 0\n"},
             "CONTROL: change_column_default is two-way", None)
        case({"db/migrate/20260926_fill.rb": "Invoice.in_batches.update_all(x: 1)\n"}, "a backfill is one-way", "migration")
        case({"app/policies/invoice_policy.rb": "def show? = true\n"}, "a policy change is one-way", "access")
        case({"app/controllers/concerns/authentication.rb": "allow_unauthenticated_access\n"},
             "the authentication concern is one-way", "access")
        case({"config/routes.rb": "Rails.application.routes.draw do\n  resources :invoices\nend\n"},
             "a removed route is one-way", "contract")
        case({"config/routes.rb": "Rails.application.routes.draw do\n  resources :invoices\n  get :health\n  get :ping\nend\n"},
             "CONTROL: an added route is two-way", None)
        case({"app/serializers/invoice_serializer.rb": "attributes :id\n"}, "a removed serializer field is one-way", "contract")
        case({"app/services/pay.rb": "class Pay\n  def call = Faraday.post(URL)\nend\n"},
             "a new outside HTTP call is one-way", "outbound")
        case({"spec/services/pay_spec.rb": "stub = Faraday.new\n"}, "CONTROL: an HTTP client in a spec is two-way", None)
        try:
            diff(root, "no-such-branch")
            expect("an unresolvable base is UNUSABLE, never two-way", False)
        except Unusable:
            pass

    for f in failures:
        print(f"FAIL: {f}")
    print(f"classify_door selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
