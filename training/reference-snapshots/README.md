# SQL Training Library

An offline collection of official documentation, practical examples, datasets,
and course notes for learning portable SQL and major SQL dialects.

## Start here

1. Begin with `SQL-101/README.md` for relational and SQL fundamentals.
2. Work through `sql-ultimate-course/` for guided lessons, scripts, datasets,
   and projects. Its examples primarily target Microsoft SQL Server.
3. Use `postgresql-docs/doc/src/sgml/tutorial.sgml` for PostgreSQL's official
   tutorial, then consult the rest of the PostgreSQL manual source as needed.
4. Use `mariadb-docs/server/mariadb-quickstart-guides/` for MariaDB/MySQL-style
   SQL, and `duckdb-docs/docs/current/sql/` for analytical SQL.
5. Apply the material with examples under `sql-server-samples/samples/`.

See `CATALOG.md` for exact sources, revisions, scope, and navigation links.

## Important dialect note

Core concepts such as `SELECT`, joins, grouping, constraints, and transactions
transfer well between systems. T-SQL, PostgreSQL, MariaDB, and DuckDB also have
different functions, data types, procedural languages, and administrative
commands. Check the relevant official reference before using an example in a
different database.
