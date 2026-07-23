---
description: Publish this project's brain status to a shared cross-project brain repo, and consume sibling projects' status — so agentic flows in separate repos coordinate WITHOUT cloning each other. Uses gh (single-file reads/writes), git as source of truth.
argument-hint: "publish | pull | status   [optional shared-repo slug on first setup]"
---

# /rails-flow:brain-sync — $ARGUMENTS

A cross-project **shared brain repo** lets two (or more) agentic flows, each in its own repo,
see what the others are doing without cloning each other's code. Git is the bus: deterministic,
versioned, provenance via commit history — the same markdown-in-git brain, federated. This
command **publishes** this project's status to the hub and **pulls** siblings' status via `gh`
(single-file reads — no full clone of anyone's project repo).

## Config — `docs/brain/FEDERATION.md`

Read this file for the hub coordinates. If it's absent and the user wants federation, create it
(and offer to bootstrap the hub repo, see below):

```
shared_brain: <org>/brain        # the hub repo (small; holds only brain docs)
namespace:    <this-project>     # this project's folder under the hub's projects/
watch:        [sibling-a, sibling-b]   # sibling namespaces to consume (empty = all under projects/)
```

## Hub repo layout (the shared brain)

```
<org>/brain
  projects/
    <this-project>/STATUS.md      # each project publishes its own STATUS (+ a short digest)
    <sibling>/STATUS.md
  CONTRACTS.md                    # cross-project interfaces/contracts both sides depend on
  EVENTS.md                       # append-only, dated cross-repo event log (who shipped/changed what)
  MEMORY.md                       # shared index of cross-project decisions/lessons
```

Only brain markdown lives here — never code. A project writes **only its own** `projects/<self>/`
namespace and the shared append logs; it reads the others.

## `$ARGUMENTS` = **publish**

Push this project's current state to the hub (no clone of the hub needed — use the Contents API):

1. Build the digest from local `docs/brain/`: current `STATUS.md`, plus a 5–10 line summary
   (phase, last shipped, next, blockers, any **CONTRACT-relevant** change other projects depend on).
2. GET the existing file sha, then PUT (create-or-update) into the hub:
   ```bash
   repo="<org>/brain"; ns="<namespace>"
   sha=$(gh api "repos/$repo/contents/projects/$ns/STATUS.md" --jq .sha 2>/dev/null || true)
   gh api --method PUT "repos/$repo/contents/projects/$ns/STATUS.md" \
     -f message="brain-sync: $ns status $(git rev-parse --short HEAD)" \
     -f content="$(base64 -w0 docs/brain/STATUS.md)" ${sha:+-f sha="$sha"}
   ```
3. Append one dated line to the hub's `EVENTS.md` (GET+decode+append+PUT, same pattern):
   `<date> · <namespace> · <what changed that a sibling should know>`. Tag it `[observed]`/`[decided]`.
4. If a change alters a shared interface, update `CONTRACTS.md` too — and say so in the event line.

If the hub repo doesn't exist yet, offer to bootstrap it: `gh repo create <org>/brain --private`,
seed `projects/<namespace>/STATUS.md`, `CONTRACTS.md`, `EVENTS.md`, `MEMORY.md`, and a README
explaining the layout. Never push code there.

## `$ARGUMENTS` = **pull** (or **status**)

Read siblings **without cloning their project repos** — single-file fetches from the hub:

```bash
repo="<org>/brain"
for ns in $(gh api "repos/$repo/contents/projects" --jq '.[].name'); do
  [ "$ns" = "<namespace>" ] && continue     # skip self
  gh api "repos/$repo/contents/projects/$ns/STATUS.md" --jq .content | base64 -d
done
gh api "repos/$repo/contents/CONTRACTS.md" --jq .content | base64 -d
gh api "repos/$repo/contents/EVENTS.md"    --jq .content | base64 -d | tail -20
```

Summarize for the user: where each sibling is, any new EVENTS since last pull, and — most
important — anything in a sibling's status or `CONTRACTS.md` that **affects this project**
(a contract they changed, a dependency they shipped/broke). Flag those as action items; if one
implies a local decision, offer to record it with `/rails-flow:brain`.

## The store is git — no external synthesis layer

The `<org>/brain` hub repo is the **single source of truth** for cross-project state. Keep the
discipline the brain is built on: *plain text in git is the store* — versioned, provenance via
commit history, deterministic reads, diffable. Don't route the shared brain through an external
embeddings/RAG service; if a human wants a natural-language summary across projects, read the hub
files directly (they're small) rather than standing up a separate synthesis layer that drifts
from git and loses the audit trail.
