from typing import Dict, Any, List, Optional
import math

class VerificationResult:
    def __init__(self, verified: bool, check_name: str, expected: Any, actual: Any, details: str = ""):
        self.verified = verified
        self.check_name = check_name
        self.expected = expected
        self.actual = actual
        self.details = details

    def to_dict(self) -> Dict[str, Any]:
        return {
            "verified": self.verified,
            "check_name": self.check_name,
            "expected": self.expected,
            "actual": self.actual,
            "details": self.details
        }

def verify_invoice_read_back(expected: Dict[str, Any], actual: Dict[str, Any]) -> VerificationResult:
    """
    Independently verifies that the invoice created in the ERP matches
    the extracted document values by comparing read-back DOM elements.
    """
    mismatches = []

    # 1. Vendor
    exp_vendor = str(expected.get("vendor", "")).strip().lower()
    act_vendor = str(actual.get("vendor", "")).strip().lower()
    if exp_vendor != act_vendor:
        mismatches.append(f"Vendor mismatch: expected '{exp_vendor}', got '{act_vendor}'")

    # 2. Invoice Number
    exp_num = str(expected.get("invoice_number", "")).strip().lower()
    act_num = str(actual.get("invoice_number", "")).strip().lower()
    if exp_num != act_num:
        mismatches.append(f"Invoice number mismatch: expected '{exp_num}', got '{act_num}'")

    # 3. Amount
    try:
        exp_amount = float(expected.get("amount", 0.0))
        act_amount = float(str(actual.get("amount", "0")).replace("$", "").replace(",", "").strip())
        if not math.isclose(exp_amount, act_amount, abs_tol=0.01):
            mismatches.append(f"Amount mismatch: expected {exp_amount:.2f}, got {act_amount:.2f}")
    except Exception as e:
        mismatches.append(f"Amount parsing failed: {str(e)}")

    # 4. Due Date
    exp_due = str(expected.get("due_date", "")).strip()
    act_due = str(actual.get("due_date", "")).strip()
    if exp_due != act_due:
        mismatches.append(f"Due date mismatch: expected '{exp_due}', got '{act_due}'")

    if not mismatches:
        return VerificationResult(
            verified=True,
            check_name="invoice_read_back_comparison",
            expected=expected,
            actual=actual,
            details="All invoice fields matched read-back UI elements perfectly."
        )
    else:
        return VerificationResult(
            verified=False,
            check_name="invoice_read_back_comparison",
            expected=expected,
            actual=actual,
            details="; ".join(mismatches)
        )

def verify_email_in_outbox(idempotency_key: str, outbox_emails: List[Dict[str, Any]]) -> VerificationResult:
    """
    Verifies that an outbound payment reminder or missing-field email exists
    in the email sandbox outbox matching the unique idempotency key.
    """
    for em in outbox_emails:
        if em.get("idempotency_key") == idempotency_key:
            return VerificationResult(
                verified=True,
                check_name="email_sandbox_outbox_confirmation",
                expected={"idempotency_key": idempotency_key},
                actual={"idempotency_key": em.get("idempotency_key"), "recipient": em.get("recipient"), "email_id": em.get("id")},
                details=f"Email successfully located in sandbox outbox with ID {em.get('id')}."
            )

    return VerificationResult(
        verified=False,
        check_name="email_sandbox_outbox_confirmation",
        expected={"idempotency_key": idempotency_key},
        actual=None,
        details=f"No email with idempotency key '{idempotency_key}' found in outbox."
    )
