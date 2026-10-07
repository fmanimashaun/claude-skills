#!/usr/bin/env python3
"""Judge the two release-only certification layers (#1428), and refuse a stamp without them.

A downstream app passed certification -- load, DAST, race tests, three browsers -- and shipped a root
admin who could not create staff, two ways to sign in as root that skipped its second factor, and a
role that could demote root. The day-one journey was never walked (its one row was `Blocked` and
never re-run), and authorization was tested by action, not by target: nothing sent a forged request
from a lower role against a higher account. Both were then found by hand in one pass. These checks
make the two passes a precondition of `qa/CERTIFICATION`.

  first-boot DIR   the operator walkthrough on an EMPTY database: DIR/pages.csv plus screenshots.
  authz CSV        the forged-request sweep: one row per (action, actor, target).
  stamp [--rev R]  read qa/CERTIFICATION, run both checks on the evidence it names, and print the
                   evidence paths (the release gate lets the stamp's own commit carry them). A stamp
                   with `"schema": 2` must name both; an older one passes with a warning while
                   GRANDFATHER_OLD_STAMPS is on (one release), and fails once it is off.

WHAT first-boot JUDGES
  * pages.csv has the columns Step, Width, Actor, URL, Action, Expected, Actual, Status, Notes,
    Screenshot (Also, Issue and Env are optional), and at least one row.
  * Status is one of Pass, Fail, Blocked, Not walked. A **Blocked or Not walked row with no Notes**
    (the documented reason) fails: the escaped release's root row was `Blocked` and nobody asked why.
  * A Fail row names the filed issue (Issue column); a failure with nowhere to go is not reported.
  * At least one phone width (<= 480) and one desktop width (>= 1024).
  * Every screenshot the rows name (Screenshot and Also, `;`-separated) exists INSIDE DIR.
  * No second-factor secret is committed. It MATCHES: an `otpauth://` URI; an upper-case base32 key
    of 16+ characters, whole or in groups of four, after a label secret/key/seed/totp; three or more
    `xxxx-xxxx` codes (a letter somewhere, a digit in each half) on a line that says "recovery", or
    listed one per line within twelve lines after it -- in every text file in DIR and in PNG text
    chunks (tEXt, iTXt, zTXt). It CANNOT see pixels: a QR code or a typed key drawn in a screenshot
    is invisible to it. It does not flag an UNLABELLED base32 run either: 16+ capitals and 2-7 is
    also an ID or a hash, and a gate that fires on those gets switched off. Redacting the image is
    the walker's job; this catches the secret that leaked as text.
  NOT JUDGED: whether the database was really empty, which roles the app has, or whether every
  role's first sign-in was walked. Those are the plan's (qa-lead) and the reviewer's.

WHAT authz JUDGES
  * Columns: action, location (file:line), actor_role, target_role, guard, verdict (evidence and
    issue optional), and at least one row.
  * verdict is GUARDED, HOLE or UI-ONLY. **Any HOLE fails.** UI-ONLY -- a control that is hidden
    but not enforced, so the forged request got through -- fails too: hiding a button is not a guard.
  * A GUARDED row names its guard; `location` is a file with an extension, then :line.
  * At least one row targets the built-in root as a whole word (`--root-role`, default "root"; the
    stamp may carry "root_role"). The escaped release's holes were all against root.

WHAT stamp JUDGES
  * A stamp with NO `schema` is old: grandfathered (passes, warned) while GRANDFATHER_OLD_STAMPS is
    on, refused once it is off. A stamp that carries any schema other than the integer 2 is refused.
  * `first_boot` and `authz` are relative paths under qa/manual-tests/, with no `..`. The release
    gate lets the stamp's commit carry them, so evidence named anywhere else would carry code.
  * With `--rev REV` (the release gate passes dev's sha) the evidence is judged AS COMMITTED at REV,
    extracted with `git archive`: a HOLE committed on dev with its fix only staged still fails, and
    symlinks are dropped, never followed. Without `--rev` (qa-reporter, before committing) it is
    judged in the working tree.
  * Printed findings redact any cell value or file name that itself looks like a secret.
  NOT JUDGED: whether the table lists EVERY action that changes another account. Deriving that
  from routes is the sweep's job, not this reader's.

Exit: 0 clean · 1 findings (the layer fails) · 2 unusable (nothing to read).
Run:  release_evidence.py first-boot qa/manual-tests/first-boot-<version>
      release_evidence.py authz qa/manual-tests/authz-<version>/sweep.csv [--root-role NAME]
      release_evidence.py stamp [--stamp qa/CERTIFICATION]
      release_evidence.py --selftest
Stdlib only.
"""
from __future__ import annotations

import argparse
import contextlib
import errno
from datetime import datetime
import csv
import io
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import zlib
from pathlib import Path

EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2

# The stamp schema a certify step that knows both layers writes (#1428). A stamp carrying it MUST
# name passing evidence -- fail closed. An older stamp (no `schema`, or below this) was written by a
# toolchain that had no such layers, so it cannot carry them.
STAMP_SCHEMA = 2
# GRANDFATHER OLD STAMPS for one release: an older stamp passes with a loud warning, so no project is
# blocked mid-release by a rule its certification predates. The owner rule governs NEW certifications.
# Flip to False in the next release to make every stamp need the layers. ONE constant, deliberately:
# the owner's decision on #1428 is a one-line change either way.
GRANDFATHER_OLD_STAMPS = True
# WHICH stamps are old is decided from git, not from the stamp: a stamp is old only if the commit that
# introduced it (read at the tested sha) has a COMMITTER date before this instant. Without that, any
# NEW stamp could simply omit `schema` and be grandfathered (#1437 review, round 3). Committer date,
# because an agent's ordinary commit cannot carry an old one by accident. KNOWN LIMIT: a deliberately
# backdated commit passes, for this one release, until GRANDFATHER_OLD_STAMPS is turned off. Set to
# the date this rule merged to dev; the next release's arm flips GRANDFATHER_OLD_STAMPS to False.
GRANDFATHER_BEFORE = "2026-09-29T00:00:00+00:00"

FIRST_BOOT_COLUMNS = ("Step", "Width", "Actor", "URL", "Action", "Expected", "Actual", "Status",
                      "Notes", "Screenshot")
STATUSES = {"pass", "fail", "blocked", "not walked"}
UNWALKED = {"blocked", "not walked"}
PHONE_MAX, DESKTOP_MIN = 480, 1024
TEXT_SUFFIXES = {".csv", ".md", ".txt", ".json", ".svg", ".html", ".yml", ".yaml"}

AUTHZ_COLUMNS = ("action", "location", "actor_role", "target_role", "guard", "verdict")
VERDICTS = {"GUARDED", "HOLE", "UI-ONLY"}
FAILING = {"HOLE", "UI-ONLY"}
# A FILE, with an extension, and a line: `UserPolicy:1` names a class, not a place to look.
LOCATION = re.compile(r"^[\w./-]*\w\.\w+:\d+(?:-\d+)?$")
# Evidence lives here, and only here. The stamp is writable by anyone who can commit, and the release
# gate lets the stamp's own commit carry the evidence it names -- so a stamp naming `app` would carry
# code past the gate (#1437 review). Relative, under this root, no `..`.
EVIDENCE_ROOT = "qa/manual-tests/"

OTPAUTH = re.compile(r"otpauth://", re.I)
# The LABEL is case-insensitive; the secret is upper-case base32, optionally in groups of 4 ("JBSW Y3DP
# EHPK 3PXP"), as authenticator screens print it. Lower-case prose after "key:" is not a secret.
# The separator may hold a table's pipes and backticks, or one line break (the key printed under its
# label). Upper-case keys may run together; a lower-case key only counts in groups (JBSW-style), so a
# run of lower-case prose is never read as one. A key must also carry a digit 2-7 (checked in
# leak_reasons), so "Key: PASS FAIL SKIP WARN" is a legend, not a secret.
BASE32_SECRET = re.compile(r"(?i:\b(?:secret|key|seed|totp)\b)[^A-Za-z0-9\n]{0,8}\n?[^A-Za-z0-9\n]{0,8}"
                           r"((?:[A-Z2-7]{4}[ -]?){3}[A-Z2-7]{4,}|(?:[a-z2-7]{4}[ -]){3}[a-z2-7]{4,}|[A-Z2-7]{16,})\b")
