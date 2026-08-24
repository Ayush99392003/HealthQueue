# System Design Document

**System Title**: Intelligent Healthcare Appointment & Clinical Lifecycle Management Platform
**Word Count**: ~800 words
**Core Focus**: Concurrency, Conflict Handling, Multi-Tier Queueing, and Fault-Tolerant Integrations

---

## 1. Problem Statement
Modern outpatient healthcare clinics face operational bottlenecks when relying on conventional booking engines. Clinics must reconcile two conflicting realities: accommodating critical, high-urgency clinical presentations without starving routine preventative appointments, while eliminating double-bookings during peak booking windows. Furthermore, physicians spend excessive consultation time deciphering unorganized patient notes, and patients frequently misunderstand technical prescriptions upon discharge. This platform delivers an end-to-end clinical workflow with zero-tolerance concurrency protection, automated pre- and post-visit LLM intelligence, multi-tier queue management, and resilient dual-channel notifications.

---

## 2. Architecture Overview
The platform uses a **Three-Tier Architecture**:
1. **Presentation Layer**: A responsive React 18 + Vite SPA offering dedicated, role-segregated portals for Patients, Doctors, and Administrators. Deployed on Vercel with SPA rewrite rules.
2. **Application Layer**: A stateless **Python 3.14+ / FastAPI** async REST API built with Pydantic v2 for schema validation and SQLAlchemy 2.0 Async for non-blocking database access. Integrates a provider-agnostic LLM router (`instructor` + Groq, OpenAI, Claude, Gemini), a dual-channel notification dispatcher (Twilio WhatsApp + SMS + SMTP Email), and a Google Calendar OAuth 2.0 synchronizer. Resilient retries on all external integrations are handled by `tenacity` with exponential backoff and jitter. Deployed on Railway via Docker.
3. **Data Layer**: A normalized PostgreSQL relational database hosted on Railway, enforcing strict referential integrity, UNIQUE constraints, and `SERIALIZABLE` transaction isolation across all queue mutations.

---

## 3. Double-Booking Prevention & Concurrency Control
To guarantee absolute slot exclusivity in high-concurrency environments (e.g., hundreds of users competing for a specialist's queue), the system implements a **multi-layered defensive locking protocol**:

1. **Database Relational Constraint**: An explicit unique constraint on `(doctor_id, appointment_date, session, token_number)` in the `doctor_queue` table prevents duplicate token assignment at the database engine level.
2. **Pessimistic Row-Level Locking (`FOR UPDATE`)**: During booking transactions (`POST /api/v1/queue/book`), the backend opens a `SERIALIZABLE` transaction and executes `SELECT ... FOR UPDATE` on the doctor's queue for the target `(doctor_id, appointment_date, session)`. Any concurrent request attempting to lock the same row is placed in a blocking queue until the first transaction commits or rolls back.
3. **Atomic Token Increment**: The next `token_number` is computed inside the locked transaction, guaranteeing sequential, conflict-free assignment.
4. **tenacity Retry on Collision**: If a database serialization exception occurs, `tenacity` automatically retries the full booking transaction up to 3 times with exponential backoff before surfacing an `HTTP 409 Conflict` to the client.

```
Incoming Booking Request ──► BEGIN SERIALIZABLE ──► SELECT FOR UPDATE (doctor_queue)
                                                              │
            ┌──────────────── Token Status Check ────────────┤
            ▼                                                 ▼
    [Token Available]                                 [Collision Detected]
INSERT into doctor_queue                              ROLLBACK Transaction
COMMIT Transaction                                    tenacity retry (×3)
Return HTTP 201 {token_number}                        Return HTTP 409 Conflict
```

---

## 4. Hybrid Priority-FCFS Queue & Dynamic Delay Handling
To prevent high-urgency cases from being delayed while ensuring fair access for routine visits, each doctor's daily capacity is partitioned into a configurable **Four-Tier Distribution** stored on the `Doctor` profile:
- **Regular Tier (FCFS)**: Standard open queue for routine consultations — served in strict First-Come, First-Served order by `booked_at`.
- **Priority Tier**: Reserved for pre-screened urgent cases, interleaved into the regular queue at a configured ratio (e.g., 1 priority per 3 regular) to prevent starvation.
- **Anchor Slots**: Fixed clock-time appointments pulled forward if the doctor runs behind schedule (within a grace window), held if running ahead.
- **Emergency Tier**: Acute same-day escalations inserted immediately at `current_serving_position + 1`, bypassing all other tiers.

For walk-in and hybrid clinics, the system assigns permanent `token_number` identifiers at booking while dynamically recomputing `display_position` and live `estimated_wait_minutes` using actual physician consultation pace (`avg_consult_minutes` rolling average). Every time a doctor completes a consultation and clicks **"Complete & Call Next"**, the `getNextToken()` engine re-evaluates priorities and broadcasts updated positions to all waiting patients.

---

## 5. Doctor Leave Conflict Resolution
When an Administrator marks a doctor on leave for a date range via `POST /api/v1/doctors/{id}/leave`:
1. The system initiates an atomic transaction that registers the leave in `doctor_leave` and queries all `waiting` status queue entries within the leave window from `doctor_queue`.
2. Affected appointments are transitioned to `cancelled` status in bulk.
3. The system immediately dispatches high-priority dual-channel notifications — WhatsApp alert with one-click RESCHEDULE option, followed by a formal Email cancellation receipt if WhatsApp fails.
4. Patients receive clear, actionable alerts containing rebooking instructions and the reason for cancellation.

---

## 6. Fault Tolerance & Graceful Degradation

### LLM Resilience (`instructor` + `tenacity`)
All LLM operations (pre-visit triage and post-visit clinical summarization) are wrapped in a `tenacity`-guarded async retry loop with `instructor` enforcing Pydantic schema compliance:
- Maximum **5-second timeout** per LLM call with up to **2 exponential backoff retries** and random jitter.
- If all attempts fail, the core appointment booking or notes submission transaction completes unhindered — **never blocked**.
- The raw symptom text or clinical shorthand is safely stored with `is_processed = false` in `symptoms` / `post_visit_notes`, and the failure is logged to `llm_call_log` with provider, latency, and error details. Doctors always see the raw input as a fallback.

### Notification Failure Recovery (3-Tier Cascade)
Notifications implement a cascading delivery strategy — WhatsApp → SMS → Email. Each channel is guarded by `tenacity` with 3 retry attempts and exponential backoff. Outbound messages are recorded in the `notifications` table with `status = 'pending'`. Failed dispatches are retried by a background worker; messages exceeding all retry attempts are marked `status = 'failed'` and retained for administrative audit.

---

## 7. Scalability & Security
The database utilizes targeted composite indexes on `(doctor_id, appointment_date, status)` and `(status, retry_count)`. All passwords are hashed with `bcrypt`, JWT tokens expire after a configurable window, and all external credentials and Google OAuth refresh tokens are stored encrypted at rest. The FastAPI application is fully stateless and horizontally scalable behind Railway's container orchestration.
