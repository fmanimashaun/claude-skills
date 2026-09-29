---
name: feedback-a-watcher-that-cannot-see-a-dead-job
description: Three supervision instruments each reported "in progress" for work that was dead or incomplete; verify by PID and re-read the raw list.
type: feedback
---

Three different instruments reported "still running" for work that was dead or not finished,
within one promotion. Each looked like progress and none was.

- **`nohup cmd > f 2>&1 &` inside a Bash tool call died with its parent shell** and left `f` at
  **zero bytes**. I read 0 bytes as "buffering" for ~15 minutes. Python buffers when stdout is not
  a tty, so an empty file is genuinely ambiguous — use the harness's `run_in_background`, whose
  exit is tracked, and confirm life with `pgrep`/`ps` by PID, never by output size.
- **The waiter `until ! pgrep -f "maintainer_doctor.py --gates-only"; do sleep 10; done` matched
  its own command line**, so it could never exit. Any `pgrep -f` inside a loop whose own argv
  contains the pattern is self-matching. Grep for the interpreter too (`python3 scripts/x.py`), or
  exclude `$$`.
- **A Monitor filtering `select(.bucket != "pending")` reported 7 checks all passing** while a
  direct `gh pr checks <n>` returned **11 rows, 4 pending, rc=8** — a second workflow run had
  registered after the monitor sampled. The filter removed exactly the rows that said "wait".

**Why:** an instrument that cannot distinguish *not running* from *in progress*, or *incomplete
list* from *complete list*, reports the same thing in both states — and the reassuring reading is
the one you take. This is [[a-check-that-cannot-tell-the-two-apart]] applied to job supervision,
and it nearly published a release on a partial check list.

**How to apply:** before trusting any "still running", confirm the process by PID. Before trusting
any "all green", re-read the raw list and assert the exit code (`gh pr checks` → `rc=0`), never a
stream's filtered view. Silence and emptiness are not evidence of progress. See
[[gate-the-commit-on-the-check]] and [[filter-ci-runs-by-event]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-watcher-that-cannot-see-a-dead-job.md._
