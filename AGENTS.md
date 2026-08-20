# AGENTS.md — Healthcare Appointment & Follow-up Manager

> **Workspace Guidelines, Architecture Reference, and Invariants for AI Coding Agents**

---

## 1. Project Overview & Core Mission

The **Healthcare Appointment & Follow-up Manager** is an intelligent clinical workflow platform engineered to solve real-world healthcare scheduling bottlenecks (unpredictable consultation times, walk-in vs. advance booking friction, post-visit compliance, and emergency triage).

### Core Problem Solved
Traditional clock-time booking fails in clinics because consultation durations vary widely. This platform replaces rigid clock-time slots with an **intelligent, token-based hybrid queue engine** backed by:
- Automated AI pre-visit clinical triage (symptom intake & urgency scoring).
- Real-time delay detection and dynamic ETA recalculation.
- Post-visit clinical summarization and structured medication reminder scheduling.
- Dual-channel notifications (WhatsApp for real-time alerts, Email for formal records).
- Dual-calendar syncing via Google Calendar OAuth 2.0.

---

## 2. Technology Stack & Infrastructure

- **Backend:** Python 3.14+ (FastAPI + Pydantic v2 + SQLAlchemy 2.0 Async + `asyncpg`) adhering to PEP 8
- **Package Manager:** `uv`
- **Logging & Observability:** `rich.logging.RichHandler` + standard `logging` with structured contextual metadata and trace IDs
- **Resilient Retries:** **`tenacity`** for robust exponential backoff, jitter, and error-intercepting retry loops across LLM calls, notifications, and calendar syncs
- **Database:** PostgreSQL (Hosted on Railway) with ACID transactions & `SERIALIZABLE` isolation
- **Frontend:** React (Vite) + Tailwind CSS (Patient Portal, Doctor Dashboard, Admin Control Center)
- **Queue / Background Workers:** Celery / AsyncIO BackgroundTasks / `node-cron` for delay monitoring, notification retries, and medication alerts
- **AI / Structured Extraction:** **`instructor`** + Pydantic v2 for schema-enforced, type-safe multi-provider LLM routing (**Groq, Azure OpenAI, Google Gemini, OpenAI, Anthropic**)
- **Dual-Channel Notifications:**
  - **WhatsApp (Twilio):** Real-time queue delay alerts, token approach pings, interactive response (`SHIFT` / `RESCHEDULE`)
  - **Email (SMTP / SendGrid):** Booking confirmations, post-visit reports, cancellations
- **Calendar:** Google Calendar API via OAuth 2.0 with encrypted token storage

---

## 3. Documentation Index

Before modifying or implementing any feature, agents **must** consult the relevant specifications in [`docs/`](./docs):

| Document | Purpose |
| :--- | :--- |
| [`docs/01-requirements.md`](./docs/01-requirements.md) | Functional/non-functional requirements, RBAC matrix, and SLA targets |
| [`docs/02-system-architecture.md`](./docs/02-system-architecture.md) | System components, LLM router flow, and notification pipelines |
| [`docs/03-database-architecture.md`](./docs/03-database-architecture.md) | Normalized PostgreSQL schema DDL, indexes, and constraints |
| [`docs/04-scheduling-and-concurrency.md`](./docs/04-scheduling-and-concurrency.md) | `getNextToken()` engine, race condition mitigation, anchor slot rules |
| [`docs/05-api-specification.md`](./docs/05-api-specification.md) | Full RESTful API contracts, request/response schemas, and auth headers |
| [`docs/06-ai-llm-integration.md`](./docs/06-ai-llm-integration.md) | Prompt templates, JSON output schemas, timeout & fallback handling |
| [`docs/07-system-design-document.md`](./docs/07-system-design-document.md) | System design summary (800 words), concurrency & fault-tolerance model |
| [`docs/08-task-breakdown-and-roadmap.md`](./docs/08-task-breakdown-and-roadmap.md) | Implementation roadmap from Phase 1 to Phase 6 |
| [`docs/09-phase-2-3-finalized-design.md`](./docs/09-phase-2-3-finalized-design.md) | Finalized design choices for Phase 2 backend & Phase 3 frontend portals |

---

## 4. Key Architectural Invariants & Non-Negotiable Rules

Agents must preserve the following core design invariants across all implementations:

### Invariant 1: `token_number` vs. `display_position`
- **`token_number`** is an **immutable, permanent identifier** assigned at booking time. It **MUST NEVER** be used to infer serving order.
- **`display_position`** is the **dynamic, live serving order** shown to patients, recalculated by `getNextToken()` on every queue event (consultation completion, emergency triage insertion, anchor slot trigger, delay reflow).

### Invariant 2: Concurrency & Double-Booking Prevention
- Token booking (`POST /queue/book`) **MUST ALWAYS** run inside a `SERIALIZABLE` transaction with `SELECT ... FOR UPDATE` on the queue for that `(doctor_id, appointment_date, session)`.
- Unique constraint enforced in DB: `UNIQUE (doctor_id, appointment_date, session, token_number)`.

### Invariant 3: Queue Serving Algorithm (`getNextToken`)
Whenever a doctor clicks **"Complete & Call Next"**, the backend selects the next token using strict priority:
1. **Emergency Tier:** Any waiting patient in `emergency` tier is served immediately (inserted at `current_serving_token + 1`).
2. **Anchor Slots:** Any `anchor` slot whose `anchor_time` has arrived (within grace window) is pulled forward if behind schedule, but held (not served prematurely) if the doctor is running ahead.
3. **Priority Tier:** Served at the configured ratio (e.g., 1-in-4) among waiting patients.
4. **Regular Open Queue:** Strict First-Come, First-Served (FCFS) order based on `booked_at`.

### Invariant 4: Resilient AI Pipeline (`instructor` + Pydantic + `tenacity` + `logging`)
- All LLM structured extractions use **`instructor`** wrapped around target providers with Pydantic response models.
- All LLM and external integration calls are guarded with **`tenacity`** retry policies:
  - Strict **5-second per-attempt timeout** (`stop=stop_after_attempt(2)` or `stop_after_delay(5)`).
  - Exponential backoff with jitter (`wait=wait_random_exponential(multiplier=1, max=4)`).
  - Explicit retry logging before each attempt (`before_sleep=before_sleep_log(logger, logging.WARNING)`).
- If retries are exhausted, log structured error to `llm_call_log`, set `is_processed = false`, and **never block** appointment booking or doctor note submission. Raw doctor clinical notes and raw symptom text must remain fully accessible.

### Invariant 5: Actionable Notification Copy
- WhatsApp messages must be informative and actionable (e.g., provide explicit estimated delay, updated ETA, and options to reply `SHIFT` to move later same day or `RESCHEDULE` for a future date).
- Email notifications must contain full structured summaries and formal records.

---

## 5. Centralized Error Handling & Domain Fallback Matrix

To guarantee clinical safety and 99.9% operational uptime, every subsystem must strictly enforce its designated fallback strategy:

| Subsystem | Failure Trigger | Retries (`tenacity`) | Fallback Strategy | Blocking? |
| :--- | :--- | :--- | :--- | :--- |
| **AI Pre-Visit Triage** | Provider down, timeout (>5s), schema parse error | 2 attempts with jitter | Mark `is_processed=False`, log to `llm_call_log`, default `urgency_level='medium'`, display raw symptom text to doctor | ❌ **Non-blocking** |
| **AI Post-Visit Notes** | Provider down, timeout (>5s), rate limit | 2 attempts with jitter | Mark `is_processed=False`, log to `llm_call_log`, preserve raw clinical notes for patient & doctor, skip auto-reminder generation | ❌ **Non-blocking** |
| **Token Booking Concurrency** | Race condition, DB serialization collision | 3 attempts with exponential backoff | Roll back transaction, refetch next available token, retry `SELECT ... FOR UPDATE` | ⚠️ **Internal Retry** (Raises `409 Conflict` only on 3 exhausted retries) |
| **WhatsApp Notification** | Twilio API error, invalid phone, rate limit | 3 attempts with exponential backoff | Log error, downgrade/fallback to Email dispatch, record `status='failed'` in `notifications` | ❌ **Non-blocking** |
| **Email Notification** | SMTP connection drop, SendGrid timeout | 3 attempts with exponential backoff | Record in `notifications` with `status='pending'` for asynchronous background worker retry | ❌ **Non-blocking** |
| **Google Calendar Sync** | OAuth expired, Google API rate limit | 2 attempts after auto-refresh token | Record error in `calendar_events.sync_error`, continue queue booking flow | ❌ **Non-blocking** |
| **Missing/Corrupt Input Data** | Required field missing, invalid enum | None | **Strict stop-and-reject**: Raise explicit `422 Unprocessable Entity` or domain validation error; **NEVER** substitute fake mock data | 🛑 **Blocking (Client Error)** |

