import os
import hashlib
from typing import Dict, Any, List, Optional
import httpx

from .tool_registry import tool_registry, ToolDefinition
from .state_store import state_store
from .invoice_extractor import invoice_extractor
from .config import settings

# Import browser tools
from packages.browser_tools import (
    typed_search_inbox,
    typed_open_email_and_download,
    typed_create_invoice_in_erp,
    typed_send_sandbox_email,
    browser_navigate,
    browser_click,
    browser_fill,
    browser_get_page_snapshot,
)

COMPANY_API_URL = os.getenv("COMPANY_APP_BASE_URL", "http://localhost:8001")

def handle_search_inbox(query: str = "") -> Dict[str, Any]:
    return typed_search_inbox(query)

def handle_open_email_and_download(email_id: str) -> Dict[str, Any]:
    return typed_open_email_and_download(email_id)

def handle_extract_invoice_pdf(file_path: str) -> Dict[str, Any]:
    text = invoice_extractor.extract_text_from_pdf(file_path)
    fields = invoice_extractor.parse_invoice_text(text)
    
    # Compute SHA-256
    with open(file_path, "rb") as f:
        file_hash = hashlib.sha256(f.read()).hexdigest()
    fields["file_hash"] = file_hash

    return {
        "extracted_fields": fields,
        "text_snippet": text[:400] + ("..." if len(text) > 400 else "")
    }

def handle_validate_invoice_data(vendor: str, invoice_number: str, amount: Any, due_date: str) -> Dict[str, Any]:
    fields = {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "amount": amount,
        "due_date": due_date
    }
    is_valid, missing, status_code = invoice_extractor.validate(fields)
    return {
        "is_valid": is_valid,
        "missing_fields": missing,
        "status": status_code
    }

def handle_check_duplicate_invoice(vendor: str, invoice_number: str, file_hash: Optional[str] = None) -> Dict[str, Any]:
    # Query company app API
    try:
        r = httpx.get(f"{COMPANY_API_URL}/api/invoices", timeout=5.0)
        invoices = r.json()
    except Exception:
        # Fallback to direct sqlite query
        from apps.company_app.company_db import get_db as get_company_db
        with get_company_db() as c_conn:
            rows = c_conn.execute("SELECT * FROM invoices").fetchall()
            invoices = [dict(row) for row in rows]

    norm_v = vendor.strip().lower()
    norm_num = invoice_number.strip().lower()

    for inv in invoices:
        # Check business duplicate
        if inv["vendor"].strip().lower() == norm_v and inv["invoice_number"].strip().lower() == norm_num:
            return {
                "is_duplicate": True,
                "reason": f"Invoice '{invoice_number}' for vendor '{vendor}' already exists in system.",
                "existing_invoice_id": inv["id"]
            }
        # Check file hash duplicate
        if file_hash and inv.get("file_hash") == file_hash:
            return {
                "is_duplicate": True,
                "reason": f"File content hash {file_hash[:8]} matches existing invoice {inv['id']}.",
                "existing_invoice_id": inv["id"]
            }

    return {"is_duplicate": False}

def handle_create_invoice_in_erp(
    vendor: str,
    invoice_number: str,
    amount: float,
    currency: str,
    due_date: str,
    issue_date: Optional[str] = None,
    file_hash: Optional[str] = None
) -> Dict[str, Any]:
    return typed_create_invoice_in_erp(
        vendor=vendor,
        invoice_number=invoice_number,
        amount=amount,
        currency=currency,
        due_date=due_date,
        issue_date=issue_date,
        file_hash=file_hash
    )

