import os
import sys
import uuid
import time
import json
from pathlib import Path
from typing import Optional, List

BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = BASE_DIR.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from fastapi import FastAPI, Request, Form, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from email_db import get_db, init_email_db, seed_email_data, PDF_DIR
UPLOADS_DIR = WORKSPACE_ROOT / "data" / "uploads"


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="centrAlign Email Sandbox", version="1.0.0")

@app.on_event("startup")
def on_startup():
    init_email_db()
    seed_email_data()

def get_sandbox_settings():
    with get_db() as conn:
        row = conn.execute("SELECT fault_mode FROM sandbox_settings WHERE id = 1").fetchone()
        if row:
            return row["fault_mode"]
        return "none"

def set_sandbox_settings(fault_mode: str):
    with get_db() as conn:
        conn.execute("UPDATE sandbox_settings SET fault_mode = ?, updated_at = datetime('now') WHERE id = 1", (fault_mode,))

def get_folder_counts():
    with get_db() as conn:
        inbox_c = conn.execute("SELECT COUNT(*) as c FROM emails WHERE folder = 'inbox'").fetchone()["c"]
        outbox_c = conn.execute("SELECT COUNT(*) as c FROM emails WHERE folder = 'outbox'").fetchone()["c"]
        return inbox_c, outbox_c

@app.get("/health")
def health_check():
    return {"status": "ok", "app": "email-sandbox", "port": 8002}

@app.get("/", response_class=HTMLResponse)
def index():
    return RedirectResponse(url="/inbox")

