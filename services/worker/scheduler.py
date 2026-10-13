import uuid
import time
import json
import threading
from typing import Dict, Any, List, Optional
from datetime import datetime

from .db import get_db
from .clock import clock
from .config import settings
from .payment_followup_flow import handle_check_eligible_invoices, handle_send_payment_reminder

class PaymentScheduler:
    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.worker_id = f"worker-{uuid.uuid4().hex[:6]}"
        self.is_enabled = True

    def acquire_lock(self) -> bool:
        with get_db() as conn:
            row = conn.execute("SELECT locked_by, acquired_at FROM scheduler_lock WHERE id = 1").fetchone()
            if row and row["locked_by"] is not None:
                # Check if lock is stale (> 5 minutes)
                try:
                    acq = datetime.fromisoformat(row["acquired_at"])
                    if (clock.now() - acq).total_seconds() < 300:
                        return False
                except Exception:
                    pass

            conn.execute("""
            UPDATE scheduler_lock 
            SET locked_by = ?, acquired_at = ?
            WHERE id = 1
            """, (self.worker_id, clock.iso_now()))
            return True

    def release_lock(self):
        with get_db() as conn:
            conn.execute("UPDATE scheduler_lock SET locked_by = NULL, acquired_at = NULL WHERE id = 1 AND locked_by = ?", (self.worker_id,))

    def run_cycle(self, run_type: str = "scheduled") -> Dict[str, Any]:
        """
        Executes a payment follow-up cycle guarded by single-instance SQLite lock.
        """
        if not self.acquire_lock():
            return {"status": "skipped", "reason": "Scheduler lock currently held by another worker instance"}

        run_id = f"RUN-{uuid.uuid4().hex[:8].upper()}"
        start_time = clock.iso_now()

        with get_db() as conn:
            conn.execute("""
            INSERT INTO scheduler_runs (
                id, run_type, started_at, status, invoices_checked, reminders_sent, details
            ) VALUES (?, ?, ?, 'running', 0, 0, '{}')
            """, (run_id, run_type, start_time))

        try:
            # Audit overdue invoices
            check_res = handle_check_eligible_invoices()
            eligible_invoices = check_res.get("eligible_invoices", [])
            invoices_checked = len(eligible_invoices) + len(check_res.get("skipped_records", []))
            reminders_sent = 0
            dispatch_results = []

            for inv in eligible_invoices:
                res = handle_send_payment_reminder(
                    invoice_id=inv["invoice_id"],
                    vendor=inv["vendor"],
                    invoice_number=inv["invoice_number"],
                    amount=inv["amount"],
                    due_date=inv["due_date"],
                    recipient=inv["recipient_email"],
                    currency=inv.get("currency", "USD")
                )
                dispatch_results.append(res)
                if res.get("verified"):
                    reminders_sent += 1

            details = {
                "check_summary": check_res,
                "dispatch_results": dispatch_results
            }

            completed_time = clock.iso_now()
            with get_db() as conn:
                conn.execute("""
                UPDATE scheduler_runs
                SET status = 'completed', completed_at = ?, invoices_checked = ?,
                    reminders_sent = ?, details = ?
                WHERE id = ?
                """, (completed_time, invoices_checked, reminders_sent, json.dumps(details), run_id))

            return {
                "run_id": run_id,
                "status": "completed",
                "invoices_checked": invoices_checked,
                "reminders_sent": reminders_sent,
                "details": details
            }

        except Exception as e:
            with get_db() as conn:
                conn.execute("""
                UPDATE scheduler_runs SET status = 'failed', completed_at = ?, details = ? WHERE id = ?
                """, (clock.iso_now(), json.dumps({"error": str(e)}), run_id))
            return {"run_id": run_id, "status": "failed", "error": str(e)}

        finally:
            self.release_lock()

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        # Run periodically
        while self._running:
            if self.is_enabled:
                try:
                    self.run_cycle(run_type="scheduled")
                except Exception:
                    pass
            # Check every minute
            time.sleep(60.0)

scheduler = PaymentScheduler()
