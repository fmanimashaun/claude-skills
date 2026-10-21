# pipeline

Part of the claude-skills marketplace. Install:
```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install pipeline@claude-skills
```

See the repo root README.md and CHANGELOG.md for full documentation.

## Commands

One line each, from the command's own description; the command file is the authority.

- `/pipeline:ack` — Dismiss the post-merge QA-verify nudge marker (.git/pipeline-pending) without another merge or a manual rm.
- `/pipeline:board` — Measure the repository and write the status board, .claude/state/board.json and a static drawing-sheet page, board.html. Read-only; a source that cannot be read shows as unknown.
- `/pipeline:deploy-cloud` — One-command autonomous cloud deploy — the project's stack declares its deploy target and agent; this command gates, bounds and reports the run.
- `/pipeline:install-hooks` — Install the local git hooks: the `pre-push` / `pre-commit` guards (protected branches are only fast-forwarded; staged content is checked) and the lifecycle nudges that spend no tokens.
- `/pipeline:pipeline` — Drive the software lifecycle — detect the current stage and run the next flow (build → verify → certify → release), honoring every gate.
- `/pipeline:release` — Build the release artifact — a versioned Docker image pushed to ghcr.io, pull-and-run verified locally; Kamal deploy when cloud config is present.
- `/pipeline:setup-cloud` — Prepare cloud deployment — generate the .kamal/deploy.env.example briefing-sheet template (every value the deploy agent needs, annotated by destination) and README setup docs.
- `/pipeline:setup-pipeline` — Scaffold pipeline.yml and the local git-hook nudges; verify the Docker/Kamal release prerequisites.
- `/pipeline:status` — Report where the repo sits in the lifecycle and the exact next command.

## Platform note

This plugin's hooks are **bash** scripts, and the two advisory ones (the SessionStart nudge and the Stop board refresh) also use **python3**. On Windows, run Claude Code inside
**WSL or Git Bash**. macOS/Linux need no action.

Without `python3`, those two advisories skip and say nothing. The git guards that `/pipeline:install-hooks` installs (`pre-push`, `pre-commit`) need only bash and git, and fail closed. The blocking
release gate is **qa-flow's**, not this plugin's: its platform note is in the qa-flow README.

**The Python floor is 3.9**, the `python3` stock macOS ships: every script this plugin ships parses there, and a change that needs newer syntax is refused before it ships.
