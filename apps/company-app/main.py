import os
import sys
import uuid
import time
import hashlib
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = BASE_DIR.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from fastapi import FastAPI, Request, Form, UploadFile, File, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from company_db import get_db, init_company_db, seed_company_data

WORKER_DB_PATH = WORKSPACE_ROOT / "data" / "worker.db"
UPLOADS_DIR = WORKSPACE_ROOT / "data" / "uploads"


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="CentrAlign Simulated Company ERP", version="1.0.0")

@app.on_event("startup")
def on_startup():
    init_company_db()
    seed_company_data()

def get_app_settings():
    with get_db() as conn:
        row = conn.execute("SELECT perturbation_enabled, fault_mode FROM app_settings WHERE id = 1").fetchone()
        if row:
            return bool(row["perturbation_enabled"]), row["fault_mode"]
        return False, "none"

def set_app_settings(perturbation_enabled: Optional[bool] = None, fault_mode: Optional[str] = None):
    with get_db() as conn:
        current_p, current_f = get_app_settings()
        new_p = int(perturbation_enabled if perturbation_enabled is not None else current_p)
        new_f = fault_mode if fault_mode is not None else current_f
        conn.execute("""
        UPDATE app_settings 
        SET perturbation_enabled = ?, fault_mode = ?, updated_at = datetime('now')
        WHERE id = 1
        """, (new_p, new_f))

@app.get("/health")
def health_check():
    return {"status": "ok", "app": "company-app", "port": 8001}

@app.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse(url="/invoices")

