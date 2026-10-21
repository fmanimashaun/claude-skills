---
description: Audit a running app's screens against the interface architecture framework (shell, navigation, state contract, cross-cutting contracts). Every finding cites its rule and authority; ranked; improvements proposed as a mock-up first.
argument-hint: "<app url> [routes or screens to audit; default: the app's own navigation]"
---

# /design-flow:interface-audit — $ARGUMENTS

Audit the screens of the running app at the first argument. Delegate to the **interface-auditor**
agent, which measures with a browser and lets scripts decide.

| | `/design-flow:audit` | `/design-flow:critique` | this |
|---|---|---|---|
| reads | source files | source and rendered look | **rendered pages** |
| asks | does it conform to the tokens and primitives? | is it considered? | **does it meet the architecture's rules?** |
| authority | gate | lens, advisory | **each finding names its rule and whether it is a standard or a house rule** |

## Preconditions

1. **The `design-system` skill is readable**, in particular `references/architecture.md`. It ships
   in `rails-stack`; no `plugin.json` can declare that, so check. If you cannot read it, name what is
   missing (`/plugin install rails-stack@claude-skills`) and stop.
2. **The app is running and reachable**, and a browser tool is available. If either is missing, say
   which and stop: an audit from memory of the source is `/design-flow:audit`.
3. **Where the evidence goes:** `docs/evidence/design/<date>-interface-audit/` in the project.

## Steps

1. Hand the **interface-auditor** the app URL and the screens. It collects one snapshot per screen,
   runs `interface_audit.py`, merges any qa-flow judge output it finds, validates with
   `audit_findings.py check`, and writes `report.md` with `audit_findings.py report`.
2. Read the report back to the user: the ranked findings, **each with its authority line**, then the
   **Not audited** list. Do not soften a house rule into advice and do not harden one into a
   standard; the authority line is computed.
3. For the top findings, show the **proposed mock-up** change. Offer to draft it; do not build it.
   A change a user can see waits for an approved mock-up (`/rails-flow` mock-up gate).

## Exit

The command reports; it does not block. A script gate is what blocks: run the findings through
`audit_findings.py check` and treat exit 1 as "the audit is malformed", not "the app is bad".
