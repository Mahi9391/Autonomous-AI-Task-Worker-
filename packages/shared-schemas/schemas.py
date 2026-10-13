from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from enum import Enum
from datetime import datetime

class TaskStatus(str, Enum):
    QUEUED = "queued"
    ACTIVE = "active"
    AWAITING_UPLOAD = "awaiting_upload"
    AWAITING_HUMAN = "awaiting_human"
    MANUAL_REVIEW = "manual_review"
    COMPLETED = "completed"
    FAILED = "failed"

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class ToolCallRequest(BaseModel):
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    rationale: Optional[str] = None

class ToolExecutionResult(BaseModel):
    tool_name: str
    success: bool
    data: Any = None
    error: Optional[str] = None
    observation: str
    evidence: Optional[Dict[str, Any]] = None

class StepRecord(BaseModel):
    step_id: str
    task_id: str
    step_number: int
    tool_name: str
    arguments: Dict[str, Any] = Field(default_factory=dict)
    observation: str
    status: str
    retry_count: int = 0
    evidence_ref: Optional[str] = None
    timestamp: str

class HumanQuestion(BaseModel):
    question_id: str
    task_id: str
    question_text: str
    question_type: str = "clarification" # clarification | approval
    options: Optional[List[str]] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending" # pending | answered
    answer: Optional[str] = None
    created_at: str
    answered_at: Optional[str] = None

class InvoiceRecord(BaseModel):
    id: Optional[str] = None
    vendor: str
    invoice_number: str
    amount: float
    currency: str = "USD"
    issue_date: Optional[str] = None
    due_date: str
    status: str = "unpaid" # unpaid | paid | overdue | pending_approval
    file_hash: Optional[str] = None
    source: str = "email" # email | manual_upload | watched_folder
    created_at: Optional[str] = None
    last_reminder_sent_at: Optional[str] = None
    reminder_count: int = 0

class VendorRecord(BaseModel):
    id: str
    name: str
    contact_email: str
    payment_terms_days: int = 30
    is_verified: bool = True

class EmailRecord(BaseModel):
    id: str
    sender: str
    recipient: str
    subject: str
    body: str
    attachments: List[str] = Field(default_factory=list)
    idempotency_key: Optional[str] = None
    folder: str = "inbox" # inbox | outbox
    timestamp: str

class VerificationResult(BaseModel):
    verified: bool
    check_name: str
    expected: Any
    actual: Any
    details: Optional[str] = None
