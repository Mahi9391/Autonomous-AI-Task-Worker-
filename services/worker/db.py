import sqlite3
import json
from contextlib import contextmanager
from typing import Generator, Any, Dict, List, Optional
from .config import settings
from .clock import clock

def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.worker_db_path)
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

def init_worker_db():
    settings.worker_db_path.parent.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            workflow_id TEXT NOT NULL,
            status TEXT NOT NULL,
            context TEXT DEFAULT '{}',
            result_summary TEXT,
            evidence TEXT DEFAULT '{}',
            step_count INTEGER DEFAULT 0,
            llm_call_count INTEGER DEFAULT 0,
            token_usage TEXT DEFAULT '{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS steps (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            step_number INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            arguments TEXT DEFAULT '{}',
            observation TEXT,
            status TEXT NOT NULL,
            retry_count INTEGER DEFAULT 0,
            evidence_ref TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS human_questions (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            question_text TEXT NOT NULL,
            question_type TEXT NOT NULL,
            options TEXT DEFAULT '[]',
            context TEXT DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending',
            answer TEXT,
            created_at TEXT NOT NULL,
            answered_at TEXT,
            FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS upload_tokens (
            token_hash TEXT PRIMARY KEY,
            invoice_ref TEXT NOT NULL,
            vendor_contact TEXT NOT NULL,
            task_id TEXT NOT NULL,
            is_used INTEGER DEFAULT 0,
            expires_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduler_runs (
            id TEXT PRIMARY KEY,
            run_type TEXT NOT NULL,
            started_at TEXT NOT NULL,
            completed_at TEXT,
            status TEXT NOT NULL,
            invoices_checked INTEGER DEFAULT 0,
            reminders_sent INTEGER DEFAULT 0,
            details TEXT DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS scheduler_lock (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            locked_by TEXT,
            acquired_at TEXT
        );

        CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        INSERT OR IGNORE INTO scheduler_lock (id, locked_by, acquired_at) VALUES (1, NULL, NULL);
        """)
