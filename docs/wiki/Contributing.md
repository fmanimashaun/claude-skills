# Contributing

## Reporting a bug from the field

```bash
/rails-flow:report
```

Run it from the project where the problem happened. It files a structured, version-pinned,
deduplicated issue on this repo — carrying the versions, installed paths and evidence a maintainer
would otherwise have to ask for. Every issue in the tracker arrived this way, and it is the fastest
route to a fix.

**Include what you actually observed.** The best reports here have been the ones with a computed
style, an exit code, or a copied error — those get fixed the same day. An issue body is treated as a
**hypothesis, not a specification**: every externally verifiable claim in it is checked before
anything is implemented, and reports have been wrong in both directions — asserting a rule that does
not exist, and omitting one that does.

## The git flow, if you are sending a change

- Branch off `dev`, PR into `dev`, with `Refs #n` — **never** a closing keyword
- No version bumps on `dev`: a version number is a claim about what someone can install
- A release is a separate, deliberate `dev → main` promotion carrying every `Closes #n`

## Before you open the PR

```bash
python3 scripts/maintainer_doctor.py --gates-only
```

Read the output as **three verdicts**, not two — plus an informational `note` that is not a verdict:
`ok` is verified, `FAIL` blocks, and **`skip` means the check did not run** — it is not a pass.

Two rules that catch most of what review would otherwise miss:

- **A gate that cannot fail is worse than no gate.** If you add a check, add the mutation that
  proves it can fail, and confirm the *named fixture* catches it. A crash is not a verdict.
- **Measure before you assert.** Re-run the query at the moment you quote the number, and bound it —
  `gh issue list` silently defaults to 30, so an unbounded call reports one page as the total.
