"""Search prepared chunks locally: python3 -m training_pipeline.search 'window functions'."""

import argparse
import json
from pathlib import Path
import re
import sqlite3

from .prepare import ROOT


def search(database, query, dialect=None, split=None, eligible_only=False, limit=5):
    terms = re.findall(r"\w+", query, re.UNICODE)
    if not terms:
        return []
    # Treat user input as literal search terms, not FTS operators or SQL.
    match = " AND ".join('"' + word.replace('"', '""') + '"' for word in terms)
    conditions, values = ["chunks MATCH ?"], [match]
    if dialect:
        conditions.append("EXISTS (SELECT 1 FROM json_each(chunks.dialects) WHERE value = ?)")
        values.append(dialect)
    if split:
        conditions.append("split = ?")
        values.append(split)
    if eligible_only:
        conditions.append("training_eligible = 1")
    sql = "SELECT id, text, dialects, source_urls, split, training_eligible FROM chunks WHERE " + " AND ".join(conditions) + " ORDER BY bm25(chunks) LIMIT ?"
    values.append(limit)
    with sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True) as db:
        rows = db.execute(sql, values).fetchall()
    return [{"id": r[0], "text": r[1], "dialects": json.loads(r[2]), "source_urls": json.loads(r[3]),
             "split": r[4], "training_eligible": bool(r[5])} for r in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query")
    parser.add_argument("--database", type=Path, default=ROOT / "TRAINING/prepared/search.sqlite")
    parser.add_argument("--dialect", choices=["postgresql", "tsql", "mariadb", "duckdb", "mixed", "odbc"])
    parser.add_argument("--split", choices=["train", "validation", "test"])
    parser.add_argument("--eligible-only", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.limit <= 50:
        parser.error("--limit must be between 1 and 50")
    print(json.dumps(search(args.database, args.query, args.dialect, args.split, args.eligible_only, args.limit), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
