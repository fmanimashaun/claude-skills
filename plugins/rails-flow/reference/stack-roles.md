# Stack roles: which agent does the work

The flows (`/feature`, `/fix`, `/review`, `/issues`, `/handoff`, `/pr-comments`) never name a stack's agent. They name a **role**, and the project's stack plugin says which agent plays it. A Rails project's developer writes Rails; a Next.js project's developer must not be handed to the Rails one, so there is no default and no fallback.

## Resolve the roles once per run

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/detect_stack.py" --descriptor
```

It prints the merged descriptor of every stack the project matches, as JSON. The roles are under `descriptor.agents`, each a `<plugin>:<agent>` name to delegate to:

| role | does | delegate when |
|---|---|---|
| `developer` | implements the change | any non-trivial code change, once a plan exists |
| `migrations` | writes and reviews schema changes | the change touches the database schema |
| `test_runner` | runs the suite and classifies failures | every verification step (the full suite, 0 failures) |
| `reviewer` | reviews the diff against the stack's practice | the review gate (`VERDICT: CLEAN`) |
| `security` | audits endpoints, auth and user data | the change touches those |
| `design_auditor` | audits views against the design system | views or UI components changed |

`descriptor.tests.command` (with `descriptor.runner_prefix` before it, when present) is how the stack runs its suite, and `descriptor.tests.glob` is where its specs live.

## When the stack gives no answer: stop or ask, never Rails

| what `--descriptor` says | what the flow does |
|---|---|
| exit 0 and the role is in `descriptor.agents` | delegate to that agent |
| exit 0 but `descriptor.agents` is missing, or lacks the role (for example a project that matches only an add-on stack such as Supabase, or a stack whose plugin ships no agents yet) | **STOP and ask the user** which agent to use, saying which role is missing and which stacks were detected. Do not pick an agent by name, and do not use a Rails agent. |
| exit 1 (no stack detected) | say so, run only the stack-neutral steps, and **ask** before any step that needs a role |
| exit 2 (a manifest problem, or two stack plugins declaring the same key, as in a Rails API with a Next.js frontend) | **STOP** and show the `problems` it printed; ask the user which stack this change belongs to |

A role a stack does not fill is an answer, not a gap to patch: the flow says the step cannot run for this stack and asks.
