import os
from typing import Dict, Any, List
import httpx

from .tool_registry import tool_registry, ToolDefinition

COMPANY_API_URL = os.getenv("COMPANY_APP_BASE_URL", "http://localhost:8001")

def handle_lookup_vendor(vendor: str) -> Dict[str, Any]:
    try:
        r = httpx.get(f"{COMPANY_API_URL}/api/vendors", timeout=5.0)
        vendors = r.json()
    except Exception:
        from apps.company_app.company_db import get_db
        with get_db() as c_conn:
            vendors = [dict(r) for r in c_conn.execute("SELECT * FROM vendors").fetchall()]

    for v in vendors:
        if v["name"].strip().lower() == vendor.strip().lower():
            return {"found": True, "vendor": v}
    return {"found": False, "vendor": vendor}

def handle_audit_vendor_invoices(vendor: str) -> Dict[str, Any]:
    try:
        r = httpx.get(f"{COMPANY_API_URL}/api/invoices", timeout=5.0)
        invoices = r.json()
    except Exception:
        from apps.company_app.company_db import get_db
        with get_db() as c_conn:
            invoices = [dict(r) for r in c_conn.execute("SELECT * FROM invoices").fetchall()]

    norm_v = vendor.strip().lower()
    matched = [inv for inv in invoices if inv["vendor"].strip().lower() == norm_v]

    total_outstanding = sum(inv["amount"] for inv in matched if inv["status"] in ["unpaid", "overdue"])
    total_paid = sum(inv["amount"] for inv in matched if inv["status"] == "paid")

    return {
        "vendor": vendor,
        "total_records": len(matched),
        "total_outstanding": total_outstanding,
        "total_paid": total_paid,
        "invoices": matched
    }

def register_generalization_tools():
    tool_registry.register(ToolDefinition(
        name="lookup_vendor",
        description="Looks up a vendor in the certified directory to verify registration and terms.",
        parameters={"type": "object", "properties": {"vendor": {"type": "string"}}, "required": ["vendor"]},
        handler=handle_lookup_vendor
    ))

    tool_registry.register(ToolDefinition(
        name="audit_vendor_invoices",
        description="Retrieves and audits all invoices for a specific vendor from the ERP register.",
        parameters={"type": "object", "properties": {"vendor": {"type": "string"}}, "required": ["vendor"]},
        handler=handle_audit_vendor_invoices
    ))

register_generalization_tools()
