import os
import sys
import uuid
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

# Setup sys.path for worker service
BASE_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = BASE_DIR.parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .config import settings
from .db import init_worker_db
from .clock import clock
from .state_store import state_store
from .agent_loop import agent_loop
from .scheduler import scheduler
from .folder_watcher import folder_watcher
from workflows.workflow_config import workflow_registry

# Import flow registrations
import services.worker.invoice_flow
import services.worker.payment_followup_flow
import services.worker.generalization_flow

app = FastAPI(title="centrAlign Autonomous Task Worker API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    init_worker_db()
    folder_watcher.start()
    scheduler.start()

@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "app": "worker",
        "port": settings.worker_port,
        "clock_time": clock.iso_now(),
        "is_business_hours": clock.is_within_business_hours(),
        "clock_override": clock.is_override_active(),
        "gemini_model": settings.gemini_model,
        "gemini_key_configured": bool(settings.gemini_api_key)
    }

# --- Task Management APIs ---

class CreateTaskRequest(BaseModel):
    goal: str
    workflow_id: Optional[str] = "invoice_processing"
    context: Optional[Dict[str, Any]] = None

@app.get("/api/tasks")
def list_tasks():
    return state_store.list_tasks(limit=50)

@app.delete("/api/tasks")
def delete_all_tasks():
    from .db import get_db
    with get_db() as conn:
        conn.execute("DELETE FROM human_questions")
        conn.execute("DELETE FROM steps")
        conn.execute("DELETE FROM upload_tokens")
        conn.execute("DELETE FROM tasks")
    return {"status": "ok", "message": "All execution tasks and history deleted"}

@app.delete("/api/tasks/{task_id}")
def delete_single_task(task_id: str):
    from .db import get_db
    with get_db() as conn:
        conn.execute("DELETE FROM human_questions WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM steps WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM upload_tokens WHERE task_id = ?", (task_id,))
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    return {"status": "ok", "message": f"Task {task_id} deleted"}

@app.post("/api/tasks")
def create_task(req: CreateTaskRequest, background_tasks: BackgroundTasks):
    task_id = state_store.create_task(
        goal=req.goal,
        workflow_id=req.workflow_id or "invoice_processing",
        context=req.context or {}
    )

    # Launch task in background thread
    background_tasks.add_task(agent_loop.run_task, task_id)

    return {"status": "queued", "task_id": task_id}

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    task = state_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    steps = state_store.get_task_steps(task_id)
    task["steps"] = steps
    return task

@app.post("/api/tasks/{task_id}/resume")
def resume_task(task_id: str, background_tasks: BackgroundTasks):
    task = state_store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    background_tasks.add_task(agent_loop.run_task, task_id)
    return {"status": "resumed", "task_id": task_id}

# --- Human In The Loop APIs ---

class AnswerQuestionRequest(BaseModel):
    answer: str

@app.get("/api/questions")
def list_questions(task_id: Optional[str] = None):
    return state_store.get_pending_questions(task_id=task_id)

@app.post("/api/questions/{question_id}/answer")
def answer_question(question_id: str, req: AnswerQuestionRequest, background_tasks: BackgroundTasks):
    # Lookup question to find associated task
    from .db import get_db
    task_id = None
    with get_db() as conn:
        q_row = conn.execute("SELECT task_id FROM human_questions WHERE id = ?", (question_id,)).fetchone()
        if q_row:
            task_id = q_row["task_id"]

    success = state_store.answer_human_question(question_id, req.answer)
    if not success:
        raise HTTPException(status_code=404, detail="Question not found or already answered")

    if task_id:
        background_tasks.add_task(agent_loop.run_task, task_id)

    return {"status": "answered", "question_id": question_id, "task_resumed": task_id}

# --- Scheduler APIs ---

@app.get("/api/scheduler/runs")
def list_scheduler_runs():
    from .db import get_db
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM scheduler_runs ORDER BY started_at DESC LIMIT 30").fetchall()
        runs = []
        for r in rows:
            item = dict(r)
            import json
            item["details"] = json.loads(item["details"] or "{}")
            runs.append(item)
        return runs

@app.post("/api/scheduler/run-now")
def trigger_scheduler_run():
    result = scheduler.run_cycle(run_type="manual_run_now")
    return result

class SchedulerToggleRequest(BaseModel):
    enabled: bool

@app.post("/api/scheduler/toggle")
def toggle_scheduler(req: SchedulerToggleRequest):
    scheduler.is_enabled = req.enabled
    return {"status": "ok", "scheduler_enabled": req.enabled}

# --- Clock Abstraction APIs ---

class ClockOverrideRequest(BaseModel):
    override_datetime: Optional[str] = None # ISO format or empty to reset

@app.get("/api/clock")
def get_clock():
    return {
        "current_time": clock.iso_now(),
        "timezone": settings.scheduler_timezone,
        "is_override_active": clock.is_override_active(),
        "is_business_hours": clock.is_within_business_hours(),
        "business_hours_start": settings.business_hours_start,
        "business_hours_end": settings.business_hours_end,
        "business_days": settings.business_days
    }

@app.post("/api/clock/override")
def override_clock(req: ClockOverrideRequest):
    clock.set_override(req.override_datetime)
    return {
        "status": "ok",
        "current_time": clock.iso_now(),
        "is_override_active": clock.is_override_active(),
        "is_business_hours": clock.is_within_business_hours()
    }

# --- Document Ingestion APIs (Manual Upload) ---

@app.post("/api/upload-pdf")
async def manual_upload_pdf(pdf_file: UploadFile = File(...), background_tasks: BackgroundTasks = None):
    if not pdf_file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")

    content = await pdf_file.read()
    save_filename = f"manual_{uuid.uuid4().hex[:6]}_{pdf_file.filename}"
    save_path = settings.uploads_dir / save_filename
    with open(save_path, "wb") as f:
        f.write(content)

    # Automatically queue task
    task_id = state_store.create_task(
        goal=f"Extract, validate, and record manually uploaded invoice: {pdf_file.filename}",
        workflow_id="invoice_processing",
        context={
            "file_path": str(save_path),
            "filename": pdf_file.filename,
            "source": "manual_upload"
        }
    )

    if background_tasks:
        background_tasks.add_task(agent_loop.run_task, task_id)

    return {"status": "queued", "task_id": task_id, "file_path": str(save_path)}

@app.get("/api/workflows")
def list_workflows():
    return workflow_registry.list_all()
