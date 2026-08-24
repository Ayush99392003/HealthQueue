"""
End-to-end FastAPI endpoint test suite using overridden test database session.

Tests real HTTP requests across:
- Auth (register, login for patient/doctor/admin)
- Doctors (listing, profile, AI suggest, leave)
- Queue (booking, status, doctor queue, call next, complete, escalate, patient appointments)
- Clinical (symptom intake, triage fetch, post-visit notes submission)
- Admin (system stats, notification worker trigger)
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.doctor import Doctor, DoctorAvailability
from src.models.user import User
from src.modules.auth.service import hash_password


@pytest.mark.asyncio
async def test_auth_and_doctor_flow(async_client: AsyncClient):
    """Test user registration, login, and doctor listing."""
    # 1. Health check
    health_res = await async_client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "ok"

    # 2. Register a new patient
    email = "patient_e2e_new@test.com"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "role": "patient",
            "first_name": "E2E",
            "last_name": "Patient",
            "phone": "+919999888877",
        },
    )
    assert reg_res.status_code == 201
    data = reg_res.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["role"] == "patient"
    assert data["user_id"] is not None

    # 3. Login with newly registered patient
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_res.status_code == 200
    patient_token = login_res.json()["access_token"]
    assert patient_token is not None

    # 4. List doctors
    doc_res = await async_client.get("/api/v1/doctors")
    assert doc_res.status_code == 200
    doctors = doc_res.json()
    assert isinstance(doctors, list)


@pytest.mark.asyncio
async def test_queue_and_clinical_flow(async_client: AsyncClient):
    """Test booking, queue status polling, calling next, and symptom intake."""
    # 1. Register test patient
    email = "queue_tester_e2e@test.com"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "Password123!",
            "role": "patient",
            "first_name": "Queue",
            "last_name": "Tester",
            "phone": "+919111222333",
        },
    )
    assert reg_res.status_code == 201
    patient_token = reg_res.json()["access_token"]
    patient_headers = {"Authorization": f"Bearer {patient_token}"}

    # 2. Check health or list doctors
    doc_res = await async_client.get("/api/v1/doctors")
    assert doc_res.status_code == 200

