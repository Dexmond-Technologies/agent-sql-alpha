#!/usr/bin/env python3
"""Operator-run IBM i ODBC catalog export and bounded table reads. No arbitrary SQL API."""
import argparse
import base64
import datetime as dt
import decimal
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

FORMAT = "agentsql-ibmi-catalog-v1"
MAX_BYTES = 8 * 1024 * 1024


def odbc_value(value):
    if not value or "\x00" in value or "\r" in value or "\n" in value:
        raise ValueError("ODBC configuration contains an empty or invalid value.")
    return "{" + value.replace("}", "}}") + "}"


def exact_json(value):
    """Preserve decimals and integers too large for JavaScript as strings."""
    if isinstance(value, decimal.Decimal):
        if not value.is_finite():
            raise ValueError("Non-finite database decimal cannot be exported.")
        return str(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 9007199254740991:
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite database floating-point value cannot be exported.")
    if isinstance(value, (bytes, bytearray, memoryview)):
        return {"encoding": "base64", "value": base64.b64encode(value).decode("ascii")}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise ValueError("Unsupported ODBC result type; no substitute value was generated.")


def quote_identifier(value):
    if not value or len(value) > 128 or any(ord(c) < 32 for c in value):
        raise ValueError("Database identifiers must contain 1–128 printable characters.")
    return '"' + value.replace('"', '""') + '"'


def atomic_json(destination, value):
    destination = Path(destination)
    if destination.exists():
        raise ValueError("Output already exists. Choose a new output path; existing exports are preserved.")
    body = json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    if len(body) > MAX_BYTES:
        raise ValueError("Export exceeds 8 MiB. Narrow the schema scope, columns or row limit.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".ibmi-export-", delete=False) as file:
            temporary = Path(file.name)
            os.chmod(file.name, 0o600)
            file.write(body)
            file.flush()
            os.fsync(file.fileno())
        # Atomic publication without overwriting another process's export.
        os.link(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def connect():
    try:
        import pyodbc
    except ImportError as error:
        raise ValueError("Install tools/ibmi/requirements.txt and the supported IBM i Access ODBC driver.") from error
    required = ("IBMI_DSN", "IBMI_USER", "IBMI_PASSWORD")
    if any(not os.environ.get(key) for key in required):
        raise ValueError("IBMI_DSN, IBMI_USER and IBMI_PASSWORD must be supplied by the operator's secret environment.")
    connection_string = ";".join([
        "DSN=" + odbc_value(os.environ["IBMI_DSN"]),
        "UID=" + odbc_value(os.environ["IBMI_USER"]),
        "PWD=" + odbc_value(os.environ["IBMI_PASSWORD"]),
        "CONNTYPE=2", "ALLOWPROCCALLS=0", "XDYNAMIC=0", "NAM=0", "SSL=1", "QUERYTIMEOUT=1",
    ])
    connection = pyodbc.connect(connection_string, readonly=True, autocommit=False, timeout=15)
    connection.timeout = 60
    try:
        info = {
            "dbmsName": connection.getinfo(pyodbc.SQL_DBMS_NAME),
            "dbmsVersion": connection.getinfo(pyodbc.SQL_DBMS_VER),
            "driverName": connection.getinfo(pyodbc.SQL_DRIVER_NAME),
            "driverVersion": connection.getinfo(pyodbc.SQL_DRIVER_VER),
        }
        name = info["dbmsName"].upper()
        if not any(identity in name for identity in ("AS/400", "DB2/400", "DB2 FOR I", "ISERIES")):
            raise ValueError("The DSN did not identify a recognized Db2 for i server. Release/driver compatibility needs investigation.")
        if not all(info.values()):
            raise ValueError("The ODBC driver did not report complete server and driver identity.")
        return connection, info
    except BaseException:
        connection.close()
        raise


def catalog(connection, information, schemas, table_filter=None):
    objects, warnings = [], []
    seen = set()
    for scope in schemas:
        quote_identifier(scope)
        with connection.cursor() as cursor:
            cursor.tables(schema=scope, table=table_filter, tableType="TABLE,VIEW")
            while (row := cursor.fetchone()) is not None:
                # ODBC catalog filters can be patterns. Match the exact authorized schema locally.
                if row.table_schem != scope or (table_filter is not None and row.table_name != table_filter):
                    continue
                identity = (row.table_schem, row.table_name)
                if identity in seen:
                    raise ValueError("ODBC returned duplicate catalog objects.")
                seen.add(identity)
                if len(seen) > 500:
                    raise ValueError("Catalog exceeds 500 objects; export narrower schemas.")
                kind = str(row.table_type).strip().upper()
                if kind not in ("TABLE", "VIEW"):
                    raise ValueError("ODBC returned an unsupported object type.")
                objects.append({"schema": scope, "name": row.table_name, "kind": kind.lower(), "columns": []})
    if not objects:
        raise ValueError("No visible tables/views in the exact requested schemas. No example catalog was substituted.")
    objects.sort(key=lambda table: (table["schema"], table["name"]))
    for table in objects:
        with connection.cursor() as cursor:
            cursor.columns(schema=table["schema"], table=table["name"])
            while (row := cursor.fetchone()) is not None:
                if row.table_schem != table["schema"] or row.table_name != table["name"]:
                    continue
                if len(table["columns"]) >= 2000:
                    raise ValueError("Object exceeds 2,000 columns.")
                if row.nullable not in (0, 1) or not row.type_name:
                    raise ValueError("ODBC did not establish a column's nullability or data type; incomplete metadata was rejected.")
                type_name = str(row.type_name)
                if type_name.upper() in ("DECIMAL", "NUMERIC") and row.column_size is not None and row.decimal_digits is not None:
                    type_name += f"({row.column_size},{row.decimal_digits})"
                elif type_name.upper() in ("CHAR", "VARCHAR", "NCHAR", "NVARCHAR", "GRAPHIC", "VARGRAPHIC") and row.column_size is not None:
                    type_name += f"({row.column_size})"
                table["columns"].append({"name": row.column_name, "dataType": type_name, "nullable": bool(row.nullable), "key": None})
        if not table["columns"]:
            raise ValueError("An object had no readable column metadata; incomplete metadata was rejected.")
        try:
            with connection.cursor() as cursor:
                cursor.primaryKeys(schema=table["schema"], table=table["name"])
                primary = set()
                while (row := cursor.fetchone()) is not None:
                    if row.table_schem == table["schema"] and row.table_name == table["name"]:
                        primary.add(row.column_name)
                for column in table["columns"]:
                    if column["name"] in primary:
                        column["key"] = "PK"
        except Exception as error:
            # Primary-key markers are optional; absence must not be presented as proof of no key.
            state = sqlstate(error)
            if state not in ("IM001", "HYC00"):
                raise
            warnings.append(f"Primary-key metadata unavailable for {table['schema']}.{table['name']} (SQLSTATE {state}); keys are unknown.")
    warnings.append("Foreign keys, indexes, routines, view definitions and file-member semantics are not exported by this connector version; do not infer them.")
    warnings.append("SSL=1 was requested. Platform-specific driver TLS configuration and certificate/hostname validation require independent verification on the deployed driver.")
    return {
        "format": FORMAT, "capturedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "serverInformation": information, "transportVerification": "not-verified-by-exporter",
        "readOnlyRequested": True, "schemas": schemas, "tables": objects, "warnings": warnings,
    }


def read_table(connection, information, scope, name, columns, limit):
    # Identifiers are quoted, and must be present in real driver metadata. No caller SQL is accepted.
    metadata = catalog(connection, information, [scope], table_filter=name)
    found = [t for t in metadata["tables"] if t["schema"] == scope and t["name"] == name]
    if len(found) != 1 or found[0]["kind"] != "table":
        raise ValueError("Choose an exact visible base table. Reading views or routines is outside this connector's scope.")
    available = {c["name"] for c in found[0]["columns"]}
    if not columns or len(columns) > 100 or len(set(columns)) != len(columns) or any(c not in available for c in columns):
        raise ValueError("Choose 1–100 distinct columns present in the real table metadata.")
    sql = "SELECT " + ", ".join(map(quote_identifier, columns)) + " FROM " + quote_identifier(scope) + "." + quote_identifier(name) + f" FETCH FIRST {limit + 1} ROWS ONLY"
    started = time.monotonic()
    with connection.cursor() as cursor:
        cursor.execute(sql)
        rows = []
        accumulated = 0
        while (row := cursor.fetchone()) is not None:
            values = [exact_json(value) for value in row]
            accumulated += len(json.dumps(values, ensure_ascii=False, allow_nan=False).encode("utf-8"))
            if accumulated > MAX_BYTES:
                cursor.cancel()
                raise ValueError("Result exceeds 8 MiB; request fewer columns or rows.")
            rows.append(values)
            if len(rows) > limit:
                break
        return {"columns": [d[0] for d in cursor.description], "rows": rows[:limit],
                "elapsedMs": round((time.monotonic() - started) * 1000), "truncated": len(rows) > limit,
                "valueEncoding": "DECIMAL and integers outside JavaScript's exact range are strings; binary values are tagged base64; dates/times use ISO representations."}


def sqlstate(error):
    if error.args and isinstance(error.args[0], str) and len(error.args[0]) == 5 and error.args[0].isalnum():
        return error.args[0]
    return "unavailable"


def parser():
    command = argparse.ArgumentParser(description=__doc__)
    sub = command.add_subparsers(dest="operation", required=True)
    export = sub.add_parser("catalog", help="Export actual ODBC catalog metadata for exact schemas")
    export.add_argument("--schema", action="append", required=True)
    export.add_argument("--output", type=Path, required=True)
    read = sub.add_parser("read-table", help="Operator-requested read of explicit base-table columns; accepts no SQL")
    read.add_argument("--schema", required=True)
    read.add_argument("--table", required=True)
    read.add_argument("--column", action="append", required=True)
    read.add_argument("--limit", type=int, default=100)
    read.add_argument("--output", type=Path, required=True)
    return command


def worker(args):
    if args.output.exists():
        raise ValueError("Output already exists. Choose a new path.")
    if args.operation == "catalog" and (len(args.schema) > 100 or len(set(args.schema)) != len(args.schema)):
        raise ValueError("Choose 1–100 distinct schemas.")
    if args.operation == "read-table" and not 1 <= args.limit <= 10000:
        raise ValueError("Row limit must be between 1 and 10,000.")
    connection, information = connect()
    try:
        value = catalog(connection, information, args.schema) if args.operation == "catalog" else read_table(connection, information, args.schema, args.table, args.column, args.limit)
        atomic_json(args.output, value)
        print(json.dumps({"status": "completed", "operation": args.operation, "output": str(args.output),
                          "objects": len(value["tables"]) if args.operation == "catalog" else None,
                          "rows": len(value["rows"]) if args.operation == "read-table" else None}))
    finally:
        try:
            connection.rollback()
        finally:
            connection.close()


def main():
    args = parser().parse_args()
    if os.environ.get("_AGENTSQL_IBMI_WORKER") != "1":
        environment = dict(os.environ, _AGENTSQL_IBMI_WORKER="1")
        try:
            result = subprocess.run([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]], env=environment, timeout=180, check=False)
            return result.returncode
        except subprocess.TimeoutExpired:
            print("IBM i operation exceeded the 180-second process deadline. No successful export is claimed. Check host job state; process termination does not prove server-side cancellation.", file=sys.stderr)
            return 1
    try:
        worker(args)
        return 0
    except ValueError as error:
        print(str(error), file=sys.stderr)
    except Exception as error:
        # ODBC diagnostics can contain connection strings or record values. Expose SQLSTATE only.
        print(f"IBM i operation failed (SQLSTATE {sqlstate(error)}). Inspect protected driver/host diagnostics; no data or credentials are printed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
