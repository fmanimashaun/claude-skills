---
description: Measure the repository and write the status board, .claude/state/board.json and a static drawing-sheet page, board.html. Read-only; a source that cannot be read shows as unknown. `publish` (coordinator only, on request) re-publishes the page to one artifact.
---

# /pipeline:board

Write the status board for this repository: the record `.claude/state/board.json` and one self-contained
page, `.claude/state/board.html`. Every figure is measured when the command runs (`gh`, `git`, `ps`).
Nothing is remembered, and nothing is written to the repository's git history.

## Do

1. Run `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/status_board.py" collect` from the repository root.
   Add `--audience coordinator` when you coordinate several sessions: the page then also counts questions
   that stayed drafted too long, which the owner never sees.
2. Read the one line it prints: where the page is, and how many panels it measured.
3. Name each panel that shows `unknown`, with its `reason` from `.claude/state/board.json`. **Never call an
   unknown panel empty or zero.** Unknown means the source could not be read, and the fix is the reason.
4. If the command prints `Add .claude/state/ to .gitignore.`, add that line.
5. Tell the user to open `.claude/state/board.html` in a browser. It makes no network request.

## Publish the live page (coordinator only, on request or at a checkpoint)

`/pipeline:board publish` re-publishes `.claude/state/board.html` to ONE claude.ai artifact, so the owner keeps a single link.
There is one renderer: the published page is the same static page, with no new capability and nothing a viewer can write.

**When.** Only when the user asks for `/pipeline:board publish`, or at a small number of checkpoints: after a merge, and at a
promotion. **Never per event, never on a timer, never from a hook.** The owner complained on 2026-10-03 that board republishes
kept opening browser windows; a hook only ever refreshes the local files (`board-refresh.sh`).

**Who.** Only the coordinator, the session named in `coordinator` of `.claude/state/board.json`. A session that is not the
coordinator does not publish: `collect` prints the line "The live board is at <url>." when one is recorded, and that is all it does.

**Steps, for the coordinator.**
1. Run `collect --audience coordinator`, then read `live.url` in `.claude/state/board.json`.
2. Call the Artifact tool with `file_path` set to `.claude/state/board.html`. When `live.url` is set, pass it as `url`, so the
   same page is updated. Otherwise this is the first publish: pass `icon: "dashboard"` and `title: "Status board"`.
3. After a FIRST publish, record the address once with the coordination script of `rails-flow`, the one you already use for `claim`
   and `assign`: `python3 <rails-flow>/hooks/scripts/lib/coordination.py board-url --session-id <your session id> --url <the artifact URL>`. Only a `https://claude.ai/artifact/<id>` or
   `https://claude.ai/code/artifact/<id>` link is accepted. A restarted or successor coordinator then updates the same page.
4. Say the link once. Do not open it again.

## What the panels are

A Needs you (questions that reached the owner) · B Release lines · C Open pull requests · D Sessions ·
E Limits · F Today. The title block names the coordinator when several sessions run.

## Configure (optional): `.claude/board.config.json`

`full_run_workflow` (the workflow file whose dispatched run counts as the full run; without it every run
reads `unknown`), `integration_branch` (the branch a finished worktree's head must reach; without it: `dev` when
`origin/dev` exists, else the remote's default branch, else `main`), `review_pattern` (a regex that replaces the
built-in verdict reader: group 1 the commit, group 2 CLEAN or BLOCKED), `release_lines` (`[{name, exclude_labels, next}]`: the open issues
without those labels block that line), `stale_minutes`, `zombie_warn`, `worktree_warn`, `notes` (one
sentence under a panel: `prs`, `sessions`, `asks`, `lines`, `limits`, `today`). The collector flags a note
that breaks the text rules in `board.json` under `ste_warnings`. It never rewrites it.

## The Stop hook (optional, opt-in)

When `.claude/board.config.json` or an earlier `.claude/state/board.json` exists, `hooks/scripts/board-refresh.sh` runs the
collector at every Stop, no more often than every 2 minutes (`BOARD_HOOK_FRESH_MIN`) and for at most 8 seconds
(`BOARD_HOOK_BUDGET`). It prints nothing and never fails a stop. A project without either file gets nothing from it.

## How a review verdict is read

A comment is a verdict when its first line says `review` or `re-check` and holds `CLEAN` or `BLOCKED` in
capitals. The last such word on that line is the verdict. The commit is the first hex word after `at`, `of`,
`head` or `commit`. The last verdict comment decides. A verdict without a commit reads `unknown`. A verdict
worded only in prose ("one blocker remains") is not read; the board then shows the review before it as stale.
`status_board_verdicts.json` pins this against the first lines of 57 real verdicts and 10 near-misses.

## Rules

- **Do not edit `board.json` or `board.html` by hand.** Run the command again.
- **This command reads the coordination record and never writes it.** Only the coordinator writes
  `coordination.json`, through `coordination.py` in `rails-flow`.
- Exit 0: the files were written (some panels may be `unknown`). Exit 2: not inside a git repository.
  Exit 3: the files could not be written.
- This is the first of three parts of the board. A hook refresh, the session check-in and the live
  artifact come later; until then, run this command when you want a fresh board.