def handle_request_missing_info(
    task_id: str,
    invoice_ref: str,
    vendor: str,
    missing_fields: List[str]
) -> Dict[str, Any]:
    # 1. Lookup verified vendor in directory
    try:
        r = httpx.get(f"{COMPANY_API_URL}/api/vendors", timeout=5.0)
        vendors = r.json()
    except Exception:
        from apps.company_app.company_db import get_db as get_company_db
        with get_company_db() as c_conn:
            rows = c_conn.execute("SELECT * FROM vendors").fetchall()
            vendors = [dict(row) for row in rows]

    matched_vendor = None
    for v in vendors:
        if v["name"].strip().lower() == vendor.strip().lower():
            matched_vendor = v
            break

    # If unverified or unknown recipient, pause and ask human question
    if not matched_vendor or not matched_vendor.get("is_verified"):
        q_id = state_store.create_human_question(
            task_id=task_id,
            question_text=f"Cannot dispatch missing-field request for '{vendor}'. No certified vendor contact found in directory. Please specify email address or escalate to manual review.",
            question_type="approval",
            options=["Provide Contact Email", "Escalate to Manual Review"],
            context={"invoice_ref": invoice_ref, "missing_fields": missing_fields}
        )
        return {
            "status": "awaiting_human",
            "question_id": q_id,
            "message": "Task paused awaiting human approval for unverified vendor recipient."
        }

    vendor_email = matched_vendor["contact_email"]

    # 2. Check if correction attempt was already made (One Correction Attempt Rule)
    task = state_store.get_task(task_id)
    ctx = task.get("context", {}) if task else {}
    if ctx.get("correction_attempted", False):
        # Escalate to manual review immediately
        state_store.update_task_status(
            task_id,
            status="manual_review",
            summary=f"One correction attempt was already utilized for invoice {invoice_ref}. Document remains invalid. Escalated to manual review per SOP policy."
        )
        return {
            "status": "manual_review",
            "message": "Maximum correction attempts exceeded (limit: 1). Escalated to manual review."
        }

    # 3. Create unguessable, single-use upload token
    token = state_store.create_upload_token(
        task_id=task_id,
        invoice_ref=invoice_ref,
        vendor_contact=vendor_email,
        expiry_hours=48
    )
    upload_url = f"{COMPANY_API_URL}/upload-correction?token={token}"

    # 4. Compose and dispatch email to sandbox
    subject = f"Information Required: Billing Invoice {invoice_ref}"
    body = (
        f"Dear {vendor} Accounts Department,\n\n"
        f"During compliance review of invoice reference '{invoice_ref}', the following required fields were missing or invalid:\n"
        + "\n".join([f" - {field.replace('_', ' ').title()}" for field in missing_fields]) + "\n\n"
        f"Please upload a corrected PDF document using your secure single-use portal link below:\n"
        f"{upload_url}\n\n"
        f"Note: This link is single-use and will expire in 48 hours.\n\n"
        f"Sincerely,\nAccounts Payable Compliance Team\ncentrAlign"
    )
    idempotency_key = f"REQ-CORRECT-{invoice_ref}"

    send_res = typed_send_sandbox_email(
        recipient=vendor_email,
        subject=subject,
        body=body,
        idempotency_key=idempotency_key
    )

    # Mark correction attempt recorded in task context and transition to awaiting_upload
    ctx["correction_attempted"] = True
    ctx["upload_token"] = token
    ctx["upload_url"] = upload_url
    ctx["vendor_contact"] = vendor_email
    state_store.update_task_context(task_id, ctx)
    state_store.update_task_status(
        task_id,
        status="awaiting_upload",
        summary=f"Missing fields request dispatched to {vendor_email}. Task paused awaiting vendor document upload."
    )

    return {
        "status": "awaiting_upload",
        "recipient": vendor_email,
        "upload_url": upload_url,
        "email_verified": send_res.get("verified", False)
    }

def handle_ask_human_question(
    task_id: str,
    question_text: str,
    question_type: str = "clarification",
    options: Optional[List[str]] = None
) -> Dict[str, Any]:
    q_id = state_store.create_human_question(
        task_id=task_id,
        question_text=question_text,
        question_type=question_type,
        options=options
    )
    return {
        "status": "awaiting_human",
        "question_id": q_id,
        "message": f"Question registered. Task {task_id} paused awaiting human answer."
    }

def handle_complete_task(
    task_id: str,
    summary: str,
    invoice_id: Optional[str] = None
) -> Dict[str, Any]:
    state_store.update_task_status(
        task_id=task_id,
        status="completed",
        summary=summary,
        evidence={"invoice_id": invoice_id} if invoice_id else None
    )
    return {
        "status": "completed",
        "summary": summary
    }

