import os
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional

from .browser_session import get_browser_session
from .verifiers import verify_invoice_read_back, verify_email_in_outbox

COMPANY_BASE_URL = os.getenv("COMPANY_APP_BASE_URL", "http://localhost:8001")
EMAIL_BASE_URL = os.getenv("EMAIL_SANDBOX_BASE_URL", "http://localhost:8002")

DOWNLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "downloads"
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)

def typed_search_inbox(query: str = "") -> Dict[str, Any]:
    """
    Typed browser tool to navigate to email sandbox inbox, search for emails,
    and return structured email list.
    """
    session = get_browser_session()
    page = session.page

    inbox_url = f"{EMAIL_BASE_URL}/inbox"
    if query:
        inbox_url += f"?q={query}"
    page.goto(inbox_url, wait_until="domcontentloaded")

    # Extract email list
    emails = page.evaluate("""() => {
        const rows = document.querySelectorAll('#email-table tbody tr.email-row');
        const results = [];
        rows.forEach(r => {
            const id = r.id.replace('email-row-', '');
            const sender = r.getAttribute('data-sender');
            const subject = r.getAttribute('data-subject');
            const dateCell = r.querySelector('td:nth-child(4)');
            const attBadge = r.querySelector('.badge-attachment');
            results.push({
                email_id: id,
                sender: sender,
                subject: subject,
                date: dateCell ? dateCell.innerText.trim() : '',
                has_attachment: !!attBadge
            });
        });
        return results;
    }""")

    screenshot = session.screenshot("inbox_search")
    return {
        "query": query,
        "count": len(emails),
        "emails": emails,
        "screenshot": screenshot
    }

