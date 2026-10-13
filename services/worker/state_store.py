import uuid
import json
import hashlib
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from .db import get_db
from .clock import clock

class StateStore:
    def create_task(self, goal: str, workflow_id: str, context: Optional[Dict[str, Any]] = None) -> str:
        task_id = f"TASK-{uuid.uuid4().hex[:8].upper()}"
        now_str = clock.iso_now()
        ctx_json = json.dumps(context or {})

        with get_db() as conn:
            conn.execute("""
            INSERT INTO tasks (
                id, goal, workflow_id, status, context, result_summary, evidence,
                step_count, llm_call_count, token_usage, created_at, updated_at
            ) VALUES (?, ?, ?, 'queued', ?, NULL, '{}', 0, 0, '{"prompt_tokens":0,"completion_tokens":0,"total_tokens":0}', ?, ?)
            """, (task_id, goal, workflow_id, ctx_json, now_str, now_str))

        return task_id

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with get_db() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            if not row:
                return None
            res = dict(row)
            res["context"] = json.loads(res["context"] or "{}")
            res["evidence"] = json.loads(res["evidence"] or "{}")
            res["token_usage"] = json.loads(res["token_usage"] or "{}")
            return res

    def list_tasks(self, limit: int = 50) -> List[Dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["context"] = json.loads(item["context"] or "{}")
                item["evidence"] = json.loads(item["evidence"] or "{}")
                item["token_usage"] = json.loads(item["token_usage"] or "{}")
                results.append(item)
            return results

    def update_task_status(
        self,
        task_id: str,
        status: str,
        summary: Optional[str] = None,
        evidence: Optional[Dict[str, Any]] = None
    ):
        with get_db() as conn:
            task = self.get_task(task_id)
            if not task:
                return

            existing_evidence = task.get("evidence", {})
            if evidence:
                existing_evidence.update(evidence)

            conn.execute("""
            UPDATE tasks
            SET status = ?, result_summary = COALESCE(?, result_summary),
                evidence = ?, updated_at = ?
            WHERE id = ?
            """, (status, summary, json.dumps(existing_evidence), clock.iso_now(), task_id))

    def update_task_context(self, task_id: str, context_updates: Dict[str, Any]):
        with get_db() as conn:
            task = self.get_task(task_id)
            if not task:
                return
            ctx = task.get("context", {})
            ctx.update(context_updates)
            conn.execute("""
            UPDATE tasks SET context = ?, updated_at = ? WHERE id = ?
            """, (json.dumps(ctx), clock.iso_now(), task_id))

    def increment_task_metrics(self, task_id: str, steps: int = 1, llm_calls: int = 1, tokens: Optional[Dict[str, int]] = None):
        with get_db() as conn:
            task = self.get_task(task_id)
            if not task:
                return
            new_step_count = task.get("step_count", 0) + steps
            new_llm_count = task.get("llm_call_count", 0) + llm_calls

            usage = task.get("token_usage", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})
            if tokens:
                usage["prompt_tokens"] += tokens.get("prompt_tokens", 0)
                usage["completion_tokens"] += tokens.get("completion_tokens", 0)
                usage["total_tokens"] += tokens.get("total_tokens", 0)

            conn.execute("""
            UPDATE tasks
            SET step_count = ?, llm_call_count = ?, token_usage = ?, updated_at = ?
            WHERE id = ?
            """, (new_step_count, new_llm_count, json.dumps(usage), clock.iso_now(), task_id))

    def record_step(
        self,
        task_id: str,
        step_number: int,
        tool_name: str,
        arguments: Dict[str, Any],
        observation: str,
        status: str,
        evidence_ref: Optional[str] = None,
        retry_count: int = 0
    ) -> str:
        step_id = f"STEP-{uuid.uuid4().hex[:8].upper()}"
        with get_db() as conn:
            conn.execute("""
            INSERT INTO steps (
                id, task_id, step_number, tool_name, arguments, observation, status, retry_count, evidence_ref, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                step_id, task_id, step_number, tool_name, json.dumps(arguments),
                observation, status, retry_count, evidence_ref, clock.iso_now()
            ))
        return step_id

    def get_task_steps(self, task_id: str) -> List[Dict[str, Any]]:
        with get_db() as conn:
            rows = conn.execute("SELECT * FROM steps WHERE task_id = ? ORDER BY step_number ASC", (task_id,)).fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["arguments"] = json.loads(item["arguments"] or "{}")
                results.append(item)
            return results

    # --- Human in the Loop ---

    def create_human_question(
        self,
        task_id: str,
        question_text: str,
        question_type: str = "clarification",
        options: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        q_id = f"Q-{uuid.uuid4().hex[:8].upper()}"
        with get_db() as conn:
            conn.execute("""
            INSERT INTO human_questions (
                id, task_id, question_text, question_type, options, context, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
            """, (q_id, task_id, question_text, question_type, json.dumps(options or []), json.dumps(context or {}), clock.iso_now()))
            
            # Pause task into awaiting_human state
            conn.execute("UPDATE tasks SET status = 'awaiting_human', updated_at = ? WHERE id = ?", (clock.iso_now(), task_id))

        return q_id

    def get_pending_questions(self, task_id: Optional[str] = None) -> List[Dict[str, Any]]:
        with get_db() as conn:
            if task_id:
                rows = conn.execute("SELECT * FROM human_questions WHERE task_id = ? AND status = 'pending' ORDER BY created_at DESC", (task_id,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM human_questions WHERE status = 'pending' ORDER BY created_at DESC").fetchall()
            results = []
            for r in rows:
                item = dict(r)
                item["options"] = json.loads(item["options"] or "[]")
                item["context"] = json.loads(item["context"] or "{}")
                results.append(item)
            return results

    def answer_human_question(self, question_id: str, answer: str) -> bool:
        with get_db() as conn:
            row = conn.execute("SELECT task_id FROM human_questions WHERE id = ? AND status = 'pending'", (question_id,)).fetchone()
            if not row:
                return False
            task_id = row["task_id"]
            now_str = clock.iso_now()

            conn.execute("""
            UPDATE human_questions 
            SET status = 'answered', answer = ?, answered_at = ?
            WHERE id = ?
            """, (answer, now_str, question_id))

            # Resume task from awaiting_human to active
            conn.execute("""
            UPDATE tasks SET status = 'active', updated_at = ? WHERE id = ?
            """, (now_str, task_id))
            return True

    # --- Upload Tokens ---

    def create_upload_token(self, task_id: str, invoice_ref: str, vendor_contact: str, expiry_hours: int = 48) -> str:
        raw_token = f"tok_{uuid.uuid4().hex}_{uuid.uuid4().hex[:12]}"
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        expires_at = (clock.now() + timedelta(hours=expiry_hours)).isoformat()

        with get_db() as conn:
            conn.execute("""
            INSERT INTO upload_tokens (
                token_hash, invoice_ref, vendor_contact, task_id, is_used, expires_at, created_at
            ) VALUES (?, ?, ?, ?, 0, ?, ?)
            """, (token_hash, invoice_ref, vendor_contact, task_id, expires_at, clock.iso_now()))

        return raw_token

state_store = StateStore()
