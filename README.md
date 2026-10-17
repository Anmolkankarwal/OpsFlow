# ⚡ OpsFlow — Team Operations Hub

### From operational chaos to organized execution.

**OpsFlow** is a full-stack work management platform designed to help teams create, assign, track, and resolve operational tasks with confidence. Built for the *Newtonite Software Engineering Challenge — Operations Under Pressure*, it focuses on reliable workflows, team-level authorization, concurrent updates, and transparent activity history.

> 🚀 **The goal:** Build a system that doesn't just manage tasks, but handles the real-world problems that make operational work difficult.

- Login with seeded demo accounts; signed bearer tokens expire after 12 hours.
- Team-scoped roles: Viewer, Member, Lead, Admin. Authorization is checked by the API, not only in the UI.
- Create and search/filter work items, with server-side pagination.
- Dashboard views: Assigned to me, Unassigned urgent, Awaiting my approval (limited to teams where the user is a Lead/Admin).
- Workflow: `Open → In Progress → Awaiting Approval → Resolved → Closed`; only a Lead/Admin in the item's team can approve (to `Resolved`) or reject (back to `In Progress`). The detail panel exposes explicit review actions, and the API records each decision in activity history.
- Atomic claim operation; only one user can claim an unassigned item.
- Optimistic concurrency via a `version` field and HTTP `409 Conflict` for stale edits/transitions.
- `Idempotency-Key` support on create requests.
- Activity events are written in the same transaction as the item change; comments are also tracked.
- Transactional outbox table and polling worker with retry cap. Current handler logs the event instead of sending a real notification.
- Automated API tests for idempotency, simultaneous claims/updates, workflow rules, team authorization, inactive users, viewer permissions and approval scoping.
<p align="center">

  <img src="https://img.shields.io/badge/Status-Working%20MVP-success?style=for-the-badge" alt="Working MVP" />
  <img src="https://img.shields.io/badge/Backend-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Frontend-React-61DAFB?style=for-the-badge&logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/Database-PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Containerized-Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />

</p>

---

## 📌 Table of Contents

