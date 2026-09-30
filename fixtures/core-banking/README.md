# Synthetic Core Banking Fixture

This folder is a deterministic, entirely fictional banking system for testing agentSQL. It supports both application paths:

1. Connect `banking-small.sqlite` as a SQLite database for live introspection and read-query execution.
2. Open this folder as a project source to test schema inference from `schema.sql`.

No names, emails, account references, card values, or financial events represent real people or institutions.

## Ready-to-use database

`banking-small.sqlite` contains:

- 22 tables and five reporting views.
- 1,000 customers and 1,500 accounts.
- 6,000 balanced transactions and exactly 12,000 ledger entries.
- Composite keys, generated columns, foreign keys, partial/expression indexes, triggers, `STRICT` tables, and `WITHOUT ROWID` tables.
- Synthetic lending, card, payment, FX, KYC, AML, and audit data.

The ledger is deliberately larger than agentSQL's 10,000-row result cap.

## Rebuild and verify

The scripts use only Python's standard library and Python 3.10 or later.

```powershell
python generate.py --profile small --write-expectations
python verify.py
```

Generate the larger local profile with exactly 250,000 ledger entries:

```powershell
python generate.py --profile full --write-expectations
python verify.py generated\banking-full.sqlite --profile full
```

The full database is generated under `generated/` and is intentionally ignored. Its deterministic logical checksums are retained in `expected/data-full.json`.

The generator refuses to write outside this fixture folder. It uses seed `20260922`, a fixed 2024–2025 time range, integer minor units for money, and balanced pairs of postings for every transaction.

## Golden expectations

- `expected/full-catalog.json` is the authoritative SQLite catalog. It includes ordered primary keys, foreign keys, indexes, generated/hidden column flags, view definitions, and triggers.
- `expected/querycraft-live-v1.json` is the current normalized output of agentSQL's real SQLite introspector.
- `expected/querycraft-source-v1.json` is the current normalized output of agentSQL's project-folder analyzer.
- `expected/data-small.json` and `expected/data-full.json` contain deterministic row counts and logical checksums.

The richer catalog is intentionally not reduced to agentSQL's present model. It records the metadata needed to test future reverse-engineering improvements. Current known gaps include foreign keys, index definitions, generated columns, composite-key order, triggers, and view SQL. The source scanner currently recognizes table declarations but not views, indexes, triggers, or later `ALTER TABLE` migrations.

## Manual scenarios

- `queries/read-only.sql` contains representative joins, aggregates, views, CTEs, and window queries.
- `queries/blocked.json` contains statements that must be rejected before SQLite sees them.
- `prompts.json` contains natural-language acceptance prompts and the schema objects a useful answer should reference.

To test in agentSQL, create a SQLite connection using the absolute path to `banking-small.sqlite`, refresh its schema, start a new chat, and try the prompts. Open this folder separately to compare source inference with live introspection.
