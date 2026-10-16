# Independent review: DRAFT write-tools epic (claude-skills-93) — reviewer claude-skills-3c, 2026-10-14

> **Evidence, not doctrine.** The independent review of the draft write-tools epic (reviewer claude-skills-3c). Its points were applied before #2050 was filed. It names `DRAFT-implementation-issue.md`, the unfiled draft, which #2050 superseded and which is not kept. Nothing here is a claim a skill relies on; each source carries its own VERIFIED / SECONDARY / RECALL / NOT FOUND label. Moved on 2026-10-14 from `claude-skills-wt/_logs/agent-ready-research/REVIEW-3c-write-tools-epic.md` (#2061); the text below is unchanged.


Read in full: `DRAFT-implementation-issue.md` (43 lines) and `research-write-tools.md` (148 lines). I re-checked the LOCAL claims against origin/dev of both repos; external pages were not re-fetched (I note where that matters).

**Verdict: file it after the four MUST-FIX points below. The research is careful and labelled; the problems are in how the epic is split into one-PR children, and in two stale facts.**

## What I re-measured (all hold unless noted)
- `skills/rails-8/references/mcp-server.md` is 96 lines; §3's "Write tools are a separate, later decision" is at line 66; `mcp` gem `v1.6.0` at line 17; the §4 proof "No tool writes: run every registered tool and assert that no table's row count changed" at line 88. ✔
- `check_mcp_annotations.py` docstring: requires `read_only_hint` and `open_world_hint` explicit, "TWO of them" (lines 2, 16). ✔ (Behaviour on `read_only_hint: false` is from the docstring, not a run; the draft states it as fact. See point 6.)
- The downstream app's specs pin all four hints. ✔
- **STALE:** the downstream app's CLI code is now on that app's main development branch. The draft and the research say it is not.
- **DRIFT:** a line number for one downstream spec example disagreed between the draft and the research; cite such an example by name, not by line.

## Findings, each with a disposition

1. **MUST-FIX: Stage 1 is not closable by one PR.** It is MIXED, and the draft itself says "Split the PR (CLAUDE.md 'split a mixed change')". One child issue cannot then be closed by one PR. **Disposition:** file Stage 1 as TWO children: 1a, the cited MUST/SHOULD quotes (each with a `doctrine-verifier` verdict against revision 2026-07-28); and 1b, the checklist's existence and wording (maintainer decision recorded on the issue). 1b depends on 1a.

2. **MUST-FIX: Stage 2 bundles two mechanisms in two homes.** (a) is a change to `plugins/rails-flow/scripts/check_mcp_annotations.py` (comp:rails-flow, a gate with selftest and mutation guard). (b) is a "spec template" for the §4 proof, and the draft does not say where it ships: doctrine text in `mcp-server.md` (comp:rails-8, the verifier gate applies), or a rails-flow scaffold. **Disposition:** file them as separate children: 2a, the gate; 2b, the proof template, naming its home. That makes each closable by one PR and gives each the right `comp:*` label. The epic's own label `comp:rails-8` does not fit 2a.

3. **MUST-FIX: the #2034 boundary is stated ambiguously.** Stage 1 adds write-tool content to the SHIPPED `mcp-server.md`, and #2034 rules the shipped doctrine read-only for now. The draft's "Blocked by: … the #2034 out-of-scope statement" can be read as blocked by a text edit rather than by the ruling. **Disposition:** state it plainly: "Stage 1 and Stage 3 cannot start until the owner records a ruling on #2049 that supersedes #2034's read-only scope." Owner question 2 already asks this; tie the blocker to it. Nothing in the draft CONTRADICTS #2034 (no doctrine edit or code is proposed now; it is a plan), so it holds.

4. **MUST-FIX: Stage 2(b) is read-side work inside a write epic.** The §4 "no tool writes" proof is about READ-ONLY servers. It enforces a claim the shipped read-only doctrine already makes, so it is not blocked by #2034. The draft's "Not in this epic: read-side doctrine corrections (#2033, #2035)" conflicts with it. **Disposition:** move 2b to the read-side issues (or its own issue beside #2033/#2035) so it can proceed under #2034 now; keep the epic write-only. That also matches the title once "read AND" is dropped (point 9).

5. **SHOULD-FIX: update the two stale or drifted facts.** The downstream CLI is on its main branch now: drop the sentence saying it is not, which also lets the downstream evidence be re-read from that branch directly. Cite a spec example by name, not by line number. **Disposition:** edit both files.

6. **SHOULD-FIX: two statements are presented as fact but come from reading, not running.** (a) "It accepts a tool that says `read_only_hint: false`" (draft line 10). The research says "docstring read, behaviour not run"; label it the same way in the draft, or run the gate's `--selftest` / a one-tool fixture. (b) "the only downstream app that built the server (Retask)" is an unverified negative; say "the one downstream app we know of". **Disposition:** label both.

7. **SHOULD-FIX: one inference is unlabelled.** Draft point 18 says "Anthropic reports approval prompts are weak alone (93% approved…)". The source gives 93% approval and "approval fatigue"; "weak alone" is our reading. **Disposition:** quote the number and mark the conclusion [Inferred], as the research's §3 last bullet already does.

8. **NOTE: external quotes were not re-fetched by me.** The draft asks the reviewer to "re-read the load-bearing ones". I did not re-fetch the spec, MRTR, elicitation, authorization, OWASP or RFC pages, because no stage edits doctrine now and each stage that does is gated by `doctrine-verifier` per quote (point 1). **Disposition:** state in the epic that every external quote is re-verified at the child issue, not trusted from this research. No change is needed beyond that sentence.

9. **NOTE: the title promises more than the scope.** "agent-ready products, read AND write", yet read-side corrections are explicitly out. **Disposition:** retitle to "EPIC: MCP and CLI WRITE tools — staged plan (timing is the owner's)", once point 4 moves 2b out.

10. **NOTE: one open conflict is left for the right reason.** The `mcp` gem version/revision question (point 7 of the draft): our file names one release, the latest release is newer, and a downstream app locks a release that is not the one our file names; the changelog claims 2026-07-28 support from 1.1.0. **Disposition:** keep it listed as a blocker for Stage 1a's verifier work, as the draft does; no change.

11. **NOTE: the acceptance is sound.** `Refs`, never `Fixes`, to the epic until the last stage, with each child carrying its own guard, fragment and decision link. This matches CLAUDE.md's EPIC rule. **Disposition:** keep.

## Recommended child list after the fixes (each closable by one PR)
- 1a: verified quotes for the write checklist (verifier-gated; blocked by the #2049 ruling and the gem-version check)
- 1b: the write-tool decision checklist wording (maintainer decision; after 1a)
- 2a: `mcp-annotations` gate: `destructive_hint` and `idempotent_hint` required when `read_only_hint: false`; selftest plus a mutation guard (comp:rails-flow)
- (moved out) 2b: the §4 "no tool writes" row-count proof for read-only servers, beside #2033/#2035 (comp:rails-8; can proceed under #2034)
- 3: CLI write doctrine (blocked by #2036 Q1/Q2 and the #2049 ruling)