# Each half carries a digit. Without that, screenshot names on a line about recovery codes
# ("1280-05-root-landed-security.png": root-landed, root-after) read as codes -- found by running
# this on a real downstream walkthrough, which it flagged twice for nothing.
# ...and a letter somewhere: a purely numeric pair is a reference ("REQ-2026-000002"), which the same
# walkthrough printed three times near the word "recovery".
RECOVERY_CODE = re.compile(r"\b(?=[a-z0-9-]*[a-z])(?=[a-z]*\d)[a-z0-9]{4,6}-(?=[a-z]*\d)[a-z0-9]{4,6}\b", re.I)
CODE_LINE = re.compile(r"^\s*(?:[-*]\s*|\d+[.)]\s*)?(\S+)\s*$")


def shown(value: object) -> str:
    """A cell value or file name as it may be PRINTED: redacted when it looks like a secret. A
    finding is printed to the terminal and CI log, so quoting a leaked key there leaks it again."""
    text = str(value)
    return "<redacted: looks like a second-factor secret>" if leak_reasons(text) else text


class Unusable(Exception):
    """Nothing to judge -- a missing file or an unreadable table. Exit 2, never a pass."""


# --------------------------------------------------------------------------- shared

def read_table(path: Path, required: tuple[str, ...], *, casefold: bool) -> list[dict]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        raise Unusable(f"{path}: cannot read ({exc.strerror or exc})") from exc
    reader = csv.DictReader(io.StringIO(text))
    header = reader.fieldnames or []
    norm = (lambda h: h.strip().lower()) if casefold else (lambda h: h.strip())
    have = {norm(h) for h in header}
    missing = [c for c in required if norm(c) not in have]
    if missing:
        raise Unusable(f"{path}: missing column(s) {missing}; header is {header}")
    rows = [{norm(k): (v or "").strip() for k, v in row.items() if k is not None}
            for row in reader]
    if not rows:
        raise Unusable(f"{path}: no rows -- an empty table is not evidence")
    return rows


def png_text(data: bytes) -> str:
    """The text chunks of a PNG (tEXt, iTXt, zTXt), concatenated. Not a PNG -> ''."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ""
    out, pos = [], 8
    while pos + 8 <= len(data):
        (length,), kind = struct.unpack(">I", data[pos:pos + 4]), data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if kind == b"tEXt":
            out.append(body.replace(b"\x00", b" ").decode("latin-1", "replace"))
        elif kind == b"zTXt":
            key, _, rest = body.partition(b"\x00")
            with contextlib.suppress(zlib.error):
                out.append(key.decode("latin-1") + " " + zlib.decompress(rest[1:]).decode("latin-1", "replace"))
        elif kind == b"iTXt":
            key, _, rest = body.partition(b"\x00")
            compressed, rest = rest[:1], rest[2:]
            _lang, _, rest = rest.partition(b"\x00")
            _tkey, _, text = rest.partition(b"\x00")
            with contextlib.suppress(zlib.error):
                text = zlib.decompress(text) if compressed == b"\x01" else text
            out.append(key.decode("latin-1") + " " + text.decode("utf-8", "replace"))
        if kind == b"IEND":
            break
        pos += 12 + length
    return "\n".join(out)


def leak_reasons(text: str) -> list[str]:
    """Why `text` looks like it carries a second-factor secret; [] when it does not.

    Returns fixed LABELS only, never the matched text: a finding is printed, and a finding that
    quoted the secret would leak it a second time (the selftest asserts no finding carries it).
    """
    found = []
    if OTPAUTH.search(text):
        found.append("an otpauth:// URI")
    if any(re.search(r"[2-7]", m.group(1)) for m in BASE32_SECRET.finditer(text)):
        found.append("a labelled base32 secret")
    # A line that says "recovery" with three or more codes ON it, or followed within twelve lines by
    # three or more lines that are nothing but a code (a list printed one per line is still a list).
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if "recovery" not in line.lower():
            continue
        listed = sum(1 for nxt in lines[i + 1:i + 13]
                     if (m := CODE_LINE.match(nxt)) and RECOVERY_CODE.fullmatch(m.group(1)))
        if len(RECOVERY_CODE.findall(line)) >= 3 or listed >= 3:
            found.append("a list of recovery codes")
            break
    return found


# --------------------------------------------------------------------------- first-boot

def check_first_boot(folder: Path) -> list[str]:
    if not folder.is_dir():
        raise Unusable(f"{folder}: no such directory -- the walkthrough was never recorded")
    rows = read_table(folder / "pages.csv", FIRST_BOOT_COLUMNS, casefold=False)
    findings: list[str] = []
    widths: list[int] = []
    for row in rows:
        step = shown(row.get("Step") or "?")
        status = row.get("Status", "").lower()
        if status not in STATUSES:
            findings.append(f"step {step}: status {shown(repr(row.get('Status')))} is not Pass, Fail, Blocked or Not walked")
        elif status in UNWALKED and not row.get("Notes"):
            findings.append(f"step {step}: {shown(row.get('Status'))} with no documented reason in Notes -- "
                            f"an unwalked step with no reason is the one that escaped")
        elif status == "fail" and not row.get("Issue"):
            findings.append(f"step {step}: Fail names no filed issue (Issue column)")
        try:
            widths.append(int(row.get("Width", "")))
        except ValueError:
            findings.append(f"step {step}: Width {shown(repr(row.get('Width')))} is not a number of pixels")
        for col in ("Screenshot", "Also"):
            for name in filter(None, (s.strip() for s in row.get(col, "").split(";"))):
                target = (folder / name).resolve()
                if Path(name).is_absolute() or folder.resolve() not in target.parents:
                    findings.append(f"step {step}: {col} {shown(name)} is outside {folder.name}/ -- evidence is the folder")
                elif not target.is_file():
                    findings.append(f"step {step}: {col} names {shown(name)}, which is not in {folder.name}/")
    if not any(w <= PHONE_MAX for w in widths):
        findings.append(f"no step was walked at a phone width (<= {PHONE_MAX}px)")
    if not any(w >= DESKTOP_MIN for w in widths):
        findings.append(f"no step was walked at a desktop width (>= {DESKTOP_MIN}px)")
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8", errors="replace")
        elif path.suffix.lower() == ".png":
            text = png_text(path.read_bytes())
        else:
            continue
        for why in leak_reasons(text):
            findings.append(f"{shown(path.relative_to(folder))}: carries {why} -- redact it before committing")
    return findings


# --------------------------------------------------------------------------- authz

def check_authz(table: Path, root_role: str = "root") -> list[str]:
    rows = read_table(table, AUTHZ_COLUMNS, casefold=True)
    findings: list[str] = []
    for i, row in enumerate(rows, 2):           # row 1 is the header
        where = shown(f"row {i} ({row.get('action') or '?'}: {row.get('actor_role')} -> {row.get('target_role')})")
        verdict = row.get("verdict", "").upper()
        if verdict not in VERDICTS:
            findings.append(f"{where}: verdict {shown(repr(row.get('verdict')))} is not GUARDED, HOLE or UI-ONLY")
        elif verdict == "HOLE":
            findings.append(f"{where}: HOLE -- the forged request changed the target")
        elif verdict == "UI-ONLY":
            findings.append(f"{where}: UI-ONLY -- the control is hidden, not enforced")
        elif not row.get("guard"):
            findings.append(f"{where}: GUARDED names no guard")
        if not LOCATION.match(row.get("location", "")):
            findings.append(f"{where}: location {shown(repr(row.get('location')))} is not file:line")
    root_word = re.compile(rf"(?<![\w-]){re.escape(root_role)}(?![\w-])", re.I)
    if not any(root_word.search(row.get("target_role", "")) for row in rows):
        findings.append(f"no row targets the built-in {root_role!r} -- the escaped release's holes were all against it")
    return findings


# --------------------------------------------------------------------------- stamp

CONTROL = re.compile(r"[\x00-\x1f\x7f]")
VERSION = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def evidence_path_ok(value: str) -> bool:
    # NO CONTROL CHARACTERS. The release gate reads the evidence paths one per line, so a newline
    # inside one ("qa/manual-tests/x\napp") would smuggle a second path -- `app` -- into the allowance
    # and carry any code past the gate (#1437 review, round 3). A tab or CR is refused for the same
    # reason: nothing legitimate needs them in a path.
    if CONTROL.search(value):
        return False
    parts = Path(value).parts
    return (value.startswith(EVIDENCE_ROOT) and not Path(value).is_absolute() and ".." not in parts
            and len(parts) > len(Path(EVIDENCE_ROOT).parts) and "\\" not in value)


def same_release(key: str, value: str, version: str) -> bool:
    """The evidence is NAMED for the stamp's version: qa/manual-tests/first-boot-<version> and a sweep
    under qa/manual-tests/authz-<version>/. A stamp naming last release's walkthrough is refused."""
    if key == "first_boot":
        return value == f"{EVIDENCE_ROOT}first-boot-{version}"
    return value.startswith(f"{EVIDENCE_ROOT}authz-{version}/") and value.endswith(".csv")


