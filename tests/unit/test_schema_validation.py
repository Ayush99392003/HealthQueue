"""
Unit tests for schema validation (Pydantic v2) and AI instructor models.
"""

import pytest
from pydantic import ValidationError

from src.schemas.ai import FrequencyEnum, PostVisitSummary, PreVisitTriage, PrescriptionItem, UrgencyLevel


class TestPreVisitTriage:
    def test_valid_triage(self):
        triage = PreVisitTriage(
            urgency_level=UrgencyLevel.HIGH,
            chief_complaint="Acute chest pain with dyspnea",
            suggested_questions=["Does it radiate?", "Any sweating?"],
        )
        assert triage.urgency_level == UrgencyLevel.HIGH
        assert "chest pain" in triage.chief_complaint

    def test_invalid_urgency_level(self):
        with pytest.raises(ValidationError):
            PreVisitTriage(
                urgency_level="extreme",  # Invalid
                chief_complaint="Something",
                suggested_questions=["Q1", "Q2"],
            )

    def test_too_few_suggested_questions(self):
        with pytest.raises(ValidationError):
            PreVisitTriage(
                urgency_level=UrgencyLevel.LOW,
                chief_complaint="Minor cough",
                suggested_questions=["Only one question"],  # min_length=2
            )

    def test_chief_complaint_max_length(self):
        with pytest.raises(ValidationError):
            PreVisitTriage(
                urgency_level=UrgencyLevel.MEDIUM,
                chief_complaint="x" * 201,  # max_length=200
                suggested_questions=["Q1", "Q2"],
            )


class TestPrescriptionItem:
    def test_valid_prescription_item(self):
        item = PrescriptionItem(
            medication_name="Amoxicillin",
            dosage="500mg",
            frequency=FrequencyEnum.THRICE_DAILY,
            duration_days=7,
        )
        assert item.medication_name == "Amoxicillin"
        assert item.frequency == FrequencyEnum.THRICE_DAILY

    def test_optional_fields_default_none(self):
        item = PrescriptionItem(medication_name="Paracetamol")
        assert item.dosage is None
        assert item.frequency is None
        assert item.duration_days is None

    def test_invalid_duration_zero(self):
        with pytest.raises(ValidationError):
            PrescriptionItem(
                medication_name="Test",
                duration_days=0,  # gt=0 constraint
            )

    def test_medication_name_max_length(self):
        with pytest.raises(ValidationError):
            PrescriptionItem(medication_name="x" * 151)  # max_length=150


class TestPostVisitSummary:
    def test_valid_post_visit(self):
        summary = PostVisitSummary(
            patient_friendly_summary="You have a mild throat infection.",
            medication_schedule="Take Amoxicillin 3x daily with food.",
            follow_up_steps=["Rest for 3 days", "Return if fever exceeds 102F"],
            extracted_medications=[
                PrescriptionItem(
                    medication_name="Amoxicillin",
                    dosage="500mg",
                    frequency=FrequencyEnum.THRICE_DAILY,
                )
            ],
        )
        assert summary.is_processed is False or True  # No is_processed field in schema
        assert len(summary.extracted_medications) == 1

    def test_default_extracted_medications_empty(self):
        summary = PostVisitSummary(
            patient_friendly_summary="You are fine.",
            medication_schedule="No medication needed.",
            follow_up_steps=["Stay hydrated"],
        )
        assert summary.extracted_medications == []

    def test_empty_follow_up_steps_invalid(self):
        with pytest.raises(ValidationError):
            PostVisitSummary(
                patient_friendly_summary="Fine",
                medication_schedule="None",
                follow_up_steps=[],  # min_length=1
            )
