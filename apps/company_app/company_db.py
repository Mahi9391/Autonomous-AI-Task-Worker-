import sqlite3
from contextlib import contextmanager
from typing import Generator
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "company.db"

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.row_factory = sqlite3.Row
    return conn

@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

def init_company_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS vendors (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            contact_email TEXT NOT NULL,
            payment_terms_days INTEGER DEFAULT 30,
            is_verified INTEGER DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS invoices (
            id TEXT PRIMARY KEY,
            vendor TEXT NOT NULL,
            invoice_number TEXT NOT NULL,
            amount REAL NOT NULL,
            currency TEXT NOT NULL DEFAULT 'USD',
            issue_date TEXT,
            due_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'unpaid', -- unpaid, paid, overdue
            file_hash TEXT,
            source TEXT DEFAULT 'manual', -- email, manual_upload, watched_folder
            created_at TEXT NOT NULL,
            last_reminder_sent_at TEXT,
            reminder_count INTEGER DEFAULT 0,
            UNIQUE(vendor, invoice_number)
        );

        CREATE TABLE IF NOT EXISTS app_settings (
            id INTEGER PRIMARY KEY CHECK(id = 1),
            perturbation_enabled INTEGER DEFAULT 0,
            fault_mode TEXT DEFAULT 'none', -- none, fail_before_save, fail_after_save, timeout
            updated_at TEXT
        );

        INSERT OR IGNORE INTO app_settings (id, perturbation_enabled, fault_mode, updated_at)
        VALUES (1, 0, 'none', datetime('now'));
        """)

def seed_company_data(clean: bool = True):
    init_company_db()
    with get_db() as conn:
        # Seed Vendors
        vendors = [
            ("VEND-X", "Company X", "billing@companyx.internal", 30, 1, "2026-01-01T00:00:00Z"),
            ("VEND-ACME", "Acme Corp", "ap@acmecorp.internal", 30, 1, "2026-01-01T00:00:00Z"),
            ("VEND-BETA", "Beta Logistics", "accounts@betalogistics.internal", 30, 1, "2026-01-01T00:00:00Z"),
            ("VEND-GAMMA", "Gamma Services", "finance@gammaservices.internal", 15, 1, "2026-01-01T00:00:00Z"),
            ("VEND-DELTA", "Delta Supplies", "contact@deltasupplies.internal", 45, 1, "2026-01-01T00:00:00Z"),
            ("VEND-NOVA", "Nova Tech", "billing@novatech.internal", 30, 1, "2026-01-01T00:00:00Z"),
        ]
        for v in vendors:
            conn.execute("""
            INSERT OR REPLACE INTO vendors (id, name, contact_email, payment_terms_days, is_verified, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """, v)

        if clean:
            # Clean out any non-baseline created invoices so that new bill flows are never duplicates
            conn.execute("DELETE FROM invoices WHERE id NOT IN ('INV-DELTA-101', 'INV-ACME-800');")

        # Seed initial baseline invoices:
        # One overdue unpaid invoice for Delta Supplies (to test payment follow-up!)
        # One already paid invoice for Acme Corp
        # Note: We do NOT seed Company X latest invoice or Nova Tech because the agent enters them as brand new bills!
        invoices = [
            ("INV-DELTA-101", "Delta Supplies", "DS-101", 1450.00, "USD", "2026-09-01", "2026-09-15", "unpaid", "hash_delta_101", "email", "2026-09-02T10:00:00Z", None, 0),
            ("INV-ACME-800", "Acme Corp", "ACME-800", 3200.00, "USD", "2026-08-10", "2026-09-10", "paid", "hash_acme_800", "manual_upload", "2026-08-11T10:00:00Z", None, 0),
        ]
        for inv in invoices:
            conn.execute("""
            INSERT OR REPLACE INTO invoices (
                id, vendor, invoice_number, amount, currency, issue_date, due_date, status, file_hash, source, created_at, last_reminder_sent_at, reminder_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, inv)
