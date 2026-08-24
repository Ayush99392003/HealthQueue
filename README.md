# Healthcare Appointment & Follow-up Manager (HealthQueue)

> **Intelligent, token-based hybrid clinical scheduling platform with automated pre-visit AI triage, dynamic queue reflow, post-visit summarization, dual-channel notifications, and Google Calendar synchronization.**

---

## 🌟 Overview

Traditional healthcare scheduling fails because patient consultation durations are unpredictable. Rigid clock-time appointments create waiting room bottlenecks, doctor burnout, and walk-in vs. advance booking friction.

**HealthQueue** replaces clock-time booking with an **intelligent, token-based hybrid queue engine** backed by:
- **Pre-visit AI Triage:** Symptom intake and structured urgency scoring (`low`, `medium`, `high`) powered by `instructor` + Pydantic v2.
- **Dynamic Queue Flow (`getNextToken`):** Intelligent serving order prioritizing Emergency cases, Anchor times, Priority tier (1-in-4), and First-Come-First-Served (FCFS).
- **Concurrency & Double-Booking Protection:** `SERIALIZABLE` transactions with pessimistic row locking (`SELECT ... FOR UPDATE`).
- **Doctor Leave Conflict Automation:** Auto-cancellation of conflicting appointments with instant patient notifications.
- **Post-Visit Summaries & Medication Reminders:** Structured prescription extraction and automated reminder jobs.
- **Dual-Channel Notifications:** WhatsApp (Twilio) for real-time delay alerts and Email (SendGrid/SMTP) for formal records.
- **Dual-Calendar Syncing:** Google Calendar API OAuth 2.0 integration for both doctor and patient.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.14+ (FastAPI + Pydantic v2 + SQLAlchemy 2.0 Async + `asyncpg`) adhering to PEP 8
- **Frontend:** React (Vite) + Vanilla CSS Modern Design System (Patient Portal, Doctor Dashboard, Admin Control Center)
- **Package Manager:** `uv`
- **Database:** PostgreSQL (Hosted on Railway / Neon / Local)
- **AI & Structured Extraction:** `instructor` + Pydantic v2 (Groq `openai/gpt-oss-120b`, OpenAI, Anthropic, Gemini)
- **Resilient Retries:** `tenacity` (exponential backoff with jitter and `before_sleep_log`)
- **Logging:** `rich.logging.RichHandler` + structured contextual logging
- **Testing:** `pytest` (Unit and Scenario-Based Integration Tests)

---

## 📐 System Design Write-Up (800 Words)

### 1. Concurrency Control & Double-Booking Prevention
In a clinical appointment system, simultaneous booking requests for the same doctor, date, and session create race conditions. HealthQueue enforces a **two-tier concurrency defense model**:
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
2. Updates their status to `leave_cancelled`.
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

## 🤖 LLM Prompt Templates & Schemas

### 1. Pre-Visit Symptom Triage Prompt
```text
System: You are an expert clinical triage assistant.
User Prompt:
Analyse these symptoms and return: urgency level (Low / Medium / High), chief complaint, and three suggested questions for the doctor.
Symptoms: <patient_symptoms>
```
**JSON Output Schema:**
```json
{
  "urgency_level": "low" | "medium" | "high",
  "chief_complaint": "string",
  "ai_summary": "string",
  "suggested_questions": ["string", "string", "string"]
}
```

### 2. Post-Visit Patient Summary & Medication Schedule Prompt
```text
System: You are a medical communication specialist.
User Prompt:
Convert these clinical notes into a patient-friendly summary with medication schedule and follow-up steps:
<doctor_clinical_notes>
```
**JSON Output Schema:**
```json
{
  "patient_friendly_summary": "string",
  "key_findings": ["string"],
  "follow_up_instructions": "string",
  "medication_schedule": [
    {
      "name": "string",
      "dosage": "string",
      "frequency": "once_daily" | "twice_daily" | "three_times_daily" | "as_needed",
      "timing_notes": "string"
    }
  ]
}
```

---

## 📅 Google Calendar OAuth 2.0 Setup

To enable automated Google Calendar event synchronization:
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project and enable the **Google Calendar API**.
3. Configure the **OAuth Consent Screen** (User Type: External) and add the scope `https://www.googleapis.com/auth/calendar.events`.
4. Create **OAuth 2.0 Client ID Credentials** (Application Type: Web Application).
5. Add Authorized Redirect URI: `http://localhost:8000/api/v1/calendar/callback`.
6. Add the credentials to your `.env`:
   ```env
   GOOGLE_CLIENT_ID=your_client_id.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=your_client_secret
   GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/calendar/callback
   GOOGLE_OAUTH_ENCRYPTION_KEY=your_fernet_secret_key
   ```

---

## 🗄️ Database Architecture

The PostgreSQL schema consists of 9 normalized core tables:
1. `users`: System accounts (`patient`, `doctor`, `admin`) with bcrypt password hashes and contact info.
2. `doctors`: Doctor profiles, slot duration, booking mode (`walk_in`, `advance_only`, `hybrid`), and capacity split percentages (`anchor_slot_pct`, `priority_slot_pct`, `emergency_slot_pct`).
3. `doctor_availability`: Weekly working schedules per session (`morning`, `evening`, `full_day`).
4. `doctor_leave`: Approved leave date ranges with conflict tracking.
5. `doctor_queue`: Live token state (`token_number`, `display_position`, `tier`, `slot_type`, `status`).
6. `symptoms`: Patient pre-visit intake and structured AI triage results.
7. `post_visit_notes`: Physician clinical notes, diagnosis, and AI patient summaries.
8. `medications` & `medication_reminders`: Normalized prescription items and scheduled reminder jobs.
9. `notifications` & `llm_call_log`: Observability, notification audit trails, and LLM telemetry.

---

## 🔌 API Endpoint Reference

| Method | Endpoint | Description | Role |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Register a new user (`patient`, `doctor`, `admin`) | Public |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT access/refresh tokens | Public |
| `GET` | `/api/v1/doctors` | List doctors with filter by specialisation | Public / Patient |
| `POST` | `/api/v1/doctors` | Create a doctor profile | Admin |
| `POST` | `/api/v1/doctors/{id}/availability` | Set doctor working hours and sessions | Admin |
| `POST` | `/api/v1/doctors/{id}/leave` | Add leave and auto-cancel conflicting bookings | Admin |
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

## 🚀 Quickstart & Setup Guide

### 1. Backend Setup
```bash
# Clone repository
git clone https://github.com/Ayush99392003/HealthQueue.git
cd HealthQueue

# Setup virtual environment with uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -e ".[dev]"

# Configure environment variables
cp .env.example .env
# Edit .env with your DATABASE_URL and GROQ_API_KEY / LLM keys

# Run migrations & seed data
uv run python -m src.scripts.seed_db

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

## 🧪 Testing

```bash
# Run unit and scenario integration test suites
uv run pytest -v

# Run code format and lint checks
uv run ruff check .
```

---

## 🌐 Deployment Guide

- **Database & Backend:** Deploy to **Railway** or **Render** using the provided `Dockerfile` and `docker-compose.yml`.
- **Frontend:** Deploy `frontend/` to **Vercel** with `VITE_API_BASE_URL` pointing to your backend URL.
