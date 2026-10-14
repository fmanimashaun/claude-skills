# doctrine-verifier verdicts for #2037 (rails-8 observability.md, Postgres production signals), 2026-10-14

One read-only `doctrine-verifier` run against the **PostgreSQL 16** docs (the repo baseline; `/docs/current` resolves to 18
and was not used). Sibling of `2026-10-11-observability-otel-1694.md`, which verified the existing pg_stat_statements bullets.
Items 7-8 of the issue (index health, bloat) were split to #2045: they need a recorded run on a real database. Edits in
`skills/rails-8/references/observability.md` follow CONFIRMED rows only. PSS = https://www.postgresql.org/docs/16/pgstatstatements.html

| id | claim | verdict | authority (PG16) | what the doctrine does |
|---|---|---|---|---|
| 1a | queryid depends on OIDs; unstable across drop/recreate, major versions, logical replicas | CONFIRMED with corrections: the doc's example is a *table*; physical replicas "can be expected to have identical queryid values" | PSS | stated as "an object (for example a table)", logical replicas only |
| 1b | stored text is the first query's | CONFIRMED | PSS | stated |
| 1c | no percentiles, only min/max/mean/stddev | CONFIRMED | PSS (column list) | stated |
| 1d | `dealloc` counts evictions past `pg_stat_statements.max` | CONFIRMED | PSS | stated |
| 1e | window via `stats_since`/`minmax_stats_since` | **PG17+ only, out of scope**; PG16 window is `pg_stat_statements_info.stats_reset` (CONFIRMED) | PSS; https://www.postgresql.org/docs/17/release-17.html | `stats_reset` for 16, the two columns named as arriving in 17 |
| 1f | `showtext := false` skips reading texts | CONFIRMED | PSS | stated |
| 1g | other users' text/queryid need `pg_read_all_stats`; reset is superuser by default | CONFIRMED | PSS | stated |
| 2 | `track_planning`, `track_io_timing` default off, cost overhead | CONFIRMED | PSS; https://www.postgresql.org/docs/16/runtime-config-statistics.html | stated |
| 3a-d | auto_explain inert until `log_min_duration`; `log_analyze` "extremely negative impact"; `sample_rate` 1; `log_timing`; `log_parameter_max_length` -1 logs in full (exists on 16); preload libraries | CONFIRMED | https://www.postgresql.org/docs/16/auto-explain.html | stated; 0 recommended for the parameter length (design) |
| 4 | `log_min_duration_sample`, `log_statement_sample_rate`, `log_lock_waits`, `log_temp_files` exist with defaults -1 / 1 / off / -1 | CONFIRMED | https://www.postgresql.org/docs/16/runtime-config-logging.html | stated |
| 5a | `pg_monitor` includes `pg_stat_scan_tables`, which "may take ACCESS SHARE locks on tables, potentially for a long time" | CONFIRMED | https://www.postgresql.org/docs/16/predefined-roles.html | stated |
| 5b | timeouts per role; `statement_timeout` (and `lock_timeout`) in postgresql.conf "not recommended" | CONFIRMED | https://www.postgresql.org/docs/16/sql-alterrole.html; https://www.postgresql.org/docs/16/runtime-config-client.html | stated |
| 6 | standby stats are per node; WAL replay does not increment `n_tup_*`; autovacuum inactive in recovery; conflicts cancel queries | CONFIRMED | https://www.postgresql.org/docs/16/hot-standby.html | stated |
| 8x | `pgstattuple` EXECUTE is `pg_stat_scan_tables` by default | CONFIRMED | https://www.postgresql.org/docs/16/pgstattuple.html | one clause in 5: a `pg_read_all_stats` reader cannot measure bloat; the role choice is #2045's |
