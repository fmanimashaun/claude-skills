section: qa-flow
- **`plugins/qa-flow/scripts/mockup_records.py` reads the task-list `Statuses:` line** (#2327). A byte-identical copy of rails-flow's reader, updated with it (the `vendored-copy-drift` lint holds the pair); qa-flow itself reads no new behaviour from the key.
