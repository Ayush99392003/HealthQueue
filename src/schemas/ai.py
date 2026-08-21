"""Pydantic v2 schemas for AI/LLM structured extraction via instructor."""

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class UrgencyLevel(str, Enum):
    """Clinical urgency levels for pre-visit triage."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FrequencyEnum(str, Enum):
    """Medication dosage frequency options."""

    ONCE_DAILY = "once_daily"
    TWICE_DAILY = "twice_daily"
    THRICE_DAILY = "thrice_daily"
    AS_NEEDED = "as_needed"


class PrescriptionItem(BaseModel):
    """
    A single prescribed medication item extracted from doctor clinical notes.

    Used by instructor to enforce structured extraction from LLM output.
    """

    medication_name: Annotated[str, Field(max_length=150, description="Generic or brand medication name")]
    dosage: Annotated[str | None, Field(default=None, max_length=50, description="Dose strength, e.g. '500mg'")]
    frequency: Annotated[FrequencyEnum | None, Field(default=None, description="Dosing frequency")]
    duration_days: Annotated[int | None, Field(default=None, gt=0, description="Duration in days")]
    special_instructions: Annotated[str | None, Field(default=None, description="e.g. 'take with food'")]


class PreVisitTriage(BaseModel):
    """
    Structured pre-visit triage output extracted by instructor from the LLM.

    If instructor fails to populate this after retries:
    - urgency_level defaults to 'medium' (conservative clinical default)
    - Raw symptom_text is shown to the doctor instead
    - is_processed is set to False in the symptoms table
    """

    urgency_level: Annotated[
        UrgencyLevel,
        Field(description="Clinical urgency level based on reported symptoms"),
    ]
    chief_complaint: Annotated[
        str,
        Field(
            max_length=200,
            description="Single concise clinical phrase summarizing the primary complaint",
        ),
    ]
    suggested_questions: Annotated[
        list[str],
        Field(
            min_length=2,
            max_length=5,
            description="High-yield diagnostic questions for the doctor to ask",
        ),
    ]


class PostVisitSummary(BaseModel):
    """
    Structured post-visit patient summary extracted by instructor from the LLM.

    If instructor fails after retries:
    - patient_friendly_summary is set to None
    - Raw doctor_clinical_notes are shown to the patient instead
    - is_processed is set to False in post_visit_notes table
    """

    patient_friendly_summary: Annotated[
        str,
        Field(description="Plain-language explanation of diagnosis and treatment for the patient"),
    ]
    medication_schedule: Annotated[
        str,
        Field(description="Clear, step-by-step instructions for taking all prescribed medications"),
    ]
    follow_up_steps: Annotated[
        list[str],
        Field(
            min_length=1,
            max_length=5,
            description="Concrete recovery actions and red-flag warning signs for the patient",
        ),
    ]
    extracted_medications: Annotated[
        list[PrescriptionItem],
        Field(
            default_factory=list,
            description="Structured medication items parsed from clinical notes",
        ),
    ]
