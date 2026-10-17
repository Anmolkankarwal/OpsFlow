# Engineering Decisions

## 1. Relational data model and activity history

**Context:** Work items belong to teams and reference users; important changes must be auditable.  
**Options considered:** Store the current state only; store a free-form JSON document; use relational tables plus append-only events.  
**Choice:** PostgreSQL with SQLAlchemy models for users, teams, memberships, work items, comments, activity events, idempotency records, and outbox jobs. Every item mutation and its activity event are committed in one database transaction.  
**Trade-off:** More tables and explicit relationships, but clear integrity boundaries and straightforward auditing. Formal Alembic migrations are a next step; this MVP creates tables on startup.

## 2. Optimistic concurrency and atomic claims

**Context:** Two operators may update or claim the same work item concurrently.  
**Options considered:** Last-write-wins; process-local locks; a version column with conditional SQL updates.  
**Choice:** Every item has a monotonically increasing `version`. Update and transition operations compare the submitted version and atomically increment it; claim conditionally updates only an unassigned row with the expected version. Conflicts return HTTP `409`.  
**Trade-off:** Clients must reload and retry after a conflict, but newer changes are not silently overwritten. The tests exercise stale updates and repeated claims; a dedicated multi-process stress test remains useful.

## 3. Authorization at the API boundary

**Context:** Users can belong to several teams with different roles; hiding UI controls is not security.  
**Options considered:** Global roles; frontend-only checks; membership-scoped server checks.  
**Choice:** Each protected item read/write first resolves the item and verifies that the current user has a membership in its team. Viewers are read-only; Leads/Admins can approve the workflow step.  
**Trade-off:** A few extra queries per request, in exchange for resource-level authorization. A production system should consolidate checks into a service/policy layer and add audit/security review.

## 4. Controlled workflow and approval queue

**Context:** Work needs to move through investigation, review, resolution, and closure without skipping required steps.  
**Choice:** The server permits `Open → In Progress`, `In Progress → Awaiting Approval` or back to `Open`, `Awaiting Approval → Resolved` or back to `In Progress`, and `Resolved → Closed` or back to `In Progress`. A Lead/Admin member of the item's team must make either decision at the approval gate: Approve moves the item to `Resolved`; Reject returns it to `In Progress`. The API enforces both decisions regardless of client, writes distinct approval activity events, and the detail panel shows explicit review actions only to eligible team roles. The approval queue is scoped to teams where the current user has one of those roles.
**Trade-off:** Rework can return an item to active work, while direct jumps remain rejected. Treating rejection as a return to `In Progress` avoids adding another workflow state; the workflow is intentionally small and should be changed through explicit server rules and tests.

## 5. Idempotency for retried create requests

**Context:** A double-click or network retry should not create duplicate work items.  
**Options considered:** Rely on UI disabling; deduplicate by title; accept a client-supplied idempotency key stored in the database.  
**Choice:** `POST /api/items` accepts `Idempotency-Key`; the key and resulting item ID are stored under a unique constraint, with a SHA-256 hash of the canonical request stored separately. Repeating the same key and payload as the same user returns the original item; reusing the key with a different payload returns HTTP 409.  
**Trade-off:** Clients must generate and retain keys per logical operation. Hashes detect payload changes without persisting another copy of the request. Existing legacy keys without a stored hash fail closed with HTTP 409; normal startup creates the new fingerprint table, while formal migrations remain a production follow-up.

## 6. Transactional outbox instead of direct side effects

**Context:** Item creation/status changes may later trigger notifications. Sending a notification before committing can announce changes that roll back; sending afterward can be lost if the process crashes.  
**Options considered:** Send inline; use a broker immediately; persist an outbox row in the same transaction and process it asynchronously.  
**Choice:** The API writes an outbox job alongside the item change. A small worker polls pending jobs, processes persisted jobs; the unique event key prevents duplicate outbox rows, and tracks attempts/status.  
**Trade-off:** The included handler only logs simulated notifications, and the single-process worker is deliberately simple. Production requires multi-worker locking, stuck-job recovery, scheduled backoff, metrics, and a real delivery provider.

## 7. Server-side filtering and pagination

**Context:** The system may contain many thousands of work items; fetching all records to the browser is inefficient and leaks unrelated team data.  
**Options considered:** Client-side filtering; unbounded API lists; indexed server-side filtering with bounded pagination.  
**Choice:** The list endpoint scopes queries to the user's team IDs, supports search/status/priority/assignee/team filters, and applies a bounded page size. Frequently filtered columns are indexed.  
**Trade-off:** Offset pagination is simple and familiar but can become expensive at very large offsets; cursor/keyset pagination and PostgreSQL full-text search are sensible next steps.

## 8. Deliberately excluded scope

Email delivery, SSO, file attachments, WebSockets, mobile applications, signup/password reset, and elaborate animation are excluded to keep the core workflow correct and explainable within the challenge's 8–10 focused-hour budget.
