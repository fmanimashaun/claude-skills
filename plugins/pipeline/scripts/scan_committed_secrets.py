#!/usr/bin/env python3
"""Prove no secret from .kamal/deploy.env sits in a file git would commit (#1341).

Run:  scan_committed_secrets.py [--root DIR]     # 0 clean · 1 a secret found · 2 cannot check
      scan_committed_secrets.py --selftest

WHY. The deploy safety pass is BLOCKING, and it said "`git diff` proves no plaintext secret entered
a committed file". Plain `git diff` shows only UNSTAGED changes to TRACKED files. A freshly generated
`config/deploy.yml` is untracked, and a staged edit is invisible to it, so the check could not see the
file most likely to carry a secret. A BLOCKING step that cannot see its target passes vacuously.

WHAT IS A SECRET. `.kamal/deploy.env` tags each section with where its keys are routed. Keys under
"ROUTED TO: .kamal/secrets" and "ROUTED TO: Rails encrypted credentials" are secrets. Keys routed to
`config/deploy.yml` are non-secret deploy facts and are EXPECTED to appear there, so they are not
scanned. An untagged key counts as a secret: guessing "public" is the unsafe direction.

WHAT IS SCANNED. Every file `git ls-files --cached --others --exclude-standard` lists: tracked plus
untracked-but-not-ignored, which is exactly what a `git add` of the tree would commit. Values shorter
than 8 characters are skipped (a bare `true` or `5432` would match everywhere); the count skipped is
reported so a short real secret is not silently exempt. Findings name the KEY and the FILE, never
the value.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

BRIEFING = Path(".kamal/deploy.env")
SECTION = re.compile(r"ROUTED TO:\s*(?P<dest>[^(]+)")
SECRET_DESTS = (".kamal/secrets", "rails encrypted credentials")
PUBLIC_DESTS = ("config/deploy.yml",)
ASSIGN = re.compile(r"^(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$")
MIN_LEN = 8


class Unusable(RuntimeError):
    pass


def routed_names(text: str) -> list[str]:
    """The NAMES of the secret-routed keys that hold a value. Only names ever reach the output."""
    return sorted(secrets(text))


def secrets(text: str) -> dict[str, str]:
    """KEY -> value for every secret-routed key with a value. Values are compared, never printed."""
    out, secret = {}, True  # before any section tag: treat as secret
    for raw in text.splitlines():
        line = raw.strip()
        tag = SECTION.search(line) if line.startswith("#") else None
        if tag:
            dest = tag.group("dest").strip().lower()
            secret = not any(dest.startswith(p) for p in PUBLIC_DESTS) or any(s in dest for s in SECRET_DESTS)
            continue
        if not line or line.startswith("#"):
            continue
        m = ASSIGN.match(line)
        if not m or not secret:
            continue
        value = re.split(r"\s+#", m.group("value"), maxsplit=1)[0].strip().strip("\"'")
        if value:
            out[m.group("key")] = value
    return out


def committable(root: Path) -> list[Path]:
    proc = subprocess.run(["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise Unusable(f"not a git work tree: {proc.stderr.strip()}")
    return [root / p for p in proc.stdout.split("\0") if p]


def scan(root: Path) -> tuple[int, list[str]]:
    briefing = root / BRIEFING
    if not briefing.is_file():
        return 2, [f"UNUSABLE: no {BRIEFING}, so there are no secret values to look for"]
    try:
        text_env = briefing.read_text(encoding="utf-8")
        files = committable(root)
    except (OSError, Unusable) as exc:
        return 2, [f"UNUSABLE: {exc}"]
    names = routed_names(text_env)
    routed = secrets(text_env)
    long_names = [k for k in names if len(routed[k]) >= MIN_LEN]   # one order, shared by both lists
    needles = [routed[k] for k in long_names]
    short = [k for k in names if k not in long_names]
    findings = []
    for path in files:
        if path.resolve() == briefing.resolve() or not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:
            continue  # binary, the way git decides it
        text = data.decode("utf-8", errors="replace")
        for index, needle in enumerate(needles):
            if needle in text:
                findings.append(f"  [secret-in-committable-file] {long_names[index]} appears in {path.relative_to(root)}")
    note = f" ({len(short)} value(s) under {MIN_LEN} chars not scanned: {', '.join(short)})" if short else ""
    if findings:
        return 1, [f"{len(findings)} secret value(s) in files git would commit{note}:", *findings]
    return 0, [f"no secret from {BRIEFING} in any of {len(files)} committable file(s); "
               f"{len(needles)} value(s) scanned{note}"]


def selftest() -> int:
    import tempfile

    failures: list[str] = []

    def expect(label: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"{label} {detail}".rstrip())

    env = ("# ═══ ROUTED TO: config/deploy.yml  (non-secret deploy facts) ═══\n"
           "WEB_HOST=203.0.113.10                 # server\n"
           "# ═══ ROUTED TO: .kamal/secrets  (gitignored) ═══\n"
           "KAMAL_REGISTRY_PASSWORD=example-registry-token-0001   # PAT\n"
           "POSTGRES_PASSWORD=short\n"
           "# ═══ ROUTED TO: Rails encrypted credentials ═══\n"
           "CRED__stripe__api_key=example-api-key-0002\n")
    got = secrets(env)
    expect("secret-routed keys are read, comments stripped",
           got.get("KAMAL_REGISTRY_PASSWORD") == "example-registry-token-0001" and got.get("CRED__stripe__api_key") == "example-api-key-0002",
           str(got))
    expect("CONTROL: a deploy.yml-routed fact is not a secret", "WEB_HOST" not in got, str(got))
    expect("an untagged key counts as a secret", "X" in secrets("X=abcdefghij\n"))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        subprocess.run(["git", "init", "-q"], cwd=root, check=True)
        (root / ".gitignore").write_text(".kamal/deploy.env\n.kamal/secrets\n", encoding="utf-8")
        (root / ".kamal").mkdir()
        (root / BRIEFING).write_text(env, encoding="utf-8")
        (root / "config").mkdir()
        deploy = root / "config" / "deploy.yml"
        deploy.write_text("servers:\n  web: [203.0.113.10]\nregistry:\n  password: [KAMAL_REGISTRY_PASSWORD]\n",
                          encoding="utf-8")
        code, out = scan(root)
        expect("CONTROL: a deploy.yml holding names and public facts is clean", code == 0, str(out))
        expect("...and the short value is reported as not scanned", "POSTGRES_PASSWORD" in out[0], str(out))
        deploy.write_text(deploy.read_text() + "  token: example-registry-token-0001\n", encoding="utf-8")
        code, out = scan(root)
        expect("an UNTRACKED file holding a secret is found (plain git diff cannot see it)",
               code == 1 and any("KAMAL_REGISTRY_PASSWORD appears in config/deploy.yml" in l for l in out), str(out))
        expect("...and the value itself is never printed", not any("example-registry-token-0001" in l for l in out), str(out))
        subprocess.run(["git", "add", "config/deploy.yml"], cwd=root, check=True)
        expect("a STAGED file holding a secret is found", scan(root)[0] == 1)
        (root / ".kamal" / "secrets").write_text("KAMAL_REGISTRY_PASSWORD=example-registry-token-0001\n", encoding="utf-8")
        subprocess.run(["git", "rm", "-q", "--cached", "config/deploy.yml"], cwd=root, check=True)
        deploy.write_text("registry:\n  password: [KAMAL_REGISTRY_PASSWORD]\n", encoding="utf-8")
        expect("CONTROL: an ignored secrets file is not scanned", scan(root)[0] == 0, str(scan(root)))
        (root / BRIEFING).unlink()
        expect("no briefing is UNUSABLE, never clean", scan(root)[0] == 2)

    for f in failures:
        print(f"FAIL: {f}")
    print(f"scan_committed_secrets selftest: {len(failures)} failure(s)")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="scan_committed_secrets.py", description=__doc__.splitlines()[0])
    ap.add_argument("--root", default=".", type=Path)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    code, lines = scan(a.root.resolve())
    print("\n".join(lines), file=sys.stderr if code == 2 else sys.stdout)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