def typed_open_email_and_download(email_id: str) -> Dict[str, Any]:
    """
    Typed browser tool to open an email by ID, download its attached invoice PDF,
    compute its SHA-256 hash, and return file information.
    """
    session = get_browser_session()
    page = session.page

    page.goto(f"{EMAIL_BASE_URL}/email/{email_id}", wait_until="domcontentloaded")
    
    sender = page.inner_text("#email-sender").strip()
    subject = page.inner_text("#email-subject").strip()
    body = page.inner_text("#email-body").strip()

    download_button = page.query_selector("#btn-download-pdf")
    attachment_path = None
    file_hash = None

    if download_button:
        with page.expect_download() as download_info:
            download_button.click()
        download = download_info.value
        
        save_path = DOWNLOADS_DIR / download.suggested_filename
        download.save_as(str(save_path))
        attachment_path = str(save_path)

        # Compute SHA-256 hash
        with open(save_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

    screenshot = session.screenshot(f"email_{email_id}")
    return {
        "email_id": email_id,
        "sender": sender,
        "subject": subject,
        "body": body,
        "attachment_path": attachment_path,
        "file_hash": file_hash,
        "screenshot": screenshot
    }

def typed_create_invoice_in_erp(
    vendor: str,
    invoice_number: str,
    amount: float,
    currency: str,
    due_date: str,
    issue_date: Optional[str] = None,
    file_hash: Optional[str] = None
) -> Dict[str, Any]:
    """
    Typed browser tool to create an invoice in the company ERP via Playwright.
    Adapts dynamically to UI perturbation (renamed fields, swapped order, confirmation check).
    Performs read-back verification after creation.
    """
    session = get_browser_session()
    page = session.page

    page.goto(f"{COMPANY_BASE_URL}/invoices/new", wait_until="domcontentloaded")

    # Check for perturbed UI vs standard UI
    is_perturbed = page.query_selector("#field-reference-doc") is not None

    if is_perturbed:
        # Perturbed form handling
        page.fill("#amount", f"{amount:.2f}")
        page.select_option("#currency", currency)
        page.fill("#vendor", vendor)
        page.fill("#field-reference-doc", invoice_number)
        page.fill("#due_date", due_date)
        if issue_date and page.query_selector("#issue_date"):
            page.fill("#issue_date", issue_date)
        
        confirm_check = page.query_selector("#confirm-accuracy")
        if confirm_check:
            confirm_check.check()
        
        submit_btn = page.query_selector("#btn-submit-entry")
        submit_btn.click()
    else:
        # Standard form handling
        page.fill("#vendor", vendor)
        page.fill("#invoice_number", invoice_number)
        page.fill("#amount", f"{amount:.2f}")
        page.select_option("#currency", currency)
        page.fill("#due_date", due_date)
        if issue_date and page.query_selector("#issue_date"):
            page.fill("#issue_date", issue_date)
        
        submit_btn = page.query_selector("#btn-save-invoice")
        submit_btn.click()

    page.wait_for_load_state("domcontentloaded")

    # Check if an error occurred (e.g. duplicate 409 or 500 fault)
    error_el = page.query_selector(".alert-error, #form-error")
    if error_el:
        err_text = error_el.inner_text().strip()
        screenshot = session.screenshot("invoice_create_error")
        return {
            "success": False,
            "error": err_text,
            "screenshot": screenshot
        }

    # Verify we landed on invoice detail view
    current_url = page.url
    if "/invoices/" in current_url and not current_url.endswith("/new"):
        # Read back values from UI
        read_back_data = {
            "vendor": page.inner_text("#detail-vendor").strip(),
            "invoice_number": page.inner_text("#detail-invoice-number").strip(),
            "amount": page.inner_text("#detail-amount").strip(),
            "currency": page.inner_text("#detail-currency").strip(),
            "due_date": page.inner_text("#detail-due-date").strip(),
            "status": page.inner_text("#detail-status").strip(),
            "record_id": page.inner_text("#detail-record-id").strip()
        }

        expected_data = {
            "vendor": vendor,
            "invoice_number": invoice_number,
            "amount": amount,
            "currency": currency,
            "due_date": due_date
        }

        # Perform deterministic read-back verification
        verification = verify_invoice_read_back(expected_data, read_back_data)
        screenshot = session.screenshot(f"invoice_created_{read_back_data['record_id']}")

        return {
            "success": True,
            "invoice_id": read_back_data["record_id"],
            "read_back": read_back_data,
            "verified": verification.verified,
            "verification_details": verification.details,
            "screenshot": screenshot,
            "ui_perturbed": is_perturbed
        }
    else:
        screenshot = session.screenshot("invoice_create_unknown_state")
        return {
            "success": False,
            "error": f"Did not redirect to invoice detail page. Current URL: {current_url}",
            "screenshot": screenshot
        }

def typed_send_sandbox_email(
    recipient: str,
    subject: str,
    body: str,
    idempotency_key: str
) -> Dict[str, Any]:
    """
    Typed browser tool to send an email via the sandbox compose UI,
    then independently verify that the email was recorded in the outbox.
    """
    session = get_browser_session()
    page = session.page

    page.goto(f"{EMAIL_BASE_URL}/compose", wait_until="domcontentloaded")
    page.fill("#recipient", recipient)
    page.fill("#subject", subject)
    page.fill("#body", body)
    if idempotency_key:
        page.fill("#idempotency_key", idempotency_key)

    page.click("#btn-send-email")
    page.wait_for_load_state("domcontentloaded")

    # Navigate to Outbox to verify delivery
    page.goto(f"{EMAIL_BASE_URL}/outbox", wait_until="domcontentloaded")
    
    # Read outbox rows
    outbox_emails = page.evaluate("""() => {
        const rows = document.querySelectorAll('#outbox-table tbody tr.outbox-row');
        const results = [];
        rows.forEach(r => {
            const id = r.id.replace('outbox-row-', '');
            const recipient = r.getAttribute('data-recipient');
            const ikey = r.getAttribute('data-idempotency');
            results.push({
                id: id,
                recipient: recipient,
                idempotency_key: ikey
            });
        });
        return results;
    }""")

    verification = verify_email_in_outbox(idempotency_key, outbox_emails)
    screenshot = session.screenshot("email_sent_verified")

    return {
        "success": verification.verified,
        "recipient": recipient,
        "idempotency_key": idempotency_key,
        "verified": verification.verified,
        "verification_details": verification.details,
        "screenshot": screenshot
    }