def copied_from(base: Path, rev: str, value: str, prefix: str) -> str | None:
    """Another release's evidence whose git object is IDENTICAL to this one at `rev`, or None.

    Renaming last release's walkthrough to this release's name keeps its tree (or the sweep's blob)
    byte-identical, so the object id gives the copy away without reading a file. A walkthrough
    genuinely re-run produces different rows, screenshots or dates, and a different id.
    """
    try:
        done = subprocess.run(["git", "-C", str(base), "ls-tree", "-r", "-t", rev, "--", EVIDENCE_ROOT],
                              capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None
    ids: dict[str, str] = {}
    for line in done.stdout.splitlines():
        meta, _, path = line.partition("\t")
        ids[path] = meta.split()[-1] if meta.split() else ""
    own = ids.get(value)
    if not own:
        return None
    for path, oid in ids.items():
        if path != value and oid == own and path.startswith(EVIDENCE_ROOT + prefix):
            return path
    return None


def committed_tree(base: Path, rev: str, rels: list[str], dest: Path) -> list[str]:
    """Extract `rels` as committed at `rev` into `dest`, regular files and directories only.

    The release gate judges what dev COMMITTED, not the working tree: a HOLE committed on dev, with
    the fixed copy only staged in the gate's checkout, must still deny (#1437 review). Symlinks and
    anything outside `dest` are dropped, never followed -- so a link under qa/manual-tests/ pointing
    at app/ contributes nothing. Returns the problems; [] when every path was found at `rev`.
    """
    try:
        done = subprocess.run(["git", "-C", str(base), "archive", "--format=tar", rev, "--", *rels],
                              capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"cannot read the evidence committed at {rev[:12]} ({exc})"]
    if done.returncode != 0:
        return [f"the evidence is not committed at {rev[:12]}: "
                f"{done.stderr.decode('utf-8', 'replace').strip()[:200]}"]
    root = dest.resolve()
    with tarfile.open(fileobj=io.BytesIO(done.stdout)) as tar:
        for member in tar.getmembers():
            target = (dest / member.name).resolve()
            if not (member.isfile() or member.isdir()) or (target != root and root not in target.parents):
                continue
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                target.write_bytes(source.read() if source else b"")
    return []


def committed_at(base: Path, rev: str, rel: str) -> int | None:
    """Committer time (epoch) of the commit that last changed `rel` as of `rev`, or None."""
    try:
        done = subprocess.run(["git", "-C", str(base), "log", "-1", "--format=%ct", rev, "--", rel],
                              capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    out = done.stdout.strip()
    return int(out) if done.returncode == 0 and out.isdigit() else None


def published_ref(base: Path) -> str | None:
    """The last PUBLISHED release: origin/main, else main. None when the repo has neither."""
    for ref in ("origin/main", "main"):
        try:
            done = subprocess.run(["git", "-C", str(base), "rev-parse", "--verify", "-q", f"{ref}^{{commit}}"],
                                  capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        if done.returncode == 0 and done.stdout.strip():
            return done.stdout.strip()
    return None


def already_published(base: Path, rev: str, published: str, record: str) -> str | None:
    """Why `record` (the walkthrough's pages.csv, or the sweep) is last release's, or None.

    The version tie trusts the stamp's own `version`, and the copy check only sees evidence still at
    dev -- so `git mv first-boot-v1 first-boot-v2`, with the old folder gone, passed (#1437 round 3).
    The last PUBLISHED release is main: a record whose PATH is already there is last release's
    evidence, and one whose blob is byte-identical to any record there is a copy of it. Records, not
    screenshots: an unchanged page can render to the same PNG bytes in two honest walks.
    KNOWN LIMITS: a lightly EDITED copy (one line changed) has a new blob and passes; and so does an
    unedited copy of an OLDER release whose evidence is no longer in main's TREE, because main's tree
    is read, not its history. It makes an unedited copy of the LAST published release impossible.
    """
    def ids(ref: str) -> dict[str, str]:
        try:
            done = subprocess.run(["git", "-C", str(base), "ls-tree", "-r", ref, "--", EVIDENCE_ROOT],
                                  capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            return {}
        out = {}
        for line in done.stdout.splitlines():
            meta, _, path = line.partition("\t")
            parts = meta.split()
            if len(parts) == 3:
                out[path] = parts[2]
        return out

    shipped = ids(published)
    own = ids(rev).get(record)
    if record in shipped:
        return f"{record} is already in the last published release (main) -- it is that release's evidence"
    records = {p: oid for p, oid in shipped.items() if p.endswith("/pages.csv") or p.endswith(".csv")}
    for path, oid in records.items():
        if own and oid == own:
            return f"{record} is byte-identical to {path}, published in the last release (main) -- a copy"
    return None


def check_stamp(stamp: Path, base: Path, grandfather: bool | None = None,
                rev: str | None = None,
                grandfather_before: str | None = None) -> tuple[list[str], list[str], list[str]]:
    """(findings, evidence paths, warnings). A schema-2 stamp must NAME both layers, and both pass.

    With `rev` (the release gate), the evidence is judged as committed at that revision; without it
    (qa-reporter, before the stamp and its evidence are committed), as it is in the working tree.
    """
    grandfather = GRANDFATHER_OLD_STAMPS if grandfather is None else grandfather
    try:
        if rev:
            # The STAMP is read as committed at `rev` too, not from the working tree: an uncommitted
            # or edited stamp in the gate's checkout is not what dev will promote (#1437 review).
            rel = stamp.relative_to(base) if stamp.is_absolute() else stamp
            shown_blob = subprocess.run(["git", "-C", str(base), "show", f"{rev}:{rel.as_posix()}"],
                                        capture_output=True, text=True, timeout=30)
            if shown_blob.returncode != 0:
                raise Unusable(f"no {rel.as_posix()} is committed at {rev[:12]} -- commit the stamp to dev first")
            raw = shown_blob.stdout
        else:
            raw = stamp.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        raise Unusable(f"{stamp}: not a readable JSON stamp ({exc})") from exc
    if not isinstance(data, dict):
        raise Unusable(f"{stamp}: not a JSON object")
    findings: list[str] = []
    paths: list[str] = []
    # ONLY a stamp with no `schema` at all is old. A stamp that carries one -- "2", 2.0, true -- was
    # written by something that knows the field; a malformed value is refused, never grandfathered
    # (#1437 review: `"schema": "2"` let a HOLE sweep through).
    if "schema" in data:
        schema = data["schema"]
        if not (isinstance(schema, int) and not isinstance(schema, bool) and schema >= STAMP_SCHEMA):
            return [f"the stamp's schema is {schema!r}; it must be the integer {STAMP_SCHEMA}. Re-run /qa-flow:certify"], [], []
    elif grandfather:
        cutoff = datetime.fromisoformat(grandfather_before or GRANDFATHER_BEFORE).timestamp()
        rel = (stamp.relative_to(base) if stamp.is_absolute() else stamp).as_posix()
        when = committed_at(base, rev or "HEAD", rel)
        if not rev:
            # Judged from the working tree: only the COMMITTED stamp's date means anything, so the file
            # on disk must be that stamp.
            try:
                head = subprocess.run(["git", "-C", str(base), "show", f"HEAD:{rel}"],
                                      capture_output=True, text=True, timeout=30)
                if head.returncode != 0 or head.stdout != raw:
                    when = None
            except (OSError, subprocess.SubprocessError):
                when = None
        if when is not None and when < cutoff:
            return [], [], [f"this stamp predates the first-boot walkthrough and authorization sweep layers "
                            f"(#1428): accepted for this release only. Re-run /qa-flow:certify to add them -- "
                            f"the next release refuses a stamp without them."]
        return [f"the stamp carries no `schema` but was not committed before {grandfather_before or GRANDFATHER_BEFORE} "
                f"-- a stamp written now must be schema {STAMP_SCHEMA} and name its evidence (#1428). "
                f"Re-run /qa-flow:certify"], [], []
    version = data.get("version")
    if not isinstance(version, str) or not VERSION.match(version):
        findings.append(f"the stamp's `version` is {shown(repr(version))}: a schema-2 stamp names the release it "
                        f"certifies (letters, digits, `.`, `_`, `-`), and its evidence is named for it")
    for key in ("first_boot", "authz"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            findings.append(f"the stamp names no `{key}` evidence -- it predates #1428, or the layer was "
                            f"skipped. Re-run /qa-flow:certify")
    if findings:
        return findings, paths, []
    fb, az = data["first_boot"].strip().rstrip("/"), data["authz"].strip()
    for key, value in (("first_boot", fb), ("authz", az)):
        # The RAW value too: a control character is refused even where strip() would have removed it.
        if not evidence_path_ok(value) or CONTROL.search(data[key]):
            findings.append(f"`{key}` is {value!r}: evidence must be a relative path under {EVIDENCE_ROOT} with no "
                            f"`..` or control character -- the gate lets the stamp's commit carry it, so anything "
                            f"else would carry code")
        elif not same_release(key, value, version):
            findings.append(f"`{key}` is {value!r}, which is not named for this release ({version}): expected "
                            + (f"{EVIDENCE_ROOT}first-boot-{version}" if key == "first_boot"
                               else f"a .csv under {EVIDENCE_ROOT}authz-{version}/"))
    if findings:
        return findings, [], []
    if rev:
        for key, value, prefix in (("first_boot", fb, "first-boot-"), ("authz", az, "authz-")):
            twin = copied_from(base, rev, value, prefix)
            if twin:
                findings.append(f"`{key}` {value} is byte-identical to {twin} -- another release's evidence, "
                                f"renamed, is not this release's")
        published = published_ref(base)
        if published:
            for key, record in (("first_boot", fb + "/pages.csv"), ("authz", az)):
                why = already_published(base, rev, published, record)
                if why:
                    findings.append(f"`{key}`: {why}")
        if findings:
            return findings, [], []
    with tempfile.TemporaryDirectory() as td:
        root = base
        if rev:
            findings += committed_tree(base, rev, [fb, az], Path(td))
            if findings:
                return findings, [], []
            root = Path(td)
        for label, fn in (("first-boot", lambda: check_first_boot(root / fb)),
                          ("authz", lambda: check_authz(root / az, str(data.get("root_role") or "root")))):
            try:
                findings += [f"{label}: {f}" for f in fn()]
            except Unusable as exc:
                findings.append(f"{label}: {exc}")
    # A directory ends in "/" (the gate matches it as a prefix); the sweep is ONE file, matched exactly.
    return findings, [fb + "/", az], []


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("first-boot"); p.add_argument("dir", type=Path)
    p = sub.add_parser("authz"); p.add_argument("table", type=Path)
    p.add_argument("--root-role", default="root")
    p = sub.add_parser("stamp"); p.add_argument("--stamp", type=Path, default=Path("qa/CERTIFICATION"))
    p.add_argument("--rev", help="judge the evidence as committed at REV (the release gate passes dev's sha)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    try:
        if args.cmd == "first-boot":
            findings = check_first_boot(args.dir)
        elif args.cmd == "authz":
            findings = check_authz(args.table, args.root_role)
        elif args.cmd == "stamp":
            findings, paths, warnings = check_stamp(args.stamp, Path.cwd(), rev=args.rev)
            for w in warnings:
                print(f"WARNING {w}", file=sys.stderr)
            if not findings:
                if paths:
                    print("\n".join(paths))        # the release gate reads these
                return EXIT_OK
        else:
            ap.print_help(sys.stderr)
            return EXIT_UNUSABLE
    except Unusable as exc:
        print(f"unusable: {exc}", file=sys.stderr)
        return EXIT_UNUSABLE
    for f in findings:
        print(f"FAIL {f}", file=sys.stderr)
    if findings:
        print(f"{len(findings)} finding(s): this layer blocks certification", file=sys.stderr)
        return EXIT_FINDINGS
    print("ok", file=sys.stderr)
    return EXIT_OK


# --------------------------------------------------------------------------- selftest

def _png(text_chunks: list[tuple[bytes, bytes]]) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    for kind, body in text_chunks:
        out += chunk(kind, body)
    return out + chunk(b"IDAT", zlib.compress(b"\x00\x00")) + chunk(b"IEND", b"")


HEADER = "Step,Width,Actor,URL,Action,Expected,Actual,Status,Notes,Screenshot,Also,Issue,Env\n"


def _walk(root: Path, rows: list[str], shots: dict[str, bytes] | None = None) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "pages.csv").write_text(HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
    for name, data in (shots or {"a.png": _png([]), "b.png": _png([])}).items():
        (root / name).write_bytes(data)
    return root


GOOD_ROWS = [
    "1.1,1280,root,/login/root,Sign in,Signed in,Signed in,Pass,,a.png,,,empty db",
    "1.2,390,root,/login/root,Sign in (phone),Signed in,Signed in,Pass,,b.png,,,empty db",
    "3.2,1280,desk,/auth/zoho,SSO,Handoff,Not completed,Not walked,external IdP,,,,empty db",
]

AUTHZ_HEADER = "action,location,actor_role,target_role,guard,verdict,evidence,issue\n"
AUTHZ_GOOD = [
    "demote,app/models/user.rb:40,it,root,User#root? refusal,GUARDED,spec/x_spec.rb,",
    "demote,app/models/user.rb:40,it,admin,only root changes an Admin,GUARDED,spec/x_spec.rb,",
]


# The fixture repo's git, made hermetic. A fixture `git commit` otherwise starts `git maintenance run
# --auto --quiet --detach` (GIT_TRACE shows it), a background process that can still be writing into the
# repo when the temp directory is removed -- `rmtree` then raises "Directory not empty" from cleanup, the
# selftest dies before printing its verdict, and mutation coverage reads a correct mutant as caught by the
# wrong fixture (#1493). Signing is off too, so a maintainer's own git config never reaches the fixture.
FIXTURE_GIT = ("-c", "user.email=t@t", "-c", "user.name=t", "-c", "maintenance.auto=false", "-c", "gc.auto=0",  # fixture-git: exempt (the argv is the subject: this fixture tests git's own maintenance behaviour; repo-locating env stripped: bare_env drops every GIT_*)
               "-c", "commit.gpgSign=false", "-c", "tag.gpgSign=false")


def _fixture_tempdir() -> tempfile.TemporaryDirectory:
    """The selftest's scratch directory. Cleanup errors are ignored -- for CLEANUP only: every verdict has
    been decided and recorded by then, so a straggling writer leaves debris in the temp dir, never a crash
    that swallows the result (#1493)."""
    return tempfile.TemporaryDirectory(ignore_cleanup_errors=True)


def selftest() -> int:
    failures: list[str] = []
    checks = 0

    def check(label: str, ok: bool, detail: object = "") -> None:
        nonlocal checks
        checks += 1
        if not ok:
            failures.append(f"{label}: {detail}")

    def fb(rows, shots=None, name="w"):
        return check_first_boot(_walk(tmp / name, rows, shots))

    # #1493: cleanup cannot crash the verdict. The CI traceback was `os.rmdir` raising "Directory not
    # empty" inside TemporaryDirectory.cleanup, a writer racing the removal; that exact failure is made
    # deterministic here by refusing the probe directory's own rmdir, and only it.
    real_rmdir = os.rmdir
    probe = ""

    def busy_rmdir(path, *args, **kwargs):
        if probe and os.path.basename(os.fspath(path)) == probe:
            raise OSError(errno.ENOTEMPTY, "Directory not empty", os.fspath(path))
        return real_rmdir(path, *args, **kwargs)

    os.rmdir = busy_rmdir
    try:
        crashed = None
        try:
            with _fixture_tempdir() as probe_dir:
                probe = Path(probe_dir).name
                (Path(probe_dir) / "written-late").write_text("x", encoding="utf-8")
        except OSError as exc:
            crashed = exc
    finally:
        os.rmdir = real_rmdir
        if probe:
            shutil.rmtree(Path(tempfile.gettempdir()) / probe, ignore_errors=True)
    check("cleanup: a directory still being written at cleanup does not crash the selftest", crashed is None, crashed)

    with _fixture_tempdir() as td:
        tmp = Path(td)

        # -- first-boot: the clean control, then one planted defect per rule --------------
        check("first-boot: a clean walkthrough passes", fb(GOOD_ROWS, name="ok") == [], fb(GOOD_ROWS, name="ok2"))
        # THE ESCAPED DEFECT: a Blocked row with no reason.
        blocked = GOOD_ROWS + ["2.1,1280,root,/users/new,Create staff,Created,,Blocked,,,,,empty db"]
        got = fb(blocked, name="blk")
        check("first-boot: Blocked with no reason fails", any("2.1" in f and "Blocked" in f for f in got), got)
        reasoned = GOOD_ROWS + ["2.1,1280,root,/users/new,Create staff,Created,,Blocked,password unset: #12,,,,x"]
        check("first-boot: Blocked WITH a documented reason passes", fb(reasoned, name="blk2") == [],
              fb(reasoned, name="blk3"))
        unwalked = GOOD_ROWS + ["3.3,1280,desk,/auth/ms,SSO,Handoff,,Not walked,,,,,x"]
        check("first-boot: Not walked with no reason fails",
              any("3.3" in f for f in fb(unwalked, name="nw")), fb(unwalked, name="nw2"))
        check("first-boot: an unknown status fails",
              any("Skipped" in f for f in fb(GOOD_ROWS + ["9,1280,a,/,x,y,z,Skipped,,,,,"], name="st")))
        failing = GOOD_ROWS + ["2.3,1280,root,/users,Submit blank,Named,Only one,Fail,,a.png,,,x"]
        check("first-boot: a Fail with no filed issue fails",
              any("2.3" in f and "issue" in f for f in fb(failing, name="fl")))
        filed = GOOD_ROWS + ["2.3,1280,root,/users,Submit blank,Named,Only one,Fail,,a.png,,#1025,x"]
        check("first-boot: a Fail naming its issue passes", fb(filed, name="fl2") == [])
        desktop_only = [r for r in GOOD_ROWS if ",390," not in r]
        check("first-boot: no phone width fails",
              any("phone" in f for f in fb(desktop_only, name="ph")), fb(desktop_only, name="ph2"))
        phone_only = [r.replace(",1280,", ",390,") for r in GOOD_ROWS]
        check("first-boot: no desktop width fails", any("desktop" in f for f in fb(phone_only, name="dk")))
        check("first-boot: a non-numeric width fails",
              any("Width" in f for f in fb(GOOD_ROWS + ["9,phone,a,/,x,y,z,Pass,,,,,"], name="wd")))
        missing = GOOD_ROWS + ["4.1,1280,a,/,x,y,z,Pass,,gone.png,,,"]
        check("first-boot: a named screenshot that is missing fails",
              any("gone.png" in f for f in fb(missing, name="ms")))
        outside = GOOD_ROWS + ["4.3,1280,a,/,x,y,z,Pass,,../elsewhere.png,,,"]
        (tmp / "elsewhere.png").write_bytes(_png([]))
        check("first-boot: a screenshot outside the folder is not evidence",
              any("outside" in f for f in fb(outside, name="out")))
        also = GOOD_ROWS + ["4.2,1280,a,/,x,y,z,Pass,,a.png,b.png; lost.png,,"]
        check("first-boot: a missing Also screenshot fails", any("lost.png" in f for f in fb(also, name="al")))
        try:
            check_first_boot(tmp / "never")
            check("first-boot: no directory is unusable", False, "judged")
        except Unusable:
            check("first-boot: no directory is unusable", True)

        # -- second-factor secrets: text files and PNG text chunks, with a clean control ----
        uri = "otpauth://totp/App:root?secret=JBSWY3DPEHPK3PXP&issuer=App"
        leaky = GOOD_ROWS + [f'1.3,1280,root,/login/code,Enrol,QR,"{uri}",Pass,,,,,x']
        check("secrets: an otpauth URI in pages.csv fails",
              any("otpauth" in f for f in fb(leaky, name="s1")))
        # A finding names WHERE and WHAT KIND, never the secret itself -- it is printed.
        leaked = fb(leaky, name="s1b") + fb(GOOD_ROWS + ['1.3,1280,root,/c,Enrol,Key,"Setup key: JBSW Y3DP EHPK 3PXP",'
                                                         'Pass,,,,,x'], name="s1c")
        check("secrets: no finding quotes the secret it found",
              leaked and not any("JBSW" in f or "secret=" in f for f in leaked), leaked)
        png_leak = {"a.png": _png([(b"tEXt", b"Comment\x00" + uri.encode())]), "b.png": _png([])}
        check("secrets: an otpauth URI in a PNG tEXt chunk fails",
              any("a.png" in f and "otpauth" in f for f in fb(GOOD_ROWS, png_leak, name="s2")))
        itxt = {"a.png": _png([(b"iTXt", b"Description\x00\x01\x00\x00\x00" + zlib.compress(uri.encode()))]),
                "b.png": _png([])}
        check("secrets: a compressed iTXt chunk is read too",
              any("a.png" in f for f in fb(GOOD_ROWS, itxt, name="s3")))
        keyed = GOOD_ROWS + ['1.3,1280,root,/login/code,Enrol,Key,"typed key: JBSWY3DPEHPK3PXP",Pass,,,,,x']
        check("secrets: a labelled base32 key fails", any("base32" in f for f in fb(keyed, name="s4")))
        grouped = GOOD_ROWS + ['1.3,1280,root,/login/code,Enrol,Key,"Setup key: JBSW Y3DP EHPK 3PXP",Pass,,,,,x']
        check("secrets: a grouped base32 key fails", any("base32" in f for f in fb(grouped, name="s4b")))
        for label, cell in (("lower-case grouped", "setup key: jbsw y3dp ehpk 3pxp"),
                            ("under its label", "Setup key:\nJBSWY3DPEHPK3PXP"),
                            ("in a markdown table", "| Setup key | `JBSWY3DPEHPK3PXP` |")):
            (tmp / "kv").mkdir(exist_ok=True)
            got = fb(GOOD_ROWS, {"a.png": _png([]), "b.png": _png([]), "notes.md": cell.encode()}, name=f"k-{label}")
            check(f"secrets: a key {label} fails", any("base32" in f for f in got), got)
        legend = GOOD_ROWS + ['1.3,1280,root,/r,Legend,Shown,"Key: PASS FAIL SKIP WARN",Pass,,,,,x']
        check("secrets: an upper-case legend with no digit is not a key", fb(legend, name="k-leg") == [],
              fb(legend, name="k-leg2"))
        # A printed finding redacts a cell that itself looks like a secret.
        cell = GOOD_ROWS + ['9,1280,a,/,x,y,z,"otpauth://totp/App:root?secret=JBSWY3DPEHPK3PXP",,,,,']
        got = fb(cell, name="red")
        check("secrets: a secret in a quoted cell is redacted in the finding", got and
              not any("JBSWY3DP" in f for f in got) and any("redacted" in f for f in got), got)
        # Lower-case prose that even carries a base32 digit: only an UPPER-case run is a key.
        prose = GOOD_ROWS + ['1.3,1280,root,/login/code,Enrol,Key,"key: internationalization issue; '
                             'key: q2roadmapdiscussion",Pass,,,,,x']
        check("secrets: lower-case prose after key: is not a secret", fb(prose, name="s4c") == [],
              fb(prose, name="s4d"))
        (tmp / "list").mkdir()
        (tmp / "list" / "notes.md").write_text("Recovery codes:\n\n- a1b2c-3d4e5\n- f6g7h-8i9j0\n- k1l2m-3n4o5\n",
                                               encoding="utf-8")
        check("secrets: recovery codes one per line fail",
              any("recovery" in f for f in fb(GOOD_ROWS, {"a.png": _png([]), "b.png": _png([]),
                                                          "notes.md": (tmp / "list" / "notes.md").read_bytes()},
                                               name="s5b")))
        ztxt = {"a.png": _png([(b"zTXt", b"Comment\x00\x00" + zlib.compress(uri.encode()))]), "b.png": _png([])}
        check("secrets: a zTXt chunk is read", any("a.png" in f for f in fb(GOOD_ROWS, ztxt, name="s3z")))
        codes = GOOD_ROWS + ['1.5,1280,root,/s,Codes,Shown,"recovery codes a1b2-c3d4 e5f6-g7h8 i9j0-k1l2",Pass,,,,,x']
        check("secrets: a line of recovery codes fails", any("recovery" in f for f in fb(codes, name="s5")))
        redacted = GOOD_ROWS + ['1.5,1280,root,/s,Codes,Shown,"recovery codes shown (redacted)",Pass,,,,,x']
        check("secrets: a redacted mention is NOT a leak", fb(redacted, name="s6") == [], fb(redacted, name="s7"))
        # Control from a real walkthrough: screenshot names on a recovery-code line are not codes.
        names = GOOD_ROWS + ['1.5,1280,root,/s,Codes,Shown,"recovery codes redacted; see 1280-05-root-landed-security.png '
                             'and 1280-05-root-after-code.png and 1280-06-root-demo-off.png",Pass,,,,,x']
        check("secrets: screenshot names beside the word recovery are not codes", fb(names, name="s8") == [],
              fb(names, name="s9"))
        # Control from the same walkthrough: request references near a recovery line are not codes.
        refs = GOOD_ROWS + ['1.5,1280,root,/s,Codes,Shown,"recovery codes redacted; later raised REQ-2026-000001, '
                            'REQ-2026-000002 and REQ-2026-000003",Pass,,,,,x']
        check("secrets: numeric request references are not recovery codes", fb(refs, name="s10") == [],
              fb(refs, name="s11"))

        # -- authz ---------------------------------------------------------------------
        def az(rows, name, root="root"):
            path = tmp / f"{name}.csv"
            path.write_text(AUTHZ_HEADER + "".join(r + "\n" for r in rows), encoding="utf-8")
            return check_authz(path, root)

        check("authz: a clean sweep passes", az(AUTHZ_GOOD, "a0") == [], az(AUTHZ_GOOD, "a0b"))
        # THE ESCAPED DEFECT: an unguarded action against root.
        hole = AUTHZ_GOOD + ["demote,app/controllers/staff_controller.rb:88,it,root,,HOLE,forged PATCH,#1034"]
        check("authz: a HOLE fails", any("HOLE" in f for f in az(hole, "a1")), az(hole, "a1b"))
        ui = AUTHZ_GOOD + ["demote,app/views/staff/_row.html.erb:12,it,admin,button hidden,UI-ONLY,,"]
        check("authz: a UI-ONLY protection fails", any("UI-ONLY" in f for f in az(ui, "a2")))
        noguard = AUTHZ_GOOD + ["reset,app/models/user.rb:9,it,admin,,GUARDED,,"]
        check("authz: GUARDED with no guard named fails", any("no guard" in f for f in az(noguard, "a3")))
        badloc = AUTHZ_GOOD + ["reset,UserPolicy:1,it,admin,policy,GUARDED,,"]
        check("authz: a location that is not file:line fails", any("file:line" in f for f in az(badloc, "a4")))
        noroot = [r for r in AUTHZ_GOOD if ",root," not in r]
        check("authz: no row targeting root fails", any("root" in f for f in az(noroot, "a5")))
        lookalike = noroot + ["demote,app/models/user.rb:40,it,grooter,g,GUARDED,,"]
        check("authz: a target merely containing 'root' is not root", any("root" in f for f in az(lookalike, "a5b")))
        check("authz: --root-role names the app's own root",
              az([r.replace(",root,", ",superadmin,") for r in AUTHZ_GOOD], "a6", root="superadmin") == [])
        check("authz: an unknown verdict fails",
              any("PARTIAL" in f for f in az(AUTHZ_GOOD + ["x,a.rb:1,it,admin,g,PARTIAL,,"], "a7")))
        check("authz: a lowercase verdict is read", az([r.replace("GUARDED", "guarded") for r in AUTHZ_GOOD], "a8") == [])
        (tmp / "empty.csv").write_text(AUTHZ_HEADER, encoding="utf-8")
        try:
            check_authz(tmp / "empty.csv")
            check("authz: an empty table is unusable", False, "judged")
        except Unusable:
            check("authz: an empty table is unusable", True)

        # -- stamp, through main(), as the release gate calls it -------------------------
        proj = tmp / "proj"
        V = "v1"
        _walk(proj / f"qa/manual-tests/first-boot-{V}", GOOD_ROWS)
        (proj / f"qa/manual-tests/authz-{V}").mkdir(parents=True)
        sweep = proj / f"qa/manual-tests/authz-{V}/sweep.csv"
        sweep.write_text(AUTHZ_HEADER + "\n".join(AUTHZ_GOOD) + "\n", encoding="utf-8")
        stamp = proj / "qa/CERTIFICATION"
        g = ["git", "-C", str(proj), *FIXTURE_GIT]
        # The work branch is dev; main is created below, only where a fixture needs a PUBLISHED release.
        subprocess.run(["git", "init", "-q", "-b", "dev", str(proj)], check=True)
        subprocess.run([*g, "add", "qa/manual-tests"], check=True)
        subprocess.run([*g, "commit", "-q", "-m", "evidence"], check=True)
        # #1493, the root cause: a fixture commit starts no detached background git.
        # Only FIXTURE_GIT may supply the settings: a runner that already disables maintenance through
        # GIT_CONFIG_* (ours does, #1510) would otherwise satisfy this check with the fixture's own
        # settings removed -- and a downstream project runs this selftest without our runner.
        # No GIT_* at all (#1660 review R3): not the CONFIG pairs this check must not inherit, and not an inherited
        # GIT_DIR either, which `-C` does not override -- the #1588 incident.
        bare_env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        traced = subprocess.run([*g, "commit", "-q", "--allow-empty", "-m", "trace"], capture_output=True,
                                text=True, env={**bare_env, "GIT_TRACE": "1"})
        # CONTROL: with auto-maintenance ON the same commit does run it, so the check above is not vacuous
        # on this git. It runs in the FOREGROUND (`autoDetach=false`): a detached control would be the very
        # #1493 race, hidden by the cleanup (review of PR #1511). `maintenance.auto=true` on the command
        # line, so a maintainer's global config cannot turn the control red.
        bare = ["git", "-C", str(proj), "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgSign=false",  # fixture-git: exempt (the argv is the subject: this fixture tests git's own maintenance behaviour; repo-locating env stripped: bare_env drops every GIT_*)
                "-c", "maintenance.auto=true", "-c", "maintenance.autoDetach=false", "-c", "gc.autoDetach=false"]
        control = subprocess.run([*bare, "commit", "-q", "--allow-empty", "-m", "control"], capture_output=True,
                                 text=True, env={**bare_env, "GIT_TRACE": "1"})
        check("cleanup CONTROL: with auto-maintenance on, a commit runs it -- in the foreground, never detached",
              ("maintenance run --auto" in control.stderr or "gc --auto" in control.stderr)
              and " --detach" not in control.stderr,
              [l for l in control.stderr.splitlines() if "run_command" in l][:3])
        check("cleanup: a fixture commit starts no background maintenance or gc",
              traced.returncode == 0 and "maintenance run" not in traced.stderr and "gc --auto" not in traced.stderr,
              [l for l in traced.stderr.splitlines() if "maintenance" in l or "gc" in l][:3])

        def commit(msg: str, when: str | None = None) -> None:
            env = dict(os.environ)
            if when:
                env["GIT_COMMITTER_DATE"] = env["GIT_AUTHOR_DATE"] = when
            subprocess.run([*g, "add", "qa"], check=True, env=env)
            subprocess.run([*g, "commit", "-q", "--allow-empty", "-m", msg], check=True, env=env)

        def put(payload, *, committed: bool = True, when: str | None = None) -> None:
            stamp.write_text(json.dumps(payload) if not isinstance(payload, str) else payload, encoding="utf-8")
            if committed:
                commit("stamp", when)

        def run(*argv: str) -> tuple[int, str, str]:
            out, err = io.StringIO(), io.StringIO()
            here = Path.cwd()
            try:
                os.chdir(proj)
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = main(["stamp", *argv])
            finally:
                os.chdir(here)
            return rc, out.getvalue().strip(), err.getvalue()

        old = {"sha": "abc", "date": "2026-09-28", "verdict": "PASS", "report": "qa/reports/r.md"}
        ev = {"first_boot": f"qa/manual-tests/first-boot-{V}", "authz": f"qa/manual-tests/authz-{V}/sweep.csv"}
        base = {**old, "schema": STAMP_SCHEMA, "version": V}
        put({**base, **ev})
        rc, out, _ = run("--rev", "HEAD")
        check("stamp: both layers passing -> 0 and the evidence paths on stdout",
              (rc, out) == (0, f"qa/manual-tests/first-boot-{V}/\nqa/manual-tests/authz-{V}/sweep.csv"), (rc, out))
        put(base)
        rc, out, err = run("--rev", "HEAD")
        check("stamp: a schema-2 stamp naming no evidence is refused", rc == 1 and out == "" and "first_boot" in err,
              (rc, out, err))

        # GRANDFATHERING is decided from git: the committer date of the stamp's commit (#1437 round 3).
        cut = "2026-09-29T00:00:00+00:00"
        put({**old, "date": "old-1"}, when="2026-09-20T12:00:00+00:00")
        f_o, p_o, w_o = check_stamp(stamp, proj, rev="HEAD", grandfather_before=cut)
        check("stamp: an old stamp committed before the cutoff passes, warned", f_o == [] and p_o == [] and len(w_o) == 1,
              (f_o, w_o))
        f_off, _, w_off = check_stamp(stamp, proj, rev="HEAD", grandfather=False, grandfather_before=cut)
        check("stamp: an old stamp is refused once grandfathering is off",
              any("first_boot" in f for f in f_off) and w_off == [], (f_off, w_off))
        put({**old, "date": "at-cutoff"}, when="2026-09-29T00:00:00+00:00")
        f_b, _, _ = check_stamp(stamp, proj, rev="HEAD", grandfather_before=cut)
        check("stamp: a schema-less stamp committed AT the cutoff is refused", any("schema" in f for f in f_b), f_b)
        put({**old, "date": "just-before"}, when="2026-09-28T23:59:59+00:00")
        f_b2, _, w_b2 = check_stamp(stamp, proj, rev="HEAD", grandfather_before=cut)
        check("stamp: one second before the cutoff is still grandfathered", f_b2 == [] and len(w_b2) == 1, (f_b2, w_b2))
        put({**old, "date": "new"}, when="2026-10-02T09:00:00+00:00")
        f_n, _, w_n = check_stamp(stamp, proj, rev="HEAD", grandfather_before=cut)
        check("stamp: a NEW stamp that merely omits schema is refused", any("schema" in f for f in f_n) and w_n == [],
              (f_n, w_n))
        put({**old, "date": "old-2"}, when="2026-09-20T12:00:00+00:00")
        stamp.write_text(json.dumps({**old, "sha": "edited"}), encoding="utf-8")   # edited, not committed
        f_e, _, w_e = check_stamp(stamp, proj, grandfather_before=cut)
        check("stamp: an old stamp edited in the working tree is not the committed one", f_e != [] and w_e == [],
              (f_e, w_e))

        # evidence_path_ok on its own, since check_stamp backs it up with other rules: each rule must be
        # able to fail by itself.
        for bad_path in ("qa/manual-tests/x\napp", "qa/manual-tests/x\ty", "docs/manual-tests/first-boot-v1",
                         "app/qa/manual-tests/first-boot-v1"):
            check(f"evidence_path_ok refuses {bad_path!r}", not evidence_path_ok(bad_path))
        check("evidence_path_ok accepts a real evidence path", evidence_path_ok(f"qa/manual-tests/first-boot-{V}"))
        # A stamp that CARRIES a schema is not old, whatever the value -- even one committed long before
        # the cutoff, which is the case grandfathering would otherwise let through.
        for bad in (True, "2", 2.0, 1):
            put({**old, **ev, "version": V, "schema": bad, "date": f"bad-{bad!r}"}, when="2026-09-20T12:00:00+00:00")
            f_bad, _, w_bad = check_stamp(stamp, proj, rev="HEAD", grandfather_before=cut)
            check(f"stamp: schema {bad!r} is refused, not grandfathered",
                  any("schema" in f for f in f_bad) and w_bad == [], (f_bad, w_bad))
        # CONFINEMENT: evidence named outside qa/manual-tests/ would carry code, and a control character
        # would smuggle a second path into the gate's line-by-line allowance (#1437 round 3 blocker).
        for key, value in (("first_boot", "app"), ("first_boot", "."), ("authz", "a"),
                           ("first_boot", "qa/manual-tests/../../app"), ("authz", "/etc/passwd"),
                           ("first_boot", "qa/manual-tests"), ("first_boot", f"qa/manual-tests/first-boot-{V}\napp"),
                           ("authz", f"qa/manual-tests/authz-{V}/sweep.csv\napp.rb"),
                           ("first_boot", f"qa/manual-tests/first-boot-{V}\r"),
                           ("first_boot", f"qa/manual-tests/first-boot-{V}\tx")):
            put({**base, **ev, key: value})
            f_conf, p_conf, _ = check_stamp(stamp, proj, rev="HEAD")
            check(f"stamp: {key}={value!r} outside the evidence root is refused",
                  any("evidence must be" in f for f in f_conf) and p_conf == [], (f_conf, p_conf))
        # THE RELEASE: evidence is named for the stamp's version, and is not a renamed copy of another's.
        put({**base, **ev, "first_boot": "qa/manual-tests/first-boot-v0"})
        f_ver, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: evidence named for another release is refused", any("not named for this release" in f
                                                                          for f in f_ver), f_ver)
        put({**base, **ev, "version": "../x"})
        f_bv, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: a version that is not a plain release name is refused", any("version" in f for f in f_bv), f_bv)
        shutil.copytree(proj / f"qa/manual-tests/first-boot-{V}", proj / "qa/manual-tests/first-boot-v2")
        (proj / "qa/manual-tests/authz-v2").mkdir()
        (proj / "qa/manual-tests/authz-v2/sweep.csv").write_text(
            AUTHZ_HEADER + "\n".join(AUTHZ_GOOD) + "\nreset,app/models/user.rb:9,it,admin,g,GUARDED,,\n",
            encoding="utf-8")
        put({**base, "version": "v2", "first_boot": "qa/manual-tests/first-boot-v2",
             "authz": "qa/manual-tests/authz-v2/sweep.csv"})
        f_cp, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: last release's walkthrough, renamed, is refused as a copy",
              any("byte-identical" in f and "first-boot-v1" in f for f in f_cp), f_cp)
        (proj / "qa/manual-tests/first-boot-v2/pages.csv").write_text(
            HEADER + "".join(r + "\n" for r in GOOD_ROWS) + "1.9,1280,root,/x,x,y,z,Pass,,,,,re-walked\n",
            encoding="utf-8")
        put({**base, "version": "v2", "first_boot": "qa/manual-tests/first-boot-v2",
             "authz": "qa/manual-tests/authz-v2/sweep.csv"})
        f_rw, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: a walkthrough genuinely re-walked is not a copy", f_rw == [], f_rw)

        # --rev judges what is COMMITTED; the reporter, before committing, judges the working tree.
        _walk(proj / "qa/manual-tests/first-boot-v3", GOOD_ROWS + ["1.8,1280,a,/,x,y,z,Pass,,,,,v3"])
        (proj / "qa/manual-tests/authz-v3").mkdir()
        (proj / "qa/manual-tests/authz-v3/sweep.csv").write_text(
            AUTHZ_HEADER + "\n".join(AUTHZ_GOOD) + "\nx,app/a.rb:1,it,admin,g,GUARDED,,\n", encoding="utf-8")
        v3 = {**base, "version": "v3", "first_boot": "qa/manual-tests/first-boot-v3",
              "authz": "qa/manual-tests/authz-v3/sweep.csv"}
        put(v3, committed=False)
        f_tree, _, _ = check_stamp(stamp, proj)
        check("stamp: uncommitted evidence passes in the working tree (the reporter's pre-commit check)",
              f_tree == [], f_tree)
        # At --rev the COMMITTED stamp is judged, never the working-tree one: commit a stamp naming
        # missing evidence, then write a valid one on disk. The gate must still see the committed one.
        committed_bad = {**v3, "first_boot": "qa/manual-tests/first-boot-v3x"}
        stamp.write_text(json.dumps(committed_bad), encoding="utf-8")
        subprocess.run([*g, "add", "qa/CERTIFICATION"], check=True)
        subprocess.run([*g, "commit", "-q", "-m", "a stamp naming missing evidence"], check=True)
        stamp.write_text(json.dumps(v3), encoding="utf-8")
        f_ws, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: at --rev the committed stamp is judged, not the working-tree one",
              any("first-boot-v3x" in f for f in f_ws), f_ws)
        subprocess.run([*g, "add", "qa/CERTIFICATION"], check=True)
        subprocess.run([*g, "commit", "-q", "-m", "stamp only"], check=True)
        f_rev, p_rev, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: uncommitted evidence is refused at --rev", any("not committed" in f for f in f_rev)
              and p_rev == [], (f_rev, p_rev))
        commit("the v3 evidence")
        # A HOLE committed, with the fixed copy only staged, still denies at --rev.
        sweep3 = proj / "qa/manual-tests/authz-v3/sweep.csv"
        good3 = sweep3.read_text(encoding="utf-8")
        sweep3.write_text(good3 + "\n".join(hole[-1:]) + "\n", encoding="utf-8")
        commit("a HOLE, committed")
        sweep3.write_text(good3, encoding="utf-8")
        subprocess.run([*g, "add", str(sweep3)], check=True)
        f_c, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: a committed HOLE denies at --rev though the fix is staged", any("HOLE" in f for f in f_c), f_c)
        commit("fix the hole")
        # A symlink under the evidence root pointing at code contributes nothing: it is never followed.
        (proj / "app").mkdir()
        _walk(proj / "app", GOOD_ROWS)
        (proj / "qa/manual-tests/first-boot-v4").symlink_to(proj / "app", target_is_directory=True)
        (proj / "qa/manual-tests/authz-v4").mkdir()
        (proj / "qa/manual-tests/authz-v4/sweep.csv").write_text(good3 + "y,app/b.rb:2,it,admin,g,GUARDED,,\n",
                                                                 encoding="utf-8")
        subprocess.run([*g, "add", "app"], check=True)
        put({**base, "version": "v4", "first_boot": "qa/manual-tests/first-boot-v4",
             "authz": "qa/manual-tests/authz-v4/sweep.csv"})
        f_l, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: a committed symlink into code is not evidence", f_l != [], f_l)
        # Planted defects in committed evidence block the stamp, through main().
        pages3 = proj / "qa/manual-tests/first-boot-v3/pages.csv"
        pages3.write_text(HEADER + "".join(r + "\n" for r in blocked), encoding="utf-8")
        put(v3)
        rc, out, err = run("--rev", "HEAD")
        check("stamp: a planted Blocked row blocks the stamp", rc == 1 and "Blocked" in err, (rc, err))
        _walk(proj / "qa/manual-tests/first-boot-v3", GOOD_ROWS + ["1.8,1280,a,/,x,y,z,Pass,,,,,v3"])
        sweep3.write_text(good3 + "\n".join(hole[-1:]) + "\n", encoding="utf-8")
        put(v3)
        rc, out, err = run("--rev", "HEAD")
        check("stamp: a planted HOLE blocks the stamp", rc == 1 and "HOLE" in err, (rc, err))
        put({**v3, "first_boot": "qa/manual-tests/nope"})
        rc, out, err = run("--rev", "HEAD")
        check("stamp: evidence the stamp names but that is missing is refused", rc == 1 and "nope" in err, (rc, err))
        put("not json")
        rc, _, _ = run("--rev", "HEAD")
        check("stamp: an unreadable stamp is unusable (2), never 0", rc == 2, rc)

        # LAST RELEASE'S EVIDENCE (#1437 round 3): main is the last published release. Publish v5,
        # then try to pass it off as v6 three ways.
        _walk(proj / "qa/manual-tests/first-boot-v5", GOOD_ROWS + ["1.7,1280,a,/,x,y,z,Pass,,,,,v5"])
        (proj / "qa/manual-tests/authz-v5").mkdir()
        (proj / "qa/manual-tests/authz-v5/sweep.csv").write_text(good3 + "z,app/c.rb:3,it,admin,g,GUARDED,,\n",
                                                                 encoding="utf-8")
        v5 = {**base, "version": "v5", "first_boot": "qa/manual-tests/first-boot-v5",
              "authz": "qa/manual-tests/authz-v5/sweep.csv"}
        put(v5)
        subprocess.run([*g, "branch", "-f", "main", "HEAD"], check=True)          # v5 is published
        v6 = {**base, "version": "v6", "first_boot": "qa/manual-tests/first-boot-v6",
              "authz": "qa/manual-tests/authz-v6/sweep.csv"}
        # 1. `git mv` of last release's folders, the old ones gone.
        subprocess.run([*g, "mv", "qa/manual-tests/first-boot-v5", "qa/manual-tests/first-boot-v6"], check=True)
        subprocess.run([*g, "mv", "qa/manual-tests/authz-v5", "qa/manual-tests/authz-v6"], check=True)
        put(v6)
        f_mv, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: last release's evidence, git-mv'd to this release's name, is refused",
              any("published in the last release" in f and "pages.csv" in f for f in f_mv)
              and any("published in the last release" in f and "sweep.csv" in f for f in f_mv), f_mv)
        # 2. A new stamp that declares the OLD version and names the old, published evidence.
        subprocess.run([*g, "mv", "qa/manual-tests/first-boot-v6", "qa/manual-tests/first-boot-v5"], check=True)
        subprocess.run([*g, "mv", "qa/manual-tests/authz-v6", "qa/manual-tests/authz-v5"], check=True)
        put({**v5, "date": "re-used"})
        f_old, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: a new stamp re-declaring the published version is refused",
              any("already in the last published release" in f for f in f_old), f_old)
        # 3. KNOWN LIMIT, pinned: a lightly edited copy (one line added) is NOT caught. It is stated in
        # certify.md and the doctrine map; this fixture keeps the statement true.
        shutil.copytree(proj / "qa/manual-tests/first-boot-v5", proj / "qa/manual-tests/first-boot-v6")
        (proj / "qa/manual-tests/first-boot-v6/pages.csv").write_text(
            (proj / "qa/manual-tests/first-boot-v6/pages.csv").read_text(encoding="utf-8") + "\n", encoding="utf-8")
        (proj / "qa/manual-tests/authz-v6").mkdir()
        (proj / "qa/manual-tests/authz-v6/sweep.csv").write_text(good3 + "w,app/d.rb:4,it,admin,g,GUARDED,,\n",
                                                                 encoding="utf-8")
        put(v6)
        f_near, _, _ = check_stamp(stamp, proj, rev="HEAD")
        check("stamp: KNOWN LIMIT -- a copy with one line added is not caught (stated, not hidden)",
              f_near == [], f_near)

    print(f"release_evidence selftest: {checks} check(s)")
    if failures:
        print(f"{len(failures)} FAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
