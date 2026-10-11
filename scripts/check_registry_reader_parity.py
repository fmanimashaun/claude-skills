#!/usr/bin/env python3
"""The two requirement-registry readers answer the same (#1857).

qa-flow's `check_requirements.py` gates the registry and rails-flow's `check_registry_closed.py` reads one more key from it. Plugins install alone, so rails-flow
cannot import qa-flow and carries its own small reader of the same grammar (`- id:` opens an entry, every line `key: <JSON value>`). Two readers of one
format drift silently; this maintainer gate runs both over the same registries, valid and malformed, and fails when their entries or their problems differ.

    python3 scripts/check_registry_reader_parity.py             # the gate
    python3 scripts/check_registry_reader_parity.py --selftest  # a reader that disagrees is reported, and a fault in the comparison is not silent
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QA = ROOT / "plugins" / "qa-flow" / "scripts" / "check_requirements.py"
RAILS = ROOT / "plugins" / "rails-flow" / "scripts" / "check_registry_closed.py"

SAMPLES = {
    "valid": '# rows: 2\n- id: "R-1"\n  area: "A"\n  requirement: "x"\n  status: "done"\n  issue: 12\n  closed: true\n- id: "R-2"\n  status: "partial"\n  feature: true\n',
    "comments and blanks": '# a comment\n\n- id: "R-1"\n\n  # inside\n  status: "done"\n',
    "not JSON": '- id: R-1\n  status: "done"\n',
    "not a key line": '- id: "R-1"\n  oops\n',
    "a field before the first entry": '  status: "done"\n- id: "R-1"\n',
    "a BOM": '\ufeff- id: "R-1"\n  status: "done"\n',
    "an empty file": "",
    "a repeated key": '- id: "R-1"\n  issue: 1\n  issue: null\n',
    "a repeated id key": '- id: "R-1"\n  id: "R-2"\n',
    "uppercase key": '- id: "R-1"\n  Status: "done"\n',
    "a nested value": '- id: "R-1"\n  specs: ["a", "b"]\n  issue: null\n',
}


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def differences(read_a, read_b, samples: dict[str, str]) -> list[str]:
    """The samples on which two `load(root, registry) -> (entries, problems)` functions disagree."""
    found = []
    for name, text in samples.items():
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "qa").mkdir()
            (root / "qa" / "requirements.yml").write_text(text, encoding="utf-8")
            a, b = read_a(root, "qa/requirements.yml"), read_b(root, "qa/requirements.yml")
        if a != b:
            found.append(f"{name}: qa-flow read {a!r}, rails-flow read {b!r}")
    return found


def selftest() -> int:
    failures = []
    same = lambda root, registry: ([{"_line": 1, "id": "R"}], [])  # noqa: E731
    other = lambda root, registry: ([{"_line": 1, "id": "S"}], [])  # noqa: E731
    if differences(same, same, SAMPLES):
        failures.append("two identical readers are reported as different")
    if len(differences(same, other, SAMPLES)) != len(SAMPLES):
        failures.append("a reader that disagrees is not reported on every sample")
    only_problems = lambda root, registry: ([{"_line": 1, "id": "R"}], ["a problem"])  # noqa: E731
    if not differences(same, only_problems, {"x": "y"}):
        failures.append("a difference only in the problems is not reported")
    if failures:
        print("check_registry_reader_parity selftest FAILED --\n" + "\n".join(f"  - {f}" for f in failures))
        return 1
    print("check_registry_reader_parity selftest: ok (0 failure(s))")
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--selftest"]:
        return selftest()
    qa, rails = load_module(QA, "parity_check_requirements"), load_module(RAILS, "parity_check_registry_closed")
    found = differences(qa.load, rails.load, SAMPLES)
    for line in found:
        print(line)
    print(f"registry reader parity: {len(SAMPLES)} sample(s), {'the two readers agree' if not found else str(len(found)) + ' difference(s)'}")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
