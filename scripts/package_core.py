#!/usr/bin/env python3
"""Deterministic .skill packager — the ONE canonical zip builder.

Removes the metadata sources of nondeterminism: fixed timestamps, sorted
entries, fixed permissions, deflate level 9. Output is byte-identical across
runs and machines *that share a zlib/DEFLATE implementation*. Note: the
compressed bytes still depend on the zlib version (e.g. stock zlib vs zlib-ng
produce different output), so byte-for-byte agreement is not guaranteed across
differing zlib builds — the archive contents are always identical. package.sh
and package.ps1 are thin wrappers around this, and automated rebuilds use it
too. Never zip skills any other way — ad-hoc zip tools can never byte-agree.
"""
import os, sys, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
DIST = os.path.join(ROOT, "dist")

def build(name: str) -> str:
    src = os.path.join(SKILLS_DIR, name)
    if not os.path.isdir(src):
        sys.exit(f"unknown skill: {name}")
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"{name}.skill")
    entries = []
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for f in sorted(files):
            fp = os.path.join(root, f)
            arc = os.path.relpath(fp, SKILLS_DIR).replace(os.sep, "/")
            entries.append((arc, fp))
    entries.sort()
    with zipfile.ZipFile(out, "w") as z:
        for arc, fp in entries:
            zi = zipfile.ZipInfo(arc, date_time=(2020, 1, 1, 0, 0, 0))
            zi.external_attr = 0o100644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(fp, "rb") as fh:
                z.writestr(zi, fh.read(), compresslevel=9)
    return out

if __name__ == "__main__":
    names = sys.argv[1:] or sorted(os.listdir(SKILLS_DIR))
    for n in names:
        if os.path.isdir(os.path.join(SKILLS_DIR, n)):
            out = build(n)
            print(f"{out}  {os.path.getsize(out)} bytes")
