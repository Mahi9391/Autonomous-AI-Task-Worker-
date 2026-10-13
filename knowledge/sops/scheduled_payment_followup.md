# Standard Operating Procedure (SOP): Scheduled Payment Follow-up
Authority: Level 1 (Authoritative Business Procedure)

## 1. Objective
Ensure automated payment follow-up reminders are dispatched exclusively to verified vendor contacts for overdue unpaid invoices during business hours, with strict idempotency and zero duplicate messages.

## 2. Business Hours & Timing Rules
- Timezone: `Asia/Kolkata` (default, configurable).
- Business days: Monday through Friday (business days 0, 1, 2, 3, 4).
- Business hours: 09:00 to 18:00 local time.
- If current time is outside business hours, follow-up runs must skip dispatching reminders unless dev clock override is active or "Run Now" is explicitly forced.

## 3. Eligibility Criteria
An invoice is eligible for a reminder ONLY if:
1. Status is `unpaid` or `overdue`.
2. Due date has passed (`due_date <= current_date`).
3. Paid or pending-approval invoices must NEVER receive reminders.
4. If a reminder was sent within the last 3 business days (or within current period), skip to avoid harassment.

## 4. Idempotency & Intent Record
1. Before dispatching any reminder email, construct a unique deterministic **idempotency key**:
   `REMIND-{vendor_slug}-{invoice_number}-{due_date}`
2. Check the email sandbox outbox for this idempotency key. If found, SKIP dispatch.
3. Write an **intent record** in the run log.
4. Send the reminder email using Playwright to the verified vendor billing contact.
5. Include the idempotency key in the email headers/field.
6. Verify delivery by reading back the sent email from `/outbox`.

## 5. Failure Reconciliation
If sending encounters a timeout or network failure:
1. Do NOT immediately re-send!
2. Inspect the outbox for the idempotency key.
3. If the email is present (e.g. failure occurred after save), mark successful.
4. Only retry if the email was confirmed not sent.
