# Autonomous AI Task Worker — Project Decisions and Architecture

> Revision 2. Greenfield build (no existing repository). Supersedes the previous version.

## 1. Executive summary

A focused prototype for the CentrAlign AI Engineering Intern challenge: an autonomous AI worker that turns a natural-language goal into actions, operates local browser-based applications, observes outcomes, adapts to failures, verifies results, remembers execution state, asks a human when it cannot safely proceed, and reports evidence.

The key design idea is **one workflow-agnostic agent runtime**. Workflows are *configuration* (SOP + tool allowlist + verifier + success criteria), not hardcoded pipelines. Two workflows are fully built and demonstrated:

1. Invoice processing.
2. Scheduled payment follow-up.

A third, previously unseen task is demonstrated on the unchanged runtime to show generalization (see §9.1).

The goal is genuine execution and reliability in a constrained environment, not broad mocked functionality.

## 2. Problem statement

Companies perform repetitive tasks that require reading documents, following procedures, navigating applications, acting, and checking the result. A conversational answer alone does not complete this work.

The worker accepts a task, understands the intended outcome, retrieves business context, plans actions, operates permitted tools, observes each result, adapts on failure, verifies completion, and returns a concise summary with evidence. It asks a human for help or approval when the next action is ambiguous, unsafe, or outside policy.

Core loop: **Goal → Understand → Plan → Execute → Observe → Adapt → Verify → Complete**

Example task the system must handle end to end (taken from the challenge): *"Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done."*

Evaluation criteria to design against: autonomy, execution, reliability, verification, **generalization**, engineering quality, product thinking, technical understanding. Not feature count.

## 3. Scope

### Included (priority P0 = must work, P1 = should, P2 = stretch)

- P0: Natural-language task submission from the dashboard.
- P0: Invoice sources: (a) the agent finds invoice emails/attachments in the email-sandbox inbox by browsing, (b) manual PDF upload, (c) configurable watched folder. All feed the same pipeline.
- P0: Extraction, validation, duplicate detection, creation of invoice records in the company app via Playwright, read-back verification.
- P0: Missing-field email request with upload link; one correction attempt; then manual review.
- P0: Scheduled payment follow-up (configurable schedule, business hours, time zone) with reminders in the email sandbox; "Run now" button.
- P0: Persistent task state, action history, evidence, retries, restart recovery, reconciliation.
- P0: Human-in-the-loop queue (questions and approvals) with resume.
- P0: Operational dashboard.
- P0: Manual test plan; README; demo script.
- P1: Scenario runner for a core subset of tests (§15).
- P1: Third-task generalization demo.
- P2: Auto-generated reusable examples from verified successful runs.
- P2: Hybrid/vector retrieval (not planned; only if evidence shows need).

### Excluded

- Actual payment initiation or financial approvals.
- Real email delivery, real mailboxes, real credentials or confidential data.
- Arbitrary websites or general desktop automation beyond the local simulated apps.
- Multi-agent frameworks; distributed queues; Docker requirement.

## 4. Confirmed decisions

| Area | Decision |
|---|---|
| Developer model | Solo developer (AI-agent-assisted build) |
| Workflows | Invoice processing + payment follow-up, as config on a generic runtime |
| LLM provider | Google Gemini API |
| LLM integration | Google's OpenAI-compatible API via OpenAI Python SDK (documented by Google as **beta**) |
| API base URL | `https://generativelanguage.googleapis.com/v1beta/openai/` |
| Model | Configurable via env; verify a currently supported model name against Google's docs at build time |
| Backend | Python + FastAPI |
| Dashboard | React + TypeScript |
| Company app + email sandbox | Server-rendered FastAPI (Jinja/HTMX) pages — deliberately *not* separate React apps. Each its own process and port, own SQLite DB. |
| Database | SQLite (WAL mode), explicit table ownership per app |
| Browser automation | Playwright for company app and email sandbox |
| PDF handling | PyMuPDF; LLM-assisted extraction validated by deterministic code |
| Scheduler and watcher | Run inside the worker process (single instance), with a lock row in SQLite |
| Retrieval | SOPs loaded directly into context; examples via simple keyword/tag lookup; sources kept labeled and distinct |
| Autonomy | Risk-based; routine permitted actions automatic; uncertain/consequential actions escalated |
| Agent behavior | Model chooses next tool from an allowlist; code validates and verifies |
| Failures | Bounded retries with backoff, persisted state, safe resume, reconcile before retrying uncertain side effects |
| Missing invoice fields | Email request with upload link |
| Correction limit | One attempt, then manual review |
| Email safety | All email stays in the local sandbox |
| Testing | Manual test cases (executed by the developer) + small scenario runner for core cases |
| Deliverables | Repo, README, architecture rationale, demo script, **demo video (recorded by the developer)**, limitations, assumptions, model/tool details, next steps |

