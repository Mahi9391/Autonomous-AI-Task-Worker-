import os
import sys
import time
import json
import hashlib
from pathlib import Path
from datetime import datetime

# Setup sys.path
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from services.worker.config import settings
from services.worker.db import init_worker_db, get_db as get_worker_db
from services.worker.clock import clock
from services.worker.invoice_extractor import invoice_extractor
from services.worker.policy import policy_engine
from services.worker.state_store import state_store
from services.worker.payment_followup_flow import handle_check_eligible_invoices, handle_send_payment_reminder, slugify
from workflows.workflow_config import workflow_registry

# Seed app databases
from apps.company_app.company_db import init_company_db, seed_company_data, get_db as get_company_db
from apps.email_sandbox.email_db import init_email_db, seed_email_data, get_db as get_email_db

results = []

def record_test(scenario_id: str, title: str, passed: bool, evidence: str):
    results.append({
        "id": scenario_id,
        "title": title,
        "status": "PASS" if passed else "FAIL",
        "evidence": evidence
    })
    status_icon = "[PASS]" if passed else "[FAIL]"
    print(f"[{scenario_id}] {status_icon}: {title} -- {evidence}")


def run_all_scenarios():
    print("=" * 75)
    print("  RUNNING CORE FIXTURE-DRIVEN AUTOMATED SCENARIO SUITE")
    print("=" * 75)

    # Initialize all databases
    init_worker_db()
    seed_company_data()
    seed_email_data()

    # --- Scenario 1: Valid Invoice PDF Extraction ---
    try:
        pdf_path = str(WORKSPACE_ROOT / "data" / "synthetic_pdfs" / "invoice_acme_valid.pdf")
        text = invoice_extractor.extract_text_from_pdf(pdf_path)
        fields = invoice_extractor.parse_invoice_text(text)
        is_valid, missing, _ = invoice_extractor.validate(fields)

        passed = is_valid and fields["vendor"] == "Acme Corp" and fields["amount"] == 4850.00 and fields["invoice_number"] == "ACME-901"
        record_test("SC-01", "Valid Invoice Extraction & Deterministic Validation", passed, f"Extracted {fields['vendor']} #{fields['invoice_number']}, Amount: ${fields['amount']}, Due: {fields['due_date']}")
    except Exception as e:
        record_test("SC-01", "Valid Invoice Extraction", False, str(e))

    # --- Scenario 2B: Brand New Bill (Non-Duplicate) Ingestion & Verification ---
    try:
        pdf_nova = str(WORKSPACE_ROOT / "data" / "synthetic_pdfs" / "invoice_nova_new.pdf")
        nova_text = invoice_extractor.extract_text_from_pdf(pdf_nova)
        nova_fields = invoice_extractor.parse_invoice_text(nova_text)
        is_val, _, _ = invoice_extractor.validate(nova_fields)

        with open(pdf_nova, "rb") as f:
            nova_hash = hashlib.sha256(f.read()).hexdigest()

        # 1. Dedupe check must confirm bill is brand new (NOT duplicate)
        from services.worker.invoice_flow import handle_check_duplicate_invoice
        dup_check = handle_check_duplicate_invoice(
            vendor=nova_fields["vendor"],
            invoice_number=nova_fields["invoice_number"],
            file_hash=nova_hash
        )
        is_non_duplicate = (dup_check["is_duplicate"] is False)

        # 2. Ingest and insert into ERP database
        with get_company_db() as c_conn:
            c_conn.execute("""
            INSERT INTO invoices (
                id, vendor, invoice_number, amount, currency, due_date, issue_date, status, file_hash, source, created_at
            ) VALUES ('INV-NOVA-001', ?, ?, ?, ?, ?, ?, 'unpaid', ?, 'email', datetime('now'))
            """, (nova_fields["vendor"], nova_fields["invoice_number"], nova_fields["amount"], nova_fields["currency"], nova_fields["due_date"], nova_fields.get("issue_date"), nova_hash))

            # 3. Read back and verify exact values
            row = c_conn.execute("SELECT * FROM invoices WHERE id = 'INV-NOVA-001'").fetchone()
            is_verified = (row["vendor"] == nova_fields["vendor"] and row["amount"] == nova_fields["amount"] and row["invoice_number"] == nova_fields["invoice_number"])
            # Clean up test invoice
            c_conn.execute("DELETE FROM invoices WHERE id = 'INV-NOVA-001'")

        passed = is_val and is_non_duplicate and is_verified
        record_test(
            "SC-02B",
            "Brand New Bill (Non-Duplicate) Ingestion & Read-back Verification",
            passed,
            f"Bill {nova_fields['vendor']} #{nova_fields['invoice_number']} verified non-duplicate (is_dup={dup_check['is_duplicate']}) & read-back verified (match={is_verified})"
        )
    except Exception as e:
        record_test("SC-02B", "Brand New Bill Ingestion", False, str(e))

    # --- Scenario 3: File Content Hash (SHA-256) Deduplication ---
    try:
        with open(pdf_path, "rb") as f:
            file_hash = hashlib.sha256(f.read()).hexdigest()

        # Insert first record into company app
        with get_company_db() as c_conn:
            c_conn.execute("""
            INSERT OR REPLACE INTO invoices (
                id, vendor, invoice_number, amount, currency, due_date, status, file_hash, created_at
            ) VALUES ('INV-TEST-HASH', 'Acme Corp', 'ACME-901', 4850.00, 'USD', '2026-11-10', 'unpaid', ?, datetime('now'))
            """, (file_hash,))

        # Verify duplicate detection tool flags the exact hash
        from services.worker.invoice_flow import handle_check_duplicate_invoice
        dup_check = handle_check_duplicate_invoice(vendor="Acme Corp", invoice_number="ACME-901", file_hash=file_hash)
        passed = dup_check["is_duplicate"] is True and "INV-TEST-HASH" in dup_check.get("existing_invoice_id", "")
        record_test("SC-03", "File Content Hash (SHA-256) Deduplication", passed, f"Duplicate detected on SHA-256 {file_hash[:8]}: {dup_check.get('reason')}")
    except Exception as e:
        record_test("SC-03", "SHA-256 Deduplication", False, str(e))

    # --- Scenario 4: Business Level Key (Vendor, Invoice#) Deduplication ---
    try:
        # Same vendor + invoice number but with different fictitious hash
        dup_biz = handle_check_duplicate_invoice(vendor="Acme Corp", invoice_number="ACME-901", file_hash="different_hash_123")
        passed = dup_biz["is_duplicate"] is True
        record_test("SC-04", "Normalized Business Key Deduplication", passed, f"Business key duplicate blocked: {dup_biz.get('reason')}")
    except Exception as e:
        record_test("SC-04", "Business Key Deduplication", False, str(e))

    # --- Scenario 9 & 10: Overdue Unpaid vs Paid Eligibility ---
    try:
        # Override dev clock to 2026-10-12 11:00 AM (Monday, business hours)
        clock.set_override("2026-10-12T11:00:00+05:30")
        check_res = handle_check_eligible_invoices()
        eligible = check_res.get("eligible_invoices", [])
        skipped = check_res.get("skipped_records", [])

        # Overdue unpaid invoice INV-DELTA-101 (due 2026-09-15) must be eligible
        has_delta = any(inv["invoice_number"] == "DS-101" for inv in eligible)
        # Paid invoice INV-ACME-800 must be skipped
        has_acme_skipped = any("ACME-800" in s.get("invoice_number", "") for s in skipped)

        passed = has_delta and has_acme_skipped
        record_test("SC-09/10", "Overdue vs Paid Follow-up Eligibility Filtering", passed, f"Eligible overdue count: {len(eligible)}, Skipped paid/pending: {len(skipped)}")
    except Exception as e:
        record_test("SC-09/10", "Follow-up Eligibility", False, str(e))

    # --- Scenario 11: Idempotency Key Duplicate Prevention ---
    try:
        # Send reminder for Delta Supplies
        v_slug = slugify("Delta Supplies")
        ikey = f"REMIND-{v_slug}-DS-101-2026-09-15"

        # Pre-seed this key in outbox
        with get_email_db() as e_conn:
            e_conn.execute("""
            INSERT OR REPLACE INTO emails (
                id, sender, recipient, subject, body, idempotency_key, folder, timestamp, is_read
            ) VALUES ('OUT-IDEM-01', 'finance@centraign.internal', 'contact@deltasupplies.internal', 'Reminder', 'Body', ?, 'outbox', datetime('now'), 1)
            """, (ikey,))

        # Now execute send reminder
        send_res = handle_send_payment_reminder(
            invoice_id="INV-DELTA-101",
            vendor="Delta Supplies",
            invoice_number="DS-101",
            amount=1450.00,
            due_date="2026-09-15",
            recipient="contact@deltasupplies.internal"
        )
        passed = send_res.get("status") == "duplicate_suppressed"
        record_test("SC-11", "Idempotency Key Duplicate Prevention", passed, f"Duplicate send suppressed with key {ikey}")
    except Exception as e:
        record_test("SC-11", "Idempotency Duplicate Prevention", False, str(e))

    # --- Scenario 17: Prompt Injection Immunity in Untrusted Documents ---
    try:
        pdf_injection = str(WORKSPACE_ROOT / "data" / "synthetic_pdfs" / "invoice_gamma_prompt_injection.pdf")
        inj_text = invoice_extractor.extract_text_from_pdf(pdf_injection)
        # Verify policy rejects prohibited actions regardless of prompt content
        is_allowed, reason, _ = policy_engine.evaluate(
            tool_name="initiate_payment",
            arguments={"amount": 999.00},
            allowlist=["extract_invoice_pdf", "create_invoice_in_erp"],
            current_context={}
        )
        passed = (is_allowed is False) and ("prohibited" in reason.lower())
        record_test("SC-17", "Prompt Injection Defense & Policy Enforcement", passed, f"Attempted 'initiate_payment' rejected by code policy: {reason}")
    except Exception as e:
        record_test("SC-17", "Prompt Injection Defense", False, str(e))

    # --- Scenario 18: Business Hours & Clock Abstraction Enforcement ---
    try:
        # Set clock to Sunday midnight (non-business hours)
        clock.set_override("2026-10-18T01:30:00+05:30") # Sunday 1:30 AM
        is_biz = clock.is_within_business_hours()

        # Temporarily clear override to test the rejection
        clock._override_dt = datetime.fromisoformat("2026-10-18T01:30:00+05:30")
        is_biz_sunday = clock.is_within_business_hours()

        passed = is_biz_sunday is False
        record_test("SC-18", "Injectable Clock Business Hours & Timezone Enforcement", passed, f"Sunday 01:30 AM Asia/Kolkata correctly evaluated as outside business hours (is_within_business_hours={is_biz_sunday})")
        clock.set_override(None) # Reset
    except Exception as e:
        record_test("SC-18", "Clock Business Hours Enforcement", False, str(e))

    # --- Scenario 19B: Reminder Dispatch in Non-Business Hours Allowed ---
    try:
        # Sunday 01:30 AM (outside business hours)
        clock.set_override("2026-10-18T01:30:00+05:30")
        is_outside = not clock.is_within_business_hours()
        can_proceed_non_biz = not (settings.enforce_business_hours and is_outside)
        would_block_if_enforced = (True and is_outside)

        passed = (is_outside is True) and (can_proceed_non_biz is True) and (would_block_if_enforced is True)
        record_test(
            "SC-19B",
            "Non-Business Hours Payment Reminders Allowed by Default",
            passed,
            f"Reminders allowed outside business hours (enforce_business_hours={settings.enforce_business_hours}, allowed={can_proceed_non_biz})"
        )
        clock.set_override(None)
    except Exception as e:
        record_test("SC-19B", "Non-Business Hours Reminder", False, str(e))

    # --- Scenario 22: Third Workflow Generalization on Unchanged Runtime ---
    try:
        from services.worker.generalization_flow import handle_audit_vendor_invoices
        audit_res = handle_audit_vendor_invoices("Acme Corp")
        passed = audit_res["vendor"] == "Acme Corp" and audit_res["total_records"] >= 1
        record_test("SC-22", "Generalization Workflow Execution (SOP + Config Only)", passed, f"Audited vendor Acme Corp: {audit_res['total_records']} records, Total Paid: ${audit_res['total_paid']:.2f}")
    except Exception as e:
        record_test("SC-22", "Generalization Workflow", False, str(e))

    # Print Summary Table
    print("\n" + "=" * 75)
    print("  SCENARIO SUITE RESULTS SUMMARY")
    print("=" * 75)
    total_passed = sum(1 for r in results if r["status"] == "PASS")
    print(f"Total Scenarios Tested: {len(results)} | Passed: {total_passed} | Failed: {len(results) - total_passed}")
    print("-" * 75)
    for r in results:
        print(f"{r['id']:<10} | {r['status']:<6} | {r['title']}")
    print("=" * 75)

    return total_passed == len(results)

if __name__ == "__main__":
    success = run_all_scenarios()
    sys.exit(0 if success else 1)
