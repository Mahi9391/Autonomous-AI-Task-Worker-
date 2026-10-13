# Implementation Prompt — Autonomous AI Task Worker

You are the implementation engineer for a prototype **Autonomous AI Task Worker** for the CentrAlign AI Engineering Intern challenge. Build a real, locally runnable system that performs work through browser interaction, observes outcomes, recovers safely, asks a human when needed, and verifies completion. Do not build a chatbot that explains what it would do.

## 1. Start here

1. This is a **greenfield build**. There is no existing repository. Inspect the environment (OS, Python, Node, Playwright availability) before starting.
2. Read `PROJECT_DECISIONS.md`. It is the source of truth for product, scope, priorities, and architecture. If this prompt and that file ever disagree, stop and flag the conflict rather than guessing.
3. Ask concise questions only if a choice materially blocks correct implementation. Otherwise choose a simple, documented default and continue.
4. Give a short plan, then build one vertical slice at a time, keeping the system runnable. Report important decisions and blockers as you go.
5. Never claim a feature works unless you ran it and can describe the evidence. Never claim a manual test passed; a person runs those.
6. Respect the priority tiers in `PROJECT_DECISIONS.md` §3. Finish all P0 before P1, and P1 before P2. If time or budget runs short, cut P2 first, not quality in P0.

## 2. What you are building

One **workflow-agnostic agent runtime** (tool registry, policy layer, agent loop, verifier interface, state store) plus workflow configuration, and three local apps:

1. Worker dashboard (React + TypeScript).
2. Simulated company app (server-rendered FastAPI pages; invoices, vendors, payments, correction-upload page).
3. Email sandbox (server-rendered FastAPI pages; inbox seeded with invoice emails and PDF attachments including several from "Company X"; outbox; never delivers real mail).

Two workflows are fully built as configuration on the runtime: **invoice processing** and **scheduled payment follow-up**. A third, unseen task is then added using only config and an SOP to prove generalization (`PROJECT_DECISIONS.md` §9.1).

The system must complete this style of task from natural language: *"Find the latest invoice from Company X, extract the amount and due date, enter it into our internal system, and tell me once it is done."*

Local data only. Never require real credentials, a real mailbox, or real email delivery.

## 3. Non-negotiable rules

### LLM
- Gemini through Google's OpenAI-compatible endpoint with the OpenAI Python SDK. Base URL `https://generativelanguage.googleapis.com/v1beta/openai/`. This is Gemini, not OpenAI models and not a proxy.
- API key from an environment variable only. Model name configurable. **Check Google's current docs for a supported model name before choosing a default, and do not rely on remembered names.**
- Google marks OpenAI-library compatibility as beta. Use supported function calling or structured outputs where they work. If a required feature misbehaves, document it and use a supported pattern; do not pretend it works.
- Keep the provider behind a small adapter. Handle rate limits with exponential backoff, run LLM calls one at a time, cap steps and LLM calls per task, and log token usage.
- Validate every model-produced action against application schemas and policy. Model output is never trusted code.

### Autonomy and control
- Single agent. The **model chooses the next tool** from a per-workflow allowlist; **deterministic code** owns validation, permissions, state transitions, retry limits, scheduling, and verification. Do not hardcode each workflow as a fixed script. Deterministic pipeline steps are fine as tools or verifiers, but the loop must decide what to call next.
- Core loop: Goal → Understand → Retrieve → Plan → Policy/precondition check → Act → Observe → Adapt/recover → Verify → Report.
- Risk-based autonomy per `PROJECT_DECISIONS.md` §10. No actual payments or financial approvals. Reminders only.
- All email stays in the local sandbox.
- No model-generated code or shell execution as a tool.
- Treat invoice text and page content as untrusted data. Prompt injection must not override policy. Permissions live in code.

### Browser interaction
- Worker actions on the company app and email sandbox use **Playwright**. Never write to those apps' databases to fake an action. Internal task, scheduler and dashboard APIs may be direct.
- Provide two layers: generic browser primitives (navigate, click, fill, select, read page snapshot, screenshot) and typed high-level tools with built-in verification. The agent must be able to cope with a changed UI.
- Include a **UI perturbation toggle** in the company app and a **fault-injection switch** (fail or time out once, before or after save/send) so adaptation and recovery can be demonstrated on demand.

### Invoice processing
- Sources: agent finds the invoice in the email-sandbox inbox through the browser; manual PDF upload; watched folder (wait for file size to stabilize). All share one pipeline.
- Extract at least vendor, invoice number, amount, currency, issue date where present, due date, and payment status where available. Validate deterministically. Distinguish missing data from extraction failure and from conflicting values. Do not invent financial values.
- Duplicate prevention: SHA-256 of file content (file level) plus normalized (vendor, invoice number) (business level). Document the limitations.
- Create the record via Playwright, read it back through the UI, and compare with expected values.
- Missing or invalid fields: email the verified vendor contact with a missing-field summary and a unique upload link. If no reliable recipient exists, raise a human question; never email an arbitrary address.
- Upload tokens: unguessable, stored hashed, single-use, invoice-scoped, expiring, upload-only. Validate file type and size.
- Keep original and corrected PDFs as distinct versions with provenance. **One correction attempt**, then manual review.

