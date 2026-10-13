# Standard Operating Procedure (SOP): Vendor Invoice Summary & Audit Report
Authority: Level 1 (Authoritative Business Procedure)

## 1. Objective
Generate an audit summary of all registered invoices for a specified vendor, verifying outstanding balances, due dates, and payment statuses, and compile a verified executive report.

## 2. Procedure
1. **Identify Vendor Entity:** Look up the requested vendor in the Vendor Registry (`/vendors`).
2. **Retrieve Invoices:** Search the Accounts Payable register (`/invoices`) for all invoices associated with the vendor.
3. **Audit Statuses:** For each record, record the invoice number, total amount, currency, due date, and whether the record is `paid`, `unpaid`, or `overdue`.
4. **Compile Balances:** Calculate total outstanding (unpaid/overdue) amount and total settled amount.
5. **Verify Accuracy:** Compare total counts with register entries.
6. **Report Summary:** Present a clear, itemized report to the requester with direct references to invoice numbers.
