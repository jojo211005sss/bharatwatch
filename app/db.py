"""BharatWatch database layer — SQLite (stdlib only)."""
import os
import sqlite3
import threading

DB_PATH = os.environ.get(
    "BHARATWATCH_DB",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "bharatwatch.db"),
)

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS entities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    type TEXT NOT NULL,              -- Politician | Person | Company | GovtBody | Trust
    pan TEXT, din TEXT, cin TEXT,
    party TEXT, position TEXT, constituency TEXT, state TEXT,
    address TEXT, incorporation_date TEXT, photo_url TEXT,
    criminal_cases INTEGER DEFAULT 0,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(name);
CREATE INDEX IF NOT EXISTS idx_entities_pan ON entities(pan);
CREATE INDEX IF NOT EXISTS idx_entities_din ON entities(din);
CREATE INDEX IF NOT EXISTS idx_entities_cin ON entities(cin);

CREATE TABLE IF NOT EXISTS declarations (        -- ECI affidavit asset declarations
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    year INTEGER NOT NULL,
    assets REAL DEFAULT 0,           -- rupees
    liabilities REAL DEFAULT 0,
    income REAL DEFAULT 0,           -- declared annual income
    source TEXT
);

CREATE TABLE IF NOT EXISTS contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id TEXT,
    title TEXT,
    buyer_id INTEGER REFERENCES entities(id),     -- govt dept
    supplier_id INTEGER REFERENCES entities(id),  -- company
    value REAL DEFAULT 0,
    award_date TEXT,
    status TEXT DEFAULT 'Awarded',
    description TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS fund_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scheme TEXT,
    from_id INTEGER REFERENCES entities(id),
    to_id INTEGER REFERENCES entities(id),
    amount REAL DEFAULT 0,
    date TEXT,
    purpose TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL REFERENCES entities(id),
    to_id INTEGER NOT NULL REFERENCES entities(id),
    type TEXT NOT NULL,   -- Director_Of | Shareholder_Of | Family_Link | Donor_To | Oversees | Directs_Funds_To | Shared_Address
    evidence TEXT,
    source TEXT,
    start_date TEXT,
    value REAL
);
CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_id);
CREATE INDEX IF NOT EXISTS idx_rel_to ON relationships(to_id);

CREATE TABLE IF NOT EXISTS flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    pattern TEXT NOT NULL,
    risk_score INTEGER NOT NULL,
    title TEXT,
    explanation TEXT,
    value_involved REAL DEFAULT 0,
    evidence TEXT,                  -- JSON
    status TEXT DEFAULT 'auto',
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT,
    payload TEXT,                   -- JSON of the incoming row
    suggestion TEXT,                -- JSON of the suggested match / action
    confidence REAL,
    status TEXT DEFAULT 'pending',  -- pending | approved | rejected
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS imports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT,
    dataset TEXT,
    rows INTEGER DEFAULT 0,
    accepted INTEGER DEFAULT 0,
    queued INTEGER DEFAULT 0,
    status TEXT DEFAULT 'done',
    summary TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS company_financials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES entities(id),
    year INTEGER NOT NULL,
    assets REAL DEFAULT 0,
    liabilities REAL DEFAULT 0,
    revenue REAL DEFAULT 0,
    net_profit REAL DEFAULT 0,
    source TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    UNIQUE(company_id, year)
);
CREATE INDEX IF NOT EXISTS idx_financials_company ON company_financials(company_id);

CREATE TABLE IF NOT EXISTS tenures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    office TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT,
    source TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_tenures_entity ON tenures(entity_id);
"""


def get_db():
    conn = getattr(_local, "conn", None)
    if conn is None:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


def init_db():
    conn = get_db()
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def rows_to_dicts(rows):
    return [dict(r) for r in rows]
