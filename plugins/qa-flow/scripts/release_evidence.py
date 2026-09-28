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
  stamp            read qa/CERTIFICATION, run both checks on the evidence it names, and print the
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
  * Every screenshot the rows name (Screenshot and Also, `;`-separated) exists in DIR.
  * No second-factor secret is committed. It MATCHES: an `otpauth://` URI; a base32 run of 16+
    characters labelled secret/key/seed/totp; three or more `xxxx-xxxx` codes (a digit in each half) on a line
    that says "recovery" -- in every text file in DIR and in PNG text chunks (tEXt, iTXt, zTXt). It CANNOT
    see pixels: a QR code or a typed key drawn in a screenshot is invisible to it. Redacting the
    image is the walker's job; this catches the secret that leaked as text.
  NOT JUDGED: whether the database was really empty, which roles the app has, or whether every
  role's first sign-in was walked. Those are the plan's (qa-lead) and the reviewer's.

WHAT authz JUDGES
  * Columns: action, location (file:line), actor_role, target_role, guard, verdict (evidence and
    issue optional), and at least one row.
  * verdict is GUARDED, HOLE or UI-ONLY. **Any HOLE fails.** UI-ONLY -- a control that is hidden
    but not enforced, so the forged request got through -- fails too: hiding a button is not a guard.
  * A GUARDED row names its guard; `location` is file:line.
  * At least one row targets the built-in root (`--root-role`, default "root"; the stamp may
    carry "root_role"). The escaped release's holes were all against root.
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
import csv
import io
import json
import re
import struct
import sys
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

FIRST_BOOT_COLUMNS = ("Step", "Width", "Actor", "URL", "Action", "Expected", "Actual", "Status",
                      "Notes", "Screenshot")
STATUSES = {"pass", "fail", "blocked", "not walked"}
UNWALKED = {"blocked", "not walked"}
PHONE_MAX, DESKTOP_MIN = 480, 1024
TEXT_SUFFIXES = {".csv", ".md", ".txt", ".json", ".svg", ".html", ".yml", ".yaml"}

AUTHZ_COLUMNS = ("action", "location", "actor_role", "target_role", "guard", "verdict")
VERDICTS = {"GUARDED", "HOLE", "UI-ONLY"}
FAILING = {"HOLE", "UI-ONLY"}
LOCATION = re.compile(r"^\S+:\d+(?:-\d+)?$")

OTPAUTH = re.compile(r"otpauth://", re.I)
BASE32_SECRET = re.compile(r"\b(?:secret|key|seed|totp)\b[^A-Za-z0-9\n]{0,4}([A-Z2-7]{16,})\b", re.I)
# Each half carries a digit. Without that, screenshot names on a line about recovery codes
# ("1280-05-root-landed-security.png": root-landed, root-after) read as codes -- found by running
# this on a real downstream walkthrough, which it flagged twice for nothing.
RECOVERY_CODE = re.compile(r"\b(?=[a-z]*\d)[a-z0-9]{4,6}-(?=[a-z]*\d)[a-z0-9]{4,6}\b", re.I)


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


def secrets_in(text: str) -> list[str]:
    """Why `text` looks like it carries a second-factor secret; [] when it does not."""
    found = []
    if OTPAUTH.search(text):
        found.append("an otpauth:// URI")
    if BASE32_SECRET.search(text):
        found.append("a labelled base32 secret")
    for line in text.splitlines():
        if "recovery" in line.lower() and len(RECOVERY_CODE.findall(line)) >= 3:
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
        step = row.get("Step") or "?"
        status = row.get("Status", "").lower()
        if status not in STATUSES:
            findings.append(f"step {step}: status {row.get('Status')!r} is not Pass, Fail, Blocked or Not walked")
        elif status in UNWALKED and not row.get("Notes"):
            findings.append(f"step {step}: {row.get('Status')} with no documented reason in Notes -- "
                            f"an unwalked step with no reason is the one that escaped")
        elif status == "fail" and not row.get("Issue"):
            findings.append(f"step {step}: Fail names no filed issue (Issue column)")
        try:
            widths.append(int(row.get("Width", "")))
        except ValueError:
            findings.append(f"step {step}: Width {row.get('Width')!r} is not a number of pixels")
        for col in ("Screenshot", "Also"):
            for name in filter(None, (s.strip() for s in row.get(col, "").split(";"))):
                if not (folder / name).is_file():
                    findings.append(f"step {step}: {col} names {name}, which is not in {folder.name}/")
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
        for why in secrets_in(text):
            findings.append(f"{path.relative_to(folder)}: carries {why} -- redact it before committing")
    return findings


# --------------------------------------------------------------------------- authz

