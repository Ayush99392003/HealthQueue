# Healthcare Appointment & Follow-up Manager

> **Intelligent, token-based hybrid clinical scheduling platform with automated pre-visit AI triage, dynamic queue reflow, post-visit summarization, and dual-channel notifications.**

---

## 🌟 Overview

Traditional healthcare booking systems fail because patient consultation times are unpredictable. This platform replaces rigid clock-time appointments with an **intelligent, token-based hybrid queue engine** backed by:
- **Pre-visit AI Triage:** Symptom intake and structured urgency scoring (`low`, `medium`, `high`) powered by `instructor` + Pydantic v2.
- **Dynamic Queue Flow (`getNextToken`):** Intelligent serving order prioritizing Emergency cases, Anchor times, Priority tier (1-in-4), and First-Come-First-Served (FCFS).
- **Concurrency & Double-Booking Protection:** `SERIALIZABLE` transactions with pessimistic row locking (`SELECT ... FOR UPDATE`).
- **Real-Time Delay Detection:** Dynamic ETA recalculation and patient reflow alerts when consultations run behind pace.
- **Post-Visit Summaries & Reminders:** Structured medication extraction and automatic WhatsApp/Email reminders.
- **Dual-Calendar Syncing:** Google Calendar API OAuth 2.0 integration.

---

## 🛠️ Technology Stack

- **Backend:** Python 3.14+ (FastAPI + Pydantic v2 + SQLAlchemy 2.0 Async + `asyncpg`) adhering to PEP 8
- **Package Manager:** `uv`
- **Structured AI / LLM Routing:** `instructor` (Groq, Azure OpenAI, Google Gemini, OpenAI, Anthropic) with Pydantic v2 schemas
- **Retry & Fault Tolerance:** `tenacity` (exponential backoff, jitter, before-sleep logging)
- **Logging:** `rich` structured console and file logging (`RichHandler` + contextual loggers)
- **Database:** PostgreSQL (Hosted on Railway)
- **Testing:** `pytest` (Unit and Scenario-Based Integration Tests, strict real data validation with no dummy mocks)
- **Frontend:** React (Vite) + Tailwind CSS (Patient Portal, Doctor Dashboard, Admin Control Center)
- **Notifications:** WhatsApp (Twilio) & Email (SMTP / SendGrid)

---

## 🛡️ Centralized Error Handling & Fallbacks
The system enforces strict domain fallbacks to ensure clinical workflows are never interrupted:
- **AI Extractions (`instructor` + `tenacity`):** If an LLM call fails or times out (>5s), the system retries with exponential backoff. If retries fail, it logs to `llm_call_log`, marks `is_processed=False`, and falls back to displaying raw symptoms/doctor notes without blocking bookings.
- **Dual-Channel Notification Fallback:** If WhatsApp delivery fails, it automatically falls back to Email dispatch, and logs pending retries for background queue workers.
- **Database Concurrency Retries:** High-concurrency serialization collisions automatically retry up to 3 times before raising conflict errors.
- **No Dummy Mock Policy:** If required payload parameters are missing, the API rejects immediately with `422 Unprocessable Entity` rather than silently inventing fake data.

---

## 📁 Repository Structure

```
├── .gitignore                      # Comprehensive exclusion for Python, Node, caches, secrets
├── AGENTS.md                       # Core architectural invariants and guidelines for AI agents
├── README.md                       # Main project overview and setup instructions
├── pyproject.toml                  # Python package configuration and dependencies
├── docs/                           # Technical documentation suite
│   ├── 01-requirements.md          # Functional & non-functional requirements
│   ├── 02-system-architecture.md   # High-level architecture and data flows
│   ├── 03-database-architecture.md # PostgreSQL DDL schemas & ER diagrams
│   ├── 04-scheduling-and-concurrency.md # getNextToken algorithm and locking rules
│   ├── 05-api-specification.md     # REST API contracts and endpoints
│   ├── 06-ai-llm-integration.md    # Multi-provider LLM prompts and fallbacks
│   ├── 07-system-design-document.md# 800-word formal system design document
│   ├── 08-task-breakdown-and-roadmap.md # 6-phase implementation roadmap
│   └── 09-phase-2-3-finalized-design.md # Finalized backend/frontend design specifications
├── src/                            # Backend source code (FastAPI)
│   ├── core/                       # Config, database engine, rich logging, exceptions
│   ├── models/                     # SQLAlchemy 2.0 mapped models (9 core tables)
│   ├── schemas/                    # Pydantic v2 request/response schemas
│   ├── modules/                    # Domain logic (queue, AI triage, notifications, delay)
│   ├── api/                        # FastAPI endpoint routers
│   └── main.py                     # Application entrypoint
└── tests/                          # Automated test suite
    ├── conftest.py                 # Async test fixtures and database setup
    ├── unit/                       # Unit tests for algorithms and schemas
    └── scenarios/                  # Scenario-based end-to-end clinical workflow tests
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.14+
- `uv` package manager (`pip install uv` or standalone installer)
- PostgreSQL database instance (local or on Railway)

### 2. Installation & Setup
```bash
# Clone the repository
git clone <repo-url>
cd unthinkable

# Create and activate virtual environment using uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies (including dev and test tools)
uv pip install -e ".[dev]"
```

### 3. Environment Configuration
Copy `.env.example` to `.env` and fill in the required keys:
```bash
cp .env.example .env
```

### 4. Running Database Migrations & Seeding
```bash
uv run alembic upgrade head
uv run python -m src.scripts.seed_db
```

### 5. Running the Backend Server
```bash
uv run uvicorn src.main:app --reload --port 8000
```
Interactive API documentation will be available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## 🧪 Testing & Code Quality

```bash
# Run full unit and scenario-based test suite
uv run pytest -v

# Run PEP 8 linting and formatting checks
uv run ruff check .
uv run ruff format --check .
```

---

## 📖 Detailed Documentation

Consult the [`docs/`](./docs) directory for in-depth system designs, queue serving algorithms, and API specifications.
