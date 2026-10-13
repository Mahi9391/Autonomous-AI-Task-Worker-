import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel

WORKFLOWS_DIR = Path(__file__).resolve().parent
SOPS_DIR = Path(__file__).resolve().parent.parent / "knowledge" / "sops"

class WorkflowConfig(BaseModel):
    id: str
    name: str
    description: str
    sop_file: str
    allowed_tools: List[str]
    success_criteria: str

    def load_sop_text(self) -> str:
        sop_path = SOPS_DIR / self.sop_file
        if sop_path.exists():
            return sop_path.read_text(encoding="utf-8")
        return ""

class WorkflowRegistry:
    def __init__(self):
        self._configs: Dict[str, WorkflowConfig] = {}
        self._init_defaults()

    def _init_defaults(self):
        # 1. Invoice Processing Workflow
        self.register(WorkflowConfig(
            id="invoice_processing",
            name="AP Invoice Ingestion & Processing",
            description="Searches email inbox, downloads attached PDF, extracts fields, checks duplicates, enters into ERP via Playwright, and handles missing fields.",
            sop_file="invoice_processing.md",
            allowed_tools=[
                "search_inbox",
                "open_email_and_download_invoice",
                "extract_invoice_pdf",
                "validate_invoice_data",
                "check_duplicate_invoice",
                "create_invoice_in_erp",
                "request_missing_info",
                "ask_human_question",
                "browser_navigate",
                "browser_click",
                "browser_fill",
                "browser_get_page_snapshot",
                "complete_task"
            ],
            success_criteria="Invoice record created in ERP and verified by 100% read-back DOM comparison."
        ))

        # 2. Scheduled Payment Follow-up Workflow
        self.register(WorkflowConfig(
            id="scheduled_payment_followup",
            name="Scheduled Payment Follow-up",
            description="Audits overdue invoices, checks business hours and eligibility, constructs idempotency key, and dispatches reminders to verified vendor contacts.",
            sop_file="scheduled_payment_followup.md",
            allowed_tools=[
                "check_eligible_invoices",
                "send_payment_reminder",
                "verify_reminder_sent",
                "ask_human_question",
                "complete_task"
            ],
            success_criteria="Reminders dispatched with idempotency keys and independently confirmed in sandbox outbox."
        ))

        # 3. Third Task Generalization: Vendor Summary Audit Report
        self.register(WorkflowConfig(
            id="vendor_summary_report",
            name="Vendor Balance & Audit Report",
            description="Searches vendor directory and invoice register to compile an authoritative balance report for a specified vendor entity.",
            sop_file="vendor_summary_report.md",
            allowed_tools=[
                "lookup_vendor",
                "audit_vendor_invoices",
                "browser_navigate",
                "browser_get_page_snapshot",
                "complete_task"
            ],
            success_criteria="Structured audit report generated from verified ERP register entries."
        ))

    def register(self, config: WorkflowConfig):
        self._configs[config.id] = config

    def get(self, workflow_id: str) -> Optional[WorkflowConfig]:
        return self._configs.get(workflow_id)

    def list_all(self) -> List[WorkflowConfig]:
        return list(self._configs.values())

workflow_registry = WorkflowRegistry()
