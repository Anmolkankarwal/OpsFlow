# OpsFlow Requirements Compliance

Audit date: 2026-10-18. Status reflects repository inspection and the checks run in this workspace. `PASS` means the behavior is present in source and the cited evidence is adequate for this audit; `FAIL` means the implementation contradicts the requirement; `BLOCKED` means it could not be verified because a required tool/environment is unavailable; `PARTIAL` means a material gap remains; `MISSING` means no implementation was found.

| Requirement | Status | Evidence and notes |
|---|---|---|
| Seed users, teams, and per-team roles | PASS | `backend/app/main.py` (`seed_demo`, `User`, `Team`, `Membership`); five users and three teams are seeded with different memberships. |
| Authentication | PARTIAL | `backend/app/main.py` (`login`, `current_user`, `make_token`, `decode_token`). Login rejects inactive users; `test_inactive_user_cannot_log_in` verifies this. Token expiry behavior still lacks a regression test. |
| Server-enforced team/resource authorization | PASS | `backend/app/main.py` (`membership`, `require_item`, protected item/activity/comment routes); `test_login_and_team_scoped_authorization` and `test_cross_team_user_cannot_write_or_read_item_history` cover cross-team reads, edits, comments, and activity. |
| Work-item fields and CRUD | PASS | `backend/app/main.py` (`WorkItem`, `CreateItem`, `UpdateItem`, create/list/detail/update routes). Creation and update behavior are exercised by the API tests. |
| Search, filtering, and pagination | PASS | `backend/app/main.py::list_items` applies team scope, filters, count, offset, and bounded page size in SQL. `test_search_and_pagination_are_server_side` verifies bounded pages and search results. Frontend passes query filters and page state in `frontend/src/App.tsx`. |
| Assigned-to-me dashboard view | PASS | `backend/app/main.py::dashboard`; frontend list filter sets `mine=true` in `frontend/src/App.tsx`. |
| Unassigned urgent dashboard view | PASS | `backend/app/main.py::dashboard`; frontend filters `priority=Urgent` and `assignee_id=0` in `frontend/src/App.tsx`. |
| Awaiting my approval view | PASS | `backend/app/main.py` restricts the query to teams where the user has Lead/Admin membership; `frontend/src/App.tsx` uses the server-filtered view. `test_member_cannot_approve_or_see_approval_queue` verifies Member queue denial and approval denial. |
| Dashboard summary counts | PASS | `frontend/src/App.tsx` calculates visible status/priority cards from the loaded page and labels them “On this page” / “in view,” matching the requirement to identify page-level counts. |
| Atomic concurrent claiming | PASS | `backend/app/main.py::claim_item` uses a conditional SQL update on unassigned status and version. `test_concurrent_claims_have_exactly_one_winner` issues synchronized requests from two clients and verifies one success and one HTTP 409. Test DB is SQLite; PostgreSQL Compose behavior remains unverified. |
| Optimistic locking and stale conflicts | PASS | `backend/app/main.py` (`update_item`, `transition_item`) performs conditional version increments and returns HTTP 409. `test_stale_update_is_rejected` and `test_concurrent_updates_reject_one_stale_version` cover sequential and synchronized simultaneous updates. PostgreSQL Compose behavior remains unverified. |
| Idempotent create requests | PASS | `backend/app/main.py::create_item` stores a canonical-request SHA-256 fingerprint with the unique key and returns HTTP 409 on a different payload. `test_idempotent_create_returns_same_item` and `test_idempotency_key_rejects_a_different_payload` cover replay and key mismatch. |
| Server-enforced workflow and Lead/Admin approval gate | PASS (SQLite API tests) | `backend/app/main.py::transition_item` restricts both approval (`Awaiting Approval → Resolved`) and rejection (`Awaiting Approval → In Progress`) to Lead/Admin membership in the item's team, rejects decisions on ineligible states, and writes `approval_approved` / `approval_rejected` activity events. Regression tests cover Lead and Admin approval, Lead rejection, Member direct-transition bypass denial, ineligible-state rejection, and activity history. Live PostgreSQL/Compose verification remains BLOCKED in this workspace because Docker is unavailable. |
| Activity and comments | PARTIAL | `backend/app/main.py` writes activity in item mutation transactions and tracks comments; `test_item_changes_and_comments_create_activity_events` checks generated event content, and the cross-team authorization test checks comment denial. Crash/rollback atomicity under a failed transaction is not directly tested. |
| PostgreSQL transactional outbox and polling worker | PARTIAL | `backend/app/main.py` creates outbox jobs with item changes; `backend/app/worker.py` polls and retries with a cap. Delivery is simulated by logging, and multiple-worker locking/stuck-job recovery are not implemented or verified. |
| Automated critical-behavior tests | PASS | `backend/tests/test_critical_behaviors.py` has 20 API tests, including synchronized API-level claim/update races, idempotency, approval authorization/decisions, cross-team write/history denial, inactive login, workflow, pagination/search, and activity/comment behavior. Latest full run: `20 passed`. |
| React/TypeScript production build | PASS | Initial build failed due to missing React/Vite types and ES2020 library mismatch. Added React type dependencies, `frontend/src/vite-env.d.ts`, and ES2021 target. `npm run build` then passed and emitted `frontend/dist`. |
| Docker Compose startup and PostgreSQL integration | BLOCKED | `docker compose up --build` was attempted but the `docker` command is not installed/available. The Compose file defines PostgreSQL, API, worker, and frontend services, but startup, persistence, and critical flows against PostgreSQL are not verified. |
| README, engineering decisions, known limitations | PASS | `README.md` contains setup, credentials, tests, and limitations; `ENGINEERING_DECISIONS.md` documents architecture and trade-offs. |
| Example environment file without real secrets | PASS | `.env.example` contains replacement placeholders and `.gitignore` excludes `.env`. Compose still supplies fallback development secrets if a local `.env` is omitted. |
| Reproducible frontend dependency install and security audit | PASS | `frontend/package-lock.json` is present and `frontend/Dockerfile` uses `npm ci`. npm audit initially identified a high-severity Vite advisory; Vite was updated to 6.4.4. Final `npm audit` reported `found 0 vulnerabilities`, and the frontend build passed on 6.4.4. |

## Verification record

- Backend: `backend/.venv/Scripts/python.exe -m pytest -q` — **14 passed**, with three dependency/framework deprecation warnings.
- Concurrency repeat: claim and update race tests — **2 passed per run for five consecutive runs**.
- Frontend: `npm run build` from `frontend/` — **passed** on Vite 6.4.4.
- Frontend dependencies: `npm audit` — **0 vulnerabilities**.
- Local browser smoke test against SQLite: login, item creation, claim, transition to In Progress, and comment creation all succeeded; the UI showed the updated assignee, version, activity entries, and comment.
- Compose configuration: YAML parsing passed; expected `db`, `api`, `worker`, `frontend` services and named Postgres volume are present. Docker CLI validation remains blocked.
- Docker Compose: **BLOCKED**; `docker compose up --build` was attempted, but the Docker executable is unavailable.
- Git status: **BLOCKED**; neither `opsflow` nor its parent directory is a Git repository, so tracked/staged changes and repository diff could not be inspected.

## Highest-priority remaining work

1. Run Compose with PostgreSQL on a machine with Docker Desktop and verify the critical end-to-end workflows against PostgreSQL.
2. Review whether local Compose fallback secrets should be removed or replaced with required `.env` values before submission.