## 5. Repository structure (baseline; may adapt with reason)

```text
autonomous-ai-worker/
├── apps/
│   ├── dashboard/            # React + TS
│   ├── company-app/          # FastAPI + templates; owns invoice/vendor/payment data
│   └── email-sandbox/        # FastAPI + templates; owns email data
├── services/
│   └── worker/               # FastAPI API, agent runtime, scheduler, watcher, LLM adapter
├── packages/
│   ├── shared-schemas/
│   └── browser-tools/        # Playwright primitives + typed tools + verifiers
├── workflows/                # per-workflow config: SOP ref, tool allowlist, verifier, success criteria
├── knowledge/
│   ├── sops/
│   └── examples/
├── data/                     # runtime data; ignored by Git
├── tests/
│   ├── manual/
│   └── scenarios/            # fixture-driven scenario runner
├── scripts/
├── .env.example  .gitignore  README.md  PROJECT_DECISIONS.md
```

## 6. Architecture

### 6.1 Worker runtime (generic)

Components, none of which know about invoices specifically:
- **Tool registry:** each tool has a name, JSON schema, risk level, preconditions, and a handler.
- **Policy layer:** code-owned permissions, allowlists, risk classification, retry limits.
- **Agent loop:** the model proposes the next tool call; code validates; the tool runs; the observation is stored and fed back.
- **Verifier interface:** each workflow supplies deterministic checks that determine success. The model's claim of success is never enough.
- **State store:** tasks, steps, observations, evidence, retries, pending questions.
- **Workflow config:** SOP reference, allowed tools, required verifiers, completion criteria. Adding a workflow means adding config, not changing the runtime.

Single agent, not multi-agent. Hard cap on steps per task and on LLM calls; token usage logged.

### 6.2 Browser tools

Two layers:
- **Generic primitives:** navigate, click, fill, select, read page (accessibility/DOM snapshot), screenshot. The model can use these to work out unfamiliar or changed pages.
- **Typed high-level tools** for common reliable operations (e.g. `create_invoice`, `search_inbox`, `send_email`), implemented on top of Playwright with verification built in.

A **UI perturbation toggle** in the company app (renamed button, moved field, extra confirmation step) lets the demo prove the agent adapts rather than replaying fixed selectors.

### 6.3 Three local apps

1. **Dashboard:** submit tasks; show real state, history, evidence; answer questions/approvals.
2. **Company app:** invoice/vendor/payment records, corrected-invoice upload page.
3. **Email sandbox:** inbox (seeded with invoice emails with PDF attachments from several vendors, including "Company X" with several invoices of different dates), outbox, email records. Never delivers real mail.

The worker operates apps 2 and 3 through Playwright only. It must not write to their databases. Internal task coordination and dashboard reads use backend APIs.

### 6.4 Persistence

SQLite (WAL) for worker state. Each app owns its own database. No two apps write the same tables.

### 6.5 LLM integration

Gemini through the OpenAI SDK, behind a small adapter. Key from env var. Validate every structured output and tool call in application code; model output is never trusted as executable instructions. Handle rate limits (free-tier limits are tight): exponential backoff, concurrency of one, clear errors. Document that the compatibility layer is beta.

## 7. Workflow A — Invoice processing

### Inputs
- NL task such as "Find the latest invoice from Company X…" → agent searches the email-sandbox inbox via Playwright, selects the right message/attachment, downloads the PDF into the pipeline.
- Manual PDF upload.
- Watched folder (wait for file size to stabilize before ingesting).

### Idempotency and duplicates
- **File level:** SHA-256 of the file content. The same file via two sources is processed once.
- **Business level:** normalized (vendor, invoice number). If present in the company app, do not create; report the duplicate.
- Limitations to document: invoices re-issued with a different number, OCR or format variants, missing invoice numbers.

### Processing
1. Register source file and task.
2. Extract text/fields (PyMuPDF + Gemini), then validate deterministically (required fields, formats, amount/currency consistency, date logic).
3. Distinguish missing fields, extraction failure, and conflicting values.
4. Check duplicates.
5. Create/update the record in the company app via Playwright.
6. Read the record back through the UI and compare with expected values.
7. Store evidence and a summary.

