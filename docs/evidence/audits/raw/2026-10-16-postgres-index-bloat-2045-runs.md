# #2045 measured runs on postgres:16 (16.15), 2026-10-16

Scenario: `setup.sql` below. Runs: queries (run1), roles and visibility map (run2), immediate-stop reset (run3), the doctrine block verbatim on a fresh container (run4).

## setup.sql

```text
-- #2045 scenario on postgres:16: one of each condition the queries must find.
\set ON_ERROR_STOP 0
CREATE EXTENSION IF NOT EXISTS pgstattuple;
CREATE TABLE authors (id bigserial PRIMARY KEY, name text);
CREATE TABLE posts (id bigserial PRIMARY KEY, author_id bigint REFERENCES authors(id), title text, body text);
ALTER TABLE posts SET (autovacuum_enabled = false);           -- keep the dead tuples for the bloat screen
INSERT INTO authors (name) SELECT 'a' || g FROM generate_series(1, 1000) g;
INSERT INTO posts (author_id, title, body)
  SELECT 1 + g % 1000, 't' || (g % 5000), 'b' || (g % 50000) FROM generate_series(1, 100000) g;
CREATE INDEX posts_title_a ON posts (title);                   -- duplicate pair
CREATE INDEX posts_title_b ON posts (title);
CREATE UNIQUE INDEX CONCURRENTLY posts_body_uniq ON posts (body);  -- fails (duplicates): leaves an INVALID index
-- posts.author_id: foreign key with no index
SELECT * FROM posts WHERE id = 5;                              -- one primary-key scan
DELETE FROM posts WHERE id % 10 < 4;                           -- 40% dead
ANALYZE authors;
SELECT pg_stat_force_next_flush();
```

## queries.sql

```text
-- #2045 queries, as they would be documented. Run against postgres:16.
\pset footer off
\echo '== Q0 window: when were this database''s statistics last reset?'
SELECT stats_reset FROM pg_stat_database WHERE datname = current_database();

\echo '== Q1 unused indexes (never scanned since the reset; not unique, not backing a constraint)'
SELECT s.relname AS table, s.indexrelname AS index, s.idx_scan, s.last_idx_scan,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS size
FROM pg_stat_user_indexes s
JOIN pg_index i USING (indexrelid)
WHERE s.idx_scan = 0 AND NOT i.indisunique
  AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = s.indexrelid)
ORDER BY pg_relation_size(s.indexrelid) DESC;

\echo '== Q2 invalid indexes (a failed CREATE INDEX CONCURRENTLY): drop or REINDEX'
SELECT indexrelid::regclass AS index, indrelid::regclass AS table
FROM pg_index WHERE NOT indisvalid;

\echo '== Q3 duplicate indexes (same table, columns, opclasses, collations, expression and predicate)'
SELECT indrelid::regclass AS table, array_agg(indexrelid::regclass ORDER BY indexrelid) AS indexes
FROM pg_index
GROUP BY indrelid, indkey::text, indclass::text, indcollation::text,
         coalesce(pg_get_expr(indexprs, indrelid), ''), coalesce(pg_get_expr(indpred, indrelid), '')
HAVING count(*) > 1;

\echo '== Q4 foreign keys with no index leading on their columns'
SELECT c.conrelid::regclass AS table, c.conname AS foreign_key,
       array_agg(a.attname ORDER BY a.attnum) AS columns
FROM pg_constraint c
JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY (c.conkey)
WHERE c.contype = 'f'
  AND NOT EXISTS (
    SELECT 1 FROM pg_index i
    WHERE i.indrelid = c.conrelid
      AND (string_to_array(i.indkey::text, ' ')::int2[])[1:cardinality(c.conkey)] @> c.conkey
      AND (string_to_array(i.indkey::text, ' ')::int2[])[1:cardinality(c.conkey)] <@ c.conkey)
GROUP BY c.conrelid, c.conname;

\echo '== Q5 bloat screen (cheap: the statistics views, no table read)'
SELECT relname AS table, n_live_tup, n_dead_tup,
       round(n_dead_tup::numeric / nullif(n_live_tup + n_dead_tup, 0), 2) AS dead_fraction,
       last_vacuum, last_autovacuum
FROM pg_stat_user_tables ORDER BY n_dead_tup DESC;

\echo '== Q6 measure one flagged table: approx (visibility map) vs exact (full scan)'
SELECT 'approx' AS how, approx_tuple_count AS live, dead_tuple_count AS dead,
       round(dead_tuple_percent::numeric, 1) AS dead_pct, scanned_percent
FROM pgstattuple_approx('posts')
UNION ALL
SELECT 'exact', tuple_count, dead_tuple_count, round(dead_tuple_percent::numeric, 1), 100
FROM pgstattuple('posts');
```

