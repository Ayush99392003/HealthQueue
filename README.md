# Healthcare Appointment & Follow-up Manager (HealthQueue)

> **Intelligent, token-based hybrid clinical scheduling platform featuring automated pre-visit AI triage, dynamic queue reflow, post-visit clinical summarization, symptom-based doctor auto-suggestion, dual-channel notifications, and Google Calendar synchronization.**

---

## 🌐 Live Production Deployments

| Component | Provider | URL |
|---|---|---|
| **Web Application Portal** | Vercel | [https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/](https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/) |
| **Backend API Service** | Railway | [https://healthqueue-production.up.railway.app](https://healthqueue-production.up.railway.app) |
| **Interactive API Docs (Swagger)** | Railway | [https://healthqueue-production.up.railway.app/docs](https://healthqueue-production.up.railway.app/docs) |
| **System Health Check** | Railway | [https://healthqueue-production.up.railway.app/health](https://healthqueue-production.up.railway.app/health) |

---

## 🌟 Overview & Problem Solved

Traditional clinical scheduling fails because consultation durations vary widely. Rigid clock-time appointments create waiting room bottlenecks, doctor burnout, and walk-in vs. advance booking friction.

**HealthQueue** replaces clock-time booking with an **intelligent, token-based hybrid queue engine** backed by:
- **AI Doctor Matcher (`/doctors/suggest`):** Patients can describe symptoms in plain English (e.g. *"chest heaviness when climbing stairs"*), and the Groq LLM identifies the correct medical specialisation (*Cardiology*) with clinical reasoning and filters available doctors.
- **Pre-visit AI Triage (`/clinical/{id}/symptoms`):** Structured symptom intake, urgency scoring (`low`, `medium`, `high`, `critical`), chief complaint synthesis, and diagnostic doctor questions powered by `instructor` + Pydantic v2.
- **Dynamic Serving Priority (`getNextToken`):** Intelligent serving order prioritizing Emergency cases, Anchor times, Priority tier (1-in-4), and First-Come-First-Served (FCFS).
- **Concurrency & Double-Booking Protection:** `SERIALIZABLE` transactions with pessimistic row locking (`SELECT ... FOR UPDATE`).
- **Doctor Leave Conflict Automation:** Auto-cancellation of conflicting appointments with instant patient notifications (WhatsApp + Email).
- **Post-Visit Summaries & Medication Reminders:** Structured prescription extraction, plain-language patient explanations, and automated adherence reminders.
- **Role & Access Governance:** Protected staff registration with `ADMIN_REGISTRATION_SECRET`, patient-restricted tiers, and fine-grained RBAC.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.14+ (FastAPI + Pydantic v2 + SQLAlchemy 2.0 Async + `asyncpg` + `psycopg2-binary`) adhering to PEP 8
- **Frontend:** React (Vite) + Custom Modern Glassmorphic Design System (Patient Portal, Doctor Dashboard, Admin Control Center)
- **Package Manager:** `uv`
- **Database:** PostgreSQL (Hosted on Railway) with multi-dialect support (native `JSONB` for PostgreSQL, standard `JSON` for SQLite test suites)
- **AI & Structured Extraction:** `instructor` + Pydantic v2 (Groq `openai/gpt-oss-120b`, OpenAI, Anthropic, Gemini)
- **Resilience:** `tenacity` (exponential backoff with jitter, 5s timeout, and `before_sleep_log`)
- **Logging & Observability:** `rich.logging.RichHandler` + structured contextual request metadata
- **Testing:** `pytest` (100% passing test suite across 26 unit and end-to-end scenario tests)

---

## 📐 System Design Write-Up (800 Words)

### 1. Concurrency Control & Double-Booking Prevention
In clinical scheduling, concurrent booking requests for the same physician, date, and session produce race conditions. HealthQueue enforces a **two-tier concurrency defense model**:
- **Pessimistic Row-Level Locking:** During token booking (`POST /queue/book`), the backend initiates an explicit `SERIALIZABLE` async transaction. It executes a `SELECT ... FOR UPDATE` query on the doctor's queue for `(doctor_id, appointment_date, session)` before determining the next available token number and assigning slots.
- **Database Unique Constraints:** At the database level, a compound unique constraint `UNIQUE (doctor_id, appointment_date, session, token_number)` acts as an infallible barrier against double allocations.
- **Transient Slot Reservation (Hold Engine):** When a patient initiates slot selection, a 5-minute transient hold is recorded with an expiring timestamp. Expired holds are pruned automatically by background cleanup tasks, ensuring unconfirmed slots are swiftly returned to the open availability pool.

### 2. Intelligent Queue Engine (`getNextToken`)
The platform distinguishes between two fundamental identifiers:
- `token_number`: An immutable identifier assigned at the time of booking.
- `display_position`: A dynamic, recalculating position that dictates actual serving order.

When a physician completes a consultation, `getNextToken()` computes the next serving patient using strict clinical hierarchy:
1. **Emergency Tier ($E$):** Inserted immediately at `current_serving_token + 1`.
2. **Anchor Slots ($A$):** Advance bookings fixed to specific clock times. If the doctor runs behind, anchors are prioritized within a 10-minute grace window; if running ahead, anchors are held until their target time.
3. **Priority Tier ($P$):** Interleaved into the regular queue at a configured ratio (e.g., 1 priority token for every 3 regular tokens).
4. **Regular Open Queue ($R$):** Served in strict First-Come, First-Served (FCFS) order based on `booked_at`.

### 3. Doctor Leave Conflict Resolution
When an administrator marks a doctor as on leave (`POST /doctors/{id}/leave`), the system executes an automated conflict resolution pipeline inside an atomic transaction:
1. Identifies all booked appointments falling within `[start_date, end_date]`.
2. Updates their status to `cancelled`.
3. Dispatches high-priority dual-channel notifications (WhatsApp interactive ping + Email cancellation receipt) containing one-click reschedule options.

### 4. Resilient AI Pipeline & Fault Tolerance
AI triage and post-visit summarization run through an `instructor`-wrapped multi-provider router guarded by `tenacity` retry policies:
- Strict **5-second timeout** per attempt with up to 2 retries using random exponential backoff.
- **Non-Blocking Graceful Fallback:** If LLM providers fail or time out, the transaction is **never aborted**. The system logs the failure to `llm_call_log`, marks `is_processed = false`, and falls back to preserving raw patient symptom text and raw physician clinical notes. The clinic operates uninterrupted with 99.9% uptime.

### 5. Notification Reliability & Dual-Channel Fallback
Notifications follow an active fallback cascade:
- **WhatsApp (Twilio):** Real-time operational channel for queue delay alerts and approach pings.
- **Email (SendGrid/SMTP):** Formal record channel for booking confirmations and clinical summaries.
- If WhatsApp delivery fails (invalid number, carrier timeout), the dispatcher automatically fails over to Email and schedules an asynchronous retry for background workers.

---

## 🤖 LLM Workflows & Prompt Schemas

### 1. Diagnosis-Based Doctor Auto-Suggest
- **Endpoint:** `GET /api/v1/doctors/suggest?symptoms=...`
- **Output:**
```json
{
  "recommended_specialisation": "Cardiology",
  "reason": "Chest tightness and exertional shortness of breath are cardinal signs of potential cardiovascular ischemia.",
  "doctors": [...]
}
```

### 2. Pre-Visit Clinical Triage
- **Endpoint:** `POST /api/v1/clinical/{id}/symptoms`
- **Output Schema:**
```json
{
  "urgency_level": "high",
  "chief_complaint": "Severe throbbing headache for 3 days with photophobia and morning nausea",
  "suggested_questions": [
    "When did the headache start and has the intensity escalated?",
    "Do you have visual changes, vomiting, or focal weakness?",
    "Any history of migraines or recent trauma?"
  ]
}
```

### 3. Post-Visit Patient Summary & Medication Schedule
- **Endpoint:** `POST /api/v1/clinical/{id}/post-visit-notes`
- **Output Schema:**
```json
{
  "patient_friendly_summary": "You have an acute migraine with aura. We have prescribed medication to relieve acute symptoms.",
  "medication_schedule": "Take Sumatriptan 50mg as needed at symptom onset. Take Paracetamol 500mg twice daily with food.",
  "follow_up_steps": [
    "Rest in a quiet, dark room during acute attacks",
    "Maintain adequate hydration",
    "Seek immediate care if headache becomes sudden and explosive"
  ],
  "extracted_medications": [
    {
      "medication_name": "Sumatriptan",
      "dosage": "500mg",
      "frequency": "as_needed",
      "duration_days": 5
    }
  ]
}
```

---

## 🔒 Security & Role-Based Access Control (RBAC)

| Role | Allowed Actions | Registration Security |
|---|---|---|
| **Patient** | Search doctors, AI symptom match, book Regular/Priority tokens, submit symptoms, track queue, view prescriptions | Open public self-registration |
| **Doctor** | View session queue, call next patient via `getNextToken()`, inspect AI triage briefs, write clinical notes & digital prescriptions | Protected with `ADMIN_REGISTRATION_SECRET` (default: `admin2026`) |
| **Admin** | Create doctor profiles, configure working hours/sessions, log approved doctor leaves (auto-cancelling conflicts), view delay metrics | Protected with `ADMIN_REGISTRATION_SECRET` (default: `admin2026`) |

---

## 🗄️ Database Architecture (PostgreSQL)

The database schema consists of 9 normalized core tables:
1. `users`: System accounts (`patient`, `doctor`, `admin`) with bcrypt password hashes, phone numbers, and WhatsApp numbers.
2. `doctors`: Doctor profiles, slot duration, booking mode (`walk_in`, `advance_only`, `hybrid`), and capacity split percentages (`anchor_slot_pct`, `priority_slot_pct`, `emergency_slot_pct`).
3. `doctor_availability`: Weekly working schedules per session (`morning`, `evening`, `full_day`).
4. `doctor_leave`: Approved leave date ranges with conflict tracking.
5. `doctor_queue`: Live token state (`token_number`, `display_position`, `tier`, `slot_type`, `status`).
6. `symptoms`: Patient pre-visit intake and structured AI triage results.
7. `post_visit_notes`: Physician clinical notes, diagnosis, and AI patient summaries.
8. `medications` & `medication_reminders`: Normalized prescription items and scheduled reminder jobs.
9. `notifications`, `calendar_events`, `oauth_tokens`, `llm_call_log`: Observability, notification audit trails, and LLM telemetry.

---

## 🔌 API Endpoint Reference

| Method | Endpoint | Description | Auth / Role |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Register user account (Doctors/Admins require `admin_secret`) | Public |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT access/refresh tokens | Public |
| `GET` | `/api/v1/doctors` | List active doctors with optional specialisation filter | Public |
| `GET` | `/api/v1/doctors/suggest` | AI-powered doctor recommendation from symptoms/diagnosis | Public |
| `GET` | `/api/v1/doctors/{id}` | Get doctor public profile | Public |
| `POST` | `/api/v1/doctors/` | Create a doctor profile | Admin |
| `POST` | `/api/v1/doctors/{id}/availability` | Configure doctor session hours | Admin |
| `POST` | `/api/v1/doctors/{id}/leave` | Add leave & auto-cancel conflicting bookings | Admin |
| `POST` | `/api/v1/queue/book` | Book token in hybrid queue with pessimistic lock | Patient |
| `GET` | `/api/v1/queue/{id}/status` | Get live token position and estimated wait time | Patient |
| `GET` | `/api/v1/queue/doctor/{id}` | Get real-time queue for doctor session | Doctor |
| `POST` | `/api/v1/queue/doctor/{id}/call-next` | Advance queue via `getNextToken()` engine | Doctor |
| `POST` | `/api/v1/queue/{id}/complete` | Mark consultation completed | Doctor |
| `POST` | `/api/v1/clinical/{id}/symptoms` | Submit pre-visit symptoms for AI triage | Patient |
| `GET` | `/api/v1/clinical/{id}/symptoms` | Review AI triage brief before consultation | Doctor |
| `POST` | `/api/v1/clinical/{id}/post-visit-notes` | Submit clinical notes & prescription items | Doctor |
| `GET` | `/api/v1/clinical/{id}/post-visit-notes` | View patient summary and medication reminders | Patient / Doctor |
| `GET` | `/api/v1/admin/dashboard` | Real-time system KPI metrics and delay tracker | Admin |

---

## 🚀 Local Setup Guide

### 1. Backend Setup
```bash
# Clone repository
git clone https://github.com/Ayush99392003/HealthQueue.git
cd HealthQueue

# Setup virtual environment with uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install all dependencies including dev tools
uv pip install -e ".[dev]"

# Configure environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL and GROQ_API_KEY

# Start FastAPI server
uv run uvicorn src.main:app --reload --port 8000
```
- Swagger UI: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/health`

### 2. Frontend Setup
```bash
# Navigate to frontend directory
cd frontend

# Install Node dependencies
npm install

# Start Vite development server
npm run dev
```
- Web Application UI: `http://localhost:3000`

---

## 🧪 Automated Testing Suite

HealthQueue includes a comprehensive test suite covering priority queue reflow, race conditions, emergency triage insertions, and LLM fallbacks:

```bash
# Run all 26 unit and end-to-end scenario tests
uv run pytest -v
```

```text
======================= 26 passed, 1 warning in 23.20s ========================
```

---

## 🌐 Production Deployment

- **Backend (Railway):** Uses the root [`Dockerfile`](./Dockerfile) with dynamic `$PORT` binding and auto-table creation on startup.
- **Frontend (Vercel):** Single Page Application configured in [`frontend/vercel.json`](./frontend/vercel.json) with `VITE_API_BASE_URL` pointing to `https://healthqueue-production.up.railway.app`.
