# Security policy

This repository is a **Claude plugin marketplace**. What it ships is doctrine other people's agents
follow and scripts that run on other people's machines, so its security surface is not the usual
one for a documentation repo. This file says what that surface is, what is supported, and how to
tell us about a problem.

## Supported versions

| version | supported |
|---|---|
| the latest release on `main` | ✅ |
| anything older | ❌ — upgrade; releases are small and frequent |

`main` is the install surface: `/plugin marketplace add fmanimashaun/claude-skills` resolves there,
and every release is published from it by `.github/workflows/release.yml`. There are no maintained
branches behind it, so a fix ships as the next release rather than as a backport.

## Reporting a vulnerability

**Use GitHub's private vulnerability reporting** — the *Report a vulnerability* button under this
repository's [Security tab](https://github.com/fmanimashaun/claude-skills/security/advisories/new).
It opens a private advisory only the maintainers can read.

Please do **not** open a public issue for anything exploitable. Ordinary bugs in doctrine or
tooling are public issues and always welcome; this policy is for the cases where the report itself
is the exploit.

What helps most, in the order we will ask for it:

1. Which file, and which released version you found it in.
2. What an attacker controls — the input, the branch, the repository, the environment variable.
3. What they get — code execution on a maintainer's machine, a write to `main`, a published
   release, content in a downstream project's source tree.
4. A reproduction, even a partial one.

**What to expect.** An acknowledgement within three working days, an assessment with a fix or a
rejection within fourteen, and credit in the release notes unless you ask otherwise. This is a
small project maintained by one person; those are intentions, not an SLA.

## What is in scope

- **`scripts/**` and `plugins/*/scripts/**`** — they run on a maintainer's machine, and several run
  from CI with repository permissions. A path traversal, a shell injection, or an unsafe
  deserialisation here is the highest-value finding in this repo.
- **`.github/workflows/**` and `plugins/*/hooks/**`** — `release.yml` publishes, and the hooks run
  automatically inside a user's Claude Code session. A workflow that trusts an untrusted input, or
  a hook that executes attacker-controlled content, is in scope.
- **Shipped skill content (`skills/**`, `plugins/**/*.md`)** where it instructs an agent to run
  something dangerous — for example a snippet a reader is told to paste that would exfiltrate a
  credential or silence a verification. Doctrine is executable by a model, which is what makes this
  a security surface and not just an editorial one.
- **`dist/*.skill`** — the packaged bundles uploaded to claude.ai.

## What is not in scope

- **Findings that require a maintainer to already be compromised.** If the premise is "an attacker
  with write access to `main`", that is the premise, not the vulnerability.
- **The licensed design corpora** (`design-corpora/`, a gitignored nested clone). They are not
  ours, not shipped, and not part of any release.
- **Third-party plugins or marketplaces** installed alongside this one. Report those to their
  owners.
- **A gate that fails to catch something.** A check with a hole is a bug, and a public issue is the
  right place for it — unless the hole is itself exploitable, in which case use the private report.

## What we do not do

- We never ask for a credential, a token, or a session cookie in a report, and we will never send
  you a link asking you to sign in to receive a bounty. There is no bounty programme.
- We do not run a disclosure embargo longer than the fix needs. Once a release carries the fix, the
  advisory is published.