---

## 6. Database Schema Summary (PostgreSQL)

The database consists of 9 core tables:

1. **`users`**: System accounts (`patient`, `doctor`, `admin`) with bcrypt password hash, phone, and WhatsApp numbers.
2. **`doctors`**: Doctor profiles, specialisation, rolling `avg_consult_minutes`, `booking_mode` (`walk_in`, `advance_only`, `hybrid`), and slot percentage configurations (`anchor_slot_pct`, `priority_slot_pct`, `emergency_slot_pct`).
3. **`doctor_availability` & `doctor_leave`**: Session schedules (morning/evening) and approved leave ranges with auto-conflict triggers.
4. **`doctor_queue`**: Core token state (`token_number`, `display_position`, `tier`, `slot_type`, `anchor_time`, `status`, `booking_mode_used`, timestamps).
5. **`urgency_escalation_log`**: Audit trail of manual or AI-driven tier changes.
6. **`delay_events`**: Doctor delay tracking (`delay_minutes`, `detected_at`, `notified`).
7. **`symptoms` & `post_visit_notes`**: AI pre-visit triage output (`urgency_level`, `ai_summary`) and post-visit clinical notes + structured prescription JSON.
8. **`medications` & `medication_reminders`**: Normalized prescription items and scheduled reminder jobs.
9. **`notifications`, `calendar_events`, `oauth_tokens`, `llm_call_log`**: Integration tracking, OAuth credentials, and observability.

---

## 6. Development & Coding Conventions

### Backend Guidelines
- Strictly adhere to **PEP 8** standards (formatted with `ruff` / `black`).
- Use **Pydantic v2** for all request/response models and environment validation (`pydantic-settings`).
- Use **`rich`** logger (`rich.logging.RichHandler`) for all console logs.
- Use explicit async database transactions (`async with session.begin():`) with pessimistic locking for queue mutations.
- **No Mock Code Policy:** Real validation and integration handlers. If any required data is missing, stop, log clearly, and invoke designated fallback handlers or ask rather than silently continuing with fake data.

### Frontend Guidelines
- Build responsive, clean, and modern interfaces with **Tailwind CSS**.
- **Patient Portal:** Live queue tracking using lightweight polling (`GET /queue/:id/status` every 15–30s).
- **Doctor Portal:** Streamlined dashboard with a single primary action: **"Complete & Call Next"**.
- **Admin Portal:** Single unified doctor management dashboard showing live delays, capacity split, and SLA breach indicators.

### Testing Priorities (`pytest`)
- Unit tests for queue prioritization algorithms and mathematical drift detection.
- Scenario-based end-to-end tests:
  - Real concurrent token booking race conditions (verifying `SERIALIZABLE` isolation).
  - `getNextToken()` priority ordering (Emergency $\rightarrow$ Anchor $\rightarrow$ Priority $\rightarrow$ FCFS).
  - Multi-provider LLM failure simulations and non-blocking fallback handling with `instructor`.
  - Doctor leave conflict auto-cancellation and notification dispatch.

### Repository Hygiene, Git & Documentation Invariants
- **`.gitignore` Maintenance:** Always keep `.gitignore` strictly updated. Never commit `.env`, secrets, Python `__pycache__`, `.pytest_cache`, `.ruff_cache`, `venv`, coverage artifacts, or build bundles.
- **Git History Readiness:** Maintain clean, atomic commits with descriptive semantic commit messages (e.g., `feat(queue): implement get_next_token priority engine`, `test(concurrency): add serializable race condition test`).
- **Continuous README Updates:** Keep root `README.md` and `docs/README.md` up-to-date whenever new modules, endpoints, dependencies, or architectural decisions change.

---

## 7. Useful Commands (Reference)

```bash
# Package & Environment Management (using uv)
uv venv
uv pip install -e ".[dev]"

# Backend Server
uv run uvicorn src.main:app --reload --port 8000

# Database Migrations (Alembic)
uv run alembic upgrade head
uv run python -m src.scripts.seed_db

# Testing & Linting
uv run pytest -v
uv run ruff check .
uv run ruff format --check .

# Docker Deployment
docker compose up --build
```