## roles.sql

```text
-- #2045: what a pg_read_all_stats reader and a pg_stat_scan_tables role can each do on postgres:16.
\set ON_ERROR_STOP 0
\pset footer off
CREATE ROLE stats_reader LOGIN;  GRANT pg_read_all_stats TO stats_reader;
CREATE ROLE bloat_check LOGIN;   GRANT pg_stat_scan_tables TO bloat_check;
GRANT USAGE ON SCHEMA public TO stats_reader, bloat_check;
\echo '== reader: the screen (Q5) works'
SET ROLE stats_reader;
SELECT relname, n_dead_tup FROM pg_stat_user_tables WHERE relname = 'posts';
\echo '== reader: pgstattuple_approx is refused'
SELECT dead_tuple_count FROM pgstattuple_approx('posts');
RESET ROLE;
\echo '== bloat_check (pg_stat_scan_tables only, no SELECT on posts): pgstattuple_approx works'
SET ROLE bloat_check;
SELECT dead_tuple_count FROM pgstattuple_approx('posts');
\echo '== bloat_check: but cannot read the table rows'
SELECT count(*) FROM posts;
RESET ROLE;
\echo '== approx after VACUUM: a table vacuumed once, then 1% deleted'
CREATE TABLE vm_demo AS SELECT g AS id, repeat('x', 100) AS pad FROM generate_series(1, 200000) g;
VACUUM vm_demo;
DELETE FROM vm_demo WHERE id % 100 = 0;
SELECT 'approx' AS how, dead_tuple_count AS dead, round(scanned_percent::numeric, 1) AS scanned_pct FROM pgstattuple_approx('vm_demo')
UNION ALL SELECT 'exact', dead_tuple_count, 100 FROM pgstattuple('vm_demo');
```

## run1.txt

```text
== Q0 window: when were this database's statistics last reset?
 stats_reset 
-------------
 

== Q1 unused indexes (never scanned since the reset; not unique, not backing a constraint)
 table |     index     | idx_scan | last_idx_scan |  size  
-------+---------------+----------+---------------+--------
 posts | posts_title_a |        0 |               | 776 kB
 posts | posts_title_b |        0 |               | 776 kB

== Q2 invalid indexes (a failed CREATE INDEX CONCURRENTLY): drop or REINDEX
      index      | table 
-----------------+-------
 posts_body_uniq | posts

== Q3 duplicate indexes (same table, columns, opclasses, collations, expression and predicate)
 table |            indexes            
-------+-------------------------------
 posts | {posts_title_a,posts_title_b}

== Q4 foreign keys with no index leading on their columns
 table |     foreign_key      |   columns   
-------+----------------------+-------------
 posts | posts_author_id_fkey | {author_id}

== Q5 bloat screen (cheap: the statistics views, no table read)
  table  | n_live_tup | n_dead_tup | dead_fraction | last_vacuum | last_autovacuum 
---------+------------+------------+---------------+-------------+-----------------
 posts   |      60000 |      40000 |          0.40 |             | 
 authors |       1000 |          0 |          0.00 |             | 

== Q6 measure one flagged table: approx (visibility map) vs exact (full scan)
  how   | live  | dead  | dead_pct | scanned_percent 
--------+-------+-------+----------+-----------------
 approx | 60000 | 40000 |     34.9 |             100
 exact  | 60000 | 40000 |     34.9 |             100

```

