# #2107: three INCONCLUSIVE Postgres sentences, measured on postgres:18 (18.6), 2026-10-16

The #2057 verifier pass (PR #2106) left these unchanged and uncited. Each was measured on a throwaway `postgres:18` container started with `-c shared_preload_libraries=pg_stat_statements`, and quoted from the PostgreSQL 18 docs. The verdicts with quotes are also on https://github.com/fmanimashaun/claude-skills/issues/2107#issuecomment-6221311131

| id | sentence | verdict | 18 docs | measured | edit |
|---|---|---|---|---|---|
| A | `observability.md`: the extension "is created per database" | CONFIRMED | pgstatstatements.html: "not available globally but can be enabled for a specific database with CREATE EXTENSION"; sql-createextension.html: "loads a new extension into the current database" | the view is absent in a second database until `CREATE EXTENSION` runs there | quoted and the measurement stated |
| B | `observability.md`: a `pg_read_all_stats` reader "can still read `n_dead_tup`" | TRUE BUT MISLEADING | monitoring-stats.html scopes `pg_read_all_stats` to session information | a role with no grants reads `n_dead_tup` (300) and is refused `SELECT` on the table | reworded: no grant is needed |
| C | `models.md`: a generic plan can differ from the custom plans on skewed data | CONFIRMED | sql-prepare.html: a custom plan uses "the parameter values given in that call"; "in some situations a custom plan will be much more efficient" | common value: custom Seq Scan, generic Index Scan; the generic plan was not slower here (37.9 against 58.2 ms), so no cost is claimed | quoted and the measurement stated |

## Script

```sql
-- #2107 measurements on postgres:18. Run as the superuser in database "postgres".
\set ON_ERROR_STOP 0
\pset footer off
\echo '== A: pg_stat_statements is created per database'
CREATE DATABASE other;
CREATE EXTENSION pg_stat_statements;
SELECT 'postgres db: view rows readable' AS where_, count(*) >= 0 AS ok FROM pg_stat_statements;
\c other
\echo '-- in database "other", before CREATE EXTENSION there:'
SELECT count(*) FROM pg_stat_statements;
SELECT count(*) AS extension_rows_here FROM pg_extension WHERE extname = 'pg_stat_statements';
CREATE EXTENSION pg_stat_statements;
\echo '-- ...after CREATE EXTENSION in "other":'
SELECT count(*) >= 0 AS ok FROM pg_stat_statements;
\c postgres

\echo '== B: who can read n_dead_tup'
CREATE TABLE t_b (id int);
INSERT INTO t_b SELECT generate_series(1, 1000);
DELETE FROM t_b WHERE id <= 300;
SELECT pg_stat_force_next_flush();
CREATE ROLE stats_reader LOGIN; GRANT pg_read_all_stats TO stats_reader;
CREATE ROLE nobody LOGIN;
SET ROLE stats_reader;
SELECT 'stats_reader' AS role, relname, n_dead_tup FROM pg_stat_user_tables WHERE relname = 't_b';
RESET ROLE;
SET ROLE nobody;
SELECT 'nobody (no grants)' AS role, relname, n_dead_tup FROM pg_stat_user_tables WHERE relname = 't_b';
SELECT 'nobody: can it read the rows?' AS q; SELECT count(*) FROM t_b;
RESET ROLE;

\echo '== C: generic vs custom plan on skewed data'
CREATE TABLE t_c (id bigserial PRIMARY KEY, status text);
INSERT INTO t_c (status) SELECT CASE WHEN g % 10000 = 0 THEN 'rare' ELSE 'common' END FROM generate_series(1, 500000) g;
CREATE INDEX ON t_c (status);
ANALYZE t_c;
\echo '-- custom plan for the rare value (a literal):'
EXPLAIN (COSTS OFF) SELECT * FROM t_c WHERE status = 'rare';
\echo '-- custom plan for the common value:'
EXPLAIN (COSTS OFF) SELECT * FROM t_c WHERE status = 'common';
\echo '-- EXPLAIN (GENERIC_PLAN) with a placeholder:'
EXPLAIN (GENERIC_PLAN, COSTS OFF) SELECT * FROM t_c WHERE status = $1;
\echo '-- a prepared statement forced to its generic plan, executed with the rare value:'
PREPARE q(text) AS SELECT * FROM t_c WHERE status = $1;
SET plan_cache_mode = force_generic_plan;
EXPLAIN (COSTS OFF) EXECUTE q('rare');
SET plan_cache_mode = force_custom_plan;
EXPLAIN (COSTS OFF) EXECUTE q('rare');
\echo '-- GENERIC_PLAN with ANALYZE is refused:'
EXPLAIN (GENERIC_PLAN, ANALYZE) SELECT * FROM t_c WHERE status = $1;
```