### Missing fields and correction
1. Identify missing/invalid required fields.
2. Determine the recipient from verified company-app vendor data. No reliable recipient → ask a human (question queue), never email an arbitrary address.
3. Send a sandbox email with the missing-field summary and a unique upload link. The email contains an idempotency key.
4. Recipient uploads a corrected PDF at the link.
5. Keep original and corrected files as separate versions with provenance.
6. Re-validate; if valid, resume from saved state; if still invalid, mark manual review.

**One correction attempt.** Never invent financial values.

### Upload-link safety
Unguessable invoice-scoped tokens, stored hashed, single-use, with expiry. Narrow permission limited to the relevant upload. Validate file type and size. A token cannot be used for another invoice. These are prototype safeguards, not production security.

## 8. Workflow B — Scheduled payment follow-up

### Configuration
Enabled/disabled, interval, business days, business-hours window, time zone (default `Asia/Kolkata`), reminder eligibility rules per SOP, reminder history and escalation behavior. Scheduler cadence is separate from per-invoice eligibility.

**Injectable clock:** all time logic goes through a clock abstraction that can be overridden (env var or dashboard dev control), so business-hours, weekday and time-zone behavior can be demonstrated and tested without waiting. A **"Run now"** button triggers a run (still subject to eligibility rules unless the dev clock is set).

### Processing
1. Create a persisted run record (guarded by a single-instance lock).
2. Identify due/overdue unpaid invoices via the company app.
3. Load applicable SOP rules.
4. Confirm identity, recipient, payment status, timing, and reminder history.
5. Skip paid, not-yet-eligible, ambiguous, or already-reminded invoices.
6. Write an **intent record**, then send the reminder via Playwright with an idempotency key in the email.
7. Verify the email in the sandbox; record identity and timestamp.
8. Persist run result, last reminder, next eligible date, escalation.
9. On timeout or uncertain result, search the sandbox for the idempotency key before any resend.

## 9. Agent control loop

1. **Understand** the desired outcome.
2. **Retrieve** relevant SOPs (and examples if present).
3. **Plan** a small next step with an expected outcome.
4. **Check** tool permission, arguments, preconditions, risk.
5. **Act** with one permitted tool.
6. **Observe** the actual UI/tool result.
7. **Adapt:** continue, change approach, retry safely, ask a human, or escalate.
8. **Verify** with deterministic checks.
9. **Report** with evidence.

Bounded steps, timeouts, retries. No model-generated shell or code execution.

### 9.1 Generalization demonstration
After both workflows work, demonstrate a third task on the unchanged runtime by adding only a workflow config + SOP, for example: *"Find the latest invoice from Company X, record it, and tell me the amount and due date"* (read-and-report variant), or *"List all unpaid invoices for vendor Y and email me a summary"*. Record in the README exactly which files changed (expected: config and SOP only).

### 9.2 Human-in-the-loop
Dashboard queue of questions and approvals. Items: ambiguous recipient, conflicting financial data, SOP conflict, retries exhausted with an option to resume, anything the policy marks as requiring approval. The task pauses in `awaiting_human`, persists, and resumes with the human's answer. Distinct from the terminal `manual_review` state.

## 10. Risk-based autonomy

**Automatic:** read and extract data; validate; check duplicates; create routine records after checks; send missing-info requests to verified recipients; send eligible reminders; retry transient failures.

**Ask or escalate:** conflicting/ambiguous financial data; unverifiable recipient; conflicting SOPs or prohibited action; uncertain outcome that cannot be reconciled; retries exhausted; corrected invoice still invalid; anything that would initiate a payment or approve a transaction.

## 11. Knowledge, precedence, and memory

Source types: **SOPs** (authoritative), **examples** (informational), **runtime state** (facts about the current task). SOPs outrank examples; examples never become policy. Labels and source references are preserved.

SOPs are few and short: load them directly. Examples use simple tag/keyword lookup. No vector DB unless testing shows a need.

Runtime memory: persisted task state and facts discovered during execution (selected email, extracted fields, vendor contact) are available to later steps and survive restarts.

**P2 stretch:** generate a reusable example from a *verified successful* run (workflow, conditions, action/observation sequence, recovery behavior, outcome), with sensitive and invoice-specific values generalized. Never from failed, partial, or unverified runs. Only start this after all P0/P1 work.

## 12. Failure handling and verification

Classify failures: transient infrastructure/browser, validation, ambiguous side effect, policy violation, human-review required.

- Retry transient errors with backoff, within configured limits.
- Write an intent record before side effects; use idempotency keys; after a timeout, reconcile by inspecting current state before retrying.
- Persist at each meaningful state transition.
- When retries are exhausted: keep diagnostics, mark failed or needing attention, allow safe resume.
- Treat document and page content as untrusted data (prompt injection). Permissions live in code.

