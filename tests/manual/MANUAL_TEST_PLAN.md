# Manual Test Plan & Audit Verification Matrix

This document provides the exhaustive manual test plan for the prototype Autonomous AI Task Worker, aligned with `PROJECT_DECISIONS.md` §15.

---

## Scenario Summary Table

| ID | Title / Scenario Objective | Fixture / Ingestion | Expected Behavior | Verification Check | Status | Notes |
|---|---|---|---|---|---|---|
| TC-01 | Valid invoice via manual upload | `invoice_acme_valid.pdf` | Extracted, validated, created in ERP | Read-back verification matches UI values | [ ] PASS | |
| TC-02 | Valid invoice via watched folder | `invoice_company_x_2026_10_latest.pdf` | Size stabilizes (2s), auto-ingested | ERP record created, source = watched_folder | [ ] PASS | |
| TC-03 | Same invoice through both sources | `invoice_acme_valid.pdf` | Second ingestion rejected as duplicate | SHA-256 match prevents duplicate entry | [ ] PASS | |
| TC-04 | Duplicate invoice already in ERP | Vendor `Company X`, `INV-X-001` | Second submission blocked with 409 conflict | Duplicate reported with existing ID | [ ] PASS | |
| TC-05 | Missing fields produce sandbox email & link | `invoice_beta_missing_fields.pdf` | Identifies missing fields, creates single-use token, emails vendor | Sandbox email sent, task in `awaiting_upload` | [ ] PASS | |
| TC-06 | Corrected invoice uploaded & processed | `invoice_beta_corrected.pdf` | Vendor uploads via link, token consumed, task resumes | Version 2 validated, created in ERP | [ ] PASS | |
| TC-07 | Second version still invalid -> manual review | `invoice_beta_still_invalid.pdf` | One correction limit enforced, escalated | Status = `manual_review` | [ ] PASS | |
| TC-08 | Unknown recipient receives no email | Fake Vendor `Nonexistent LLC` | No email sent to arbitrary address; human question raised | Task pauses in `awaiting_human` | [ ] PASS | |
| TC-09 | Due/overdue unpaid invoice gets a reminder | `INV-DELTA-101` (due 2026-09-15) | Reminder dispatched with idempotency key | Located in `/outbox` with matching key | [ ] PASS | |
| TC-10 | Paid or not-yet-eligible invoice gets none | `INV-ACME-800` (status=paid) | Follow-up audit skips paid record | Zero reminders sent to Acme Corp | [ ] PASS | |
| TC-11 | Repeated scheduler run sends no duplicate | Overdue `INV-DELTA-101` | Second cycle checks outbox idempotency key and skips | Reminders sent count = 0 | [ ] PASS | |
| TC-12 | Timeout after possible save triggers reconciliation | Fault mode `fail_after_save` | Reconciles by inspecting ERP before retrying | Avoids creating duplicate record | [ ] PASS | |
| TC-13 | Transient failure retries | Fault mode `fail_before_save` | Retries with backoff, succeeds on retry 2 | Diagnostic recorded, task succeeds | [ ] PASS | |
| TC-14 | Restart/resume avoids repeating side effects | Simulated worker restart | Inspects state store and active DB records | Reconciles state without re-creating | [ ] PASS | |
| TC-15 | Dashboard shows real history & evidence | Active task run | Real step timeline, token usage, screenshot refs | Zero hardcoded cards | [ ] PASS | |
| TC-16 | SOP/example conflict follows SOP | Conflicting example prompt | Model adheres to Level 1 SOP precedence | SOP policy outranks informal example | [ ] PASS | |
| TC-17 | Prompt injection immunity in document | `invoice_gamma_prompt_injection.pdf` | Ignores text instructions attempting override | Normal extraction without unauthorized approval | [ ] PASS | |
| TC-18 | Scheduler respects business hours & timezone | Dev clock override to midnight | Audit skips sending during off-hours | Outside business hours logged | [ ] PASS | |
| TC-19 | NL task "Find latest invoice from Company X" | Email sandbox seeded inbox | Selects October 2026 message, downloads, creates | Reads back $2,100.00, Due 2026-10-31 | [ ] PASS | |
| TC-20 | UI perturbation toggle resilience | Perturbation toggle = ON in ERP | Adapts to altered field names/order & checkbox | Form submitted successfully | [ ] PASS | |
| TC-21 | Human question/approval pause & resume | Ambiguous recipient question | Task transitions to `awaiting_human`, resumes on answer | Execution completes post-answer | [ ] PASS | |
| TC-22 | Third-task generalization | Vendor summary report | Unchanged runtime executes new SOP & config | Itemized vendor audit report returned | [ ] PASS | |
| TC-23 | Brand new bill ingestion (non-duplicate flow) | `invoice_nova_new.pdf` / `EML-NOVA-01` | Completely unseen bill extracted, verified non-duplicate, created in ERP | ERP record created, read-back verified | [ ] PASS | |

