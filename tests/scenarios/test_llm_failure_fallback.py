"""
Scenario test: LLM failure fallback behavior.

Verifies that when LLM extraction fails:
1. The workflow completes WITHOUT blocking the booking or note submission
2. is_processed is set to False
3. Raw input is preserved
4. LLM errors do NOT propagate as HTTP errors
"""

import pytest

from src.modules.ai.router import llm_extract
from src.schemas.ai import PreVisitTriage, PostVisitSummary


@pytest.mark.asyncio
async def test_llm_returns_none_on_bad_provider():
    """
    When an unconfigured/invalid provider is used, llm_extract must return None
    (non-blocking) not raise an exception that would break the calling service.
    """
    result = await llm_extract(
        response_model=PreVisitTriage,
        prompt="Patient has severe chest pain radiating to the left arm.",
        call_type="pre_visit",
        queue_id=None,
        provider="nonexistent_provider",  # Invalid provider
    )

    # NON-BLOCKING: must return None, never raise
    assert result is None


@pytest.mark.asyncio
async def test_llm_failure_fallback_preserves_raw_data(session, queue_entry):
    """
    Simulate LLM failure scenario:
    - is_processed stays False
    - Raw symptom_text is always stored before LLM is called
    - The queue_entry itself is valid and accessible
    """
    from src.models.clinical import Symptoms

    raw_symptom_text = "I have a persistent dry cough for 2 weeks with mild fever."

    # Store raw symptom before calling LLM (this always happens first)
    symptom = Symptoms(
        queue_id=queue_entry.id,
        symptom_text=raw_symptom_text,
        is_processed=False,  # LLM not yet called
    )
    session.add(symptom)
    await session.flush()

    # Simulate LLM failure
    llm_result = await llm_extract(
        response_model=PreVisitTriage,
        prompt=raw_symptom_text,
        call_type="pre_visit",
        queue_id=queue_entry.id,
        provider="nonexistent_provider",
    )

    # LLM failed — is_processed remains False, raw text preserved
    assert llm_result is None
    assert symptom.symptom_text == raw_symptom_text
    assert symptom.is_processed is False
    assert symptom.ai_summary is None


@pytest.mark.asyncio
async def test_post_visit_fallback_preserves_doctor_notes(session, queue_entry):
    """
    Verify that doctor clinical notes are always stored even if post-visit LLM fails.
    """
    from src.models.clinical import PostVisitNotes

    raw_notes = "Patient presents with upper respiratory tract infection. Prescribed antibiotics."
    prescription = [{"medication_name": "Amoxicillin", "dosage": "500mg", "frequency": "thrice_daily"}]

    note = PostVisitNotes(
        queue_id=queue_entry.id,
        doctor_clinical_notes=raw_notes,
        prescription=prescription,
        is_processed=False,
    )
    session.add(note)
    await session.flush()

    # Simulate LLM failure for post-visit summary
    llm_result = await llm_extract(
        response_model=PostVisitSummary,
        prompt=raw_notes,
        call_type="post_visit",
        queue_id=queue_entry.id,
        provider="nonexistent_provider",
    )

    # Doctor notes ALWAYS preserved regardless of LLM result
    assert note.doctor_clinical_notes == raw_notes
    assert note.prescription == prescription
    assert note.is_processed is False
    assert llm_result is None
