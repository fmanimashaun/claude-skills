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
- `/pipeline:deploy-cloud` — One-command autonomous cloud deploy — read the prepared .kamal/deploy.env briefing sheet, route every value to its Rails-native home, wire Kamal, and deploy with self-verification.
- `/pipeline:install-hooks` — Install local git-hook nudges that detect lifecycle transitions without spending tokens.
- `/pipeline:pipeline` — Drive the software lifecycle — detect the current stage and run the next flow (build → verify → certify → release), honoring every gate.
- `/pipeline:release` — Build the release artifact — a versioned Docker image pushed to ghcr.io, pull-and-run verified locally; Kamal deploy when cloud config is present.
- `/pipeline:setup-cloud` — Prepare cloud deployment — generate the .kamal/deploy.env.example briefing-sheet template (every value the deploy agent needs, annotated by destination) and README setup docs.
- `/pipeline:setup-pipeline` — Scaffold pipeline.yml and the local git-hook nudges; verify the Docker/Kamal release prerequisites.
- `/pipeline:status` — Report where the repo sits in the lifecycle and the exact next command.

## Platform note

This plugin's hooks are **bash + python3** scripts. On Windows, run Claude Code inside
**WSL or Git Bash** with `python3` available, or the hooks (including the blocking
release gate) can't execute. macOS/Linux need no action. The release-gate and other
guards fail safe if their interpreter is missing, but a missing interpreter means the
gate does not run — so ensure the toolchain is present where enforcement matters.
