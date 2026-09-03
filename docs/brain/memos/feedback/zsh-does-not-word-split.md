---
name: feedback-zsh-does-not-word-split
description: The Bash tool runs zsh here; an unquoted $var is ONE word, so `for f in $files` and `python3 scripts/$c` with flags both silently misfire
type: feedback
---

The Bash tool on this machine is **zsh**, and zsh does not word-split an unquoted parameter.
`for f in $files` iterates once over the whole newline-joined string, and `python3 scripts/$c`
where `c="doctor.py --selftest"` looks for a file literally named `doctor.py --selftest`.

**Why:** it cost two rounds in one session — a `sed` loop that "processed 1 file" (none) and a
gate loop where every command with a flag reported "No such file" and the real failing gate stayed
hidden behind the noise. Both looked like the *target* was broken.

**How to apply:** for lists of files, do the work in Python (`git ls-files -z` + `split("\0")`).
For command-with-args loops, `eval "python3 scripts/$c"` or `${=c}`. Never `for x in $var`.
Related: [[never-pass-backticks-through-double-quotes]].

**Second shape, same trap (2026-09-03):** `for g in "x.py --check" "y.py"; do python3 $g; done` runs
`python3 "x.py --check"` — file not found, so every gate printed FAIL while all six passed. The
args-in-a-string loop is the same defect as `for f in $files`; use `eval "python3 $g"` or `${=g}`.

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, zsh-does-not-word-split.md._