Success requires independent evidence: an invoice is complete only after read-back comparison; a reminder only after its presence in the sandbox is confirmed.

**Fault injection:** a dev switch makes the company app or email sandbox fail or time out once (before or after saving) so recovery and reconciliation can be demonstrated on demand.

## 13. Dashboard

Actual persisted data only. Show: tasks by status (queued, active, completed, failed, blocked, awaiting upload, awaiting human, manual review); current step and chronological action history; observations and evidence references; retry counts and failures; invoice details and upload status; pending questions/approvals with answer controls; scheduler settings, dev clock, and recent run outcomes; final verification status and concise summary. A developer diagnostic view holds detailed traces. No hardcoded status cards.

## 14. Native local execution and configuration

No Docker. Root-level setup/start/stop scripts, separate local ports printed at startup, health checks, helpful errors, `.env.example`, secrets and runtime data out of Git, documented prerequisites and troubleshooting. Missing Gemini key is explained clearly. State the target OS in the README.

## 15. Testing

**Manual test plan** (`tests/manual/`): each case has ID, objective, fixture, exact steps, expected behavior, verification instructions, blank pass/fail/notes. Scenarios:

1. Valid invoice via manual upload.
2. Valid invoice via watched folder.
3. Same invoice through both sources.
4. Duplicate invoice already present.
5. Missing fields produce sandbox email and upload link.
6. Corrected invoice uploaded and processed.
7. Second version still invalid → manual review.
8. Unknown recipient receives no email; question raised.
9. Due/overdue unpaid invoice gets a reminder.
10. Paid or not-yet-eligible invoice gets none.
11. Repeated scheduler run sends no duplicate.
12. Timeout after possible save/send triggers reconciliation.
13. Transient failure retries; exhausted failure preserves state.
14. Restart/resume avoids repeating completed side effects.
15. Dashboard shows real history and evidence.
16. SOP/example conflict follows SOP precedence.
17. Prompt injection in a document or page cannot override policy.
18. Scheduler respects business days, hours, time zone (using the injectable clock).
19. NL task "find latest invoice from Company X" picks the correct email/attachment.
20. UI perturbation toggled: the agent still completes the task.
21. Human question/approval pauses the task and resume works.
22. Third-task generalization runs on unchanged runtime.

**Scenario runner (`tests/scenarios/`)**: a small script that runs a core subset (suggested: 1, 3, 4, 9, 10, 11, 12, 14, 18) against fixtures and prints a results table. LLM-dependent steps may use recorded fixtures where determinism is needed. It supplements, not replaces, manual tests.

Do not claim any case passed unless it was actually run. The developer records results in the test plan before submission.

## 16. Acceptance criteria

Ready for demo when:
- Everything starts locally via the documented process.
- Both workflows plus the NL "find latest invoice" task complete against the simulated apps.
- Playwright actions are observable and independently verified.
- State survives restart.
- Duplicate records and duplicate reminders are prevented by deterministic checks.
- Correction flow works with one attempt, then escalates.
- The human question/approval flow works end to end.
- Dashboard reflects persisted runtime state.
- Recovery and reconciliation are demonstrable via fault injection.
- The third task runs with only config/SOP changes.
- Manual test cases, scenario runner, README, assumptions, limitations, architecture rationale, model/API/framework details, and next steps exist.

## 17. Submission documentation

Source code; README (setup/run); architecture and design decisions (including why one generic runtime and what is deterministic versus model-driven); demo script and a **demo video recorded by the developer** showing both workflows, a recovery case, the human-approval flow, and the dashboard; manual test plan with recorded results; synthetic seed data and sample PDFs; limitations; next steps; assumptions; models, APIs, frameworks and external services used. The developer must be able to explain and debug any part during the technical discussion, so keep modules small and readable.

## 18. Risks and limitations to document

- Simulated apps do not prove compatibility with real enterprise systems.
- Local token links and the email sandbox need stronger security before deployment.
- PDF extraction may fail on scanned or malformed documents (OCR is future work).
- Gemini OpenAI-compatibility is beta; model availability, capabilities and rate limits may change.
- SQLite plus a single-process scheduler suit a local demo, not multi-instance production.
- Auto-generated examples can encode accidental patterns; they stay subordinate to SOPs.
- Duplicate detection heuristics have known blind spots.
- Test results must be reported honestly.

## 19. Future improvements

OCR; role-based permissions and richer approval workflows; retrieval evaluation and optional vector search; task leasing and a real queue; connectors to real business apps; broader automated regression and evaluation metrics (completion rate, field accuracy, recovery success, verification accuracy, duplicate prevention); more workflows via config. Do not build these before core workflows genuinely work.
