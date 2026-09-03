# docs/brain — the repo side of memory

Open the repo and reconstruct where the work is without re-reading every commit. Claude Code's
auto-memory (`~/.claude/projects/<slug>/memory/`) is per machine and per person; this directory is
the team's. `/rails-flow:brain-sync local` bridges the two: pointers in, verbatim proposals out,
nothing summarised (#877). Adopted here on 2026-09-03 as the first real run of that bridge (#884).

| file | what | cadence |
|---|---|---|
| `STATUS.md` | where we are **right now** — phase, done, next, blockers | edited in place every session |
| `PROGRESS-LOG.md` | dated log of completed chunks | append-only |
| `DECISIONS.md` | ADR-lite `D-001…`: choice, alternatives, rationale, **reversal condition** | append; amend a reversal in place |
| `HYPOTHESES.md` | `candidate → proposed → confirmed \| refuted`, dated evidence | as evidence arrives |
| `MEMORY.md` | one-line index of `feedback_*` / `decision_*` memos | one line per memo |
| `memos/feedback/*.md`, `memos/decision/*.md` | one lesson or decision each; the type is the directory; frontmatter `name` / `description` / `type` | via `/rails-flow:brain` |

**Provenance tags** on every non-obvious claim: `[observed]` (happened or measured), `[decided]`
(backed by a DECISIONS entry), `[assumed]` (working assumption), `[reported]` (someone asserted it).
Preserve contradictions — list both sides, never average them.

**Hypothesis lifecycle:** a `candidate` names what would confirm or refute it; `proposed` has a
dated evidence list; `confirmed` points at the DECISIONS entry it produced; `refuted` says why.

Commands: `/rails-flow:brain` (institutionalise a lesson) · `/rails-flow:brain-review` (weekly sweep:
staleness, drift, contradictions; stamps `.last-review`) · `/rails-flow:brain-sync` (`publish` / `pull`
to a shared hub; `local` to this machine's Claude memory). The maintainer's incident narrative that
backs `CLAUDE.md` lives in `docs/maintainer-history.md`, not here — see `D-004`.
