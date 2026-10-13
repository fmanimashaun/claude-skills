"""check_local_target.py — refuse to aim k6 or ZAP at a host that is not this machine (#1954).

  python3 check_local_target.py [URL]      # URL defaults to $QA_BASE_URL
  python3 check_local_target.py --selftest

Exit 0: the target is this machine, or the host is named in QA_ALLOW_REMOTE_TARGET (audited on stderr).
Exit 2: anything else, and the reason is printed. Run it before every k6 or ZAP command; it is the mechanism behind "never production".
The rule is robot_descriptor.local_url (one home for "is this URL this machine"). The opt-in names the HOST, not a yes: a staging host
is allowed by saying which one, and a URL with userinfo or no parsable host is refused even then, because it hides the host it dials.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent))
from robot_descriptor import local_url  # noqa: E402

HERE = Path(__file__).resolve()


def verdict(raw: object, allow: str = "") -> tuple[int, str]:
    """(exit code, message) for one target and the QA_ALLOW_REMOTE_TARGET value."""
    why = local_url(raw)
    if why is None:
        return 0, ""
    if not why.startswith("dials "):
        return 2, f"BLOCKED: QA target {why}"       # missing, malformed, wrong scheme or userinfo: never opt-in-able
    host = urlsplit(str(raw)).hostname or ""
    if host and allow.strip().lower() == host.lower():
        return 0, f"check_local_target: {host} is not this machine, but QA_ALLOW_REMOTE_TARGET={host} — allowed (audited)."
    return 2, (f"BLOCKED: QA target {why}. k6 load and ZAP run only against this machine; to aim them at a staging host, "
               f"set QA_ALLOW_REMOTE_TARGET=<that host> (audited). Never production.")


def selftest() -> int:
    bad: list[str] = []
    cases = [
        ("http://127.0.0.1:3000", "", 0, ""),
        ("http://localhost:3000/up", "", 0, ""),
        ("http://[::1]:3000", "", 0, ""),
        ("https://app.example.com", "", 2, "not this machine"),
        ("https://127.0.0.1:443@prod.example.com", "", 2, "userinfo"),
        ("https://127.0.0.1:443@prod.example.com", "prod.example.com", 2, "userinfo"),
        ("http://localhost.example.com", "", 2, "not this machine"),
        ("", "", 2, "is missing"),
        ("not a url", "", 2, "http or https"),
        ("http://localhost:99999", "", 2, "not a valid URL"),
        ("ftp://localhost", "", 2, "http or https"),
        ("https://staging.example.com", "staging.example.com", 0, "audited"),
        ("https://staging.example.com", "STAGING.example.com", 0, "audited"),
        ("https://prod.example.com", "staging.example.com", 2, "not this machine"),
        ("https://prod.example.com", "1", 2, "not this machine"),
        ("https://prod.example.com", "example.com", 2, "not this machine"),
    ]
    for raw, allow, code, text in cases:
        got, msg = verdict(raw, allow)
        if got != code or text not in msg:
            bad.append(f"verdict({raw!r}, allow={allow!r}) -> {got} {msg!r}; expected {code} containing {text!r}")
    for env, args, code, text in ((None, [], 2, "is missing"),
                                  ({"QA_BASE_URL": "https://prod.example.com"}, [], 2, "Never production"),
                                  ({"QA_BASE_URL": "http://localhost:3000"}, [], 0, ""),
                                  ({"QA_BASE_URL": "http://localhost:3000"}, ["https://prod.example.com"], 2, "BLOCKED")):
        e = {k: v for k, v in os.environ.items() if k not in ("QA_BASE_URL", "QA_ALLOW_REMOTE_TARGET")}
        e.update(env or {})
        r = subprocess.run([sys.executable, str(HERE), *args], env=e, capture_output=True, text=True, timeout=30)
        if r.returncode != code or text not in r.stderr:
            bad.append(f"cli env={env} args={args}: exit {r.returncode}, stderr {r.stderr!r}; expected {code} containing {text!r}")
    for b in bad:
        print(f"FAIL {b}")
    print(f"check_local_target selftest: {'FAILED ' + str(len(bad)) if bad else 'ok'}")
    return 1 if bad else 0


def main() -> int:
    args = sys.argv[1:]
    if args == ["--selftest"]:
        return selftest()
    if len(args) > 1:
        print(__doc__.split("\n\n")[0], file=sys.stderr)
        return 2
    code, msg = verdict(args[0] if args else os.environ.get("QA_BASE_URL", ""), os.environ.get("QA_ALLOW_REMOTE_TARGET", ""))
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
