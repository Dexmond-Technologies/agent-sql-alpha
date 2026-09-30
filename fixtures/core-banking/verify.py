#!/usr/bin/env python3
"""Verify fixture integrity, determinism, synthetic-data rules, and golden catalogs."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from generate import EXPECTED, ROOT, data_manifest, full_catalog, live_snapshot, source_snapshot


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", nargs="?", type=Path, default=ROOT / "banking-small.sqlite")
    parser.add_argument("--profile", choices=("small", "full"), default="small")
    args = parser.parse_args()
    database = args.database.resolve()
    conn = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)
    conn.execute("PRAGMA foreign_keys=ON")

    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "integrity_check failed"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == [], "foreign_key_check failed"
    table_count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchone()[0]
    view_count = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='view'").fetchone()[0]
    assert (table_count, view_count) == (22, 5), (table_count, view_count)
    assert conn.execute("SELECT count(*) FROM (SELECT transaction_id FROM ledger_entries GROUP BY transaction_id HAVING sum(amount_minor) <> 0)").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM customers WHERE email NOT LIKE '%@example.invalid'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM accounts WHERE account_reference NOT LIKE 'GB00TEST%'").fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM cards WHERE card_token NOT LIKE 'tok_test_%' OR length(last_four) <> 4").fetchone()[0] == 0
    assert data_manifest(conn, args.profile) == load(EXPECTED / f"data-{args.profile}.json"), "data manifest changed"
    if args.profile == "small":
        assert full_catalog(conn) == load(EXPECTED / "full-catalog.json"), "full catalog changed"
        assert live_snapshot(conn) == load(EXPECTED / "querycraft-live-v1.json"), "live baseline changed"
        assert source_snapshot() == load(EXPECTED / "querycraft-source-v1.json"), "source baseline changed"
    conn.close()
    assert not database.with_name(database.name + "-wal").exists()
    assert not database.with_name(database.name + "-shm").exists()
    print(f"OK: {database.name} ({table_count} tables, {view_count} views, profile={args.profile})")


if __name__ == "__main__":
    main()
