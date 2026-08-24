# 07. System Design Document

**System Title**: Intelligent Healthcare Appointment & Clinical Lifecycle Management Platform  
**Target Word Count**: ~800 words  
**Core Focus**: Concurrency, Conflict Handling, Multi-Tier Queueing, and Fault-Tolerant Integrations

---

## 1. Problem Statement
Modern outpatient healthcare clinics face operational bottlenecks when relying on conventional booking engines. Clinics must reconcile two conflicting realities: accommodating critical, high-urgency clinical presentations without starving routine preventative appointments, while eliminating double-bookings during peak booking windows. Furthermore, physicians spend excessive consultation time deciphering unorganized patient notes, and patients frequently misunderstand technical prescriptions upon discharge. This platform delivers an end-to-end clinical workflow with zero-tolerance concurrency protection, automated pre- and post-visit LLM intelligence, multi-tier queue management, and resilient dual-channel notifications.

---

## 2. Architecture Overview
The platform uses a **Three-Tier Architecture**:
1. **Presentation Layer**: A responsive React SPA offering dedicated, role-segregated portals for Patients, Doctors, and Administrators.
2. **Application Layer**: A stateless Node.js / Express REST API integrating a provider-agnostic LLM router (Groq, OpenAI, Claude, Gemini), a dual-channel notification dispatcher (Twilio WhatsApp + SendGrid Email), and a Google Calendar OAuth 2.0 synchronizer. Asynchronous tasks (medication schedules, delay alerts, retries) are offloaded to a background scheduler.
3. **Data Layer**: A normalized PostgreSQL relational database hosted on Railway, enforcing strict referential integrity, unique constraints, and transaction isolation.

---

## 3. Double-Booking Prevention & Concurrency Control
To guarantee absolute slot exclusivity in high-concurrency environments (e.g., hundreds of users competing for newly released specialist slots), the system implements a **multi-layered defensive locking protocol**:

1. **Database Relational Constraint**: An explicit unique constraint on `(doctor_id, appointment_date, appointment_time)` prevents duplicate records at the database engine level.
2. **Pessimistic Row-Level Locking (`FOR UPDATE`)**: During booking transactions, the backend opens a `SERIALIZABLE` transaction and executes `SELECT ... FOR UPDATE` on the targeted slot row in `appointment_slots`. Any concurrent request attempting to inspect or lock the same slot is placed in a blocking queue until the first transaction commits or rolls back.
3. **Atomic Evaluation**: If the slot is already booked, the second transaction is immediately aborted with a structured `HTTP 409 Conflict` error, eliminating race conditions.
4. **Temporary Slot Hold Mechanism**: When a patient initiates the booking flow, an atomic record is inserted into `slot_holds` with a 5-minute time-to-live (`expires_at = NOW() + INTERVAL '5 min'`). This reserves the slot while the patient completes the symptom questionnaire. Expired holds are automatically purged by a 60-second cron worker.

```
Incoming Booking Request â”€â”€â–º BEGIN ISOLATION SERIALIZABLE â”€â”€â–º SELECT slot FOR UPDATE 
                                                                       â”‚
           â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ Slot Status Check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¤
           â–¼                                                           â–¼
   [Status: AVAILABLE]                                         [Status: BOOKED]
Insert into APPOINTMENTS                                       ROLLBACK Transaction
Update APPOINTMENT_SLOTS (status='booked')                     Return HTTP 409 Conflict
COMMIT Transaction â”€â”€â–º Return HTTP 201
```

---

## 4. Hybrid Priority-FCFS Queue & Dynamic Delay Handling
To prevent high-urgency cases from being delayed while ensuring fair access for routine visits, each doctor's daily capacity is partitioned into a **Three-Tier Distribution**:
- **60% Regular Tier (FCFS)**: Standard booking window for routine consults.
- **25% Priority Tier**: Reserved for cases pre-screened by the LLM as `"High"` urgency, guaranteeing a 24â€“48 hour consultation SLA.
- **15% Emergency Tier**: Unallocated buffer reserved for acute same-day escalations managed by clinical administrators.

For walk-in and hybrid clinics, the system assigns fixed non-sequential token numbers (`token_number`) while dynamically recomputing `display_position` and live `estimated_start_time` using actual physician consultation pace. If an emergency case is soft-inserted, subsequent queue positions shift automatically without mutating original token identifiers.

---

## 5. Doctor Leave Conflict Resolution
When an Administrator marks a doctor on leave for a date range via `POST /doctors/:id/leave`:
1. The system initiates an atomic transaction that registers the leave in `doctor_leave` and queries all scheduled appointments within the window.
2. Affected appointments are transitioned to `leave_cancelled` status.
3. The system immediately enqueues high-priority notification jobs across WhatsApp and Email.
4. Patients receive clear alerts within 24 hours containing authenticated, one-click links to either reschedule into prioritized upcoming slots or receive an automated cancellation receipt.

---

## 6. Fault Tolerance & Graceful Degradation

### LLM Resilience
All LLM operations (pre-visit triage and post-visit translations) are wrapped in an asynchronous circuit-breaker:
- Maximum 5-second timeout per call with up to 2 exponential backoff retries.
- If all attempts fail, the core appointment booking or notes submission transaction completes unhindered.
- The raw symptom or clinical text is safely stored with `is_processed = false`, ensuring zero downtime or user disruption during third-party LLM outages.

### Notification Failure Recovery
Notifications use an asynchronous write-behind pattern. Outbound messages are recorded in `notifications` with `status = 'pending'`. The notification worker employs a 3-tier exponential backoff retry mechanism (immediate, +5 minutes, +1 hour). Messages exceeding 3 failed attempts transition to `failed_permanent` for administrative dead-letter auditing.

---

## 7. Scalability & Security
The database utilizes targeted composite indexes on `(doctor_id, appointment_date, status)` and `(status, retry_count, last_attempt_at)`. Passwords are protected using `bcrypt` (cost factor 12), and all external credentials and OAuth tokens are encrypted at rest.