## run2.txt

```text
== reader: the screen (Q5) works
 relname | n_dead_tup 
---------+------------
 posts   |      40000

== reader: pgstattuple_approx is refused
ERROR:  permission denied for function pgstattuple_approx
== bloat_check (pg_stat_scan_tables only, no SELECT on posts): pgstattuple_approx works
 dead_tuple_count 
------------------
            40000

== bloat_check: but cannot read the table rows
ERROR:  permission denied for table posts
== approx after VACUUM: a table vacuumed once, then 1% deleted
  how   | dead | scanned_pct 
--------+------+-------------
 approx | 2000 |        58.1
 exact  | 2000 |         100

```

## run3.txt

```text
== before
 indexrelname | idx_scan | has_last 
--------------+----------+----------
 posts_pkey   |        1 | t
(1 row)

== after immediate stop + restart
 indexrelname | idx_scan | has_last 
--------------+----------+----------
 posts_pkey   |        0 | f
(1 row)

stats_reset: null
2026-10-16 16:15:47.931 UTC [29] LOG:  database system was not properly shut down; automatic recovery in progress
postmaster_start: 2026-10-16 16:15:47.857712+00|window_start: 2026-10-16 16:15:47.857712+00
```

## doc-block.sql

```text
-- window start (see above)
SELECT coalesce(greatest(stats_reset, pg_postmaster_start_time()), pg_postmaster_start_time())
FROM pg_stat_database WHERE datname = current_database();
-- unused since then: skip unique indexes and any index backing a constraint
SELECT s.relname, s.indexrelname, s.idx_scan, s.last_idx_scan, pg_relation_size(s.indexrelid)
FROM pg_stat_user_indexes s JOIN pg_index i USING (indexrelid)
WHERE s.idx_scan = 0 AND NOT i.indisunique
  AND NOT EXISTS (SELECT 1 FROM pg_constraint c WHERE c.conindid = s.indexrelid)
ORDER BY pg_relation_size(s.indexrelid) DESC;
-- invalid: a failed CREATE INDEX CONCURRENTLY
SELECT indexrelid::regclass, indrelid::regclass FROM pg_index WHERE NOT indisvalid;
-- duplicates: same columns, opclasses, collations, expression and predicate
SELECT indrelid::regclass, array_agg(indexrelid::regclass)
FROM pg_index
GROUP BY indrelid, indkey::text, indclass::text, indcollation::text,
         coalesce(pg_get_expr(indexprs, indrelid), ''), coalesce(pg_get_expr(indpred, indrelid), '')
HAVING count(*) > 1;
-- foreign keys with no index leading on their columns
SELECT c.conrelid::regclass, c.conname FROM pg_constraint c
WHERE c.contype = 'f' AND NOT EXISTS (
  SELECT 1 FROM pg_index i WHERE i.indrelid = c.conrelid
    AND (string_to_array(i.indkey::text, ' ')::int2[])[1:cardinality(c.conkey)] @> c.conkey
    AND (string_to_array(i.indkey::text, ' ')::int2[])[1:cardinality(c.conkey)] <@ c.conkey);

```

## run4-docblock.txt

```text
           coalesce            
-------------------------------
 2026-10-16 16:17:10.815579+00
(1 row)

 relname | indexrelname  | idx_scan | last_idx_scan | pg_relation_size 
---------+---------------+----------+---------------+------------------
 posts   | posts_title_a |        0 |               |           794624
 posts   | posts_title_b |        0 |               |           794624
(2 rows)

   indexrelid    | indrelid 
-----------------+----------
 posts_body_uniq | posts
(1 row)

 indrelid |           array_agg           
----------+-------------------------------
 posts    | {posts_title_a,posts_title_b}
(1 row)

 conrelid |       conname        
----------+----------------------
 posts    | posts_author_id_fkey
(1 row)

```
