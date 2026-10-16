# Verdicts for #2045 (rails-8 observability.md: Postgres index health and bloat), 2026-10-16

Split from #2037 (audit `2026-10-14-observability-postgres-2037.md`). There are two kinds of evidence:
- one `doctrine-verifier` run against the **PostgreSQL 16** docs;
- runs on a throwaway **`postgres:16` (16.15)** container, each against a planted case. Their raw output is in `raw/2026-10-16-postgres-index-bloat-2045-runs.md`.

M = https://www.postgresql.org/docs/16/monitoring-stats.html

| id | claim | verdict | authority | what the doctrine does |
|---|---|---|---|---|
| 1 | `last_idx_scan` exists; it is new in 16 | CONFIRMED | M; 0 hits on the docs/15 page | tagged "new in 16" |
| 2 | counters reset on an unclean shutdown (immediate stop, crash, base backup, PITR) | CONFIRMED and MEASURED: `idx_scan` went 1 → 0 after `pg_ctl stop -m immediate` | M §28.2 (docs' own wording used); run3 | stated |
| 3 | "check `stats_reset` first" (the issue's wording) | **REFUTED by measurement**: `pg_stat_database.stats_reset` stayed null across the crash reset; the tables and indexes views have no reset column (verifier) | run3; M | the window is `greatest(stats_reset, pg_postmaster_start_time())` |
| 4 | an invalid index is ignored for queries but still costs on update; recover by dropping and running `CREATE INDEX CONCURRENTLY` again, or `REINDEX INDEX CONCURRENTLY` | CONFIRMED | https://www.postgresql.org/docs/16/sql-createindex.html; https://www.postgresql.org/docs/16/catalog-pg-index.html | stated, quoted |
| 5 | `n_live_tup`, `n_dead_tup`, `last_vacuum` and `last_autovacuum` exist; the counts are estimates | CONFIRMED | M | stated as estimates |
| 6 | `pgstattuple` full-scans; `pgstattuple_approx` skips all-visible pages; its dead count is exact | CONFIRMED and MEASURED: 100% of pages scanned without a VACUUM, 58.1% after one; dead count 2000 = 2000 | https://www.postgresql.org/docs/16/pgstattuple.html; run1, run2 | stated, with the VACUUM caveat |
| 7 | `pgstatindex` (B-tree) | CONFIRMED | same page | not used (no measured need) |
| 8 | `pg_stat_scan_tables` can be granted alone | CONFIRMED and MEASURED: a role with only that grant ran `pgstattuple_approx` and was refused `SELECT` on the rows; a `pg_read_all_stats` role was refused the function | https://www.postgresql.org/docs/16/predefined-roles.html; run2 | the design row below |
| Q | the five catalog queries (window, unused, invalid, duplicate, unindexed FK) | MEASURED: the doctrine's block, extracted verbatim, returns exactly the planted case per query on a fresh container | run4 | shipped as written |
| D | the role choice (#2037 finding 2) | **DESIGN, ours**: a separate on-demand bloat role granted `pg_stat_scan_tables` only, never `pg_monitor`; the always-on reader stays `pg_read_all_stats` | decision recorded on #2045 | stated as "our design (#2045)" |