def check_authz(table: Path, root_role: str = "root") -> list[str]:
    rows = read_table(table, AUTHZ_COLUMNS, casefold=True)
    findings: list[str] = []
    for i, row in enumerate(rows, 2):           # row 1 is the header
        where = f"row {i} ({row.get('action') or '?'}: {row.get('actor_role')} -> {row.get('target_role')})"
        verdict = row.get("verdict", "").upper()
        if verdict not in VERDICTS:
            findings.append(f"{where}: verdict {row.get('verdict')!r} is not GUARDED, HOLE or UI-ONLY")
        elif verdict == "HOLE":
            findings.append(f"{where}: HOLE -- the forged request changed the target")
        elif verdict == "UI-ONLY":
            findings.append(f"{where}: UI-ONLY -- the control is hidden, not enforced")
        elif not row.get("guard"):
            findings.append(f"{where}: GUARDED names no guard")
        if not LOCATION.match(row.get("location", "")):
            findings.append(f"{where}: location {row.get('location')!r} is not file:line")
    if not any(root_role.lower() in row.get("target_role", "").lower() for row in rows):
        findings.append(f"no row targets the built-in {root_role!r} -- the escaped release's holes were all against it")
    return findings


# --------------------------------------------------------------------------- stamp

def check_stamp(stamp: Path, base: Path,
                grandfather: bool | None = None) -> tuple[list[str], list[str], list[str]]:
    """(findings, evidence paths, warnings). A schema-2 stamp must NAME both layers, and both pass."""
    grandfather = GRANDFATHER_OLD_STAMPS if grandfather is None else grandfather
    try:
        data = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Unusable(f"{stamp}: not a readable JSON stamp ({exc})") from exc
    if not isinstance(data, dict):
        raise Unusable(f"{stamp}: not a JSON object")
    findings: list[str] = []
    paths: list[str] = []
    schema = data.get("schema")
    current = isinstance(schema, int) and not isinstance(schema, bool) and schema >= STAMP_SCHEMA
    if not current and grandfather:
        return [], [], [f"this stamp predates the first-boot walkthrough and authorization sweep layers "
                        f"(#1428): accepted for this release only. Re-run /qa-flow:certify to add them -- "
                        f"the next release refuses a stamp without them."]
    for key in ("first_boot", "authz"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            findings.append(f"the stamp names no `{key}` evidence -- it predates #1428, or the layer was "
                            f"skipped. Re-run /qa-flow:certify")
    if findings:
        return findings, paths, []
    fb, az = data["first_boot"].strip().rstrip("/"), data["authz"].strip()
    for label, fn in (("first-boot", lambda: check_first_boot(base / fb)),
                      ("authz", lambda: check_authz(base / az, str(data.get("root_role") or "root")))):
        try:
            findings += [f"{label}: {f}" for f in fn()]
        except Unusable as exc:
            findings.append(f"{label}: {exc}")
    return findings, [fb + "/", az], []


# --------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("first-boot"); p.add_argument("dir", type=Path)
    p = sub.add_parser("authz"); p.add_argument("table", type=Path)
    p.add_argument("--root-role", default="root")
    p = sub.add_parser("stamp"); p.add_argument("--stamp", type=Path, default=Path("qa/CERTIFICATION"))
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
            findings, paths, warnings = check_stamp(args.stamp, Path.cwd())
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

    with tempfile.TemporaryDirectory() as td:
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
        png_leak = {"a.png": _png([(b"tEXt", b"Comment\x00" + uri.encode())]), "b.png": _png([])}
        check("secrets: an otpauth URI in a PNG tEXt chunk fails",
              any("a.png" in f and "otpauth" in f for f in fb(GOOD_ROWS, png_leak, name="s2")))
        itxt = {"a.png": _png([(b"iTXt", b"Description\x00\x01\x00\x00\x00" + zlib.compress(uri.encode()))]),
                "b.png": _png([])}
        check("secrets: a compressed iTXt chunk is read too",
              any("a.png" in f for f in fb(GOOD_ROWS, itxt, name="s3")))
        keyed = GOOD_ROWS + ['1.3,1280,root,/login/code,Enrol,Key,"typed key: JBSWY3DPEHPK3PXP",Pass,,,,,x']
        check("secrets: a labelled base32 key fails", any("base32" in f for f in fb(keyed, name="s4")))
        codes = GOOD_ROWS + ['1.5,1280,root,/s,Codes,Shown,"recovery codes a1b2-c3d4 e5f6-g7h8 i9j0-k1l2",Pass,,,,,x']
        check("secrets: a line of recovery codes fails", any("recovery" in f for f in fb(codes, name="s5")))
        redacted = GOOD_ROWS + ['1.5,1280,root,/s,Codes,Shown,"recovery codes shown (redacted)",Pass,,,,,x']
        check("secrets: a redacted mention is NOT a leak", fb(redacted, name="s6") == [], fb(redacted, name="s7"))
        # Control from a real walkthrough: screenshot names on a recovery-code line are not codes.
        names = GOOD_ROWS + ['1.5,1280,root,/s,Codes,Shown,"recovery codes redacted; see 1280-05-root-landed-security.png '
                             'and 1280-05-root-after-code.png and 1280-06-root-demo-off.png",Pass,,,,,x']
        check("secrets: screenshot names beside the word recovery are not codes", fb(names, name="s8") == [],
              fb(names, name="s9"))

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
        badloc = AUTHZ_GOOD + ["reset,UserPolicy,it,admin,policy,GUARDED,,"]
        check("authz: a location that is not file:line fails", any("file:line" in f for f in az(badloc, "a4")))
        noroot = [r for r in AUTHZ_GOOD if ",root," not in r]
        check("authz: no row targeting root fails", any("root" in f for f in az(noroot, "a5")))
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
        _walk(proj / "qa/manual-tests/first-boot-v1", GOOD_ROWS)
        (proj / "qa/manual-tests/authz-v1").mkdir(parents=True)
        (proj / "qa/manual-tests/authz-v1/sweep.csv").write_text(AUTHZ_HEADER + "\n".join(AUTHZ_GOOD) + "\n",
                                                                 encoding="utf-8")
        stamp = proj / "qa/CERTIFICATION"

        def run(payload) -> tuple[int, str, str]:
            stamp.write_text(json.dumps(payload) if not isinstance(payload, str) else payload, encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            here = Path.cwd()
            try:
                import os
                os.chdir(proj)
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    rc = main(["stamp"])
            finally:
                os.chdir(here)
            return rc, out.getvalue().strip(), err.getvalue()

        old = {"sha": "abc", "date": "2026-09-28", "verdict": "PASS", "report": "qa/reports/r.md"}
        base = {**old, "schema": STAMP_SCHEMA}
        rc, out, _ = run({**base, "first_boot": "qa/manual-tests/first-boot-v1",
                          "authz": "qa/manual-tests/authz-v1/sweep.csv"})
        check("stamp: both layers passing -> 0 and the evidence paths on stdout",
              (rc, out) == (0, "qa/manual-tests/first-boot-v1/\nqa/manual-tests/authz-v1/sweep.csv"), (rc, out))
        rc, out, err = run(base)
        check("stamp: a schema-2 stamp naming no evidence is refused", rc == 1 and out == "" and "first_boot" in err,
              (rc, out, err))
        # Grandfathering: an OLD stamp passes with a warning and no evidence paths while the constant
        # is on, and is refused the moment it is off.
        rc, out, err = run(old)
        check("stamp: an old stamp passes, warned, while grandfathered",
              rc == 0 and out == "" and "WARNING" in err and "re-run" in err.lower(), (rc, out, err))
        stamp.write_text(json.dumps(old), encoding="utf-8")
        f_off, _, w_off = check_stamp(stamp, proj, grandfather=False)
        check("stamp: an old stamp is refused once grandfathering is off",
              any("first_boot" in f for f in f_off) and w_off == [], (f_off, w_off))
        # `true` is an int in Python. Read as schema 2 it would be refused here; read correctly as
        # an OLD stamp it is grandfathered -- passes, warned. Only grandfathering-on tells them apart.
        stamp.write_text(json.dumps({**old, "schema": True}), encoding="utf-8")
        f_bool, _, w_bool = check_stamp(stamp, proj, grandfather=True)
        check("stamp: schema true is not schema 2", f_bool == [] and len(w_bool) == 1, (f_bool, w_bool))
        (proj / "qa/manual-tests/first-boot-v1/pages.csv").write_text(
            HEADER + "".join(r + "\n" for r in blocked), encoding="utf-8")
        rc, out, err = run({**base, "first_boot": "qa/manual-tests/first-boot-v1",
                            "authz": "qa/manual-tests/authz-v1/sweep.csv"})
        check("stamp: a planted Blocked row blocks the stamp", rc == 1 and "Blocked" in err, (rc, err))
        _walk(proj / "qa/manual-tests/first-boot-v1", GOOD_ROWS)
        (proj / "qa/manual-tests/authz-v1/sweep.csv").write_text(
            AUTHZ_HEADER + "\n".join(hole) + "\n", encoding="utf-8")
        rc, out, err = run({**base, "first_boot": "qa/manual-tests/first-boot-v1",
                            "authz": "qa/manual-tests/authz-v1/sweep.csv"})
        check("stamp: a planted HOLE blocks the stamp", rc == 1 and "HOLE" in err, (rc, err))
        rc, out, err = run({**base, "first_boot": "qa/manual-tests/nope", "authz": "qa/manual-tests/authz-v1/sweep.csv"})
        check("stamp: evidence the stamp names but that is missing is refused", rc == 1 and "nope" in err, (rc, err))
        rc, _, _ = run("not json")
        check("stamp: an unreadable stamp is unusable (2), never 0", rc == 2, rc)

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