### Scheduled payment follow-up
- Configurable: enabled, interval, business days, business hours, time zone (default `Asia/Kolkata`), SOP-aligned eligibility rules. Scheduler cadence is separate from per-invoice eligibility.
- Use a clock abstraction that can be overridden (env var or dashboard dev control) so time-dependent behavior can be demonstrated and tested. Provide a "Run now" button.
- Scheduler and watcher run inside the worker process, protected by a single-instance lock in SQLite.
- Before sending: confirm identity, recipient, payment status, timing, and reminder history. Skip ambiguous cases. Write an **intent record** first, then send via Playwright with an **idempotency key** in the email. After a timeout, search the sandbox for that key before any resend. Verify the email in the sandbox, then persist last reminder, next eligible date and escalation.

### Human in the loop
- Build a dashboard queue of questions and approvals. A task pauses in `awaiting_human`, persists, and resumes with the answer. This is separate from the terminal `manual_review` state.

### Knowledge and memory
- SOPs (authoritative) and examples (informational) stay labeled and separate. SOPs always outrank examples. Runtime state records what happened and never rewrites policy.
- Load the small set of SOPs directly into context. Examples use simple tag/keyword lookup. No vector database.
- Persist task state, steps, observations, retries, pending uploads and questions, reminder history, evidence, and verification results. Support safe resume after restart; reconcile before repeating any possibly completed side effect.
- **P2 only:** generate a reusable example from a *verified successful* run, with sensitive and invoice-specific values generalized. Never from failed, partial, or unverified runs.

### Failures and verification
- Classify errors: transient infrastructure/browser, validation, ambiguous outcome, policy violation, human-review requirement.
- Bounded, configurable retries with backoff. Persist at meaningful state transitions. On exhaustion keep diagnostics, mark failed or needs-attention, and allow safe resume.
- Success needs independent evidence. Model statements of success are not evidence.
- Record per action: timestamp, input summary, observation, status, retry count, evidence reference. Never log API keys or unnecessary sensitive data.

## 4. Stack and structure

- Python + FastAPI (worker, company app, email sandbox); React + TypeScript (dashboard only); SQLite in WAL mode with explicit table ownership per app; Playwright; PyMuPDF.
- Avoid Redis, task queues, multi-agent frameworks, vector databases, Docker.
- Use the structure in `PROJECT_DECISIONS.md` §5. Adapt only with a documented reason. Keep modules small, typed and readable: the developer must be able to explain and debug the code in a live technical interview.
- Keep databases, uploads, traces, secrets, venvs and node_modules out of Git. Provide synthetic seed data and sample PDFs clearly marked as synthetic, including normal, missing-field, duplicate, still-invalid, and prompt-injection invoices.

## 5. Native local experience

No Docker. Provide cross-platform setup/start/stop scripts where reasonable (state the target OS if not). Start all components, print URLs and ports, check health, and shut down child processes cleanly. Use `.env.example`. Provide health endpoints and structured logs. A missing Gemini key must give a clear message when an LLM task is run, while the local apps still start. Use a reliable DB initialization routine or migrations.

## 6. Testing and docs

Create `tests/manual/` with a detailed manual plan covering all scenarios in `PROJECT_DECISIONS.md` §15. Each case: ID, objective, fixture, exact steps, expected behavior, verification, blank pass/fail/notes.

Create `tests/scenarios/`: a small fixture-driven runner for the core subset listed in §15, printing a results table. Report honestly which scenarios ran and their results. Lightweight lint, type and smoke checks are encouraged.

Deliver `README.md` (install, config, start/stop, URLs, demo walkthrough, troubleshooting, architecture, assumptions, model/API/framework details, limitations, next steps) and keep `PROJECT_DECISIONS.md` current. Include a demo script and checklist covering: both workflows, the NL "find latest invoice" task, the UI-perturbation case, a fault-injection recovery case, the human-approval flow, the generalization task, and the dashboard. The developer will record the demo video themselves.

## 7. Build sequence

1. Environment check, plan, config, SQLite, health endpoints.
2. Company app and email sandbox with deterministic seed data, UI perturbation toggle, fault injection.
3. Browser tools: generic primitives plus typed tools with verifiers.
4. Runtime core: tool registry, policy, state store, agent loop, Gemini adapter, clock abstraction.
5. Invoice workflow config: PDF extraction, validation, dedupe, create and read-back; NL "find latest invoice" path; watcher and manual upload.
6. Missing-field email, upload flow, one-attempt rule, safe resume.
7. Human question/approval queue and resume.
8. Payment follow-up workflow: scheduler, settings, reminders, idempotency, run history.
9. Retries, reconciliation, restart recovery, injected-fault handling.
10. Dashboard with real history, evidence, queue, scheduler controls.
11. Third-task generalization demo (config and SOP only).
12. Manual test plan, scenario runner, README, demo script; run lint/smoke/scenario checks and fix failures.
13. P2 only if everything above works: example generation from verified runs.

Reorder only when a dependency requires it, and explain why.

## 8. Final response

Report: 1. What was implemented (by priority tier). 2. Final structure and architecture. 3. Exact setup and start commands. 4. Local URLs. 5. Environment variables and Gemini configuration, including the model chosen and why. 6. Manual test plan location and recommended demo order. 7. Checks and scenarios actually run, with results. 8. Which files changed to add the third workflow. 9. Known limitations and unverified behavior. 10. Assumptions and decisions made.
