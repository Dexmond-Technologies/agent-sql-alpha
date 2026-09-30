#!/usr/bin/env python3
"""Build deterministic synthetic core-banking SQLite fixtures using the stdlib only."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parent
SCHEMA_PATH = ROOT / "schema.sql"
EXPECTED = ROOT / "expected"
SEED = 20260922
PROFILES = {
    "small": {"customers": 1_000, "accounts": 1_500, "transactions": 6_000, "merchants": 120},
    "full": {"customers": 10_000, "accounts": 20_000, "transactions": 125_000, "merchants": 500},
}


def iso(day: dt.datetime) -> str:
    return day.strftime("%Y-%m-%dT%H:%M:%SZ")


def uid(prefix: str, number: int, width: int = 8) -> str:
    return f"{prefix}-{number:0{width}d}"


def chunks(rows: Iterable[tuple[Any, ...]], size: int = 5_000) -> Iterable[list[tuple[Any, ...]]]:
    batch: list[tuple[Any, ...]] = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []
    if batch:
        yield batch


def insert_many(conn: sqlite3.Connection, sql: str, rows: Iterable[tuple[Any, ...]]) -> None:
    for batch in chunks(rows):
        conn.executemany(sql, batch)


def build_database(output: Path, profile: str) -> None:
    config = PROFILES[profile]
    resolved = output.resolve()
    if ROOT.resolve() not in resolved.parents:
        raise SystemExit(f"Refusing to write outside {ROOT}")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()

    conn = sqlite3.connect(output)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=DELETE")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))

    base = dt.datetime(2024, 1, 1, 8, 0, 0)
    currencies = [
        ("GBP", "Pound sterling", 2, 1), ("EUR", "Euro", 2, 1),
        ("USD", "US dollar", 2, 1), ("CHF", "Swiss franc", 2, 1),
        ("JPY", "Japanese yen", 0, 1),
    ]
    conn.executemany("INSERT INTO currencies VALUES(?,?,?,?)", currencies)
    branches = [(i, f"BR{i:03d}", f"Synthetic Branch {i:02d}", "GB", f"201{(i % 9)}-01-15", 1) for i in range(1, 13)]
    conn.executemany("INSERT INTO branches VALUES(?,?,?,?,?,?)", branches)
    products = [
        (1, "CUR-GBP", "Everyday Current", "CURRENT", "GBP", 0, 0, 0, 1),
        (2, "SAV-GBP", "Flexible Saver", "SAVINGS", "GBP", 225, 0, 0, 1),
        (3, "CUR-EUR", "Euro Current", "CURRENT", "EUR", 0, 0, 250, 1),
        (4, "CUR-USD", "Dollar Current", "CURRENT", "USD", 0, 0, 250, 1),
        (5, "CRD-GBP", "Credit Account", "CREDIT", "GBP", 1899, 0, 500, 1),
        (6, "ESC-GBP", "Client Escrow", "ESCROW", "GBP", 0, 10_000, 0, 1),
    ]
    conn.executemany("INSERT INTO account_products VALUES(?,?,?,?,?,?,?,?,?)", products)

    customer_count = config["customers"]
    customer_rows = []
    address_rows = []
    kyc_rows = []
    for i in range(1, customer_count + 1):
        business = i % 5 == 0
        risk = "HIGH" if i % 37 == 0 else "MEDIUM" if i % 7 == 0 else "LOW"
        status = "REVIEW" if i % 113 == 0 else "CLOSED" if i % 257 == 0 else "ACTIVE"
        created = base + dt.timedelta(days=i % 500)
        customer_rows.append((
            uid("CUS", i), "BUSINESS" if business else "INDIVIDUAL",
            None if business else f"Synthetic{i:05d}", None if business else "Customer",
            f"Synthetic Business {i:05d}" if business else None,
            f"customer{i:05d}@example.invalid", None if i % 11 == 0 else f"+440000{i:06d}",
            risk, ["GB", "IE", "FR", "DE"][i % 4], status, iso(created),
        ))
        address_rows.append((i, uid("CUS", i), "BUSINESS" if business else "HOME", f"{i} Test Avenue", None if i % 3 else "Fixture Quarter", f"Synthetic City {i % 20:02d}", f"ZZ{i % 100:02d} {i % 10}ZZ", "GB", "2024-01-01", None, 1))
        reviewed = None if i % 97 == 0 else iso(created + dt.timedelta(days=2))
        kyc_rows.append((uid("KYC", i), uid("CUS", i), "PENDING" if reviewed is None else "APPROVED", (i * 17) % 101, f"TEST-KYC-{i:08d}", iso(created), reviewed, None if reviewed is None else f"reviewer-{i % 12:02d}", None if i % 13 else "Synthetic enhanced review"))
    insert_many(conn, "INSERT INTO customers(customer_id,customer_type,given_name,family_name,legal_name,email,phone,risk_rating,tax_residency_country,status,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", customer_rows)
    insert_many(conn, "INSERT INTO customer_addresses VALUES(?,?,?,?,?,?,?,?,?,?,?)", address_rows)
    insert_many(conn, "INSERT INTO kyc_cases VALUES(?,?,?,?,?,?,?,?,?)", kyc_rows)

    account_count = config["accounts"]
    currency_codes = ["GBP", "GBP", "GBP", "EUR", "USD", "CHF", "JPY"]
    product_for_currency = {"GBP": [1, 2, 5, 6], "EUR": [3], "USD": [4], "CHF": [1], "JPY": [1]}
    account_rows = []
    holder_rows = []
    accounts: list[dict[str, Any]] = []
    customer_accounts: dict[str, list[str]] = {}
    for i in range(1, account_count + 1):
        customer_number = ((i - 1) % customer_count) + 1
        customer_id = uid("CUS", customer_number)
        currency = currency_codes[i % len(currency_codes)]
        product = product_for_currency[currency][i % len(product_for_currency[currency])]
        status = "DORMANT" if i % 97 == 0 else "FROZEN" if i % 211 == 0 else "CLOSED" if i % 389 == 0 else "ACTIVE"
        opened = base + dt.timedelta(days=i % 365)
        closed = iso(opened + dt.timedelta(days=500)) if status == "CLOSED" else None
        account_id = uid("ACC", i)
        reference = f"GB00TEST{i:012d}"
        last_activity = iso(base - dt.timedelta(days=500)) if status == "DORMANT" else iso(opened + dt.timedelta(days=300))
        account_rows.append((account_id, reference, (i % 12) + 1, product, currency, status, iso(opened), closed, last_activity, 100_000 if product in (1, 3, 4) else 0, f"EXT-TEST-{i:08d}" if i % 9 == 0 else None, iso(opened)))
        holder_rows.append((account_id, customer_id, "PRIMARY", 100 if i % 10 else 60, iso(opened)))
        if i % 10 == 0:
            joint_id = uid("CUS", (customer_number % customer_count) + 1)
            holder_rows.append((account_id, joint_id, "JOINT", 40, iso(opened + dt.timedelta(days=7))))
        accounts.append({"id": account_id, "customer": customer_id, "currency": currency, "status": status})
        customer_accounts.setdefault(customer_id, []).append(account_id)
    insert_many(conn, "INSERT INTO accounts(account_id,account_reference,branch_id,product_id,currency_code,status,opened_at,closed_at,last_activity_at,overdraft_limit_minor,external_reference,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", account_rows)
    insert_many(conn, "INSERT INTO account_holders VALUES(?,?,?,?,?)", holder_rows)
    account_by_id = {account["id"]: account for account in accounts}

    beneficiary_rows = []
    beneficiaries_by_customer: dict[str, list[str]] = {}
    for i in range(1, customer_count // 3 + 1):
        owner = uid("CUS", ((i * 3 - 1) % customer_count) + 1)
        beneficiary_id = uid("BEN", i)
        currency = currency_codes[i % len(currency_codes)]
        beneficiary_rows.append((beneficiary_id, owner, f"Test beneficiary {i:05d}", f"Synthetic Recipient {i:05d}", f"GB00DEST{i:012d}", ["GB", "DE", "FR", "US"][i % 4], currency, iso(base + dt.timedelta(days=i % 600)), iso(base + dt.timedelta(days=(i % 600) + 2)) if i % 5 else None, 0 if i % 5 == 0 else 1))
        beneficiaries_by_customer.setdefault(owner, []).append(beneficiary_id)
    insert_many(conn, "INSERT INTO beneficiaries VALUES(?,?,?,?,?,?,?,?,?,?)", beneficiary_rows)

    merchant_rows = [(uid("MER", i), f"Synthetic Merchant {i:04d}", f"{(5000 + i) % 10_000:04d}", ["GB", "FR", "DE", "US", "JP"][i % 5], (i % 5) + 1, iso(base + dt.timedelta(days=i))) for i in range(1, config["merchants"] + 1)]
    insert_many(conn, "INSERT INTO merchants VALUES(?,?,?,?,?,?)", merchant_rows)
    batches = []
    for month in range(24):
        day = dt.date(2024 + month // 12, month % 12 + 1, 1)
        batches.append((month + 1, f"BATCH-{day:%Y%m}", day.isoformat(), "CORE_LEDGER", "POSTED", f"{day.isoformat()}T23:59:00Z", f"{day.isoformat()}T00:01:00Z"))
    conn.executemany("INSERT INTO journal_batches VALUES(?,?,?,?,?,?,?)", batches)

    active_by_currency: dict[str, list[dict[str, Any]]] = {}
    for account in accounts:
        if account["status"] == "ACTIVE":
            active_by_currency.setdefault(account["currency"], []).append(account)
    tx_rows: list[tuple[Any, ...]] = []
    entry_rows: list[tuple[Any, ...]] = []
    payment_rows: list[tuple[Any, ...]] = []
    previous: tuple[str, str, int, str] | None = None
    for tx_id in range(1, config["transactions"] + 1):
        when = base + dt.timedelta(seconds=(tx_id * 10_357) % (730 * 86_400))
        batch_id = ((when.year - 2024) * 12 + when.month - 1) % 24 + 1
        if tx_id % 100 == 0 and previous is not None:
            source_id, target_id, amount, currency = previous
            source_id, target_id = target_id, source_id
            tx_type, reversal = "REVERSAL", tx_id - 1
        else:
            currency = currency_codes[tx_id % len(currency_codes)]
            pool = active_by_currency[currency]
            source = pool[(tx_id * 17) % len(pool)]
            target = pool[(tx_id * 31 + 7) % len(pool)]
            if source["id"] == target["id"]:
                target = pool[(tx_id * 31 + 8) % len(pool)]
            source_id, target_id = source["id"], target["id"]
            amount = 100 + ((tx_id * 7_919) % 2_500_000)
            tx_type, reversal = (["TRANSFER", "CARD", "FEE", "INTEREST", "LOAN"][tx_id % 5], None)
        cross_border = 1 if tx_id % 17 == 0 else 0
        channel = ["MOBILE", "WEB", "BRANCH", "CARD", "BATCH"][tx_id % 5]
        description = "Synthetic rapid movement pattern" if tx_id % 1000 in (1, 2, 3) else f"Synthetic {tx_type.lower()} {tx_id:08d}"
        metadata = json.dumps({"fixture": True, "pattern": "rapid_movement" if tx_id % 1000 in (1, 2, 3) else "ordinary"}, separators=(",", ":"), sort_keys=True)
        tx_rows.append((tx_id, batch_id, f"TXN-{tx_id:012d}", tx_type, currency, amount, iso(when), when.date().isoformat(), description, "POSTED", channel, cross_border, reversal, metadata))
        for sequence, (account_id, signed_amount) in enumerate(((source_id, -amount), (target_id, amount)), 1):
            digest = hashlib.sha256(f"{tx_id}:{sequence}:{account_id}:{signed_amount}".encode()).digest()[:16]
            entry_rows.append(((tx_id - 1) * 2 + sequence, tx_id, account_id, signed_amount, sequence, iso(when), digest))
        source_customer = account_by_id[source_id]["customer"]
        if tx_id % 4 == 0:
            beneficiary = beneficiaries_by_customer.get(source_customer, [None])[0]
            method = "SWIFT" if cross_border else "INTERNAL"
            payment_rows.append((uid("PAY", tx_id, 12), source_id, beneficiary, tx_id, amount, currency, method, "SETTLED", iso(when - dt.timedelta(minutes=5)), iso(when), None))
        previous = (source_id, target_id, amount, currency)
        if len(tx_rows) >= 5_000:
            conn.executemany("INSERT INTO ledger_transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tx_rows)
            conn.executemany("INSERT INTO ledger_entries(entry_id,transaction_id,account_id,amount_minor,running_sequence,posted_at,integrity_hash) VALUES(?,?,?,?,?,?,?)", entry_rows)
            tx_rows.clear(); entry_rows.clear()
    if tx_rows:
        conn.executemany("INSERT INTO ledger_transactions VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", tx_rows)
        conn.executemany("INSERT INTO ledger_entries(entry_id,transaction_id,account_id,amount_minor,running_sequence,posted_at,integrity_hash) VALUES(?,?,?,?,?,?,?)", entry_rows)
    insert_many(conn, "INSERT INTO payment_instructions VALUES(?,?,?,?,?,?,?,?,?,?,?)", payment_rows)

    card_rows = []
    auth_rows = []
    eligible_accounts = [a for a in accounts if a["status"] == "ACTIVE"]
    for i, account in enumerate(eligible_accounts[::3], 1):
        card_id = uid("CRD", i)
        card_rows.append((card_id, account["id"], account["customer"], f"tok_test_{i:012d}", f"{i % 10_000:04d}", ["DEBIT", "CREDIT", "VIRTUAL"][i % 3], "BLOCKED" if i % 101 == 0 else "ACTIVE", "2024-02-01", "2029-02-28", 500_000 + (i % 10) * 100_000))
        for auth_sequence in range(2):
            auth_number = (i - 1) * 2 + auth_sequence + 1
            merchant_number = (auth_number % config["merchants"]) + 1
            tx_id = (auth_number % config["transactions"]) + 1
            auth_rows.append((uid("AUT", auth_number, 10), card_id, uid("MER", merchant_number), tx_id, 500 + (auth_number * 313) % 75_000, account["currency"], "DECLINED" if auth_number % 29 == 0 else "APPROVED", "05" if auth_number % 29 == 0 else "00", iso(base + dt.timedelta(minutes=auth_number * 73)), hashlib.sha256(f"device-{auth_number}".encode()).digest()[:12], auth_number % 2))
    insert_many(conn, "INSERT INTO cards VALUES(?,?,?,?,?,?,?,?,?,?)", card_rows)
    insert_many(conn, "INSERT INTO card_authorizations VALUES(?,?,?,?,?,?,?,?,?,?,?)", auth_rows)

    fx_pairs = [("GBP", "EUR", 1_165_000), ("GBP", "USD", 1_275_000), ("EUR", "USD", 1_095_000), ("USD", "JPY", 149_500_000), ("GBP", "CHF", 1_115_000)]
    fx_rows = []
    for month in range(24):
        rate_date = dt.date(2024 + month // 12, month % 12 + 1, 1).isoformat()
        for base_currency, quote_currency, base_rate in fx_pairs:
            fx_rows.append((base_currency, quote_currency, rate_date, base_rate + month * 317, "SYNTHETIC_REFERENCE"))
    conn.executemany("INSERT INTO fx_rates VALUES(?,?,?,?,?)", fx_rows)

    loan_rows = []
    installment_rows = []
    loan_count = max(20, customer_count // 10)
    for i in range(1, loan_count + 1):
        customer_id = uid("CUS", ((i * 7 - 1) % customer_count) + 1)
        account_id = customer_accounts[customer_id][0]
        account = accounts[int(account_id.split("-")[1]) - 1]
        status = "DELINQUENT" if i % 11 == 0 else "PAID" if i % 17 == 0 else "CURRENT"
        principal = 500_000 + (i * 110_003) % 5_000_000
        originated = dt.date(2024, (i % 12) + 1, 1)
        loan_rows.append((uid("LOAN", i), customer_id, account_id, principal, account["currency"], 350 + i % 800, 12, originated.isoformat(), (originated + dt.timedelta(days=365)).isoformat(), status, json.dumps({"type": "synthetic_guarantee", "value_minor": principal * 2}, separators=(",", ":"))))
        monthly_principal = principal // 12
        for number in range(1, 13):
            due = originated + dt.timedelta(days=30 * number)
            installment_status = "LATE" if status == "DELINQUENT" and number in (9, 10, 11) else "PAID" if due < dt.date(2025, 1, 1) or status == "PAID" else "DUE"
            total_due = monthly_principal + principal * 5 // 12_000
            paid = total_due if installment_status == "PAID" else total_due // 4 if installment_status == "LATE" else 0
            installment_rows.append((uid("LOAN", i), number, due.isoformat(), monthly_principal, principal * 5 // 12_000, paid, due.isoformat() + "T12:00:00Z" if paid == total_due else None, installment_status))
    insert_many(conn, "INSERT INTO loans VALUES(?,?,?,?,?,?,?,?,?,?,?)", loan_rows)
    insert_many(conn, "INSERT INTO loan_installments VALUES(?,?,?,?,?,?,?,?)", installment_rows)

    alert_rows = []
    alert_link_rows = []
    alert_count = max(20, customer_count // 50)
    for i in range(1, alert_count + 1):
        customer_id = uid("CUS", ((i * 47 - 1) % customer_count) + 1)
        account_id = customer_accounts[customer_id][0]
        status = ["OPEN", "INVESTIGATING", "CLOSED", "ESCALATED"][i % 4]
        alert_rows.append((uid("AML", i), customer_id, account_id, ["STRUCTURING", "RAPID_MOVEMENT", "SANCTIONS", "UNUSUAL_VALUE", "NEW_BENEFICIARY"][i % 5], ["LOW", "MEDIUM", "HIGH", "CRITICAL"][i % 4], status, 55 + i % 46, iso(base + dt.timedelta(days=i * 3)), iso(base + dt.timedelta(days=i * 3 + 5)) if status == "CLOSED" else None, "FALSE_POSITIVE" if status == "CLOSED" else None, "fixture-rule-v1"))
        for offset in range(3):
            tx_id = ((i * 1000 + offset) % config["transactions"]) + 1
            alert_link_rows.append((uid("AML", i), tx_id, "Synthetic linked activity", 60 + offset * 10))
    conn.executemany("INSERT INTO aml_alerts VALUES(?,?,?,?,?,?,?,?,?,?,?)", alert_rows)
    conn.executemany("INSERT INTO aml_alert_transactions VALUES(?,?,?,?)", alert_link_rows)

    audit_count = 200 if profile == "small" else 2_000
    audit_rows = [(i, "CUSTOMER" if i % 2 else "ACCOUNT", uid("CUS", (i % customer_count) + 1) if i % 2 else uid("ACC", (i % account_count) + 1), "SYNTHETIC_REVIEW", f"fixture-user-{i % 10:02d}", iso(base + dt.timedelta(minutes=i * 19)), json.dumps({"fixture": True, "sequence": i}, separators=(",", ":"), sort_keys=True), uid("COR", i), f"192.0.2.{(i % 250) + 1}" ) for i in range(1, audit_count + 1)]
    insert_many(conn, "INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?,?)", audit_rows)

    conn.commit()
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    unbalanced = conn.execute("SELECT count(*) FROM (SELECT transaction_id FROM ledger_entries GROUP BY transaction_id HAVING sum(amount_minor) <> 0)").fetchone()[0]
    assert unbalanced == 0
    expected_entries = config["transactions"] * 2
    assert conn.execute("SELECT count(*) FROM ledger_entries").fetchone()[0] == expected_entries
    conn.execute("PRAGMA optimize")
    conn.execute("VACUUM")
    conn.close()


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def full_catalog(conn: sqlite3.Connection) -> dict[str, Any]:
    tables = []
    names = [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    for name in names:
        columns = []
        primary_key = []
        for cid, col_name, data_type, not_null, default, pk_order, hidden in conn.execute(f"PRAGMA table_xinfo({quote_identifier(name)})"):
            columns.append({"name": col_name, "dataType": data_type, "nullable": not bool(not_null), "default": default, "primaryKeyOrder": pk_order or None, "hidden": hidden})
            if pk_order:
                primary_key.append((pk_order, col_name))
        foreign_keys = []
        for row in conn.execute(f"PRAGMA foreign_key_list({quote_identifier(name)})"):
            foreign_keys.append({"id": row[0], "sequence": row[1], "table": row[2], "from": row[3], "to": row[4], "onUpdate": row[5], "onDelete": row[6], "match": row[7]})
        indexes = []
        for _, index_name, unique, origin, partial in conn.execute(f"PRAGMA index_list({quote_identifier(name)})"):
            index_columns = [{"sequence": row[0], "columnId": row[1], "name": row[2], "descending": bool(row[3]), "collation": row[4], "key": bool(row[5])} for row in conn.execute(f"PRAGMA index_xinfo({quote_identifier(index_name)})")]
            sql_row = conn.execute("SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (index_name,)).fetchone()
            indexes.append({"name": index_name, "unique": bool(unique), "origin": origin, "partial": bool(partial), "columns": index_columns, "sql": sql_row[0] if sql_row else None})
        sql = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone()[0]
        tables.append({"name": name, "sql": sql, "columns": columns, "primaryKey": [name for _, name in sorted(primary_key)], "foreignKeys": foreign_keys, "indexes": indexes})
    views = [{"name": name, "sql": sql, "columns": [row[1] for row in conn.execute(f"PRAGMA table_info({quote_identifier(name)})")]} for name, sql in conn.execute("SELECT name,sql FROM sqlite_master WHERE type='view' ORDER BY name")]
    triggers = [{"name": name, "table": table, "sql": sql} for name, table, sql in conn.execute("SELECT name,tbl_name,sql FROM sqlite_master WHERE type='trigger' ORDER BY name")]
    return {"fixtureVersion": 1, "schemaSha256": hashlib.sha256(SCHEMA_PATH.read_bytes()).hexdigest(), "tables": tables, "views": views, "triggers": triggers}


def live_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    objects = []
    for name, object_type in conn.execute("SELECT name,type FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        columns = []
        for _, col_name, data_type, not_null, _, pk in conn.execute(f"PRAGMA table_info({quote_identifier(name)})"):
            column = {"name": col_name, "dataType": data_type, "nullable": not bool(not_null), "key": None}
            if pk == 1:
                column["key"] = "PK"
            columns.append(column)
        objects.append({"schema": "main", "name": name, "kind": "view" if object_type == "view" else "table", "columns": columns})
    return {"engine": "sqlite", "tables": objects, "capturedAt": "<dynamic>"}


def strip_sql_comments(text: str) -> str:
    text = re.sub(r"--[^\n]*", "", text)
    return re.sub(r"/\*[\s\S]*?\*/", " ", text)


def balanced_body(text: str, open_at: int) -> str | None:
    depth = 0
    quote: str | None = None
    start = open_at + 1
    for index in range(open_at, len(text)):
        char = text[index]
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[start:index]
    return None


def split_top_level(body: str) -> list[str]:
    parts, start, depth, quote = [], 0, 0, None
    for index, char in enumerate(body):
        if quote:
            if char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            parts.append(body[start:index])
            start = index + 1
    parts.append(body[start:])
    return parts


def source_snapshot() -> dict[str, Any]:
    sql = strip_sql_comments(SCHEMA_PATH.read_text(encoding="utf-8"))
    table_re = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z_][A-Za-z0-9_$]*)\s*\(", re.I)
    column_re = re.compile(r"^\s*(?:\"([A-Za-z_]\w*)\"|`([A-Za-z_]\w*)`|\[([A-Za-z_]\w*)\]|([A-Za-z_]\w*))\s+(.+)\Z")
    stop = {"PRIMARY", "NOT", "NULL", "DEFAULT", "REFERENCES", "UNIQUE", "CHECK", "CONSTRAINT", "COLLATE", "GENERATED", "IDENTITY", "AUTO_INCREMENT"}
    constraints = {"CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "KEY", "INDEX"}
    objects = []
    for match in table_re.finditer(sql):
        body = balanced_body(sql, match.end() - 1)
        if body is None:
            continue
        columns = []
        for definition in split_top_level(body):
            found = column_re.match(definition)
            if not found:
                continue
            name = next(value for value in found.groups()[:4] if value is not None)
            if name.upper() in constraints:
                continue
            rest = found.group(5)
            words = rest.split()
            type_words = []
            for word in words:
                if word.upper() in stop:
                    break
                type_words.append(word)
            data_type = " ".join(type_words)
            if not data_type or len(data_type) > 80:
                continue
            upper = rest.upper()
            column = {"name": name, "dataType": data_type, "nullable": "NOT NULL" not in upper and "PRIMARY KEY" not in upper, "key": None}
            if "PRIMARY KEY" in upper:
                column["key"] = "PK"
            columns.append(column)
        if columns:
            objects.append({"schema": "inferred", "name": match.group(1), "kind": "table", "columns": columns, "sourceFile": "schema.sql"})
    objects.sort(key=lambda item: (item["schema"], item["name"]))
    return {"engine": "source", "tables": objects, "capturedAt": "<dynamic>", "sourceKind": "sql"}


def canonical_value(value: Any) -> Any:
    return {"blob": value.hex()} if isinstance(value, bytes) else value


def data_manifest(conn: sqlite3.Connection, profile: str) -> dict[str, Any]:
    manifest: dict[str, Any] = {"fixtureVersion": 1, "profile": profile, "seed": SEED, "tables": {}}
    for table in [row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]:
        info = conn.execute(f"PRAGMA table_info({quote_identifier(table)})").fetchall()
        pk = [row[1] for row in sorted((row for row in info if row[5]), key=lambda row: row[5])]
        order = ",".join(quote_identifier(name) for name in pk) if pk else "rowid"
        digest = hashlib.sha256()
        count = 0
        for row in conn.execute(f"SELECT * FROM {quote_identifier(table)} ORDER BY {order}"):
            digest.update(json.dumps([canonical_value(value) for value in row], ensure_ascii=True, separators=(",", ":")).encode())
            digest.update(b"\n")
            count += 1
        manifest["tables"][table] = {"rows": count, "sha256": digest.hexdigest()}
    return manifest


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_expectations(database: Path, profile: str) -> None:
    conn = sqlite3.connect(f"file:{database.resolve().as_posix()}?mode=ro", uri=True)
    if profile == "small":
        write_json(EXPECTED / "full-catalog.json", full_catalog(conn))
        write_json(EXPECTED / "querycraft-live-v1.json", live_snapshot(conn))
        write_json(EXPECTED / "querycraft-source-v1.json", source_snapshot())
    write_json(EXPECTED / f"data-{profile}.json", data_manifest(conn, profile))
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=PROFILES, default="small")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--write-expectations", action="store_true")
    args = parser.parse_args()
    output = args.output or (ROOT / "banking-small.sqlite" if args.profile == "small" else ROOT / "generated" / "banking-full.sqlite")
    if not output.is_absolute():
        output = ROOT / output
    build_database(output, args.profile)
    if args.write_expectations:
        write_expectations(output, args.profile)
    print(json.dumps({"database": str(output), "profile": args.profile, "ledgerEntries": PROFILES[args.profile]["transactions"] * 2, "bytes": output.stat().st_size}, indent=2))


if __name__ == "__main__":
    main()