@app.get("/inbox", response_class=HTMLResponse)
def list_inbox(request: Request, q: Optional[str] = None):
    f_mode = get_sandbox_settings()
    inbox_c, outbox_c = get_folder_counts()

    with get_db() as conn:
        if q:
            query_str = f"%{q.lower()}%"
            rows = conn.execute("""
            SELECT * FROM emails 
            WHERE folder = 'inbox' AND (LOWER(sender) LIKE ? OR LOWER(subject) LIKE ? OR LOWER(body) LIKE ?)
            ORDER BY timestamp DESC
            """, (query_str, query_str, query_str)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM emails WHERE folder = 'inbox' ORDER BY timestamp DESC").fetchall()

        emails = []
        for r in rows:
            em = dict(r)
            try:
                em["attachments_list"] = json.loads(em["attachments"] or "[]")
            except Exception:
                em["attachments_list"] = []
            emails.append(em)

    return templates.TemplateResponse(request=request, name="inbox.html", context={
        "emails": emails,
        "search_query": q,
        "active_folder": "inbox",
        "inbox_count": inbox_c,
        "outbox_count": outbox_c,
        "fault_mode": f_mode
    })

@app.get("/outbox", response_class=HTMLResponse)
def list_outbox(request: Request):
    f_mode = get_sandbox_settings()
    inbox_c, outbox_c = get_folder_counts()

    with get_db() as conn:
        rows = conn.execute("SELECT * FROM emails WHERE folder = 'outbox' ORDER BY timestamp DESC").fetchall()
        emails = [dict(r) for r in rows]

    return templates.TemplateResponse(request=request, name="outbox.html", context={
        "emails": emails,
        "active_folder": "outbox",
        "inbox_count": inbox_c,
        "outbox_count": outbox_c,
        "fault_mode": f_mode
    })

@app.get("/email/{email_id}", response_class=HTMLResponse)
def get_email_detail(request: Request, email_id: str):
    f_mode = get_sandbox_settings()
    inbox_c, outbox_c = get_folder_counts()

    with get_db() as conn:
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Email not found")
        email = dict(row)
        try:
            attachments = json.loads(email["attachments"] or "[]")
        except Exception:
            attachments = []

    return templates.TemplateResponse(request=request, name="email_detail.html", context={
        "email": email,
        "attachments": attachments,
        "active_folder": email["folder"],
        "inbox_count": inbox_c,
        "outbox_count": outbox_c,
        "fault_mode": f_mode
    })

@app.get("/attachments/{filename}")
def download_attachment(filename: str):
    # Security check: prevent path traversal
    safe_name = Path(filename).name
    file_path = PDF_DIR / safe_name
    if not file_path.exists():
        # Check in uploads dir
        alt_path = UPLOADS_DIR / safe_name
        if alt_path.exists():
            file_path = alt_path
        else:
            raise HTTPException(status_code=404, detail=f"Attachment file '{safe_name}' not found")

    return FileResponse(
        path=str(file_path),
        filename=safe_name,
        media_type="application/pdf"
    )

@app.get("/compose", response_class=HTMLResponse)
def compose_page(request: Request):
    f_mode = get_sandbox_settings()
    inbox_c, outbox_c = get_folder_counts()

    return templates.TemplateResponse(request=request, name="compose.html", context={
        "active_folder": "compose",
        "inbox_count": inbox_c,
        "outbox_count": outbox_c,
        "fault_mode": f_mode
    })

@app.post("/send")
def send_email(
    request: Request,
    recipient: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    idempotency_key: Optional[str] = Form(None)
):
    f_mode = get_sandbox_settings()

    # Fault Injection 1: Fail Before Send
    if f_mode == "fail_before_send":
        set_sandbox_settings("none")
        raise HTTPException(status_code=500, detail="Fault Injected: Sandbox mail dispatch failed before storage")

    # Fault Injection 2: Timeout
    if f_mode == "timeout":
        set_sandbox_settings("none")
        time.sleep(15.0)

    email_id = f"OUT-{uuid.uuid4().hex[:8].upper()}"

    with get_db() as conn:
        # Check idempotency: if an email with this idempotency_key was already sent, don't duplicate
        if idempotency_key:
            existing = conn.execute("SELECT id FROM emails WHERE folder = 'outbox' AND idempotency_key = ?", (idempotency_key,)).fetchone()
            if existing:
                if "application/json" in request.headers.get("accept", ""):
                    return {"success": True, "email_id": existing["id"], "status": "duplicate_idempotent_skipped"}
                return RedirectResponse(url=f"/email/{existing['id']}", status_code=status.HTTP_303_SEE_OTHER)

        conn.execute("""
        INSERT INTO emails (
            id, sender, recipient, subject, body, attachments, idempotency_key, folder, timestamp, is_read
        ) VALUES (?, 'finance@centraign.internal', ?, ?, ?, '[]', ?, 'outbox', datetime('now'), 1)
        """, (email_id, recipient.strip(), subject.strip(), body.strip(), idempotency_key))

    # Fault Injection 3: Fail After Send
    if f_mode == "fail_after_send":
        set_sandbox_settings("none")
        raise HTTPException(status_code=504, detail="Fault Injected: Gateway timeout after email was dispatched and saved in outbox")

    if "application/json" in request.headers.get("accept", ""):
        return {"success": True, "email_id": email_id, "idempotency_key": idempotency_key}

    return RedirectResponse(url=f"/email/{email_id}", status_code=status.HTTP_303_SEE_OTHER)

# --- APIs for reconciliation and search ---

@app.get("/api/search")
def api_search_emails(q: str):
    query_str = f"%{q.lower()}%"
    with get_db() as conn:
        rows = conn.execute("""
        SELECT * FROM emails 
        WHERE LOWER(sender) LIKE ? OR LOWER(recipient) LIKE ? OR LOWER(subject) LIKE ? OR LOWER(body) LIKE ? OR idempotency_key LIKE ?
        ORDER BY timestamp DESC
        """, (query_str, query_str, query_str, query_str, query_str)).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/check-idempotency/{idempotency_key}")
def check_idempotency(idempotency_key: str):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM emails WHERE idempotency_key = ? AND folder = 'outbox'", (idempotency_key,)).fetchone()
        if row:
            return {"exists": True, "email": dict(row)}
        return {"exists": False}

class EmailFaultRequest(BaseModel):
    mode: str

@app.post("/api/set-fault-mode")
def api_set_fault_mode(req: EmailFaultRequest):
    set_sandbox_settings(req.mode)
    return {"status": "ok", "fault_mode": req.mode}

@app.post("/api/reset-data")
def api_reset_data():
    seed_email_data()
    return {"status": "ok", "message": "Email sandbox reset to seed state"}
