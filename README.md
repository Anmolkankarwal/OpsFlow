# OpsFlow — Team Operations Hub

OpsFlow is a full-stack internal work-management app for teams to create, assign, track, and resolve operational work items. It includes team-scoped roles, a server-filtered dashboard, a controlled workflow, append-only activity history, comments, optimistic version checks, idempotent create requests, and a PostgreSQL outbox worker.

> **Challenge context:** Newtonite Software Engineering Challenge — “Operations Under Pressure”. Built as an individual learning/demo project. Review every implementation decision and be ready to explain it in the live discussion.

## Features

- Login with seeded demo accounts; signed bearer tokens expire after 12 hours.
- Team-scoped roles: Viewer, Member, Lead, Admin. Authorization is checked by the API, not only in the UI.
- Create and search/filter work items, with server-side pagination.
- Dashboard views: Assigned to me, Unassigned urgent, Awaiting my approval (limited to teams where the user is a Lead/Admin).
- Workflow: `Open → In Progress → Awaiting Approval → Resolved → Closed`; only a Lead/Admin can approve `Awaiting Approval → Resolved`.
- Atomic claim operation; only one user can claim an unassigned item.
- Optimistic concurrency via a `version` field and HTTP `409 Conflict` for stale edits/transitions.
- `Idempotency-Key` support on create requests.
- Activity events are written in the same transaction as the item change; comments are also tracked.
- Transactional outbox table and polling worker with retry cap. Current handler logs the event instead of sending a real notification.
- Automated API tests for idempotency, simultaneous claims/updates, workflow rules, team authorization, inactive users, viewer permissions and approval scoping.

## Run with Docker Compose (recommended)

Prerequisites: Docker Desktop with Compose enabled.

1. From the extracted `opsflow` folder, create the local environment file and set local secrets:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

2. From that same folder run:

   ```powershell
   docker compose up --build
   ```

3. Open the frontend at `http://localhost:5173` and API docs at `http://localhost:8000/docs`.
4. Load demo data once by opening Swagger (`/docs`) and calling `POST /api/dev/seed`, or use PowerShell:

   ```powershell
   Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/dev/seed
   ```

   If the database already contains data, the endpoint returns “Seed data already exists”.

## Run locally without Docker

Prerequisites: Python 3.12+, Node.js 20+, and PostgreSQL 16 (or use SQLite for local API development).

Backend, from `backend/`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./opsflow.db"
$env:SECRET_KEY = "local-development-secret-change-me"
uvicorn app.main:app --reload
```

In a second terminal, call `POST http://localhost:8000/api/dev/seed`.

Frontend, from `frontend/`:

```powershell
npm ci
$env:VITE_API_URL = "http://localhost:8000"
npm run dev
```

Open `http://localhost:5173`.

## Demo accounts

| Role | Email | Password | Team access |
|---|---|---|---|
| Admin | `admin@opsflow.local` | `Admin123!` | All teams |
| Lead | `lead@opsflow.local` | `Lead123!` | Operations |
| Member | `member@opsflow.local` | `Member123!` | Operations |
| Viewer | `viewer@opsflow.local` | `Viewer123!` | Operations (read-only) |
| Other-team member | `other@opsflow.local` | `Other123!` | Customer Support |

These are local demo credentials only. Do not use them in production. The seed endpoint is enabled by default for the challenge; set `DISABLE_DEV_SEED=1` on the API to disable it.

## API overview

- `POST /api/auth/login`, `GET /api/auth/me`
- `GET /api/teams`, `GET /api/dashboard`
- `POST /api/items` (supports `Idempotency-Key`)
- `GET /api/items?q=&status=&priority=&team_id=&mine=&unassigned=&awaiting_my_approval=&page=&page_size=`
- `GET /api/items/{id}`, `PATCH /api/items/{id}` (requires `version`)
- `POST /api/items/{id}/claim`
- `POST /api/items/{id}/transition` (requires `version`)
- `GET /api/items/{id}/activity`, `GET/POST /api/items/{id}/comments`
- `GET /api/admin/outbox` (Admin only)
- `GET /health`

## Run tests

From `backend/`:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

The suite currently has 14 API tests, including synchronized concurrent claims and updates. Tests use a dedicated SQLite test database and reset its tables between tests. The app's production database configuration is independent. Run the frontend production build from `frontend/` with `npm ci` followed by `npm run build`.

## Engineering decisions

See [`ENGINEERING_DECISIONS.md`](ENGINEERING_DECISIONS.md) for context, alternatives, choices, and trade-offs.

See [`REQUIREMENTS_COMPLIANCE.md`](REQUIREMENTS_COMPLIANCE.md) for the current requirement-by-requirement status and verification record.

## Known limitations

- The seed endpoint is intended only for local/demo use and must be disabled in production.
- Authentication is a compact custom HMAC bearer-token implementation for this bounded demo; use a vetted OAuth2/OIDC provider and a maintained JWT library in a production service.
- The outbox worker is a simple single-process poller. It logs a simulated notification; it does not send email or push messages. Multiple workers need PostgreSQL `FOR UPDATE SKIP LOCKED`, lease recovery for stuck `processing` jobs, and monitoring.
- The current worker has a bounded retry policy but does not yet implement durable exponential-backoff scheduling in the database.
- ORM schema is created on application startup for this MVP; formal Alembic migrations should be added before production use.
- There is no user-management UI, password-reset flow, signup, SSO, file attachments, real-time WebSockets, or mobile client, intentionally matching the challenge's scope.
- The dashboard stat cards count the currently loaded page for some status metrics, not a separate all-record aggregate endpoint.
- Seed data is small; pagination is server-side, but a large-scale load benchmark has not been run.
- CSS imports Google Fonts from the network; a disconnected demo falls back to system sans-serif fonts.
- The app has not been security-audited or tested under production concurrency/load. Review and test it before deployment.

## Suggested demo flow (3–5 minutes)

1. Sign in as Admin and show the dashboard/filtering.
2. Create a work item and point out the generated `Idempotency-Key`.
3. Open an item and show its activity history; add a comment.
4. Claim an unassigned item as Member; explain that the API uses a conditional update.
5. Attempt a stale edit from an old version (or demonstrate through `/docs`) and show `409`.
6. Show a forbidden Viewer mutation and a Lead approval transition.
7. Explain the outbox worker, tests, trade-offs, and known limitations honestly.
