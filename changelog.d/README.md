# changelog.d: one file per change

A PR does **not** edit `CHANGELOG.md`. It adds `changelog.d/<issue>-<slug>.md`, and the arm folds it into the component's `### Unreleased`.
Two PRs open at once can then never conflict on the CHANGELOG (79% of merges into `dev` on 2026-10-09 and 10 touched it, #1825).

```
section: rails-flow
- **The headline — `path/it/changed`** (#1234). The body, as it would read in CHANGELOG.md.
  A continuation line is indented two spaces.
```

- `section:` is a prefix of the `## ` heading (`rails-flow`, `qa-flow`, `Repository hygiene`). Where two headings share it, write more of it.
- One file is ONE bullet for ONE component. A change in two components is two files (`1234-rails-flow.md`, `1234-qa-flow.md`).
- The bullet names a path it changed, in backticks, that exists and belongs to that component, and cites its issue as `(#1234)`; the file name starts with the same number.
- Check yours: `python3 scripts/changelog_fragments.py --check`. The arm runs `--fold`; after the arm, a late fragment is folded with `--fold --into vX.Y.Z`.
- A promotion carries no fragment: `extract_release_notes.py --promotion` refuses one that is still a file.
