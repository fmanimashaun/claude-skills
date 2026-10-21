# `/design-flow:audit` for the Rails UI adapter (`viewcomponent-erb`)

Read by `/design-flow:audit` after `ui_adapter.py` resolves this adapter.

## 1. The toolchain cross-check

The checklist below audits a *project's* UI. This one audits the **toolchain** — it catches
doctrine that references a runtime artefact `/design-flow:setup` never generates, which is
invisible to every other check and only surfaces as a `NoMethodError` at a user's first setup
run. It reads the shipped doctrine and generator, so it is meaningful from any clone:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ui/viewcomponent-erb/scripts/setup_doctrine_crosscheck.py"
```

Read the exit code, because two of them mean opposite things:

- **Exit 1 — a toolchain defect, not a project defect.** Doctrine reads config the generator
  never produces. Report it with `/rails-flow:report` (component `design-flow`) rather than
  patching locally.
- **Exit 2 — the check could not run** (an input missing, unreadable, or not valid UTF-8). That
  is *your clone*, not the toolchain: fix the input and re-run. Filing it as a doctrine defect
  sends a maintainer hunting something that does not exist.

Treating any non-zero exit as a defect to report conflates the two. Warnings flag config setup
generates that no doctrine reads: probably dead scaffolding, worth a look but not a blocker.

## 2. The source directories to scan

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/llm_tell_detector.py" app/views app/components
```

An inline disable in ERB is the same HTML comment the command shows (`<!-- design-flow-disable <rule>: reason -->`).

## 3. The default boot

No `app:` block in `qa/qa.config.yml`: infer the Rails default (`bin/dev`, port 3000, `/up`) and say so.

## 4. The variants scaffold to look for

`app/views/design_variants/`, `app/controllers/design_variants_controller.rb`, or a `design_variants` route still present. Verify with:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/ui/viewcomponent-erb/scripts/variant_conformance.py" --verify-discard .
```
