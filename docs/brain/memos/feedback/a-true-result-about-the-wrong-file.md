---
name: feedback-a-true-result-about-the-wrong-file
description: Four wrong claims in one session, each from measuring a neighbour of the thing — a shim instead of its config, a floor file instead of the pin that fixed it, a filtered slice instead of the output.
type: feedback
---

`grep -icE "playwright|e2e|browser" bin/ci` returned 0, so I told a peer — and wrote in a
filed issue — that `bin/ci` never runs `bin/e2e`. `bin/ci` is a four-line shim; the steps
are in `config/ci.rb`, and line 213 is `step "Tests: Browser regressions", "bin/e2e"`. My
own run had executed that step and failed it.

Four wrong claims in one session, all the same shape — **asserting about a thing after
looking at a neighbour of it**:

1. quoted a route-coverage floor of 198/227 carried from an earlier session; the file said
   125/228 and had been re-cut in `f92f8b6`, *the very pin commit* the prediction was about
2. put a peer's `bin/e2e` mechanism into an issue body without checking it applied to `bin/ci`
3. grepped the shim (above)
4. reported "8 RSpec failures and a Seeds failure" from three separate filtered greps; the
   run was **26 green, 5 red** — I never printed the stage list whole, one message after
   quoting a warning about exactly that
5. *(next day)* told a peer my PR was **not** in a collation branch, having run
   `compare/dev...branch | head -12`. It had **46 commits**; all three of mine were below the
   cut. The peer settled it with `merge-base --is-ancestor` — a question about membership,
   answered by a test for membership rather than by eyeballing a prefix of a list.

**Why:** a true result about the wrong file is worse than no result, because it arrives
wearing the authority of a measurement. "I checked" feels identical in all five cases.

**How to apply:** before quoting a measurement, name what it was taken *on* and confirm
that is the thing in question. A claim with no line number invites the wrong file — so cite
`config/ci.rb:213`, not "bin/ci runs e2e". For a belief carried across sessions, re-read the
file rather than the memory of it — and check whether the change it predicted has already
happened.

6. *(same day)* refuted a peer's "fixed in #554" by reading the PR's **title**, which named other
   work. Its branch carried two commits and the second was the fix. I published the refutation,
   and the original claim had been right. `gh pr view <n> --json headRefName` then
   `compare/dev...<branch>` is the predicate; the title is a label someone chose.

**A label is not the thing. Keep the predicate for each question:**

| question | NOT this | this |
|---|---|---|
| is this commit in that branch? | read `git log \| head -n` | `merge-base --is-ancestor`, or `select()` on the sha |
| what does this PR contain? | its title | `compare/<base>...<headRefName>` |
| what steps does this runner run? | grep the entry-point script | grep the config it loads |
| which arm of a multi-arm gate fired? | its stage name | the message it printed |
| did this run pass? | a filtered slice of the log | every stage line, with the total beside it |

**Truncation is the commonest form of it, and my first fix was too narrow.** I wrote this
memo scoped to CI stage lists ("print every stage") and the next day made the same error on a
commit list with `head -12`. The rule is not about stages: **any `head`/`tail`/`-n` between a
list and a conclusion invalidates the conclusion.** So —

- print the **total** alongside whatever you show (`total_commits`, `wc -l`, `| nl`) and say
  both numbers, so a truncation is visible instead of silent;
- better, **do not read a list to answer a set question at all.** "Is X in Y" is
  `merge-base --is-ancestor`, `grep -q`, a `select()` on the sha — a predicate, not a prefix;
- when reporting "the only X", open every candidate the search returned. Reporting one hit as
  "only" when grep returned three is the same error wearing a different hat — a peer had to
  open the third to confirm my conclusion survived.

Related: [[verified-narrow-asserted-wide]], [[a-lookup-whose-key-you-assumed]],
[[verify-counts-before-stating-them]], [[gate-the-commit-on-the-check]],
[[check-the-denominator-not-the-percentage]].

Related: [[verified-narrow-asserted-wide]], [[a-lookup-whose-key-you-assumed]],
[[verify-counts-before-stating-them]], [[gate-the-commit-on-the-check]].

_Provenance: [observed] — brought from a local Claude memory by `/rails-flow:brain-sync local`; body verbatim, a-true-result-about-the-wrong-file.md._
