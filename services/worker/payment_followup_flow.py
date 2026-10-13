import os
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import httpx

from .tool_registry import tool_registry, ToolDefinition
from .state_store import state_store
from .clock import clock
from .config import settings
from packages.browser_tools import typed_send_sandbox_email

COMPANY_API_URL = os.getenv("COMPANY_APP_BASE_URL", "http://localhost:8001")
EMAIL_API_URL = os.getenv("EMAIL_SANDBOX_BASE_URL", "http://localhost:8002")

def slugify(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").upper()

def handle_check_eligible_invoices() -> Dict[str, Any]:
    """
    Audits internal invoices for overdue payment follow-up eligibility:
    - Status must be 'unpaid' or 'overdue'
    - Due date must be <= current system clock date
    - Paid or not-yet-due invoices are excluded
    """
    try:
        r_inv = httpx.get(f"{COMPANY_API_URL}/api/invoices", timeout=2.0)
        invoices = r_inv.json()
        r_vend = httpx.get(f"{COMPANY_API_URL}/api/vendors", timeout=2.0)
        vendors = {v["name"].strip().lower(): v for v in r_vend.json()}
    except Exception:
        from apps.company_app.company_db import get_db as get_company_db
        with get_company_db() as c_conn:
            invoices = [dict(r) for r in c_conn.execute("SELECT * FROM invoices").fetchall()]
            v_rows = c_conn.execute("SELECT * FROM vendors").fetchall()
            vendors = {v["name"].strip().lower(): dict(v) for v in v_rows}


    current_date = clock.now().strftime("%Y-%m-%d")
    eligible = []
    skipped = []

    for inv in invoices:
        inv_status = inv.get("status", "").lower()
        due_date = inv.get("due_date", "")

        # Only unpaid or overdue
        if inv_status not in ["unpaid", "overdue"]:
            skipped.append({"invoice_number": inv.get("invoice_number"), "reason": f"Status is '{inv_status}' (not unpaid)"})
            continue

        # Check due date
        if due_date > current_date:
            skipped.append({"invoice_number": inv.get("invoice_number"), "reason": f"Not overdue yet (due {due_date} > {current_date})"})
            continue

        # Check vendor recipient
        v_key = inv.get("vendor", "").strip().lower()
        vendor_info = vendors.get(v_key)
        if not vendor_info or not vendor_info.get("is_verified"):
            skipped.append({"invoice_number": inv.get("invoice_number"), "reason": "Unverified vendor recipient"})
            continue

        recipient_email = vendor_info.get("contact_email")
        eligible.append({
            "invoice_id": inv["id"],
            "vendor": inv["vendor"],
            "invoice_number": inv["invoice_number"],
            "amount": inv["amount"],
            "currency": inv.get("currency", "USD"),
            "due_date": due_date,
            "recipient_email": recipient_email,
            "reminder_count": inv.get("reminder_count", 0),
            "last_reminder_sent_at": inv.get("last_reminder_sent_at")
        })

    return {
        "current_date": current_date,
        "eligible_count": len(eligible),
        "eligible_invoices": eligible,
        "skipped_records": skipped
    }

def handle_send_payment_reminder(
    invoice_id: str,
    vendor: str,
    invoice_number: str,
    amount: float,
    due_date: str,
    recipient: str,
    currency: str = "USD"
) -> Dict[str, Any]:
    """
    Sends an automated overdue payment reminder to verified vendor contact.
    Constructs an idempotency key, checks outbox for duplicates, logs intent,
    dispatches via Playwright, and updates invoice reminder count.
    """
    # 1. Business hours check (allows non-business hours by default unless enforce_business_hours=True)
    if settings.enforce_business_hours and not clock.is_within_business_hours() and not clock.is_override_active():
        return {
            "success": False,
            "status": "outside_business_hours",
            "message": f"Current system time {clock.iso_now()} is outside configured business hours window ({settings.business_hours_start}-{settings.business_hours_end}) on weekday {clock.now().weekday()}."
        }
    timing_category = "business_hours" if clock.is_within_business_hours() else "non_business_hours"

    # 2. Construct deterministic idempotency key
    v_slug = slugify(vendor)
    idempotency_key = f"REMIND-{v_slug}-{invoice_number}-{due_date}"

    # 3. Search sandbox outbox for existing idempotency key before sending
    try:
        r_check = httpx.get(f"{EMAIL_API_URL}/api/check-idempotency/{idempotency_key}", timeout=2.0)
        if r_check.status_code == 200 and r_check.json().get("exists"):
            return {
                "success": True,
                "status": "duplicate_suppressed",
                "idempotency_key": idempotency_key,
                "message": f"Reminder already recorded in sandbox outbox with key '{idempotency_key}'. Duplicate send suppressed."
            }
    except Exception:
        from apps.email_sandbox.email_db import get_db as get_email_db
        with get_email_db() as e_conn:
            row = e_conn.execute("SELECT id FROM emails WHERE folder = 'outbox' AND idempotency_key = ?", (idempotency_key,)).fetchone()
            if row:
                return {
                    "success": True,
                    "status": "duplicate_suppressed",
                    "idempotency_key": idempotency_key,
                    "message": f"Reminder already recorded in sandbox outbox with key '{idempotency_key}'. Duplicate send suppressed."
                }


    # 4. Construct reminder message
    subject = f"Overdue Payment Reminder: Invoice {invoice_number} from {vendor}"
    body = (
        f"Attention Accounts Department ({vendor}),\n\n"
        f"This is a formal reminder regarding outstanding invoice reference {invoice_number} in the amount of "
        f"{currency} {amount:.2f}, which was due on {due_date}.\n\n"
        f"Please verify settlement or reach out to centrAlign Accounts Payable if payment has already been remitted.\n\n"
        f"Best regards,\nAccounts Payable Automation\ncentrAlign ERP"
    )

    # 5. Dispatch email via Playwright typed tool
    res = typed_send_sandbox_email(
        recipient=recipient,
        subject=subject,
        body=body,
        idempotency_key=idempotency_key
    )

    # 6. Update company ERP invoice reminder metadata
    if res.get("verified"):
        from apps.company_app.company_db import get_db as get_company_db
        try:
            with get_company_db() as c_conn:
                c_conn.execute("""
                UPDATE invoices
                SET reminder_count = reminder_count + 1,
                    last_reminder_sent_at = datetime('now')
                WHERE id = ?
                """, (invoice_id,))
        except Exception:
            pass

    return {
        "success": res.get("verified", False),
        "idempotency_key": idempotency_key,
        "recipient": recipient,
        "timing": timing_category,
        "verified": res.get("verified", False),
        "verification_details": res.get("verification_details", ""),
        "screenshot": res.get("screenshot")
    }

def handle_verify_reminder_sent(idempotency_key: str) -> Dict[str, Any]:
    try:
        r = httpx.get(f"{EMAIL_API_URL}/api/check-idempotency/{idempotency_key}", timeout=5.0)
        data = r.json()
        return {
            "verified": data.get("exists", False),
            "idempotency_key": idempotency_key,
            "details": "Confirmed in sandbox outbox" if data.get("exists") else "Not found in outbox"
        }
    except Exception as e:
        return {"verified": False, "error": str(e)}

def register_payment_followup_tools():
    tool_registry.register(ToolDefinition(
        name="check_eligible_invoices",
        description="Audits the ERP register for overdue unpaid invoices that are eligible for payment follow-up reminders.",
        parameters={"type": "object", "properties": {}},
        handler=handle_check_eligible_invoices
    ))

    tool_registry.register(ToolDefinition(
        name="send_payment_reminder",
        description="Sends a payment reminder email with an idempotency key to a verified vendor contact and verifies outbox delivery.",
        parameters={
            "type": "object",
            "properties": {
                "invoice_id": {"type": "string"},
                "vendor": {"type": "string"},
                "invoice_number": {"type": "string"},
                "amount": {"type": "number"},
                "due_date": {"type": "string"},
                "recipient": {"type": "string"},
                "currency": {"type": "string"}
            },
            "required": ["invoice_id", "vendor", "invoice_number", "amount", "due_date", "recipient"]
        },
        handler=handle_send_payment_reminder
    ))

    tool_registry.register(ToolDefinition(
        name="verify_reminder_sent",
        description="Independently verifies that a reminder email exists in the sandbox outbox with matching idempotency key.",
        parameters={
            "type": "object",
            "properties": {
                "idempotency_key": {"type": "string"}
            },
            "required": ["idempotency_key"]
        },
        handler=handle_verify_reminder_sent
    ))

register_payment_followup_tools()
