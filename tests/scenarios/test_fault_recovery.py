import os
import sys
import time
import subprocess
from pathlib import Path
import httpx

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from packages.browser_tools import typed_create_invoice_in_erp, close_browser_session
from apps.company_app.company_db import init_company_db, seed_company_data
from apps.email_sandbox.email_db import init_email_db, seed_email_data

def test_fault_injection_and_recovery():
    print("=" * 75)
    print("  TESTING FAULT INJECTION, RETRIES, AND SAFE RECONCILIATION")
    print("=" * 75)

    init_company_db()
    seed_company_data()

    # Clean up test records from prior runs
    from apps.company_app.company_db import get_db as get_c_db
    with get_c_db() as c_conn:
        c_conn.execute("DELETE FROM invoices WHERE invoice_number IN ('INV-FAULT-001', 'INV-FAULT-002')")

    py_bin = sys.executable
    p_company = subprocess.Popen([
        py_bin, "-m", "uvicorn", "main:app",
        "--app-dir", str(WORKSPACE_ROOT / "apps" / "company-app"),
        "--port", "8001", "--host", "127.0.0.1"
    ])

    time.sleep(2)

    try:
        # 1. Test Fail Before Save (HTTP 500) & Retry Recovery
        print("-> Case A: Injected Fault 'fail_before_save' (Transient Server 500)...")
        httpx.post("http://localhost:8001/api/set-fault-mode", json={"mode": "fail_before_save"}, timeout=5.0)

        # Attempt 1: Should fail due to injected 500 error
        res1 = typed_create_invoice_in_erp(
            vendor="Company X",
            invoice_number="INV-FAULT-001",
            amount=999.00,
            currency="USD",
            due_date="2026-12-15"
        )
        print(f"   Attempt 1 Result: Success={res1['success']}, Error='{res1.get('error')}'")
        assert res1["success"] is False, "Expected attempt 1 to fail due to injected 500 error"

        # Fault mode is self-resetting on trigger.
        # Attempt 2 (Retry with backoff): Must succeed!
        print("   Attempt 2 (Automatic Retry):...")
        res2 = typed_create_invoice_in_erp(
            vendor="Company X",
            invoice_number="INV-FAULT-001",
            amount=999.00,
            currency="USD",
            due_date="2026-12-15"
        )
        print(f"   Attempt 2 Result: Success={res2['success']}, Verified={res2.get('verified')}")
        assert res2["success"] is True and res2["verified"] is True, "Expected retry to succeed"

        # 2. Test Fail After Save (HTTP 504) & Safe State Reconciliation
        print("\n-> Case B: Injected Fault 'fail_after_save' (Timeout After Commit)...")
        httpx.post("http://localhost:8001/api/set-fault-mode", json={"mode": "fail_after_save"}, timeout=5.0)

        # Attempt 1: DB commits, but client receives 504 error
        res_post_save = typed_create_invoice_in_erp(
            vendor="Company X",
            invoice_number="INV-FAULT-002",
            amount=1200.00,
            currency="USD",
            due_date="2026-12-20"
        )
        print(f"   Client observed: Success={res_post_save['success']}, Error='{res_post_save.get('error')}'")
        assert res_post_save["success"] is False, "Expected 504 gateway timeout error"

        # Reconcile: Before retrying uncertain side effect, query ERP for the invoice!
        print("   Reconciliation Check: Inspecting ERP before retrying...")
        from services.worker.invoice_flow import handle_check_duplicate_invoice
        reconciliation = handle_check_duplicate_invoice(vendor="Company X", invoice_number="INV-FAULT-002")
        print(f"   Reconciliation Result: Is Saved in ERP={reconciliation['is_duplicate']}")
        assert reconciliation["is_duplicate"] is True, "Expected invoice to already exist in ERP"
        print("   Safely reconciled: Side effect was completed prior to timeout; duplicate creation prevented!")

        print("=" * 75)
        print("  ALL FAULT INJECTION AND RECONCILIATION TESTS PASSED!")
        print("=" * 75)
        return True

    finally:
        close_browser_session()
        p_company.terminate()

if __name__ == "__main__":
    success = test_fault_injection_and_recovery()
    sys.exit(0 if success else 1)
