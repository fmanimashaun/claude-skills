# skill-maintainer

Part of the claude-skills marketplace. Install:
```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install skill-maintainer@claude-skills
```

The maintenance side of the loop: downstream projects installing these skills and
plugins report issues as they hit them, and this flow turns that stream into
source-verified fixes and shipped releases.

## Commands

- `/skill-maintainer:setup-intake` — scaffold GitHub issue templates + a label
  taxonomy so reports arrive triage-ready (idempotent, marker-guarded).
- `/skill-maintainer:triage [issue | label]` — classify open issues by component ×
  type × priority, label them, dedupe, and post a prioritized work queue.
- `/skill-maintainer:work [issue]` — take one issue through the full loop: confirm →
  verify against source-of-truth → fix → PR (`Closes #n`) → version bump + CHANGELOG →
  release. Strictly one issue at a time.
- `/skill-maintainer:audit [component]` — proactive (not issue-driven) review of a
  skill or plugin against source-of-truth and open issues; logs gaps as issues.

## The non-negotiable gate

Skill content is doctrine other people's agents follow. **No skill claim is edited
until the `doctrine-verifier` agent confirms it against an authoritative source**
(official docs for the version in scope, the repo's `docs/audits/` protocol). "It
sounds right" is never sufficient — verification precedes edits, always.

## Platform note

This plugin's hooks are **bash + python3** scripts and it drives the **`gh`** CLI. On
Windows, run Claude Code inside **WSL or Git Bash** with `python3` and `gh` available,
or the SessionStart status hook simply no-ops (it is non-blocking and fails open). The
work loop needs `gh` authenticated (`gh auth status`) to read issues and open PRs.
