"""
Notification message templates for all event types.

Actionable WhatsApp copy (AGENTS.md Invariant 5):
- Explicit delay minutes and updated ETA
- SHIFT / RESCHEDULE reply instructions
- Token number always shown for patient reference
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationContent:
    subject: str           # Email subject
    whatsapp_body: str     # WhatsApp message body
    email_html: str        # HTML email body
    email_text: str        # Plain-text fallback


def booking_confirmation(
    *,
    patient_name: str,
    doctor_name: str,
    token_number: int,
    appointment_date: str,
    session: str,
    display_position: int | None,
    eta_time: str | None,
    slot_type: str,
    anchor_time: str | None,
) -> NotificationContent:
    slot_info = (
        f"Anchor slot at {anchor_time}"
        if slot_type == "anchor" and anchor_time
        else "Open queue"
    )
    eta_info = f"Estimated time: ~{eta_time}" if eta_time else "Live ETA available at clinic"

    whatsapp = (
        f"✅ Booking Confirmed!\n"
        f"Dr. {doctor_name} | Token #{token_number}\n"
        f"📅 {appointment_date} ({session})\n"
        f"🎫 {slot_info}\n"
        f"📍 Position ~{display_position} in queue\n"
        f"⏰ {eta_info}\n\n"
        f"Reply SHIFT to move to a later slot today, or RESCHEDULE for another day."
    )
    text = (
        f"Booking Confirmed — Token #{token_number}\n"
        f"Doctor: Dr. {doctor_name}\n"
        f"Date: {appointment_date} ({session})\n"
        f"Slot: {slot_info}\n"
        f"Position: ~{display_position}\n"
        f"{eta_info}"
    )
    html = f"<p>{text.replace(chr(10), '<br/>')}</p>"

    return NotificationContent(
        subject=f"Appointment Confirmed — Token #{token_number} with Dr. {doctor_name}",
        whatsapp_body=whatsapp,
        email_html=html,
        email_text=text,
    )


def delay_alert(
    *,
    patient_name: str,
    doctor_name: str,
    token_number: int,
    delay_minutes: int,
    patients_ahead: int,
    eta_time: str | None,
) -> NotificationContent:
    whatsapp = (
        f"⏳ Queue Update\n"
        f"Token #{token_number}: Dr. {doctor_name} is running ~{delay_minutes} min behind.\n"
        f"You are ~{patients_ahead} patients away. Estimated call: ~{eta_time or 'TBD'}.\n\n"
        f"Reply SHIFT to move to a later token today, or RESCHEDULE to pick another day."
    )
    text = (
        f"Queue Delay Alert — Token #{token_number}\n"
        f"Dr. {doctor_name} is running approximately {delay_minutes} minutes behind schedule.\n"
        f"You are approximately {patients_ahead} patients away.\n"
        f"Estimated call time: {eta_time or 'To be determined'}.\n\n"
        f"You may reply SHIFT or RESCHEDULE to manage your appointment."
    )
    html = f"<p>{text.replace(chr(10), '<br/>')}</p>"

    return NotificationContent(
        subject=f"Queue Delay Update — Token #{token_number}",
        whatsapp_body=whatsapp,
        email_html=html,
        email_text=text,
    )


def leave_cancellation(
    *,
    patient_name: str,
    doctor_name: str,
    token_number: int,
    appointment_date: str,
    session: str,
) -> NotificationContent:
    whatsapp = (
        f"⚠️ Appointment Cancelled\n"
        f"Dear {patient_name}, your appointment with Dr. {doctor_name} "
        f"on {appointment_date} ({session}) — Token #{token_number} "
        f"has been cancelled due to doctor leave.\n\n"
        f"Please contact the clinic to reschedule at your convenience."
    )
    text = (
        f"Appointment Cancellation Notice — Token #{token_number}\n"
        f"Dear {patient_name},\n\n"
        f"Your appointment with Dr. {doctor_name} on {appointment_date} ({session}) "
        f"has been cancelled due to an approved leave of absence.\n\n"
        f"We apologise for the inconvenience. Please contact the clinic to reschedule."
    )
    html = f"<p>{text.replace(chr(10), '<br/>')}</p>"

    return NotificationContent(
        subject=f"Appointment Cancelled — {appointment_date} with Dr. {doctor_name}",
        whatsapp_body=whatsapp,
        email_html=html,
        email_text=text,
    )


def post_visit_summary(
    *,
    patient_name: str,
    doctor_name: str,
    patient_summary: str,
    medication_schedule: str,
    follow_up_steps: list[str],
) -> NotificationContent:
    steps_text = "\n".join(f"• {s}" for s in follow_up_steps)
    text = (
        f"Post-Visit Summary — From Dr. {doctor_name}\n\n"
        f"Dear {patient_name},\n\n"
        f"{patient_summary}\n\n"
        f"Medication Schedule:\n{medication_schedule}\n\n"
        f"Follow-up Steps:\n{steps_text}"
    )
    html = f"<p>{text.replace(chr(10), '<br/>')}</p>"
    whatsapp = (
        f"📋 Your visit summary from Dr. {doctor_name} is ready.\n"
        f"Please check your email for the full report and medication schedule."
    )

    return NotificationContent(
        subject=f"Your Post-Visit Summary from Dr. {doctor_name}",
        whatsapp_body=whatsapp,
        email_html=html,
        email_text=text,
    )
