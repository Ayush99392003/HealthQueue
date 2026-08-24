<div align="center">

# 🏥 HealthQueue

### Intelligent Token-Based Clinical Queue Management Platform

[![Live Demo](https://img.shields.io/badge/Live%20Demo-Vercel-00C7B7?style=for-the-badge&logo=vercel)](https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/)
[![API Docs](https://img.shields.io/badge/API%20Docs-Swagger-85EA2D?style=for-the-badge&logo=swagger)](https://healthqueue-production.up.railway.app/docs)
[![Backend](https://img.shields.io/badge/Backend-Railway-0B0D0E?style=for-the-badge&logo=railway)](https://healthqueue-production.up.railway.app)
[![Python](https://img.shields.io/badge/Python-3.14+-3776AB?style=for-the-badge&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

> **Replaces rigid clock-time scheduling with a dynamic, AI-powered priority queue engine — featuring automated pre-visit triage, real-time delay reflow, post-visit summarization, dual-channel notifications (WhatsApp + Email), and Google Calendar OAuth 2.0 sync.**

</div>

---

## 📑 Table of Contents

1. [Live Deployments](#-live-deployments)
2. [Features](#-features)
3. [Architecture Diagrams](#-architecture-diagrams)
4. [Database Schema](#-database-schema)
5. [Sequence Diagrams](#-sequence-diagrams)
6. [Built With](#-built-with)
7. [Prerequisites](#-prerequisites)
8. [Installation](#-installation)
9. [Usage](#-usage)
10. [Configuration](#-configuration)
11. [Deployment](#-deployment)
12. [Testing](#-testing)
13. [API Reference](#-api-reference)
14. [Demo Credentials](#-demo-credentials)
15. [Contributing](#-contributing)
16. [Authors](#-authors)
17. [License](#-license)
18. [Acknowledgments](#-acknowledgments)

---

## 🌐 Live Deployments

| Component | Provider | URL | Status |
|:---|:---:|:---|:---:|
| **Web Application** | Vercel | [healthfirstqueue…vercel.app](https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/) | 🟢 Live |
| **Backend API** | Railway | [healthqueue-production.up.railway.app](https://healthqueue-production.up.railway.app) | 🟢 Live |
| **Swagger UI** | Railway | [/docs](https://healthqueue-production.up.railway.app/docs) | 🟢 Live |
| **Health Check** | Railway | [/health](https://healthqueue-production.up.railway.app/health) | 🟢 Live |

---

## ✨ Features

### 👤 Patient Portal
- **AI Doctor Matcher** — Describe symptoms in plain text; Groq AI recommends the right specialist with clinical reasoning
- **Token Booking** — Morning/Evening sessions across Regular and Priority tiers with SERIALIZABLE double-booking prevention
- **Live Queue Tracker** — Real-time position, patients-ahead count, and dynamic ETA (auto-refreshes every 20s)
- **Pre-Visit Symptom Intake** — Submit symptoms before entering the consultation room; AI prepares a triage brief for the doctor
- **My Schedule Tab** — View all past and upcoming appointments with status badges and 1-click track button
- **Post-Visit Records** — Access AI-generated health summary, recovery steps, and structured digital prescription
- **1-Click Google Calendar** — Add appointment directly to Google Calendar via OAuth 2.0

### 🩺 Doctor Dashboard
- **Session Queue** — See all waiting, in-progress, and completed patients with tier and token info
- **AI Clinical Brief** — Before calling a patient, view urgency level, chief complaint, and 3 tailored diagnostic questions
- **Complete & Call Next** — Single button triggers the 4-tier priority algorithm: Emergency → Anchor → Priority → FCFS
- **Clinical Notes & Prescriptions** — Submit structured notes that are AI-summarized and sent to the patient

### 🛡️ Admin Control Center
- **Live System KPIs** — Doctors online, bookings today, urgent triages, average delay, subsystem health badges
- **Doctor Management** — Create profiles, set Mon–Sat schedules, configure slot split percentages
- **Leave & Auto-Rescheduling** — Log doctor leave → system auto-cancels all conflicting appointments and notifies every patient via WhatsApp + Email
- **1-Click Demo Seeder** — Populate 5 specialist doctors, 3 patients, admin, and today's queue tokens instantly

---

## 🏗️ Architecture Diagrams

### System Component Architecture

```mermaid
flowchart TD
    subgraph Frontend["🖥️ Frontend (React + Vite — Vercel)"]
        PP["Patient Portal"]
        DD["Doctor Dashboard"]
        AC["Admin Control Center"]
    end

    subgraph Backend["⚙️ Backend (FastAPI — Railway)"]
        AUTH["Auth API\n/api/v1/auth"]
        QUEUE["Queue Engine\n/api/v1/queue"]
        CLINICAL["Clinical API\n/api/v1/clinical"]
        DOCTORS["Doctors API\n/api/v1/doctors"]
        ADMIN["Admin API\n/api/v1/admin"]
        CAL["Calendar API\n/api/v1/calendar"]
    end

    subgraph AI["🤖 AI Pipeline (instructor + Pydantic)"]
        GROQ["Groq (Primary)"]
        OAI["OpenAI (Fallback 1)"]
        GEM["Gemini (Fallback 2)"]
        ANT["Anthropic (Fallback 3)"]
    end

    subgraph Notify["📣 Notification Cascade"]
        WA["WhatsApp\n(Twilio)"]
        SMS["SMS\n(Twilio)"]
        EMAIL["Email\n(SMTP/SendGrid)"]
    end

    subgraph Data["🗄️ Data (PostgreSQL — Railway)"]
        DB[("PostgreSQL\nSERIALIZABLE\nTransactions")]
    end

    GCAL["📅 Google Calendar\nOAuth 2.0"]

    Frontend -->|JWT Bearer| Backend
    Backend --> Data
    Backend --> AI
    Backend --> Notify
    Backend --> GCAL
    WA -->|Fail| SMS -->|Fail| EMAIL
    GROQ -->|Fail| OAI -->|Fail| GEM -->|Fail| ANT
```

### Queue Priority Engine

```mermaid
flowchart LR
    A["Doctor clicks\n'Complete & Call Next'"] --> B{"Emergency\nPatients Waiting?"}
    B -->|Yes| E["🚨 Serve Emergency\nInsert at pos +1"]
    B -->|No| C{"Anchor Slot\nTime Window?"}
    C -->|Yes + Behind Schedule| D["⚓ Pull Forward\nAnchor Patient"]
    C -->|No| F{"Priority Ratio\nReached?"}
    F -->|Yes| G["⭐ Serve Priority\nPatient"]
    F -->|No| H["📋 Serve Regular\nFCFS by booked_at"]
    E & D & G & H --> I["Recalculate\ndisplay_position\nfor all waiting"]
    I --> J["Broadcast ETA\nUpdates"]
```

---

## 🗄️ Database Schema

```mermaid
erDiagram
    users {
        int id PK
        string email UK
        string password_hash
        string role
        string first_name
        string last_name
        string phone
        string whatsapp_number
        bool is_active
        datetime created_at
    }

    doctors {
        int id PK,FK
        string specialisation
        string bio
        int experience_years
        int slot_duration_minutes
        float avg_consult_minutes
        string booking_mode
        float anchor_slot_pct
        float priority_slot_pct
        float emergency_slot_pct
    }

    doctor_availability {
        int id PK
        int doctor_id FK
        int day_of_week
        string session
        time start_time
        time end_time
        bool is_working_day
    }

    doctor_leave {
        int id PK
        int doctor_id FK
        date start_date
        date end_date
        string reason
    }

    doctor_queue {
        int id PK
        int doctor_id FK
        int patient_id FK
        int token_number
        int display_position
        string tier
        string slot_type
        string status
        string session
        date appointment_date
        datetime booked_at
        datetime completed_at
    }

    symptoms {
        int id PK
        int queue_id FK
        string symptom_text
        string urgency_level
        json ai_summary
        bool is_processed
    }

    post_visit_notes {
        int id PK
        int queue_id FK
        string raw_notes
        string ai_summary
        json prescription_json
    }

    notifications {
        int id PK
        int patient_id FK
        string channel
        string status
        int retry_count
        datetime sent_at
    }

    users ||--o{ doctor_queue : "books"
    users ||--o| doctors : "has profile"
    doctors ||--o{ doctor_availability : "has schedule"
    doctors ||--o{ doctor_leave : "takes leave"
    doctors ||--o{ doctor_queue : "serves"
    doctor_queue ||--o| symptoms : "has triage"
    doctor_queue ||--o| post_visit_notes : "has notes"
    users ||--o{ notifications : "receives"
```

---

## 🔄 Sequence Diagrams

### Patient Booking + AI Triage Flow

```mermaid
sequenceDiagram
    participant P as Patient (Browser)
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant AI as Groq AI (instructor)
    participant WA as Twilio WhatsApp

    P->>API: POST /queue/book {doctor_id, date, session, tier}
    API->>DB: BEGIN SERIALIZABLE TRANSACTION
    API->>DB: SELECT ... FOR UPDATE (lock queue row)
    DB-->>API: Next available token_number
    API->>DB: INSERT doctor_queue row
    API->>DB: COMMIT
    DB-->>API: queue_id, token_number
    API-->>P: 201 {token_number, display_position, eta}

    P->>API: POST /clinical/{id}/symptoms {symptom_text}
    API->>AI: Extract urgency + chief complaint + questions
    AI-->>API: {urgency_level, ai_summary, suggested_questions}
    API->>DB: INSERT symptoms row
    API->>WA: Send booking confirmation + queue link
    WA-->>P: WhatsApp: "Token #7 confirmed. ETA: 45 min"
```

### Doctor Leave → Auto-Cancellation Flow

```mermaid
sequenceDiagram
    participant ADM as Admin (Browser)
    participant API as FastAPI Backend
    participant DB as PostgreSQL
    participant WA as Twilio WhatsApp
    participant EMAIL as SMTP Email

    ADM->>API: POST /doctors/{id}/leave {start_date, end_date}
    API->>DB: BEGIN TRANSACTION
    API->>DB: INSERT doctor_leave row
    API->>DB: SELECT all waiting queue entries in date range
    DB-->>API: List of affected appointments
    API->>DB: UPDATE status = 'cancelled' (bulk)
    API->>DB: COMMIT
    loop For each cancelled patient
        API->>WA: WhatsApp alert with RESCHEDULE option
        WA-->>API: delivery status
        alt WhatsApp fails
            API->>EMAIL: Send formal cancellation email
        end
    end
    API-->>ADM: {leave_id, cancelled_count, notifications_queued}
```

---

## 🔧 Built With

| Layer | Technology | Purpose |
|:---|:---|:---|
| **Backend** | [FastAPI](https://fastapi.tiangolo.com/) | Async web framework with auto OpenAPI docs |
| **Validation** | [Pydantic v2](https://docs.pydantic.dev/) | Request/response schemas and env settings |
| **ORM** | [SQLAlchemy 2.0 Async](https://docs.sqlalchemy.org/) | Async database layer with connection pooling |
| **Database** | [PostgreSQL](https://postgresql.org/) | ACID-compliant relational store |
| **AI** | [instructor](https://python.useinstructor.com/) + Groq | Structured LLM extraction with schema enforcement |
| **Resilience** | [tenacity](https://tenacity.readthedocs.io/) | Retry loops, exponential backoff, jitter |
| **Notifications** | [Twilio](https://twilio.com/) + SMTP | WhatsApp, SMS, and email dispatch |
| **Calendar** | [Google Calendar API](https://developers.google.com/calendar) | OAuth 2.0 event creation and sync |
| **Frontend** | [React 18](https://react.dev/) + [Vite](https://vitejs.dev/) | Single-page application with HMR |
| **Logging** | [Rich](https://rich.readthedocs.io/) | Colored structured console logs |
| **Testing** | [pytest](https://pytest.org/) + pytest-asyncio | Async unit and integration tests |
| **Runtime** | [uv](https://docs.astral.sh/uv/) | Ultra-fast Python package manager |
| **Containerization** | [Docker](https://docker.com/) | Reproducible build and deployment |

---

## 📋 Prerequisites

- **Python** 3.14+ ([download](https://python.org/downloads/))
- **Node.js** 18+ and npm ([download](https://nodejs.org/))
- **uv** package manager:
  ```bash
  pip install uv
  # or on macOS/Linux:
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```
- **PostgreSQL** 15+ (or use the Railway hosted instance — see `.env.example`)
- **Git** ([download](https://git-scm.com/))

---

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Ayush99392003/HealthQueue.git
cd HealthQueue
```

### 2. Backend Setup

```bash
# Create isolated virtual environment and install all dependencies
uv venv
uv pip install -e ".[dev]"

# Copy environment template and fill in your values
cp .env.example .env
```

### 3. Database Initialization

```bash
# Tables are auto-created on first startup via SQLAlchemy metadata
# For production migrations use Alembic:
uv run alembic upgrade head

# Optional: seed demo data (5 doctors, 3 patients, admin, today's queue)
# Note: also happens automatically on first boot with empty DB
curl -X POST http://localhost:8000/api/v1/admin/seed-demo
```

### 4. Start the Backend Server

```bash
uv run uvicorn src.main:app --reload --port 8000
# API available at http://localhost:8000
# Swagger UI at http://localhost:8000/docs
```

### 5. Frontend Setup

```bash
cd frontend
npm install
npm run dev
# App available at http://localhost:3000
```

### 6. Docker (Alternative — Full Stack)

```bash
docker compose up --build
```

---

## 🎮 Usage

### Quick Demo (No Setup Required)
Visit the [live app](https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/) and click any demo card on the login screen to sign in instantly.

### Book an Appointment via API

```bash
# 1. Login and get JWT token
curl -X POST https://healthqueue-production.up.railway.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "rahul@example.com", "password": "Password123!"}'

# 2. Book a token (use the access_token from step 1)
curl -X POST https://healthqueue-production.up.railway.app/api/v1/queue/book \
  -H "Authorization: Bearer <your_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "doctor_id": 2,
    "appointment_date": "2026-08-25",
    "session": "morning",
    "tier": "regular"
  }'
```

### AI Doctor Suggestion

```bash
curl "https://healthqueue-production.up.railway.app/api/v1/doctors/suggest?symptoms=severe+chest+tightness+and+palpitations"
# Returns: { recommended_specialisation: "Cardiology", reason: "...", doctors: [...] }
```

---

## ⚙️ Configuration

Create a `.env` file by copying `.env.example`:

```env
# ── Server ─────────────────────────────────────
ENVIRONMENT=production
PORT=8000
DEBUG=false
SECRET_KEY=your_super_secret_jwt_key_here
ADMIN_REGISTRATION_SECRET=admin2026

# ── Database (PostgreSQL) ──────────────────────
DATABASE_URL=postgresql://user:password@host:port/database

# ── AI / LLM (Groq primary) ───────────────────
DEFAULT_LLM_PROVIDER=groq
GROQ_MODEL=openai/gpt-oss-120b
GROQ_API_KEY=your_groq_api_key

# ── Twilio WhatsApp & SMS ──────────────────────
TWILIO_ACCOUNT_SID=your_twilio_account_sid
TWILIO_AUTH_TOKEN=your_twilio_auth_token
TWILIO_WHATSAPP_FROM=+15614733679

# ── Google Calendar OAuth 2.0 ─────────────────
GOOGLE_CLIENT_ID=your_google_client_id.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=your_google_client_secret
GOOGLE_REDIRECT_URI=https://healthqueue-production.up.railway.app/api/v1/calendar/callback

# ── Email Notifications (SMTP) ────────────────
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your_email@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_FROM_EMAIL=your_email@gmail.com
SMTP_FROM_NAME=HealthQueue Manager
```

> **Tip:** For Gmail, generate an [App Password](https://myaccount.google.com/apppasswords) — do not use your account password directly.

---

## 🚢 Deployment

### Deploy Backend to Railway

1. Push your code to GitHub
2. Connect repository to [Railway](https://railway.app/)
3. Add a PostgreSQL plugin from the Railway dashboard
4. Set all environment variables from `.env.example` in Railway's Variables tab
5. Railway auto-deploys from `main` branch using the `Dockerfile`

### Deploy Frontend to Vercel

1. Connect the GitHub repository to [Vercel](https://vercel.com/)
2. Set **Root Directory** to `frontend`
3. Set **Build Command** to `npm run build`
4. Set **Output Directory** to `dist`
5. Add environment variable: `VITE_API_BASE_URL=https://your-railway-domain.up.railway.app`
6. Vercel auto-deploys on every push; SPA routing handled by `frontend/vercel.json`

---

## 🧪 Testing

```bash
# Run the full test suite (26 unit + scenario tests)
uv run pytest -v

# Run with coverage report
uv run pytest --cov=src --cov-report=term-missing

# Run specific scenario
uv run pytest tests/scenarios/test_notification_fallback.py -v

# Lint and format check
uv run ruff check .
uv run ruff format --check .
```

**Test Coverage Includes:**
- `SERIALIZABLE` race condition simulation for concurrent token booking
- `getNextToken()` priority ordering across all 4 tiers
- Multi-provider LLM failure simulation and non-blocking fallback
- Doctor leave auto-cancellation pipeline
- Notification 3-tier fallback cascade

---

## 📡 API Reference

| Category | Method | Endpoint | Description | Auth |
|---|:---:|---|---|:---:|
| Health | `GET` | `/health` | Liveness probe | Public |
| Auth | `POST` | `/api/v1/auth/register` | Register Patient / Doctor / Admin | Public |
| Auth | `POST` | `/api/v1/auth/login` | Authenticate & get JWT | Public |
| Doctors | `GET` | `/api/v1/doctors` | List all active doctors | Any |
| Doctors | `GET` | `/api/v1/doctors/suggest` | AI doctor match by symptoms | Any |
| Doctors | `POST` | `/api/v1/doctors/` | Create doctor profile | Admin |
| Doctors | `POST` | `/api/v1/doctors/{id}/availability` | Set weekly schedule | Admin |
| Doctors | `POST` | `/api/v1/doctors/{id}/leave` | Log leave + auto-cancel queue | Admin |
| Queue | `POST` | `/api/v1/queue/book` | Book token (SERIALIZABLE) | Patient |
| Queue | `GET` | `/api/v1/queue/{id}/status` | Live ETA + position tracker | Patient |
| Queue | `GET` | `/api/v1/queue/patient/my` | My appointments schedule | Patient |
| Queue | `GET` | `/api/v1/queue/doctor/{id}` | Doctor's session queue | Doctor |
| Queue | `POST` | `/api/v1/queue/doctor/{id}/call-next` | Complete & call next patient | Doctor |
| Clinical | `POST` | `/api/v1/clinical/{id}/symptoms` | Submit pre-visit symptoms | Patient |
| Clinical | `GET` | `/api/v1/clinical/{id}/symptoms` | AI triage brief for doctor | Doctor |
| Clinical | `POST` | `/api/v1/clinical/{id}/post-visit-notes` | Submit notes & prescription | Doctor |
| Clinical | `GET` | `/api/v1/clinical/{id}/post-visit-notes` | Patient post-visit record | Patient |
| Admin | `GET` | `/api/v1/admin/stats` | System KPIs & health flags | Admin |
| Admin | `GET` | `/api/v1/admin/scheduling-dashboard` | Live delay dashboard | Admin |
| Admin | `POST` | `/api/v1/admin/seed-demo` | Seed demo data | Public* |
| Calendar | `GET` | `/api/v1/calendar/auth-url` | Google OAuth consent URL | Any |
| Calendar | `GET` | `/api/v1/calendar/callback` | OAuth token exchange | Public |

> Full interactive documentation: [Swagger UI](https://healthqueue-production.up.railway.app/docs)

---

## 🔑 Demo Credentials

Click any card on the login page to sign in instantly, or use these credentials manually:

| Role | Email | Password | Access |
|:---|:---|:---|:---|
| 👤 **Patient** | `rahul@example.com` | `Password123!` | Book appointments, track queue, view records |
| 🩺 **Doctor** | `dr.sharma@clinic.com` | `Password123!` | Manage queue (Cardiology), add clinical notes |
| 🛡️ **Admin** | `admin@clinic.com` | `Password123!` | Full system access, doctor management, leave control |

> **Additional demo doctors:** `dr.mehta@clinic.com` (Neurology), `dr.kapoor@clinic.com` (Dermatology), `dr.verma@clinic.com` (General Practice), `dr.gupta@clinic.com` (Orthopedics) — all with password `Password123!`

---

## 🤝 Contributing

Contributions, bug reports, and feature requests are welcome!

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feat/your-feature-name`
3. **Commit** with semantic messages: `feat(queue): add anchor slot grace window config`
4. **Push** your branch: `git push origin feat/your-feature-name`
5. **Open** a Pull Request against `main`

### Code Style
- Backend: `ruff check .` and `ruff format .` must pass
- Follow PEP 8; all async functions must use `async`/`await`
- Never commit `.env`, secrets, `__pycache__`, or build artifacts
- Tests required for any new API endpoint or queue algorithm change

---

## 👤 Authors

| Name | Role | GitHub |
|:---|:---|:---|
| **Ayush** | Creator & Lead Developer | [@Ayush99392003](https://github.com/Ayush99392003) |

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

```
MIT License — Copyright (c) 2026 Ayush

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software to deal in the Software without restriction, including without
limitation the rights to use, copy, modify, merge, publish, distribute, and/or
sell copies of the Software.
```

---

## 🙏 Acknowledgments

- **[FastAPI](https://fastapi.tiangolo.com/)** — For the best Python API framework with zero-boilerplate async support
- **[instructor](https://python.useinstructor.com/)** — For making structured LLM extraction with Pydantic effortless
- **[Groq](https://groq.com/)** — For blazing-fast LLM inference enabling sub-second clinical triage
- **[Railway](https://railway.app/)** — For frictionless PostgreSQL + Docker deployment
- **[Twilio](https://twilio.com/)** — For reliable WhatsApp and SMS delivery
- **[tenacity](https://tenacity.readthedocs.io/)** — For the retry library that makes every integration resilient
- **VIT Bhopal** — Academic project motivating a real clinical problem-solution

---

<div align="center">

**[🌐 Live App](https://healthfirstqueue-g5bq-izfen7jq3-ayush99392003s-projects.vercel.app/) · [📖 API Docs](https://healthqueue-production.up.railway.app/docs) · [🏥 Health Check](https://healthqueue-production.up.railway.app/health) · [📐 Architecture](docs/ARCHITECTURE.md)**

*Built with ❤️ to solve real clinical scheduling bottlenecks*

</div>
