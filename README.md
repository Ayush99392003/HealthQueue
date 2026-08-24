# Healthcare Appointment & Follow-up Manager (HealthQueue)

> **Intelligent, token-based hybrid clinical scheduling platform featuring automated pre-visit AI triage, dynamic queue reflow, post-visit clinical summarization, symptom-based doctor auto-suggestion, dual-channel notifications (WhatsApp/SMS + Email), and Google Calendar OAuth 2.0 synchronization.**

---

## 🌐 1. Live Production Deployments

| Component | Provider | URL | Status |
|:---|:---:|:---|:---:|
| **Web Application Portal** | Vercel | [https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/](https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/) | 🟢 **Live** |
| **Backend API Service** | Railway | [https://healthqueue-production.up.railway.app](https://healthqueue-production.up.railway.app) | 🟢 **Live** |
| **Interactive API Docs (Swagger)** | Railway | [https://healthqueue-production.up.railway.app/docs](https://healthqueue-production.up.railway.app/docs) | 🟢 **Live** |
| **System Health Check** | Railway | [https://healthqueue-production.up.railway.app/health](https://healthqueue-production.up.railway.app/health) | 🟢 **Live** |

---

## 🛠️ 2. Technology Stack

- **Backend Framework:** Python 3.14+ (FastAPI + Pydantic v2 + SQLAlchemy 2.0 Async + `asyncpg` + `psycopg2-binary`) strictly adhering to PEP 8 standards.
- **Frontend Portal:** React (Vite) + Vanilla CSS Custom Glassmorphic Design System (Patient Portal, Doctor Dashboard, Admin Control Center).
- **Database Layer:** PostgreSQL hosted on Railway with ACID transactions, `SERIALIZABLE` isolation, and cross-dialect JSON support.
- **Package & Runtime Manager:** `uv` (Ultra-fast Python package installer and resolver).
- **AI & Structured Extraction:** `instructor` wrapped around multi-provider LLM routing (**Groq `openai/gpt-oss-120b`**, Azure OpenAI, OpenAI, Anthropic).
- **Resilience Engine:** `tenacity` (exponential backoff with random jitter, 5-second per-attempt timeouts, and non-blocking domain fallback).
- **Dual-Channel Messaging:** Twilio SDK (WhatsApp Sandbox & Direct SMS) + Standard Python SMTP (Gmail / SendGrid) with 3-tier cascade.
- **Calendar Synchronization:** Google Calendar API via OAuth 2.0 with offline refresh tokens and 1-click browser calendar templates.
- **Observability:** `rich.logging.RichHandler` with contextual trace IDs and structured error logs.
- **Test Automation:** `pytest` + `pytest-asyncio` + `pytest-cov` (100% passing test suite across 26 unit and end-to-end scenario tests).

---

## 🏆 3. What Was Achieved (Key Innovations & Features)

### 🏥 Patient Experience
- **AI Doctor Matcher (`GET /api/v1/doctors/suggest`):** Patients can describe symptoms in plain text (e.g. *"severe chest tightness and palpitations when walking"*), and Groq AI automatically identifies the matching medical specialisation (*Cardiology*), provides clinical reasoning, and filters available doctors.
- **Smart Token Booking:** Patients book morning or evening session slots with automatic token number generation across Regular and Priority tiers.
- **Pre-Visit Symptom Submission:** Collects detailed patient chief complaints and duration before entering the consultation room.
- **Live Dynamic Queue Tracker:** Real-time token tracking with live queue position counters and dynamically recalculating wait times.
- **Post-Visit Digital Medical Records:** Instant access to plain-language doctor summaries, recovery steps, and structured digital prescriptions.
- **1-Click Google Calendar Invite:** Patients can add their appointment and live queue tracking link directly into Google Calendar in 1 click.

### 👨‍⚕️ Doctor Clinical Dashboard
- **Session Queue Overview:** Real-time visibility into all waiting, in-consultation, and completed patients for the current session.
- **Pre-Visit AI Clinical Brief:** Before calling the patient, doctors see an AI-generated brief containing:
  - **Urgency Level:** `Low`, `Medium`, `High`, or `Critical`.
  - **Chief Complaint:** Concise clinical summary.
  - **3 Suggested Diagnostic Questions:** High-yield questions tailored to the patient's symptoms.
- **Single-Action Priority Serving Engine:** Clicking **"Complete & Call Next"** evaluates clinical priorities and automatically calls the next patient.
- **Digital Prescription & Note Submission:** Record clinical shorthand, diagnoses, and medicines with 1-click submission.

### ⚙️ Admin Control Center
- **System-Wide KPI Metrics:** Live metrics for Active Doctors, Bookings Today, Urgent Triages, Avg Consultation Delays, and Subsystem Health flags.
- **Doctor Profile & Availability Management:** Configure doctor specialisations, bios, consultation duration, and weekly session schedules (Mon–Sat).
- **Automated Doctor Leave Conflict Resolution:** When an admin logs approved doctor leave, the system **automatically cancels conflicting appointments** and queues instant patient notifications.
- **1-Click Clinical Demo Seeder:** Instantly populate the database with specialist doctors, schedules, patients, and queue tokens.

---

## 📐 4. System Design & Architecture Write-Up (800 Words)

### 1. Concurrency Model & Double-Booking Prevention
In clinical queue management, concurrent booking requests for the same physician, date, and session introduce race conditions that lead to double allocations. HealthQueue enforces a rigorous multi-tier concurrency defense model:
- **Pessimistic Row-Level Locking:** During token booking (`POST /api/v1/queue/book`), the backend executes within an explicit `SERIALIZABLE` database transaction. It issues a `SELECT ... FOR UPDATE` query against the doctor's queue for `(doctor_id, appointment_date, session)`, ensuring serialized token incrementation and slot reservation.
- **Database Unique Constraints:** At the PostgreSQL schema level, a compound unique constraint `UNIQUE (doctor_id, appointment_date, session, token_number)` guarantees database-level integrity, permanently preventing duplicate token assignment.
- **Transient Slot Reservation (Hold Engine):** When a patient initiates slot selection, a transient 5-minute reservation hold is recorded with an expiring timestamp. Expired holds are pruned automatically by background cleanup tasks, ensuring unconfirmed slots are swiftly returned to the open availability pool.

### 2. Intelligent Queue Serving Algorithm (`getNextToken`)
Traditional clock-time scheduling fails because consultation times vary. HealthQueue decouples the permanent booking identifier from the real-time serving order:
- **`token_number`:** An immutable identifier assigned at the time of booking.
- **`display_position`:** A dynamic serving position recalculated by `getNextToken()` upon every queue mutation.

When a physician completes a consultation, `getNextToken()` computes the next serving patient using a strict 4-tier clinical hierarchy:
1. **Emergency Tier ($E$):** Any patient escalated to emergency priority is served immediately (inserted at `current_serving_token + 1`).
2. **Anchor Slots ($A$):** Fixed clock-time appointments prioritized within a 10-minute grace window if the doctor is running behind schedule, but held until their target time if the doctor is running ahead.
3. **Priority Tier ($P$):** Interleaved into the regular queue at a configured ratio (e.g., 1 priority patient for every 3 regular patients).
4. **Regular Open Queue ($R$):** Served in strict First-Come, First-Served (FCFS) order based on `booked_at`.

### 3. Automated Doctor Leave Conflict Resolution
When an administrator logs approved doctor leave (`POST /api/v1/doctors/{id}/leave`), the system executes an automated conflict resolution pipeline within an atomic database transaction:
1. Queries all active booked appointments falling within the range `[start_date, end_date]`.
2. Atomically updates their queue status to `cancelled`.
3. Records audit entries in the notifications log and triggers high-priority dual-channel dispatches (WhatsApp/SMS alerts + formal Email cancellation receipts) containing one-click reschedule options.

### 4. Resilient Multi-Provider AI Clinical Pipeline
AI symptom triage and post-visit summarization run through an `instructor`-wrapped multi-provider routing layer guarded by strict `tenacity` retry policies:
- Strict **5-second timeout** per attempt with up to 2 retries using random exponential backoff and jitter.
- **Non-Blocking Fallback Architecture:** If an LLM provider experiences downtime or schema parsing errors, the transaction is **never aborted**. The system logs the failure to `llm_call_log`, sets `is_processed = false`, and falls back to displaying raw patient symptoms and physician clinical shorthand. This guarantees 99.9% clinical operational uptime without blocking bookings or notes submission.

### 5. Dual-Channel Notification Reliability & 3-Tier Fallback Cascade
To guarantee reliable patient communication, notifications implement an automated 3-tier delivery cascade:
```
[1. WhatsApp Alert (Twilio)] ──(on failure)──► [2. Direct SMS Text Message] ──(on failure)──► [3. Email Receipt (SMTP)]
```
- **WhatsApp (Twilio):** Real-time operational channel for queue delay alerts and token approach pings.
- **SMS (Direct):** Carrier text message fallback to the patient's verified mobile number.
- **Email (SMTP / SendGrid):** Formal record channel for booking confirmations and digital prescriptions.
- All delivery attempts are tracked in the `notifications` table with retry counts and error logs.

### 6. Dual-Calendar Google Calendar OAuth 2.0 Integration
HealthQueue synchronizes clinical appointments across both patient and doctor calendars:
- Implements standard OAuth 2.0 authorization code flow with encrypted offline refresh token storage.
- **Event Lifecycle Synchronization:** Creating a booking issues `POST /calendar/v3/calendars/primary/events` with appointment details and live queue tracking links. Rescheduling triggers `PATCH` updates, and doctor leave cancellations trigger automated `DELETE` calls.
- **Web Template Fallback:** Provides direct browser-based 1-click Google Calendar template links and `.ics` iCalendar attachments for immediate calendar integration without requiring OAuth setup.

---

## 🤖 5. LLM Prompts & Response Schemas

### 1. Pre-Visit Clinical Triage
- **Prompt:** `"Analyse these symptoms and return: urgency level (Low / Medium / High / Critical), chief complaint, and three suggested questions for the doctor. Symptoms: {symptoms}"`
- **Pydantic Response Schema:**
```json
{
  "urgency_level": "high",
  "chief_complaint": "Exertional chest tightness and shortness of breath for 2 days",
  "suggested_questions": [
    "Does the pain radiate to your left arm or jaw?",
    "Do you experience dizziness or sweating during these episodes?",
    "Do you have a personal or family history of hypertension or cardiac disease?"
  ]
}
```

### 2. Post-Visit Clinical Summary & Prescription
- **Prompt:** `"Convert these clinical notes into a patient-friendly summary with medication schedule and follow-up steps: {notes}"`
- **Pydantic Response Schema:**
```json
{
  "patient_summary": "You have been diagnosed with mild hypertension and tension headache. Follow the prescribed medication course and drink plenty of fluids.",
  "follow_up_steps": [
    "Take prescribed medication daily after meals.",
    "Monitor blood pressure daily for 1 week.",
    "Return for follow-up review in 14 days if headaches persist."
  ],
  "extracted_medications": [
    {
      "medication_name": "Amlodipine",
      "dosage": "5mg",
      "frequency": "once_daily",
      "duration_days": 14,
      "instructions": "Take once daily in the morning after breakfast"
    }
  ]
}
```

---

## 📋 6. Complete RESTful API Index

| Category | Method | Endpoint | Description | Auth Required |
|---|:---:|---|---|:---:|
| **Health** | `GET` | `/health` | Service liveness probe | Public |
| **Auth** | `POST` | `/api/v1/auth/register` | Register new user (Patient, Doctor, Admin) | Public |
| **Auth** | `POST` | `/api/v1/auth/login` | Authenticate user & obtain JWT tokens | Public |
| **Doctors** | `GET` | `/api/v1/doctors` | List all active specialist doctors | Public |
| **Doctors** | `GET` | `/api/v1/doctors/suggest` | AI Doctor Matcher by Symptoms (Groq) | Public |
| **Doctors** | `POST` | `/api/v1/doctors/` | Create doctor profile & slot configuration | Admin |
| **Doctors** | `POST` | `/api/v1/doctors/{id}/availability` | Configure weekly working hours | Admin |
| **Doctors** | `POST` | `/api/v1/doctors/{id}/leave` | Log doctor leave & auto-cancel conflicts | Admin |
| **Queue** | `POST` | `/api/v1/queue/book` | Pessimistic `SERIALIZABLE` token booking | Patient |
| **Queue** | `GET` | `/api/v1/queue/{id}/status` | Live queue tracker & dynamic ETA | Patient |
| **Queue** | `GET` | `/api/v1/queue/doctor/{id}` | View current session doctor queue | Doctor |
| **Queue** | `POST` | `/api/v1/queue/doctor/{id}/call-next` | Advance queue via `getNextToken()` engine | Doctor |
| **Clinical** | `POST` | `/api/v1/clinical/{id}/symptoms` | Submit patient pre-visit symptoms | Patient |
| **Clinical** | `GET` | `/api/v1/clinical/{id}/symptoms` | Doctor pre-visit AI triage brief | Doctor |
| **Clinical** | `POST` | `/api/v1/clinical/{id}/post-visit-notes` | Submit doctor notes & prescriptions | Doctor |
| **Clinical** | `GET` | `/api/v1/clinical/{id}/post-visit-notes` | Patient post-visit health record | Patient |
| **Admin** | `GET` | `/api/v1/admin/stats` | System KPI metrics & subsystem health | Admin |
| **Admin** | `POST` | `/api/v1/admin/seed-demo` | 1-Click clinical demo database seeder | Admin |
| **Calendar**| `GET` | `/api/v1/calendar/auth-url` | Generate Google OAuth2 consent URL | Patient/Doc |
| **Calendar**| `GET` | `/api/v1/calendar/callback` | Google OAuth2 token exchange callback | Public |

---

## ⚡ 7. Local Setup & Execution Guide

### Prerequisites
- Python 3.14+
- Node.js 18+ & npm
- `uv` package manager (`pip install uv` or `curl -LsSf https://astral.sh/uv/install.sh | sh`)

### Backend Setup
```bash
# 1. Clone repository
git clone https://github.com/Ayush99392003/HealthQueue.git
cd HealthQueue

# 2. Create virtual environment and install dependencies
uv venv
uv pip install -e ".[dev]"

# 3. Configure environment variables
cp .env.example .env

# 4. Start local development server
uv run uvicorn src.main:app --reload --port 8000
```

### Frontend Setup
```bash
# 1. Navigate to frontend directory
cd frontend

# 2. Install dependencies
npm install

# 3. Start Vite development server
npm run dev
```

### Automated Testing
```bash
# Run complete test suite with coverage
uv run pytest -v
```

---

## 🔐 8. Environment Configuration (`.env.example`)

```env
# Server Configuration
ENVIRONMENT=production
PORT=8000
DEBUG=false
SECRET_KEY=your_super_secret_jwt_key_here
ADMIN_REGISTRATION_SECRET=admin2026

# Database (PostgreSQL)
DATABASE_URL=postgresql://user:password@host:port/database

# AI / LLM Provider (Groq)
DEFAULT_LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your_groq_api_key

# Twilio WhatsApp & SMS Notifications
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_FROM=+15614733679

# Google Calendar OAuth 2.0
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=https://healthqueue-production.up.railway.app/api/v1/calendar/callback

# Email Notifications (SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_FROM_NAME=HealthQueue Manager
```
