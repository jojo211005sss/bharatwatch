#!/usr/bin/env python3
"""Purge fake or placeholder source URLs from the BharatWatch database.

Criteria:
- Non-HTTP placeholder strings (e.g., "ECI affidavit", "MCA filings").
- Homepages without a specific record (e.g., https://pfms.nic.in/).
- URLs that do not contain the required identifier keyword (first significant word of the associated entity name).
- Dead links or HTTP errors (4xx/5xx) or redirects to login walls.

For each offending record, the `source` column is set to NULL and the action is logged to stdout.
"""
import sqlite3
import urllib.request
import urllib.error
import ssl
import re
from urllib.parse import urlparse
import time

# Import DB_PATH from the existing db module if possible
try:
    from db import DB_PATH
except Exception:
    DB_PATH = "data/bharatwatch.db"

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def required_keyword(name: str) -> str:
    """Return the first significant word of a name, mirroring verify_sources logic."""
    words = [w.strip().lower() for w in re.split(r"\\W+", name) if len(w.strip()) > 3]
    exclude = {"private", "limited", "company", "incorporated", "foundation", "trust", "seva", "department", "ministry", "authority", "national", "highways", "india"}
    words = [w for w in words if w not in exclude]
    return words[0] if words else ""

def is_homepage(url: str) -> bool:
    try:
        parsed = urlparse(url)
        return parsed.path in ("", "/")
    except Exception:
        return False

def url_is_accessible(url: str) -> bool:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError:
        return False
    except Exception:
        return False

def purge_declarations(conn):
    c = conn.cursor()
    rows = c.execute("""
        SELECT d.id, d.source, e.name
        FROM declarations d
        JOIN entities e ON e.id = d.entity_id
        WHERE d.source IS NOT NULL
    """).fetchall()
    for row_id, source, name in rows:
        _process_row(c, "declarations", row_id, source, name)
    conn.commit()

def purge_tenures(conn):
    c = conn.cursor()
    rows = c.execute("""
        SELECT t.id, t.source, e.name
        FROM tenures t
        JOIN entities e ON e.id = t.entity_id
        WHERE t.source IS NOT NULL
    """).fetchall()
    for row_id, source, name in rows:
        _process_row(c, "tenures", row_id, source, name)
    conn.commit()

def purge_company_financials(conn):
    c = conn.cursor()
    rows = c.execute("""
        SELECT cf.id, cf.source, e.name
        FROM company_financials cf
        JOIN entities e ON e.id = cf.company_id
        WHERE cf.source IS NOT NULL
    """).fetchall()
    for row_id, source, name in rows:
        _process_row(c, "company_financials", row_id, source, name)
    conn.commit()

def purge_relationships(conn):
    c = conn.cursor()
    rows = c.execute("""
        SELECT r.id, r.source, e1.name, e2.name
        FROM relationships r
        JOIN entities e1 ON e1.id = r.from_id
        JOIN entities e2 ON e2.id = r.to_id
        WHERE r.source IS NOT NULL
    """).fetchall()
    for row_id, source, name1, name2 in rows:
        _process_row(c, "relationships", row_id, source, name1, name2)
    conn.commit()

def purge_contracts(conn):
    c = conn.cursor()
    rows = c.execute("""
        SELECT c.id, c.source, b.name, s.name
        FROM contracts c
        JOIN entities b ON b.id = c.buyer_id
        JOIN entities s ON s.id = c.supplier_id
        WHERE c.source IS NOT NULL
    """).fetchall()
    for row_id, source, name1, name2 in rows:
        _process_row(c, "contracts", row_id, source, name1, name2)
    conn.commit()

def purge_fund_flows(conn):
    c = conn.cursor()
    rows = c.execute("""
        SELECT f.id, f.source, a.name, b.name
        FROM fund_flows f
        JOIN entities a ON a.id = f.from_id
        JOIN entities b ON b.id = f.to_id
        WHERE f.source IS NOT NULL
    """).fetchall()
    for row_id, source, name1, name2 in rows:
        _process_row(c, "fund_flows", row_id, source, name1, name2)
    conn.commit()

def _process_row(cursor, table, row_id, source, name1, name2=None):
    """Apply purge checks to a row and null out the source if any rule matches."""
    # Placeholder or non‑HTTP
    if not isinstance(source, str) or not source.lower().startswith("http"):
        print(f"[PURGE] {table} id {row_id}: placeholder '{source}'")
        cursor.execute(f"UPDATE {table} SET source=NULL WHERE id=?", (row_id,))
        return
    # Homepage URL
    if is_homepage(source):
        print(f"[PURGE] {table} id {row_id}: homepage '{source}'")
        cursor.execute(f"UPDATE {table} SET source=NULL WHERE id=?", (row_id,))
        return
    # Identifier keyword presence
    kw1 = required_keyword(name1)
    kw2 = required_keyword(name2) if name2 else None
    if kw1 and kw1 not in source.lower() and (kw2 is None or (kw2 and kw2 not in source.lower())):
        print(f"[PURGE] {table} id {row_id}: missing identifier in '{source}'")
        cursor.execute(f"UPDATE {table} SET source=NULL WHERE id=?", (row_id,))
        return
    # Accessibility check
    if not url_is_accessible(source):
        print(f"[PURGE] {table} id {row_id}: inaccessible '{source}'")
        cursor.execute(f"UPDATE {table} SET source=NULL WHERE id=?", (row_id,))
        return

def main():
    conn = sqlite3.connect(DB_PATH)
    purge_declarations(conn)
    purge_tenures(conn)
    purge_company_financials(conn)
    purge_relationships(conn)
    purge_contracts(conn)
    purge_fund_flows(conn)
    conn.close()

if __name__ == "__main__":
    main()
