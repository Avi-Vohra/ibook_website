"""SQLite persistence for Stripe resource identifiers."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "stripe_store.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    stripe_product_id TEXT NOT NULL UNIQUE,
    stripe_price_id TEXT NOT NULL,
    currency TEXT NOT NULL,
    unit_amount INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS checkout_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    stripe_session_id TEXT NOT NULL UNIQUE,
    stripe_price_id TEXT NOT NULL,
    url TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    payment_status TEXT,
    amount_total INTEGER,
    currency TEXT,
    customer_email TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
"""


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_product(name, product_id, price_id, currency, unit_amount):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO products (name, stripe_product_id, stripe_price_id, currency, unit_amount) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, product_id, price_id, currency, unit_amount),
        )


def get_product(name):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM products WHERE name = ? ORDER BY id DESC LIMIT 1", (name,)
        ).fetchone()
        return dict(row) if row else None


def save_checkout_session(session_id, price_id, url):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO checkout_sessions (stripe_session_id, stripe_price_id, url) "
            "VALUES (?, ?, ?)",
            (session_id, price_id, url),
        )


def mark_session_completed(session_id, payment_status, amount_total, currency, customer_email):
    with get_conn() as conn:
        conn.execute(
            "UPDATE checkout_sessions SET status = 'complete', payment_status = ?, "
            "amount_total = ?, currency = ?, customer_email = ?, completed_at = CURRENT_TIMESTAMP "
            "WHERE stripe_session_id = ?",
            (payment_status, amount_total, currency, customer_email, session_id),
        )


def list_checkout_sessions():
    with get_conn() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM checkout_sessions ORDER BY id DESC"
        ).fetchall()]
