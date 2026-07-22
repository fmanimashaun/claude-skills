# qa-flow

Part of the claude-skills marketplace. Install:
```
/plugin marketplace add fmanimashaun/claude-skills
/plugin install qa-flow@claude-skills
```

See the repo root README.md and CHANGELOG.md for full documentation.

## Platform note

This plugin's hooks are **bash + python3** scripts. On Windows, run Claude Code inside
**WSL or Git Bash** with `python3` available, or the hooks (including the blocking
release gate) can't execute. macOS/Linux need no action. The release-gate and other
guards fail safe if their interpreter is missing, but a missing interpreter means the
gate does not run — so ensure the toolchain is present where enforcement matters.