## Output

```text
== A: pg_stat_statements is created per database
             where_              | ok 
---------------------------------+----
 postgres db: view rows readable | t

You are now connected to database "other" as user "postgres".
-- in database "other", before CREATE EXTENSION there:
ERROR:  relation "pg_stat_statements" does not exist
LINE 1: SELECT count(*) FROM pg_stat_statements;
                             ^
 extension_rows_here 
---------------------
                   0

-- ...after CREATE EXTENSION in "other":
 ok 
----
 t

You are now connected to database "postgres" as user "postgres".
== B: who can read n_dead_tup
 pg_stat_force_next_flush 
--------------------------
 

     role     | relname | n_dead_tup 
--------------+---------+------------
 stats_reader | t_b     |        300

        role        | relname | n_dead_tup 
--------------------+---------+------------
 nobody (no grants) | t_b     |        300

               q               
-------------------------------
 nobody: can it read the rows?

== C: generic vs custom plan on skewed data
ERROR:  permission denied for table t_b
-- custom plan for the rare value (a literal):
               QUERY PLAN               
----------------------------------------
 Index Scan using t_c_status_idx on t_c
   Index Cond: (status = 'rare'::text)

-- custom plan for the common value:
             QUERY PLAN              
-------------------------------------
 Seq Scan on t_c
   Filter: (status = 'common'::text)

-- EXPLAIN (GENERIC_PLAN) with a placeholder:
               QUERY PLAN               
----------------------------------------
 Index Scan using t_c_status_idx on t_c
   Index Cond: (status = $1)

-- a prepared statement forced to its generic plan, executed with the rare value:
               QUERY PLAN               
----------------------------------------
 Index Scan using t_c_status_idx on t_c
   Index Cond: (status = $1)

               QUERY PLAN               
----------------------------------------
 Index Scan using t_c_status_idx on t_c
   Index Cond: (status = 'rare'::text)

-- GENERIC_PLAN with ANALYZE is refused:
ERROR:  EXPLAIN options ANALYZE and GENERIC_PLAN cannot be used together
== C (cont.): the same prepared statement, executed with the COMMON value
-- custom plan, common value:
             QUERY PLAN              
-------------------------------------
 Seq Scan on t_c
   Filter: (status = 'common'::text)

-- generic plan, common value:
               QUERY PLAN               
----------------------------------------
 Index Scan using t_c_status_idx on t_c
   Index Cond: (status = $1)

-- and its actual cost difference (custom vs generic, common value):
                   QUERY PLAN                    
-------------------------------------------------
 Seq Scan on t_c (actual rows=499950.00 loops=1)
   Filter: (status = 'common'::text)
   Rows Removed by Filter: 50
   Buffers: shared hit=2703
 Planning Time: 0.034 ms
 Execution Time: 58.222 ms

                               QUERY PLAN                               
------------------------------------------------------------------------
 Index Scan using t_c_status_idx on t_c (actual rows=499950.00 loops=1)
   Index Cond: (status = $1)
   Index Searches: 1
   Buffers: shared hit=2703 read=423
 Planning Time: 0.011 ms
 Execution Time: 37.887 ms

```