- [🎯 Why OpsFlow?](#-why-opsflow)
- [✨ Key Features](#-key-features)
- [🔄 Workflow](#-workflow)
- [🏗️ Architecture](#️-architecture)
- [🛠️ Technology Stack](#️-technology-stack)
- [🚀 Getting Started](#-getting-started)
- [🔐 Demo Accounts](#-demo-accounts)
- [🔌 API Overview](#-api-overview)
- [🧪 Testing](#-testing)
- [🧠 Engineering Decisions](#-engineering-decisions)
- [⚠️ Known Limitations](#️-known-limitations)
- [🎬 Suggested Demo](#-suggested-demo)

---

## 🎯 Why OpsFlow?

As organizations grow, operational work often becomes scattered across chats, emails, spreadsheets, and informal conversations.

This creates challenges:

- 🔎 **Low visibility:** Important requests get buried in conversations.
- 👥 **Unclear ownership:** Multiple people may start working on the same task.
- 🔒 **Permission risks:** Not everyone should be allowed to perform every action.
- 🔄 **Conflicting updates:** Users may overwrite newer changes with stale information.
- 🧾 **Limited accountability:** It can be difficult to understand who changed what and why.

**OpsFlow brings these workflows into one place** with explicit ownership, controlled transitions, server-side authorization, and traceable activity.

## ✨ Key Features

### 📋 Work Management
- Create, assign, update, search, and resolve operational work items.
- Filter items by status, priority, team, and ownership.
- Use server-side pagination instead of loading the entire dataset into the browser.
- View work assigned to you, urgent unassigned items, and approvals awaiting your attention.

### 🛡️ Team-Based Authorization
- Four roles: **Viewer, Member, Lead, and Admin**.
- Enforce permissions at the API level, not merely through frontend controls.
- Restrict approval actions to authorized Leads and Admins.
- Validate team access and inactive-user restrictions.

### 🔄 Controlled Workflow
- Enforce valid work-item state transitions.
- Require Lead/Admin approval before moving an item from `Awaiting Approval` to `Resolved`.
- Prevent unauthorized transitions through backend validation.

### ⚡ Concurrency & Reliability
- **Atomic claiming:** Prevent multiple users from successfully claiming the same unassigned item.
- **Optimistic concurrency:** Use version checks to reject stale updates with HTTP `409 Conflict`.
- **Idempotent creation:** Support `Idempotency-Key` to prevent duplicate items when a create request is retried.
- **Transactional activity history:** Store important activity events in the same transaction as the corresponding item change.

### 💬 Collaboration & Auditability
- Add comments to work items.
- Track important changes through an append-only activity history.
- Inspect previous actions to understand how a task evolved.

### 🔔 Asynchronous Processing
- Use a PostgreSQL transactional outbox to record events for background processing.
- Process pending events through a polling worker with a bounded retry policy.
- Keep secondary processing separate from the primary request.

> ℹ️ The current worker logs simulated notifications. It does not send real emails or push notifications.

---

## 🔄 Workflow

OpsFlow uses a controlled workflow to keep operational work organized.

```text
        ┌──────────┐
        │   Open   │
        └────┬─────┘
             ▼
      ┌─────────────┐
      │ In Progress │
      └──────┬──────┘
             ▼
   ┌───────────────────┐
   │ Awaiting Approval │
   └─────────┬─────────┘
             │ Lead / Admin approval
             ▼
       ┌──────────┐
       │ Resolved │
       └────┬─────┘
            ▼
       ┌──────────┐
       │  Closed  │
       └──────────┘
```

Transitions are validated by the API, so users cannot bypass workflow rules simply by modifying the frontend.

## 🏗️ Architecture

```text
┌─────────────────────┐
│   React Frontend    │
│ Dashboard & Work UI │
└──────────┬──────────┘
           │ HTTP / Bearer Token
           ▼
┌─────────────────────┐
│    FastAPI Backend  │
│ Auth • Permissions  │
│ Workflow • Versions │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│     PostgreSQL      │
│ Work Items • Teams  │
│ Activity • Outbox   │
└──────────┬──────────┘
           │ Pending Events
           ▼
┌─────────────────────┐
│ Background Worker   │
│ Poll • Process      │
│ Retry • Log         │
└─────────────────────┘
```

### 🔍 Important Design Choices

| Concern | Approach |
|---|---|
| Authorization | Team-scoped role checks in the API |
| Concurrent edits | Version-based optimistic concurrency |
| Task claiming | Atomic conditional database update |
| Duplicate requests | Idempotency keys on item creation |
| Audit history | Activity events persisted transactionally |
| Background work | PostgreSQL transactional outbox |
| Data retrieval | Server-side search, filters, and pagination |

---

## 🛠️ Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React, TypeScript, Vite |
| Backend | Python, FastAPI |
| Database | PostgreSQL 16 |
| Background processing | Python worker, PostgreSQL outbox |
| Containerization | Docker, Docker Compose |
| API documentation | OpenAPI / Swagger UI |
| Testing | Pytest, SQLite test database |

---

## 🚀 Getting Started

The quickest way to run OpsFlow is with Docker Compose.

### Prerequisites

- Docker Desktop
- Docker Compose enabled
- Git

### 1. Clone the repository

```bash
git clone https://github.com/Anmolkankarwal/OpsFlow.git
cd OpsFlow
```

### 2. Configure environment variables

In PowerShell:

```powershell
Copy-Item .env.example .env
notepad .env
```

Update the local environment variables as required by the project configuration.

> 🔐 Keep `.env` private. Never commit passwords, API keys, or production credentials.

### 3. Build and start the application

```powershell
docker compose up --build
```

Docker Compose starts the frontend, API, database, and background worker.

### 4. Initialize demo data

In a separate PowerShell terminal:

```powershell
Invoke-RestMethod -Method Post -Uri http://localhost:8000/api/dev/seed
```

The seed endpoint creates demo data if the database is empty. It may report that seed data already exists if initialization has already happened.

### 5. Open the application

| Service | URL |
|---|---|
| 🖥️ Frontend | http://localhost:5173 |
| 📚 API Documentation | http://localhost:8000/docs |
| ❤️ Health Check | http://localhost:8000/health |

---

## 🔐 Demo Accounts

Use the following accounts to explore role-based behavior locally.

| Role | Email | Password | Access |
|---|---|---|---|
| 👑 Admin | `admin@opsflow.local` | `Admin123!` | All teams |
| 🧭 Lead | `lead@opsflow.local` | `Lead123!` | Operations |
| 👤 Member | `member@opsflow.local` | `Member123!` | Operations |
| 👁️ Viewer | `viewer@opsflow.local` | `Viewer123!` | Operations, read-only |
| 👥 Other-team Member | `other@opsflow.local` | `Other123!` | Customer Support |

These are **local demo credentials only**. Never use them in production.

The development seed endpoint is enabled by default for this challenge. Disable it outside local/demo use by configuring `DISABLE_DEV_SEED=1` for the API.

---

## 🔌 API Overview

| Method | Endpoint | Purpose |
|---|---|---|
| `POST` | `/api/auth/login` | Authenticate a user |
| `GET` | `/api/auth/me` | Retrieve current-user information |
| `GET` | `/api/teams` | List accessible teams |
| `GET` | `/api/dashboard` | Retrieve dashboard information |
| `POST` | `/api/items` | Create a work item; supports idempotency |
| `GET` | `/api/items` | Search, filter, and paginate items |
| `GET` | `/api/items/{id}` | Retrieve a work item |
| `PATCH` | `/api/items/{id}` | Update an item with a version check |
| `POST` | `/api/items/{id}/claim` | Atomically claim an unassigned item |
| `POST` | `/api/items/{id}/transition` | Validate and apply a workflow transition |
| `GET` | `/api/items/{id}/activity` | Retrieve item activity history |
| `GET` / `POST` | `/api/items/{id}/comments` | Read or add comments |
| `GET` | `/api/admin/outbox` | Inspect outbox events; Admin only |
| `GET` | `/health` | Check API health |

For interactive API exploration, open [Swagger UI](http://localhost:8000/docs) after starting the application.

---

## 🧪 Testing

OpsFlow includes automated API tests focused on correctness and authorization.

### Current test coverage

- ✅ Idempotent item creation
- ✅ Simultaneous item claims
- ✅ Concurrent and stale updates
- ✅ Workflow transition validation
- ✅ Team-scoped authorization
- ✅ Inactive-user restrictions
- ✅ Viewer permission enforcement
- ✅ Approval access scoping

The current suite contains **14 API tests**, using a dedicated SQLite test database with tables reset between tests.

### Run backend tests

From the `backend/` directory:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
```

The suite currently has 20 API tests, including approval/rejection authorization and activity history, plus synchronized concurrent claims and updates. Tests use a dedicated SQLite test database and reset its tables between tests. The app's production database configuration is independent. Run the frontend production build from `frontend/` with `npm ci` followed by `npm run build`.
### Build the frontend

From the `frontend/` directory:

```powershell
npm ci
npm run build
```

> 📌 The test count and behaviors above describe the current project documentation. Run the commands to verify the current result in your environment.

---

## 🧠 Engineering Decisions

This project emphasizes engineering judgment over feature count.

The main design decisions include:

1. **Authorization at the API level** — prevent unauthorized operations independently of frontend visibility.
2. **Optimistic concurrency** — detect stale edits instead of silently overwriting newer data.
3. **Atomic claiming and idempotency** — handle repeated requests and competing users deliberately.
4. **Transactional activity and outbox records** — keep important event records consistent with database changes.
5. **Bounded asynchronous processing** — support background work while documenting retry and recovery limitations.

For the rationale, alternatives, and trade-offs, see [`ENGINEERING_DECISIONS.md`](ENGINEERING_DECISIONS.md).

For the requirement-by-requirement status, see [`REQUIREMENTS_COMPLIANCE.md`](REQUIREMENTS_COMPLIANCE.md).

---

## ⚠️ Known Limitations

OpsFlow is a working MVP and learning/demo project, not a production-hardened enterprise service.

- 🔐 Authentication uses a compact custom HMAC bearer-token implementation. Production deployments should use a vetted identity provider and maintained authentication libraries.
- 🔔 Notifications are simulated through logging; real email and push delivery are not implemented.
- 🔁 The worker uses simple polling and bounded retries. Multi-worker locking, lease recovery, monitoring, and durable exponential-backoff scheduling remain future improvements.
- 🗃️ ORM tables are created at application startup. Formal Alembic migrations are not yet implemented.
- 📊 Some dashboard status counts reflect the currently loaded page rather than a separate aggregate across all records.
- 📈 Server-side pagination is implemented, but large-scale load benchmarking has not been performed.
- 👥 Signup, password reset, SSO, user-management UI, file attachments, real-time WebSockets, and mobile support are outside the current scope.
- 🌐 Google Fonts are loaded over the network, with system-font fallbacks.
- 🛡️ The application has not undergone a formal security audit or production-scale concurrency test.

These limitations are documented intentionally to make the current scope and future engineering work clear.

---

## 🎬 Suggested Demo — 3 to 5 Minutes

Want to understand OpsFlow quickly? Follow this walkthrough:

1. 👑 **Sign in as Admin** and explore the dashboard and filters.
2. ➕ **Create a work item** and explain how `Idempotency-Key` helps with retries.
3. 🧾 **Open the activity timeline** and add a comment.
4. 👤 **Claim an unassigned task as Member** and explain the atomic database update.
5. ⚡ **Demonstrate a stale update** and inspect the `409 Conflict` response.
6. 🛡️ **Try a forbidden Viewer action** and show the API authorization behavior.
7. 🧭 **Approve a workflow transition as Lead** and explain the role restrictions.
8. 🔔 **Explain the outbox worker, automated tests, trade-offs, and known limitations.**

---

## 🚧 Future Improvements

Potential next steps include:

- 📬 Real notification delivery with reliable retry scheduling.
- 📊 Dedicated dashboard aggregate endpoints.
- 🧰 Database migrations and stronger integration-test coverage.
- 🔒 Production-grade identity and session management.
- 📈 Load testing and performance monitoring.
- 🔄 Multi-worker outbox processing with safe job claiming and recovery.

---

## 👨‍💻 Project Context

OpsFlow was built as an individual learning/demo project for the **Newtonite Software Engineering Challenge — Operations Under Pressure**.

The implementation is designed to demonstrate practical reasoning around authorization, concurrency, workflow correctness, auditability, and maintainability within a time-constrained engineering exercise.

**Built with a focus on reliable execution, not just task tracking.** ⚡

