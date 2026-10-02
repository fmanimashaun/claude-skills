"""Git that starts nothing in the background, for every subprocess the gate and mutation runners launch.

A `git commit` in a fixture repo runs `git maintenance run --auto --quiet --detach` (GIT_TRACE shows it),
a background process that can still be writing into the repo when the selftest removes its temp
directory. `rmtree` then raises "Directory not empty" from cleanup, the selftest dies before printing its
verdict, and mutation coverage reads a correct mutant as "caught by the wrong fixture" (#1493). Twenty
selftests commit in temp repos (#1510); this sets the two keys once, through git's own environment
config (`GIT_CONFIG_COUNT`/`KEY_n`/`VALUE_n`), instead of in each of them.
"""
from __future__ import annotations

import os
from collections.abc import Mapping

SETTINGS: tuple[tuple[str, str], ...] = (("maintenance.auto", "false"), ("gc.auto", "0"))


def env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    """`base` (default: this process's environment) with SETTINGS appended to any GIT_CONFIG_* pairs
    already there -- appended, never renumbered, so a caller's own pairs keep their meaning. A count git
    would reject is left untouched."""
    out = dict(os.environ if base is None else base)
    count = out.get("GIT_CONFIG_COUNT", "")
    # git's rules, not Python's int(): empty means none, ASCII digits are a count, and anything else
    # (`-1`, `abc`, ` 2 `) git itself rejects -- so leave such an environment exactly as it is rather
    # than half-repair it into one that silently drops our keys or every git call fails (PR #1514 review).
    if count and not (count.isascii() and count.isdigit()):
        return out
    start = int(count) if count else 0
    for i, (key, value) in enumerate(SETTINGS, start):
        out[f"GIT_CONFIG_KEY_{i}"] = key
        out[f"GIT_CONFIG_VALUE_{i}"] = value
    out["GIT_CONFIG_COUNT"] = str(start + len(SETTINGS))
    return out
