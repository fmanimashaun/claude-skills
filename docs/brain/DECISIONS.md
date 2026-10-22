# DECISIONS (ADR-lite)

## D-001 — Relocate, never summarise (2026-09-03) `[decided]`
**Choice:** when `CLAUDE.md` passes its ceiling, pure-history paragraphs move **verbatim** to a history
file with one pointer per section; nothing is paraphrased. **Alternatives:** summarise in place;
delete old incidents. **Rationale:** the maintainer — "blind summarising context is dangerous, it can
impact quality"; a ceiling on what *loads at session start*, not on what exists. **Enforced by:**
`plugins/rails-flow/scripts/claude_md_structure.py` (`assert_lossless`), lint `claude-md-growth`.
Refs #870, #875. **Reversal condition:** a measured case where the pointer hop costs more context
than the relocated paragraph saved.

## D-002 — `brain-sync local --propose` never writes the repo (2026-09-03) `[decided]`
**Choice:** the outbound direction renders memo files and writes nothing; `/rails-flow:brain` writes
after a human picks. **Alternatives:** auto-write memos; a hook that writes on SessionStart.
**Rationale:** the repo is reviewed truth, a local memory may be personal. **Enforced by:** the
`propose writes nothing` fixture and its mutation (`plugins/rails-flow/scripts/mutations/brain_local_sync.py`; moved from `scripts/mutations/` by #1109). Refs #877.
**Reversal condition:** a team that wants unreviewed memos and says so in a DECISIONS entry of its own.

## D-003 — A pointer memory carries the memo's own description (2026-09-03) `[decided]`
**Choice:** the local pointer's `description` is the brain memo's line verbatim, not a fixed sentence.
**Rationale:** that line is what auto-memory recall matches on; a fixed sentence would recall nothing.
**Enforced by:** fixture "the pointer carries the memo's own description verbatim" + mutation. Refs #877.
**Reversal condition:** the harness stops matching recall on `description`.

## D-004 — REVERSED 2026-09-03 by D-005: the history file moved to `docs/brain/history/maintainer-history.md` `[decided]`
**Choice:** this repo's relocated incident narrative lives at `docs/brain/history/maintainer-history.md`, while the
shipped tool's default for projects is `docs/brain/claude-md-history.md`. **Rationale:** the file
predates the brain here and 17 `doctrine_map` anchors and lint pointers name it; moving it buys
nothing a reader can measure. **Reversal condition:** a second history file appears, or a tool needs
one location for both.

## D-005 — The maintainer repo follows the shipped docs/ layout, with one declared directory (2026-09-03) `[decided]`
**Choice:** `docs/` here is laid out by `docs_layout.py` like every project's: `doctrine/` (declared in the map — the
maintainer's authored rules), `architecture/` (generated: `doctrine-map.html`; `inventory.html` until D-006), `evidence/`
(`coverage.html`, `audits/`), `brain/history/` (the relocated CLAUDE.md narrative), `wiki/` (generated). Root-file
homes are the map's `## Root files` table, which the tool reads. **Alternatives:** leave the maintainer repo as the
exception; invent a maintainer-only layout. **Rationale:** the tool's first real run on Retask-platform matched the
hand review; a repo that ships a layout and does not keep it is the claims-vs-enforcement class. Refs #886.
**Reversal condition:** a generated page that cannot live under `architecture/` or `evidence/` without a script losing
its drift gate.

## D-006 — One generated reference surface: the inventory page folds into the wiki (2026-09-03) `[decided]`
**Choice:** `docs/architecture/inventory.html`, its generator `build_inventory.py`, its selftest and its two gates are
retired; the data layer lives in `scripts/inventory_data.py` (readers imported, never re-parsed; verifications kept,
one `inventory data selftest` gate) and renders as `docs/wiki/Agents-And-Gates.md` under the wiki's existing drift
gate. `coverage.html` stays: the only browsable view of the design-system matrix. **Alternatives:** keep both and
cross-link. **Rationale:** two generated views over one input set, each with its own generator, drift gate and
selftest, is the shape this repo argues against everywhere else (`duplicated-release-extractor`); the filter chips
are the one loss. Refs #892. **Reversal condition:** a reader who needs the cross-kind filter and cannot get it from
a wiki search.

## D-007 — The on-demand Postgres bloat check runs under its own role granted only `pg_stat_scan_tables`, never `pg_monitor` (2026-10-16) `[decided]`
**Choice:** the rails-8 doctrine (`observability.md`) gives bloat measurement a separate login role granted `pg_stat_scan_tables` and nothing else, used on demand for one flagged table at a time. The always-on monitoring role stays `pg_read_all_stats` and runs only the cheap screen (`n_dead_tup` against `n_live_tup`, plus the vacuum timestamps). **Recommended:** by the author (dd / claude-skills-2c), as a design decision on #2045 ([comment](https://github.com/fmanimashaun/claude-skills/issues/2045#issuecomment-6219826365)). **Decided by:** owner ruling, 2026-10-16: "i agree to all ur recommendations" ([comment](https://github.com/fmanimashaun/claude-skills/issues/2045#issuecomment-6226277396)). **Alternatives:** the screen alone, with no measurement (rejected: the screen's counts are documented estimates, so they cannot size a repack); granting `pg_monitor` (rejected: it includes `pg_stat_scan_tables`). **Rationale:** on PostgreSQL 16 and 18 only `pg_stat_scan_tables` may execute `pgstattuple*` by default, and its functions "may take ACCESS SHARE locks on tables, potentially for a long time". Keeping that grant off anything that polls on a schedule means no timer holds those locks. Measured on `postgres:16` (16.15) and 18.6: the `pg_read_all_stats` role was refused `pgstattuple_approx`, while the separate role ran it and was refused `SELECT` on the table's rows. **Enforced by:** nothing can check it; it is an `advice` row in `scripts/doctrine_map.py`. Refs #2045, #2096; evidence in `docs/evidence/audits/2026-10-16-observability-postgres-index-bloat-2045.md`. **Reversal condition:** a PostgreSQL release that changes the default grant on `pgstattuple*`, or a measured case where the separate role is not enough.

## D-008 — MCP write tools are in scope for the shipped doctrine, but only as a five-decision checklist, not rules (2026-10-17) `[decided]`
**Choice:** `plugins/rails-stack/skills/rails-8/references/mcp-server.md` gains a "Before you add a write tool" section. It opens with "If you cannot answer these, do not ship a write tool" and asks five decisions each project records in its own CLAUDE.md:
- who may write;
- how a change is confirmed;
- what stops a retried call writing twice;
- how the audit tells agent writes from human ones;
- how a wrong write is undone.

Where the MCP spec gives a mechanism, the item cites it (`doctrine-verifier` CONFIRMED against revision 2026-07-28, #2051); where the spec defines none, the item is labelled our design.

**Recommended:** by dd / claude-skills-2c, as option 2 of 3 ([recommendation](https://github.com/fmanimashaun/claude-skills/issues/2056#issuecomment-6226373082)). **Decided by:** owner ruling, 2026-10-17 ([comment](https://github.com/fmanimashaun/claude-skills/issues/2056#issuecomment-6226384151)). This supersedes the read-only scope ruled on #2034.

**Alternatives:**
- stay read-only (rejected: projects add write tools anyway, with no guidance);
- write rules (rejected: there is no official server-side write protocol, and no app has run one, so every rule would be our invention presented as doctrine).

**Rationale:** the research (#2050) found that the spec puts "a human in the loop" on the *client*. It defines no server-side confirmation, no idempotency key on `tools/call`, no agent-versus-human audit marker and no undo pattern (NOT FOUND, searched, #2051). A checklist makes each project decide without us claiming answers the sources do not give. Its first line guards against reading it as permission.

**Enforced by:** nothing can check a project's answers; it is an `advice` row in `scripts/doctrine_map.py`. Refs #2056, #2050, #2051, #2052, PR #2113.

**Reversal condition:** an MCP spec revision that defines a server-side write protocol, or a downstream app that has run write tools and shows the checklist missed a decision.

## D-009 — Release authority: the coordinator merges `dev` and `main` and releases images; the owner's approval is needed only to deploy Retask to production, which the coordinator then runs (2026-10-17) `[decided]`
**Choice:** once everything is green, the coordinating session merges into `dev` and `main` (claude-skills and Retask), cuts releases and publishes images without asking. The one step that needs the owner is deploying Retask to production: the owner gives the go-ahead, and the coordinator runs the deploy.

**Recommended:** by the coordinator (claude-skills-e3, now -70), as part of the work it reported to the owner. **Decided by:** owner, 2026-10-17, in three messages given to the coordinator directly, not on GitHub:
- "u can merge to main once all is green, u don't need me for that";
- "u only need my approval to deploy retask to production";
- "approval means, i give you the go ahead to deploy and you do it, every other thing or flow can be done by you as per you recommendation and work including releasing images".

**Alternatives:** the previous split, recorded in the coordinator's handoff (`COORDINATOR-HANDOFF.md`, "Owner keeps: Retask release/tag, deploy, production... claude-skills promotions are mine"). This decision supersedes it.

**Rationale:** the owner's words above. A merge or release that every gate has passed needs no human. A production deploy is the outward-facing, hard-to-reverse step, so it keeps one approval.

**Enforced by:** practice, and the global CLAUDE.md rule that coordinator assignments carry the owner's authority while production access stays the owner's to approve. Refs: none on GitHub.

**Reversal condition:** the owner says so, or a release or merge goes wrong in a way a human gate would have caught.

## D-010 — The two unredacted research files stay local and untracked; the repository keeps the redacted copies (2026-10-17) `[decided]`
**Choice:** PR #2063 moved the agent-surface research into `docs/evidence/audits/`. In the public copy, the write-side report's close reading of Retask's private implementation (file paths and line numbers, check order, rate limits and a size cap, revocation, audit columns, token storage) is condensed to conclusions the public issues already state. The two unredacted originals stay in a local, untracked log and in Retask's own private repository.

**Recommended:** by the #2063 author, as "the one judgement call: the repository is public, Retask is private" ([PR body](https://github.com/fmanimashaun/claude-skills/pull/2063)). The coordinator then recommended to the owner that the two files stay local and untracked. **Decided by:** owner ruling, 2026-10-17, "i agree to all ur recommendations" (given to the coordinator directly, not on GitHub), which included that recommendation.

**Alternatives:** commit the originals verbatim. The PR named this as a one-line reversal, but it would publish a private app's security design.

**Rationale:** claude-skills is public and Retask is private, and the request was to move the files, not to publish Retask's security details. #2063 measured that the public copy contains none of them: a scan for rate-limit figures, the size cap, controller and policy names, audit column names, token-storage modes and `file:line` pointers found no matches.

**Enforced by:** nothing; the files are simply not tracked. Refs #2063, #2061.

**Reversal condition:** the owner asks for the verbatim text in the public repository.

## D-011 — When a session has no `CLAUDE_SESSION_PROJECT_TOP`, the selftest runner supplies it; the git shim's fixture exemption is not widened (2026-10-17) `[decided]`
**Choice:** `check_toolchain_selftests.py` (`selftest_env()`) sets `CLAUDE_SESSION_PROJECT_TOP` to the git toplevel of its working directory when the variable is unset or empty. It never overrides a value the caller set, and outside a repository it sets nothing. `plugins/rails-flow/git-shim/git` is unchanged.

**Recommended:** by the PR #2112 author, with the shim left alone. **Decided by:** the author's design; it was reviewed CLEAN by claude-skills-3c, who checked that it cannot widen the shim's exemption ([review](https://github.com/fmanimashaun/claude-skills/pull/2112#issuecomment-6226642485)), and merged into `dev` 2026-10-16 23:36 UTC by the coordinator under delegation.

**Alternatives:** widen the shim's exemption so that it works without the variable (rejected). The variable is how the shim refuses to treat the session's own project as a fixture. Unset, it fails closed by design. Loosening it would weaken a guarantee to fix a caller.

**Rationale (measured 2026-10-17, #2111):**
- With the variable unset, `project_gates.py` reported `toolchain-selftests` ERR on Retask: 4 findings, all a refused `git add -A`. That blocked every Retask `gh pr ready`.
- With the fix there were 0 findings, across 52 selftests.
- The runner works inside the project, so naming the project is what the variable is for.

**Enforced by:** `check_toolchain_selftests.py --selftest` (16 assertions) and mutation guard `check_toolchain_selftests` (9 mutations, caught on macOS and Linux). Refs #2111, #2112.

**Reversal condition:** the SessionStart hook exports the variable in every session, so the runner's fallback is never used. Other selftests that Retask's `bin/ci` runs outside `project_gates` share the exposure; that is noted on #2112 and is a separate issue.

## D-012 — Every claim or rule is enforced by a check; an unenforced one is not kept as doctrine (2026-10-21) `[decided]`
**Choice:** a rule or claim the repo states must be backed by a check that can fail. Where no check exists yet, the entry says so.
**Decided by:** owner ruling, 2026-10-21, verbatim: "everything must be enforced, a claim or rule not enforced is useless" ([#2225](https://github.com/fmanimashaun/claude-skills/issues/2225)).
**Alternatives:** none recorded in the ruling.
**Rationale:** the owner's words above.
**Enforced by:** not yet enforced, tracked in #2225 (open). This memo is itself prose, not a check.
**Reversal condition:** the owner withdraws the rule.

## D-013 — The full sweep runs on GitHub, because the repository is public; a local proof is for private repositories only (2026-10-21) `[decided]`
**Choice:** `.github/workflows/release.yml` runs the full gate sweep (including `mutation coverage`) on GitHub for a push to `main`. A local `maintainer_doctor.py --gates-only --require-slow --record-proof` is optional and meant for private repositories; it posts a `full-sweep` status that `release.yml` reuses for an identical tree.
**Decided by:** owner rule, 2026-10-21, verbatim: "public repo, so the full sweep runs on GitHub (release.yml); a local proof is for private repos only" ([PR #2234](https://github.com/fmanimashaun/claude-skills/pull/2234), merged 2026-10-21 19:51 UTC).
**Alternatives:** a local proof of 1 to 2 hours before every promotion (rejected for this repository by the ruling).
**Rationale:** the owner's words above; the repository is public, so GitHub runs the sweep at no cost.
**Enforced by:** the full sweep on GitHub is enforced by `release.yml` (the `proof` and `gates` jobs). Not yet enforced: refusing a local proof on this public repository. Nothing checks it, and no issue tracks that gap.
**Reversal condition:** the repository goes private, or GitHub stops running the sweep for free.

## D-014 — Design is neutral: rails-stack does not own design, and a UI change starts as a mock-up in the app's own shell (2026-10-21) `[decided]`
**Choice:** design belongs to the design flow, not to the Rails stack. Every UI change starts as a mock-up in the app's own shell; a new project first mocks its core shell and foundation screens.
**Decided by:** owner ruling, 2026-10-21, verbatim: "design is neutral and rails-stack does not own design; UI starts as a mock-up in the app's own shell" ([#2211](https://github.com/fmanimashaun/claude-skills/issues/2211), closed; [#2280](https://github.com/fmanimashaun/claude-skills/issues/2280)).
**Alternatives:** keep the design-system skill in rails-stack (the state until #2280 lands).
**Rationale:** the owner's words above.
**Enforced by:** not yet enforced, tracked in #2280 (the design-system move from rails-stack to design-flow, open). No gate for the mock-up-first rule was found: `grep -rln -i "mock-up\|mockup" plugins/design-flow/scripts` matches only `audit_findings.py` and `detect_stack.py`.
**Reversal condition:** the owner moves design back into rails-stack.

## D-015 — External catalogues are inspiration only; we build from our own design system (2026-10-21) `[decided]`
**Choice:** external UI catalogues (Shadcn Space and others) inform ideas. Their code is never pasted or installed; components are built from our own design system.
**Decided by:** owner ruling, 2026-10-21, verbatim: "external catalogues (Shadcn Space and others) are inspiration only; build from our own design system".
**Alternatives:** none recorded in the ruling.
**Rationale:** the owner's words above.
**Enforced by:** nothing. Not yet enforced, and no open or closed issue tracks it (`gh issue list --state all --limit 30 --search "Shadcn catalogue in:title,body"` finds only #1069, which is a component-gap issue).
**Reversal condition:** the owner names a catalogue as a permitted source.

## D-016 — Flows run unattended: a shipped step acts instead of printing guidance; a human is needed only for credentials, permission prompts and product calls (2026-10-21) `[decided]`
**Choice:** a step a flow ships installs and configures what it can. It prints guidance only where a human must act: credentials, a permission prompt, or a product decision.
**Decided by:** owner ruling, 2026-10-21, verbatim: "flows run unattended: a shipped step acts (installs, configures) rather than printing guidance; a human is needed only for credentials, permission prompts and product calls" ([#2288](https://github.com/fmanimashaun/claude-skills/issues/2288)).
**Alternatives:** none recorded in the ruling.
**Rationale:** the owner's words above.
**Enforced by:** not yet enforced, tracked in #2288 (toolchain-check installs and logs in autonomously, open).
**Reversal condition:** the owner withdraws the rule.

## D-017 — Vendor plugins (Vercel, Supabase) own their doctrine; we detect and hand off, and carry no copy (2026-10-21) `[decided]`
**Choice:** the Vercel and Supabase plugins own their own commands and doctrine. Our shipped docs detect the stack and hand off to the vendor plugin; they never carry a copy of a vendor CLI step.
**Decided by:** owner ruling, 2026-10-21, verbatim: "vendor plugins (vercel, supabase) own their doctrine; we detect and hand off" ([#2168](https://github.com/fmanimashaun/claude-skills/issues/2168) / [PR #2291](https://github.com/fmanimashaun/claude-skills/pull/2291), open; [#2289](https://github.com/fmanimashaun/claude-skills/issues/2289) / [PR #2290](https://github.com/fmanimashaun/claude-skills/pull/2290), merged).
**Alternatives:** none recorded in the ruling.
**Rationale:** the owner's words above. The vendor plugins are the authority on their own CLIs; a copy in our docs would go stale.
**Enforced by:** `scripts/check_vendor_handoff.py` (from #2290, merged) refuses a shipped `.md` line that tells the reader to run a vendor CLI step. It is wired into `scripts/maintainer_doctor.py`. The detect-and-hand-off part (#2168, PR #2291) is not yet merged.
**Reversal condition:** a vendor plugin is withdrawn, or the owner moves a vendor's doctrine back into our docs.

## D-018 — A worktree teardown leaves no file or folder behind, deletes the merged branch, and the temp dir is monitored and cleared (2026-10-22) `[decided]`
**Choice:** a teardown removes every file and folder the session created, deletes the branch once it is merged, and the temp directory is monitored and cleared.
**Decided by:** owner ruling, 2026-10-22, verbatim: "a teardown leaves no file or folder behind, deletes the merged branch, and the temp dir is monitored and cleared" ([#2296](https://github.com/fmanimashaun/claude-skills/issues/2296)).
**Alternatives:** none recorded in the ruling.
**Rationale:** the owner's words above. #2296 records the defect: teardown leaves files and folders behind.
**Enforced by:** not yet enforced, tracked in #2296 (open).
**Reversal condition:** the owner withdraws the rule.