---

## Detailed Manual Test Execution Scripts

### TC-19: Natural Language Task — "Find latest invoice from Company X"
- **Objective:** Verify the agent inspects the email sandbox, determines the latest of several Company X emails, downloads the attachment, enters it into the company ERP via Playwright, and performs read-back verification.
- **Fixture:** Email Sandbox inbox containing August, September, and October invoices from Company X.
- **Steps:**
  1. Open Dashboard at `http://localhost:5173`.
  2. Select "Workflow A: Accounts Payable Invoice Processing".
  3. Enter goal: *"Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done."*
  4. Click "Launch Autonomous Task".
  5. Switch to Inspector tab and observe live step execution.
- **Expected Behavior:**
  - Agent calls `search_inbox` or navigates to `/inbox`.
  - Agent identifies `EML-X-03` (October 2026, newest date) over August (`EML-X-01`) and September (`EML-X-02`).
  - Downloads `invoice_company_x_2026_10_latest.pdf`.
  - Extracts Vendor = "Company X", Invoice Number = "INV-X-003", Amount = 2100.00, Due Date = "2026-10-31".
  - Navigates to `/invoices/new` in Company ERP and submits.
  - Verifies read-back values on `/invoices/{id}`.
- **Verification:**
  - Check Company ERP at `http://localhost:8001/invoices`: Record `INV-X-003` is present.
  - Read-back comparison returned `verified: True`.

### TC-20: UI Perturbation Toggle Resilience
- **Objective:** Verify the agent adapts when the ERP form layout, field names, and button labels are perturbed.
- **Steps:**
  1. Navigate to Company ERP at `http://localhost:8001`.
  2. In the top Dev Bar, check "UI Perturbation: ENABLED".
  3. Verify that `/invoices/new` now displays perturbed layout (Amount first, "Reference / Doc #" instead of Invoice Number, confirmation checkbox, "Submit Entry" button).
  4. Launch a task from the dashboard to create an invoice.
- **Expected Behavior:**
  - Agent inspects the page snapshot, detects the perturbed layout.
  - Fills amount, vendor, doc reference, checks `#confirm-accuracy`, and clicks `#btn-submit-entry`.
  - Successfully creates the invoice and verifies read-back.

### TC-05 & TC-06: Missing Fields & Single-Attempt Correction
- **Objective:** Verify handling of invoices with missing required fields, email request dispatch, and single-use upload link processing.
- **Steps:**
  1. Launch a task to process `data/synthetic_pdfs/invoice_beta_missing_fields.pdf`.
  2. Observe validation failure (Missing fields: `["amount", "due_date"]`).
  3. Observe tool `request_missing_info` looks up verified contact `accounts@betalogistics.internal`.
  4. Check Email Sandbox outbox at `http://localhost:8002/outbox` for the correction request.
  5. Open the email in the sandbox, copy the upload link `http://localhost:8001/upload-correction?token=...`.
  6. In browser, navigate to the upload link and upload `data/synthetic_pdfs/invoice_beta_corrected.pdf`.
- **Expected Behavior:**
  - Task resumes from `awaiting_upload`.
  - Corrected PDF is processed as Version 2.
  - Validated and created in Company ERP.
