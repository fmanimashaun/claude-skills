#!/usr/bin/env python3
"""Canonical .skill packager — truly reproducible.

Entries are STORED (uncompressed): no DEFLATE means no zlib, so output cannot
vary across zlib implementations (stock zlib vs zlib-ng), Python versions, or
operating systems. Combined with fixed timestamps, sorted entries, pinned
permissions and a pinned create_system, the build is byte-identical on any
machine. package.sh / package.ps1 are thin wrappers around this; automated
rebuilds use it too. Never zip skills any other way.

LINE ENDINGS ARE NORMALISED, AND THAT IS LOAD-BEARING
-----------------------------------------------------
Text members are written with LF regardless of what the working copy holds, so
the output no longer depends on being a *clean* checkout.

Why that mattered: `.gitattributes` is `* text=auto eol=lf` with `*.skill
binary`, so git normalises sources to LF on commit but stores the artifact
byte-for-byte. Packaging a freshly authored file on Windows therefore produced an
archive carrying CRs its own committed sources did not have — 424 bytes' worth in
one case (#171). The committed artifact stopped matching a clean rebuild, and
`release.yml` fails on that drift, so the next promotion was blocked.

The check CLAUDE.md prescribes ("run the packager, confirm git status shows only
the intended dist/ change") could not catch it: it runs *before* the normalisation
that creates the mismatch, so it passed locally while producing a bad artifact.
A guarantee that only holds when you remember something is not a guarantee, so it
moved here.

Binary members are detected the way git detects them — a NUL byte in the first
8000 bytes — rather than by an extension allowlist. An allowlist needs
maintaining and **fails open**: the first type nobody adds silently reverts to
raw bytes, which is the original bug. Sniffing protects a future `.png` in a
brand pack without anyone listing it. Like git's `eol=lf`, only CRLF is
converted; a lone CR is left alone.

Verify with `python3 scripts/package_core.py --selftest`.
"""
import os, sys, tempfile, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
DIST = os.path.join(ROOT, "dist")

# git's own binary test: NUL in the first 8000 bytes.
_SNIFF_BYTES = 8000


def is_binary(blob: bytes) -> bool:
    """True when git would treat this content as binary (and so leave it alone)."""
    return b"\x00" in blob[:_SNIFF_BYTES]


def canonical_bytes(blob: bytes) -> bytes:
    """The bytes a clean checkout would have produced.

    Text -> LF line endings. Binary -> untouched, byte for byte.
    """
    if is_binary(blob):
        return blob
    return blob.replace(b"\r\n", b"\n")


def build(name: str, skills_dir: str = SKILLS_DIR, dist: str = DIST) -> str:
    src = os.path.join(skills_dir, name)
    if not os.path.isdir(src):
        sys.exit(f"unknown skill: {name}")
    os.makedirs(dist, exist_ok=True)
    out = os.path.join(dist, f"{name}.skill")
    entries = []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for f in sorted(files):
            fp = os.path.join(root, f)
            arc = os.path.relpath(fp, skills_dir).replace(os.sep, "/")
            entries.append((arc, fp))
    entries.sort()
    with zipfile.ZipFile(out, "w") as z:
        for arc, fp in entries:
            zi = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = 0o100644 << 16
            zi.create_system = 3          # pin: defaults differ Windows vs Unix
            zi.compress_type = zipfile.ZIP_STORED   # no compressor, no zlib variance
            with open(fp, "rb") as fh:
                z.writestr(zi, canonical_bytes(fh.read()))
    return out


# --------------------------------------------------------------------------
# selftest — the guarantee, asserted rather than described
# --------------------------------------------------------------------------

# A NUL in the header is what makes this binary to git's test; the CRLF inside is
# the trap. Naive normalisation corrupts it, so this fixture is the whole point of
# criterion 3 on #171.
_FAKE_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + b"row1\r\nrow2\r\n"


def _tree(root: str, files: dict) -> None:
    for relpath, blob in files.items():
        target = os.path.join(root, relpath)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as fh:
            fh.write(blob)


def selftest() -> int:
    import io

    failures, total = [], 0

    def check(label, condition):
        nonlocal total
        total += 1
        if not condition:
            failures.append(label)

    # 1. The core guarantee: CRLF and LF working copies build identical bytes.
    crlf = {"demo/SKILL.md": b"# Demo\r\n\r\nLine two.\r\n",
            "demo/references/a.md": b"alpha\r\nbeta\r\n"}
    lf = {k: v.replace(b"\r\n", b"\n") for k, v in crlf.items()}
    built = {}
    for label, files in (("crlf", crlf), ("lf", lf)):
        work = tempfile.mkdtemp(prefix=f"pkg-{label}-")
        skills, dist = os.path.join(work, "skills"), os.path.join(work, "dist")
        _tree(skills, files)
        with open(build("demo", skills, dist), "rb") as fh:
            built[label] = fh.read()
    check("CRLF and LF working copies must build identical bytes",
          built["crlf"] == built["lf"])
    # Assert on the MEMBERS, not the archive bytes: a ZIP's CRC and size fields can
    # legitimately contain 0x0D, so scanning the container would fail spuriously.
    with zipfile.ZipFile(io.BytesIO(built["crlf"])) as z:
        check("no text member may carry a CR after normalisation",
              all(b"\r" not in z.read(n) for n in z.namelist()))

    # 2. Binary members survive byte-for-byte, CRLF inside and all.
    work = tempfile.mkdtemp(prefix="pkg-bin-")
    skills, dist = os.path.join(work, "skills"), os.path.join(work, "dist")
    _tree(skills, {"demo/SKILL.md": b"# Demo\r\n", "demo/assets/logo.png": _FAKE_PNG})
    out = build("demo", skills, dist)
    with zipfile.ZipFile(out) as z:
        check("a binary member must be stored unmodified",
              z.read("demo/assets/logo.png") == _FAKE_PNG)
        check("a text member must be normalised",
              z.read("demo/SKILL.md") == b"# Demo\n")
        info = z.getinfo("demo/SKILL.md")
        check("entries must stay ZIP_STORED", info.compress_type == zipfile.ZIP_STORED)
        check("create_system must stay pinned to 3", info.create_system == 3)
        check("timestamps must stay fixed", info.date_time == (2020, 1, 1, 0, 0, 0))

    # 3. The sniffer must agree with git on both directions.
    check("NUL-bearing content is binary", is_binary(_FAKE_PNG))
    check("plain text is not binary", not is_binary(b"# hello\r\nworld\r\n"))
    check("a lone CR is left alone, matching git's eol=lf",
          canonical_bytes(b"a\rb") == b"a\rb")
    check("CRLF becomes LF", canonical_bytes(b"a\r\nb") == b"a\nb")

    print(f"ran {total} packaging assertion(s), {total - len(failures)} passed")
    if failures:
        print("\nFAILED:")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("output is byte-identical regardless of working-copy line endings")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--selftest" in argv:
        sys.exit(selftest())
    names = argv or sorted(os.listdir(SKILLS_DIR))
    for n in names:
        if os.path.isdir(os.path.join(SKILLS_DIR, n)):
            out = build(n)
            print(f"{out}  {os.path.getsize(out)} bytes")
