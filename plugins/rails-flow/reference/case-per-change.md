# A case for every change (#1858)

The owner's rule (#1853), in their words: "every fix or gap or bug must have a case to test it and help to prevent regression", and "u can't build something without a way to
test it in qa, there must be a test case for it to prove it worked as intended, if not, we are fooling ourself". It is unconditional: no feature, fix, gap or bug closes without a
manual catalogue case that proves its intent.

## What a project does

- **A case in the same PR.** `/rails-flow:feature` and `/rails-flow:fix` add or update the case in `qa/test-cases.csv` (the catalogue `/qa-flow:cases` keeps) for the behaviour they
  change, and put the issue in the case's `Source` column: `defect:#12` or `#12`.
- **For a fix, gap or bug, a spec that FAILS without the fix.** Run it on the pre-fix tree (red) and with the fix (green), and say so under a `## Red/green proof` heading in the PR body.
- **The PR template asks for both.** The claims guard (`guard-claims.sh`) already requires every section of the project's own `.github/pull_request_template.md`, so adding the
  sections below to the template is what makes the guard enforce them; the hook itself is unchanged.

```markdown
## Test case

The case id(s) in `qa/test-cases.csv` that prove this change (each names the issue in its Source). Not a fix, feature, gap or bug? Say N/A and why.

## Red/green proof

red: the spec that fails without the change, and how you ran it on the pre-fix tree.
green: the same spec passing with the change.
```

## The check

`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/check_case_in_diff.py" --base origin/dev --closes-from-body body.md --kind fix --body-file body.md`

It reads the diff `BASE...HEAD` (refs only; fsmonitor and external diff off) and requires, for EVERY issue the PR closes, a catalogue row that the diff adds or changes naming that
issue in `Source`; for `--kind fix` also an added, copied, modified or renamed spec or test SOURCE file (a path in a `spec/`, `test/`, `tests/` or `e2e/` directory or named `_spec`, `.spec.`,
`.test.` or `_test`, with a source extension: a note or fixture there is not one; a deleted spec does not count) and, with `--body-file`, the `Red/green` section. Rows are compared as whole CSV records
between the catalogue at BASE and at HEAD: a row that already existed and is untouched does not count (the case is for THIS change), a moved row is not a change, and a cosmetic edit to a row that
already names the issue does count, so a reviewer reads the case. A catalogue renamed or deleted by a change that closes an issue is a finding, and one named with `--catalogue` that exists nowhere is exit 2. Exit 1 findings; 2 could not check (the gate runner grades 2 ERROR); 3 only when the project has no catalogue.

It checks that the case and the spec are IN THE DIFF. It cannot run the spec against the pre-fix tree, so the red/green section is a statement the reviewer checks, and the flow
command is what actually runs it.