def register_invoice_tools():
    tool_registry.register(ToolDefinition(
        name="search_inbox",
        description="Searches the email sandbox inbox for messages by sender, subject, or keywords.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text (e.g. 'Company X')"}
            }
        },
        handler=handle_search_inbox
    ))

    tool_registry.register(ToolDefinition(
        name="open_email_and_download_invoice",
        description="Navigates to an email in the sandbox, downloads its attached invoice PDF, and calculates its SHA-256 hash.",
        parameters={
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "The unique ID of the email (e.g. 'EML-X-03')"}
            },
            "required": ["email_id"]
        },
        handler=handle_open_email_and_download
    ))

    tool_registry.register(ToolDefinition(
        name="extract_invoice_pdf",
        description="Extracts textual content and structured fields (vendor, invoice_number, amount, due_date) from an invoice PDF file.",
        parameters={
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Local path to the downloaded PDF file"}
            },
            "required": ["file_path"]
        },
        handler=handle_extract_invoice_pdf
    ))

    tool_registry.register(ToolDefinition(
        name="validate_invoice_data",
        description="Deterministically validates required invoice fields and identifies any missing or malformed values.",
        parameters={
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Vendor name"},
                "invoice_number": {"type": "string", "description": "Invoice number"},
                "amount": {"type": "number", "description": "Total amount"},
                "due_date": {"type": "string", "description": "Due date in YYYY-MM-DD"}
            },
            "required": ["vendor", "invoice_number", "due_date"]
        },
        handler=handle_validate_invoice_data
    ))

    tool_registry.register(ToolDefinition(
        name="check_duplicate_invoice",
        description="Checks if an invoice with the same content hash or vendor + invoice number already exists in the company ERP.",
        parameters={
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Vendor name"},
                "invoice_number": {"type": "string", "description": "Invoice reference number"},
                "file_hash": {"type": "string", "description": "Optional SHA-256 hash"}
            },
            "required": ["vendor", "invoice_number"]
        },
        handler=handle_check_duplicate_invoice
    ))

    tool_registry.register(ToolDefinition(
        name="create_invoice_in_erp",
        description="Navigates to the ERP system via Playwright, enters invoice details, adapts to UI perturbation, and executes read-back verification.",
        parameters={
            "type": "object",
            "properties": {
                "vendor": {"type": "string", "description": "Vendor name"},
                "invoice_number": {"type": "string", "description": "Invoice number"},
                "amount": {"type": "number", "description": "Total dollar amount"},
                "currency": {"type": "string", "description": "Currency code (default USD)"},
                "due_date": {"type": "string", "description": "Due date (YYYY-MM-DD)"},
                "issue_date": {"type": "string", "description": "Optional issue date"},
                "file_hash": {"type": "string", "description": "Optional file hash"}
            },
            "required": ["vendor", "invoice_number", "amount", "due_date"]
        },
        handler=handle_create_invoice_in_erp
    ))

    tool_registry.register(ToolDefinition(
        name="request_missing_info",
        description="Dispatches a missing fields correction request with a secure, expiring single-use upload link to the verified vendor contact.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Current task ID"},
                "invoice_ref": {"type": "string", "description": "Invoice identifier"},
                "vendor": {"type": "string", "description": "Vendor name"},
                "missing_fields": {"type": "array", "items": {"type": "string"}, "description": "List of missing field names"}
            },
            "required": ["task_id", "invoice_ref", "vendor", "missing_fields"]
        },
        handler=handle_request_missing_info
    ))

    tool_registry.register(ToolDefinition(
        name="ask_human_question",
        description="Pauses the task and raises a question or approval request to the human operator via the dashboard queue.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "question_text": {"type": "string", "description": "Question text"},
                "question_type": {"type": "string", "description": "clarification or approval"},
                "options": {"type": "array", "items": {"type": "string"}, "description": "Selectable options"}
            },
            "required": ["task_id", "question_text"]
        },
        handler=handle_ask_human_question
    ))

    tool_registry.register(ToolDefinition(
        name="complete_task",
        description="Finalizes task completion with an evidence summary once all required verifications have passed.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "summary": {"type": "string", "description": "Concise summary of actions and verified outcomes"},
                "invoice_id": {"type": "string", "description": "Optional created record ID"}
            },
            "required": ["task_id", "summary"]
        },
        handler=handle_complete_task
    ))

    # Generic browser primitives
    tool_registry.register(ToolDefinition(
        name="browser_navigate",
        description="Navigates browser to an arbitrary local URL.",
        parameters={"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
        handler=browser_navigate
    ))

    tool_registry.register(ToolDefinition(
        name="browser_click",
        description="Clicks an element matching the given CSS selector.",
        parameters={"type": "object", "properties": {"selector": {"type": "string"}}, "required": ["selector"]},
        handler=browser_click
    ))

    tool_registry.register(ToolDefinition(
        name="browser_fill",
        description="Fills an input field matching the given CSS selector with value.",
        parameters={"type": "object", "properties": {"selector": {"type": "string"}, "value": {"type": "string"}}, "required": ["selector", "value"]},
        handler=browser_fill
    ))

    tool_registry.register(ToolDefinition(
        name="browser_get_page_snapshot",
        description="Extracts an accessible DOM snapshot of all interactive elements on the current page.",
        parameters={"type": "object", "properties": {}},
        handler=browser_get_page_snapshot
    ))

register_invoice_tools()
