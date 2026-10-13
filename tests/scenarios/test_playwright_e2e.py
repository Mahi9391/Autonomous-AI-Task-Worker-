import os
import sys
import time
import subprocess
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from packages.browser_tools import (
    typed_search_inbox,
    typed_open_email_and_download,
    typed_create_invoice_in_erp,
    typed_send_sandbox_email,
    close_browser_session
)
from apps.company_app.company_db import init_company_db, seed_company_data
from apps.email_sandbox.email_db import init_email_db, seed_email_data

def test_playwright_full_flow():
    print("=" * 75)
    print("  TESTING PLAYWRIGHT BROWSER AUTOMATION END-TO-END FLOW")
    print("=" * 75)

    # Initialize databases
    init_company_db()
    seed_company_data()
    init_email_db()
    seed_email_data()

    # Clean up test records from prior runs so test is strictly repeatable
    from apps.company_app.company_db import get_db as get_c_db
    with get_c_db() as c_conn:
        c_conn.execute("DELETE FROM invoices WHERE invoice_number IN ('INV-X-003', 'INV-X-004')")

    # Start Company App on 8001 and Email Sandbox on 8002 in background
    py_bin = sys.executable
    p_company = subprocess.Popen([
        py_bin, "-m", "uvicorn", "main:app",
        "--app-dir", str(WORKSPACE_ROOT / "apps" / "company-app"),
        "--port", "8001", "--host", "127.0.0.1"
    ])
    p_email = subprocess.Popen([
        py_bin, "-m", "uvicorn", "main:app",
        "--app-dir", str(WORKSPACE_ROOT / "apps" / "email-sandbox"),
        "--port", "8002", "--host", "127.0.0.1"
    ])

    time.sleep(3) # Wait for uvicorn to bind

    try:
        # 1. Search Email Sandbox via Playwright
        print("-> Step 1: Searching Email Sandbox for 'Company X' via Playwright...")
        inbox_res = typed_search_inbox("Company X")
        print(f"   Found {inbox_res['count']} emails. Screenshot: {inbox_res['screenshot']}")
        assert inbox_res["count"] >= 3, "Expected at least 3 emails from Company X"

        # 2. Open latest email EML-X-03 and download PDF
        print("-> Step 2: Opening latest October invoice email (EML-X-03) and downloading PDF...")
        email_res = typed_open_email_and_download("EML-X-03")
        print(f"   Downloaded PDF: {email_res['attachment_path']}")
        print(f"   Computed SHA-256: {email_res['file_hash']}")
        assert email_res["attachment_path"] is not None, "Attachment download failed"

        # 3. Create Invoice in Company ERP via Playwright
        print("-> Step 3: Entering Invoice INV-X-003 into Company ERP via Playwright...")
        erp_res = typed_create_invoice_in_erp(
            vendor="Company X",
            invoice_number="INV-X-003",
            amount=2100.00,
            currency="USD",
            due_date="2026-10-31",
            issue_date="2026-10-01",
            file_hash=email_res["file_hash"]
        )
        print(f"   ERP Result Success: {erp_res['success']}")
        print(f"   Record ID: {erp_res.get('invoice_id')}")
        print(f"   Read-back Verified: {erp_res.get('verified')}")
        print(f"   Verification Details: {erp_res.get('verification_details')}")
        assert erp_res["success"] is True, "ERP invoice creation failed"
        assert erp_res["verified"] is True, "Read-back comparison failed"

        # 4. Test UI Perturbation Resilience
        print("-> Step 4: Toggling UI Perturbation in Company ERP...")
        from apps.company_app.main import set_app_settings
        set_app_settings(perturbation_enabled=True)

        print("   Entering Invoice INV-X-004 under Perturbed Form Layout...")
        perturbed_res = typed_create_invoice_in_erp(
            vendor="Company X",
            invoice_number="INV-X-004",
            amount=3500.00,
            currency="USD",
            due_date="2026-11-30",
            issue_date="2026-11-01"
        )
        print(f"   Perturbed Form Handled Successfully: {perturbed_res['success']}")
        print(f"   UI Perturbed Flag: {perturbed_res.get('ui_perturbed')}")
        print(f"   Read-back Verified: {perturbed_res.get('verified')}")
        assert perturbed_res["success"] is True, "Perturbed form submission failed"
        assert perturbed_res["ui_perturbed"] is True, "Perturbed UI was not detected"

        # 5. Test Email Dispatch with Idempotency Key
        print("-> Step 5: Dispatching sandbox payment reminder with idempotency verification...")
        send_res = typed_send_sandbox_email(
            recipient="contact@deltasupplies.internal",
            subject="Reminder: Overdue Invoice DS-101",
            body="Please settle invoice DS-101.",
            idempotency_key="REMIND-DELTA-E2E-TEST"
        )
        print(f"   Reminder Dispatched & Verified in Outbox: {send_res['verified']}")
        assert send_res["verified"] is True, "Outbox verification failed"

        print("=" * 75)
        print("  ALL PLAYWRIGHT E2E BROWSER CHECKS PASSED WITH 100% SUCCESS!")
        print("=" * 75)
        return True

    finally:
        close_browser_session()
        p_company.terminate()
        p_email.terminate()

if __name__ == "__main__":
    success = test_playwright_full_flow()
    sys.exit(0 if success else 1)
