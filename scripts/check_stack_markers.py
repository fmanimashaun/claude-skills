#!/usr/bin/env python3
"""Do the SHIPPED stack markers detect the projects they describe? (#2165, e6's review of #2198)

`plugins/nextjs-stack/stacks.json` tells the stack detector (`plugins/rails-flow/scripts/detect_stack.py`) what a Next.js,
Supabase or Vercel project looks like. `detect_stack.py --check` (#2189) validates every shipped manifest's SHAPE; it cannot
see a typo that is still well formed: `{"package_dependency": "nxt"}` is a valid marker that matches no Next.js project
on earth. The detector's own selftest builds its manifests inline, so it stays green too. Found by the reviewer changing
`next` to `nxt` in the shipped file: every check passed and real detection broke.

So this runs HAND-WRITTEN projects, each the smallest real layout of its stack, through the real detector against the
real shipped manifest, and states the stacks each must and must not produce. The fixtures are literal on purpose: a
fixture generated FROM the manifest would follow the typo and agree with it.

The near misses matter as much as the hits: a `react`-only app is not Next.js, and a `supabase/` directory with no
`config.toml` is not a linked Supabase project. Without them a manifest that matched everything would pass.

Usage:  python3 scripts/check_stack_markers.py            # the check (the doctor's gate)
        python3 scripts/check_stack_markers.py --selftest # the same run: the fixtures ARE the test
Exit 0 every fixture as stated; 1 a fixture disagrees, or the detector or the manifest is missing (never a silent pass).
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DETECTOR = ROOT / "plugins" / "rails-flow" / "scripts" / "detect_stack.py"
MANIFEST = ROOT / "plugins" / "nextjs-stack" / "stacks.json"
PLUGIN = "nextjs-stack"

PACKAGE_NEXT = '{"name": "app", "dependencies": {"next": "15.0.0", "react": "19.0.0", "react-dom": "19.0.0"}}\n'

# (label, files to write, the nextjs-stack stacks it must report). Written by hand; see the module docstring.
FIXTURES: list[tuple[str, dict[str, str], set[str]]] = [
    ("a Next.js app (next in dependencies) is Next.js", {"package.json": PACKAGE_NEXT}, {"nextjs"}),
    ("next in devDependencies is Next.js too", {"package.json": '{"devDependencies": {"next": "15.0.0"}}\n'}, {"nextjs"}),
    ("a linked Supabase project (supabase/config.toml) is Supabase", {"supabase/config.toml": 'project_id = "app"\n'}, {"supabase"}),
    ("a vercel.json is Vercel", {"vercel.json": "{}\n"}, {"vercel"}),
    ("a .vercel/ directory (vercel link) is Vercel", {".vercel/project.json": '{"projectId": "prj_x"}\n'}, {"vercel"}),
    ("the three together are all three",
     {"package.json": PACKAGE_NEXT, "supabase/config.toml": 'project_id = "app"\n', "vercel.json": "{}\n"},
     {"nextjs", "supabase", "vercel"}),
    ("NEAR MISS: a react-only app is not Next.js", {"package.json": '{"dependencies": {"react": "19.0.0"}}\n'}, set()),
    ("NEAR MISS: a supabase/ directory with no config.toml is not Supabase", {"supabase/migrations/0001_init.sql": "select 1;\n"}, set()),
    ("NEAR MISS: an empty project is nothing", {}, set()),
]


def detected(project: Path) -> set[str]:
    """The nextjs-stack stack ids the real detector reports for `project` (exit 1, no match, is an empty set)."""
    run = subprocess.run([sys.executable, str(DETECTOR), str(project), "--json"], capture_output=True, text=True)
    if run.returncode not in (0, 1):
        raise RuntimeError(f"detect_stack.py exited {run.returncode}: {(run.stderr or run.stdout).strip()[:300]}")
    if run.returncode == 1 and not run.stdout.strip():
        return set()
    stacks = json.loads(run.stdout).get("stacks", [])
    return {s["id"] for s in stacks if s.get("plugin") == PLUGIN}


def main(argv: list[str]) -> int:
    del argv  # `--selftest` and the plain check are the same run: the fixtures are the test
    missing = [str(p.relative_to(ROOT)) for p in (DETECTOR, MANIFEST) if not p.is_file()]
    if missing:
        print(f"FAIL: cannot check the shipped stack markers, missing: {', '.join(missing)}")
        return 1
    failures = 0
    checked = 0
    with tempfile.TemporaryDirectory() as tmp:
        for i, (label, files, expected) in enumerate(FIXTURES):
            project = Path(tmp) / f"project-{i}"
            project.mkdir()
            for rel, text in files.items():
                path = project / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            try:
                got = detected(project)
            except (RuntimeError, json.JSONDecodeError) as error:
                print(f"FAIL  {label}: {error}")
                failures += 1
                continue
            checked += 1
            if got == expected:
                print(f"ok    {label}")
            else:
                print(f"FAIL  {label}: expected {sorted(expected)}, the shipped {MANIFEST.relative_to(ROOT)} gave {sorted(got)}")
                failures += 1
    print(f"stack markers: {checked} of {len(FIXTURES)} fixture(s) run, {failures} failure(s)")
    return 1 if failures or checked != len(FIXTURES) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