@app.get("/invoices", response_class=HTMLResponse)
def list_invoices(request: Request, status_filter: Optional[str] = None, message: Optional[str] = None):
    p_enabled, f_mode = get_app_settings()
    with get_db() as conn:
        if status_filter:
            rows = conn.execute("SELECT * FROM invoices WHERE status = ? ORDER BY created_at DESC", (status_filter,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM invoices ORDER BY created_at DESC").fetchall()
        invoices = [dict(r) for r in rows]

    return templates.TemplateResponse(request=request, name="invoices.html", context={
        "invoices": invoices,
        "perturbation_enabled": p_enabled,
        "fault_mode": f_mode,
        "message": message
    })

@app.get("/invoices/new", response_class=HTMLResponse)
def new_invoice_page(
    request: Request,
    initial_vendor: Optional[str] = None,
    initial_invoice_number: Optional[str] = None,
    initial_amount: Optional[str] = None,
    initial_issue_date: Optional[str] = None,
    initial_due_date: Optional[str] = None,
    error: Optional[str] = None
):
    p_enabled, f_mode = get_app_settings()
    return templates.TemplateResponse(request=request, name="new_invoice.html", context={
        "perturbation_enabled": p_enabled,
        "fault_mode": f_mode,
        "initial_vendor": initial_vendor,
        "initial_invoice_number": initial_invoice_number,
        "initial_amount": initial_amount,
        "initial_issue_date": initial_issue_date,
        "initial_due_date": initial_due_date,
        "error": error
    })

@app.post("/invoices")
def create_invoice(
    request: Request,
    vendor: str = Form(...),
    invoice_number: str = Form(...),
    amount: float = Form(...),
    currency: str = Form("USD"),
    due_date: str = Form(...),
    issue_date: Optional[str] = Form(None),
    source: str = Form("manual"),
    file_hash: Optional[str] = Form(None),
    confirm_accuracy: Optional[str] = Form(None)
):
    p_enabled, f_mode = get_app_settings()

    # Fault Injection 1: Fail Before Save
    if f_mode == "fail_before_save":
        set_app_settings(fault_mode="none") # Reset so next retry passes
        raise HTTPException(status_code=500, detail="Fault Injected: Simulated internal database connection failure before commit")

    # Fault Injection 2: Timeout
    if f_mode == "timeout":
        set_app_settings(fault_mode="none")
        time.sleep(15.0)

    # Normalize fields
    norm_vendor = vendor.strip()
    norm_inv_num = invoice_number.strip()
    record_id = f"INV-{uuid.uuid4().hex[:8].upper()}"

    try:
        with get_db() as conn:
            # Check business level duplicate: (vendor, invoice_number)
            existing = conn.execute(
                "SELECT id FROM invoices WHERE LOWER(vendor) = LOWER(?) AND LOWER(invoice_number) = LOWER(?)",
                (norm_vendor, norm_inv_num)
            ).fetchone()
            if existing:
                raise HTTPException(
                    status_code=409,
                    detail=f"Duplicate invoice detected: Vendor '{norm_vendor}' already has invoice '{norm_inv_num}' (ID: {existing['id']})"
                )

            # Insert invoice
            conn.execute("""
            INSERT INTO invoices (
                id, vendor, invoice_number, amount, currency, issue_date, due_date, status, file_hash, source, created_at, reminder_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unpaid', ?, ?, datetime('now'), 0)
            """, (record_id, norm_vendor, norm_inv_num, amount, currency, issue_date, due_date, file_hash, source))

    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"Duplicate invoice: {norm_vendor} #{norm_inv_num} already exists.")

    # Fault Injection 3: Fail After Save
    if f_mode == "fail_after_save":
        set_app_settings(fault_mode="none")
        raise HTTPException(status_code=504, detail="Fault Injected: Gateway timeout after invoice persisted to database")

    # Check request accept header
    if "application/json" in request.headers.get("accept", ""):
        return {"success": True, "invoice_id": record_id, "vendor": norm_vendor, "invoice_number": norm_inv_num}

    return RedirectResponse(url=f"/invoices/{record_id}", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def get_invoice_detail(request: Request, invoice_id: str):
    p_enabled, f_mode = get_app_settings()
    with get_db() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Invoice record not found")
        invoice = dict(row)

    return templates.TemplateResponse(request=request, name="invoice_detail.html", context={
        "invoice": invoice,
        "perturbation_enabled": p_enabled,
        "fault_mode": f_mode
    })

@app.get("/vendors", response_class=HTMLResponse)
def list_vendors(request: Request):
    p_enabled, f_mode = get_app_settings()
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM vendors ORDER BY name ASC").fetchall()
        vendors = [dict(r) for r in rows]

    return templates.TemplateResponse(request=request, name="vendors.html", context={
        "vendors": vendors,
        "perturbation_enabled": p_enabled,
        "fault_mode": f_mode
    })

@app.get("/upload-correction", response_class=HTMLResponse)
def upload_correction_page(request: Request, token: Optional[str] = None):
    p_enabled, f_mode = get_app_settings()
    if not token:
        return templates.TemplateResponse(request=request, name="upload_correction.html", context={
            "is_valid_token": False,
            "error_message": "Missing required upload security token in link.",
            "perturbation_enabled": p_enabled,
            "fault_mode": f_mode
        })

    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Query worker DB upload_tokens table
    try:
        w_conn = sqlite3.connect(WORKER_DB_PATH)
        w_conn.row_factory = sqlite3.Row
        try:
            t_row = w_conn.execute(
                "SELECT * FROM upload_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if not t_row:
                return templates.TemplateResponse(request=request, name="upload_correction.html", context={
                    "is_valid_token": False,
                    "error_message": "Security token not found or invalid.",
                    "perturbation_enabled": p_enabled,
                    "fault_mode": f_mode
                })
            if t_row["is_used"] == 1:
                return templates.TemplateResponse(request=request, name="upload_correction.html", context={
                    "is_valid_token": False,
                    "error_message": "This single-use upload link has already been utilized.",
                    "perturbation_enabled": p_enabled,
                    "fault_mode": f_mode
                })
            # Check expiry
            expires_at = datetime.fromisoformat(t_row["expires_at"])
            if datetime.now(expires_at.tzinfo) > expires_at:
                return templates.TemplateResponse(request=request, name="upload_correction.html", context={
                    "is_valid_token": False,
                    "error_message": "This upload link has expired.",
                    "perturbation_enabled": p_enabled,
                    "fault_mode": f_mode
                })

            invoice_ref = t_row["invoice_ref"]
            vendor_contact = t_row["vendor_contact"]
        finally:
            w_conn.close()
    except Exception as e:
        return templates.TemplateResponse(request=request, name="upload_correction.html", context={
            "is_valid_token": False,
            "error_message": f"Error validating token: {str(e)}",
            "perturbation_enabled": p_enabled,
            "fault_mode": f_mode
        })

    return templates.TemplateResponse(request=request, name="upload_correction.html", context={
        "is_valid_token": True,
        "token": token,
        "invoice_ref": invoice_ref,
        "vendor_contact": vendor_contact,
        "perturbation_enabled": p_enabled,
        "fault_mode": f_mode
    })

@app.post("/upload-correction")
async def handle_upload_correction(
    token: str = Form(...),
    pdf_file: UploadFile = File(...)
):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()

    # Validate file type
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Invalid file type. Only PDF documents are permitted.")

    content = await pdf_file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds maximum limit of 10MB.")

    w_conn = sqlite3.connect(WORKER_DB_PATH)
    w_conn.row_factory = sqlite3.Row
    try:
        t_row = w_conn.execute(
            "SELECT * FROM upload_tokens WHERE token_hash = ? AND is_used = 0", (token_hash,)
        ).fetchone()
        if not t_row:
            raise HTTPException(status_code=403, detail="Invalid, expired, or already-used token.")

        task_id = t_row["task_id"]
        invoice_ref = t_row["invoice_ref"]

        # Store file with provenance
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        save_filename = f"corrected_{invoice_ref}_{uuid.uuid4().hex[:6]}.pdf"
        save_path = UPLOADS_DIR / save_filename
        with open(save_path, "wb") as f:
            f.write(content)

        # Mark token as used
        w_conn.execute("UPDATE upload_tokens SET is_used = 1 WHERE token_hash = ?", (token_hash,))

        # Update task context with the uploaded corrected file path
        t_task = w_conn.execute("SELECT context FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if t_task:
            import json
            ctx = json.loads(t_task["context"] or "{}")
            ctx["corrected_file_path"] = str(save_path)
            ctx["correction_uploaded_at"] = datetime.now().isoformat()
            w_conn.execute("""
            UPDATE tasks 
            SET status = 'active', context = ?, updated_at = datetime('now')
            WHERE id = ?
            """, (json.dumps(ctx), task_id))
        w_conn.commit()
    finally:
        w_conn.close()

    return RedirectResponse(
        url=f"/invoices?message=Corrected+document+received+successfully.+Task+{task_id}+has+been+resumed.",
        status_code=status.HTTP_303_SEE_OTHER
    )

# --- Dev and Settings Control APIs ---

class PerturbationRequest(BaseModel):
    enabled: bool

class FaultModeRequest(BaseModel):
    mode: str

@app.post("/api/toggle-perturbation")
def toggle_perturbation_api(req: PerturbationRequest):
    set_app_settings(perturbation_enabled=req.enabled)
    return {"status": "ok", "perturbation_enabled": req.enabled}

@app.post("/api/set-fault-mode")
def set_fault_mode_api(req: FaultModeRequest):
    set_app_settings(fault_mode=req.mode)
    return {"status": "ok", "fault_mode": req.mode}

@app.post("/api/reset-data")
def reset_data_api():
    seed_company_data()
    return {"status": "ok", "message": "Database reset to seed state"}

# --- JSON Read APIs for Worker & Dashboard ---

@app.get("/api/invoices")
def api_get_invoices():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM invoices ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

@app.get("/api/invoices/{invoice_id}")
def api_get_invoice(invoice_id: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM invoices WHERE id = ?", (invoice_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Invoice not found")
        return dict(row)

@app.get("/api/vendors")
def api_get_vendors():
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM vendors ORDER BY name ASC").fetchall()
        return [dict(r) for r in rows]
