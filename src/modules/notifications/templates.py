"""
Notification message templates for all event types.

Dual-channel copy:
- WhatsApp: Concise, actionable, with explicit token, delay, and SHIFT/RESCHEDULE reply commands.
- Email: Modern, responsive HTML with clinical branding, clean cards, and metadata tables.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationContent:
    subject: str           # Email subject
    whatsapp_body: str     # WhatsApp message body
    email_html: str        # HTML email body
    email_text: str        # Plain-text fallback


def _wrap_email_html(title: str, preheader: str, content_html: str) -> str:
    """Wraps body content in a clean, responsive HTML email template."""
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; color: #1e293b; margin: 0; padding: 24px; }}
    .container {{ max-width: 580px; margin: 0 auto; background: #ffffff; border-radius: 12px; overflow: hidden; border: 1px solid #e2e8f0; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.05); }}
    .header {{ background: linear-gradient(135deg, #2563eb, #1d4ed8); padding: 24px; text-align: center; color: #ffffff; }}
    .header h1 {{ margin: 0; font-size: 20px; font-weight: 700; letter-spacing: -0.02em; }}
    .body {{ padding: 24px; }}
    .card {{ background: #f1f5f9; border-radius: 8px; padding: 16px; margin: 16px 0; }}
    .token-badge {{ display: inline-block; background: #2563eb; color: #ffffff; font-size: 22px; font-weight: 800; padding: 6px 16px; border-radius: 6px; }}
    .meta-row {{ display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #e2e8f0; font-size: 14px; }}
    .meta-label {{ color: #64748b; font-weight: 500; }}
    .meta-val {{ font-weight: 600; color: #0f172a; }}
    .btn {{ display: inline-block; background: #2563eb; color: #ffffff !important; text-decoration: none; padding: 12px 24px; border-radius: 6px; font-weight: 600; font-size: 14px; margin-top: 16px; }}
    .footer {{ padding: 16px 24px; background: #f8fafc; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0; }}
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <h1>HealthQueue Clinical Manager</h1>
      <p style="margin: 4px 0 0 0; font-size: 13px; opacity: 0.9;">{preheader}</p>
    </div>
    <div class="body">
      {content_html}
    </div>
    <div class="footer">
      <p style="margin: 0;">HealthQueue Clinical Management System &bull; Secure Patient Records</p>
      <p style="margin: 4px 0 0 0;">This is an automated notification. For urgent medical emergencies, please call emergency services immediately.</p>
    </div>
  </div>
</body>
</html>"""


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
        f"✅ *Booking Confirmed!*\n\n"
        f"👨‍⚕️ *Dr. {doctor_name}*\n"
        f"🎫 *Token #{token_number}*\n"
        f"📅 Date: {appointment_date} ({session.capitalize()} Session)\n"
        f"📌 Slot: {slot_info}\n"
        f"📍 Queue Position: ~{display_position or 1}\n"
        f"⏰ {eta_info}\n\n"
        f"Reply *SHIFT* to move to a later slot today, or *RESCHEDULE* for another date."
    )

    text = (
        f"Booking Confirmed — Token #{token_number}\n\n"
        f"Dear {patient_name},\n"
        f"Your appointment with Dr. {doctor_name} is confirmed.\n"
        f"Token Number: #{token_number}\n"
        f"Date: {appointment_date} ({session} session)\n"
        f"Slot Type: {slot_info}\n"
        f"Queue Position: ~{display_position or 1}\n"
        f"{eta_info}\n\n"
        f"HealthQueue Clinical Manager"
    )

    content_html = f"""
      <h2 style="margin-top: 0; font-size: 18px;">Appointment Confirmed</h2>
      <p>Dear {patient_name}, your consultation has been successfully booked.</p>
      <div style="text-align: center; margin: 20px 0;">
        <span class="token-badge">Token #{token_number}</span>
      </div>
      <div class="card">
        <div class="meta-row"><span class="meta-label">Doctor</span><span class="meta-val">Dr. {doctor_name}</span></div>
        <div class="meta-row"><span class="meta-label">Date</span><span class="meta-val">{appointment_date}</span></div>
        <div class="meta-row"><span class="meta-label">Session</span><span class="meta-val">{session.capitalize()}</span></div>
        <div class="meta-row"><span class="meta-label">Slot Type</span><span class="meta-val">{slot_info}</span></div>
        <div class="meta-row" style="border-bottom: none;"><span class="meta-label">Est. Time</span><span class="meta-val">{eta_time or 'Calculated live'}</span></div>
      </div>
      <p style="font-size: 13px; color: #64748b;">Please arrive 10 minutes before your estimated time. You can view your real-time queue position in the Patient Portal.</p>
    """
    html = _wrap_email_html(f"Booking Confirmed — Token #{token_number}", "Appointment Confirmation", content_html)

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
        f"⏳ *Queue Update & Delay Notice*\n\n"
        f"Dr. {doctor_name} is running approximately *{delay_minutes} minutes behind schedule*.\n\n"
        f"🎫 Your Token: *#{token_number}*\n"
        f"👥 Patients ahead: *{patients_ahead}*\n"
        f"⏰ Updated ETA: *{eta_time or 'TBD'}*\n\n"
        f"Reply *SHIFT* to move to a later slot today, or *RESCHEDULE* for another date."
    )
    text = (
        f"Queue Delay Alert — Token #{token_number}\n\n"
        f"Dear {patient_name},\n"
        f"Dr. {doctor_name} is running approximately {delay_minutes} minutes behind schedule.\n"
        f"Patients ahead of you: {patients_ahead}\n"
        f"Updated estimated call time: {eta_time or 'To be determined'}.\n\n"
        f"HealthQueue Clinical Manager"
    )
    content_html = f"""
      <h2 style="margin-top: 0; font-size: 18px; color: #d97706;">⏳ Schedule Delay Alert</h2>
      <p>Dear {patient_name}, Dr. {doctor_name} is running approximately <strong>{delay_minutes} minutes behind schedule</strong> due to extended consultations.</p>
      <div class="card">
        <div class="meta-row"><span class="meta-label">Your Token</span><span class="meta-val">#{token_number}</span></div>
        <div class="meta-row"><span class="meta-label">Patients Ahead</span><span class="meta-val">{patients_ahead}</span></div>
        <div class="meta-row" style="border-bottom: none;"><span class="meta-label">New Estimated Call</span><span class="meta-val">{eta_time or 'Live updating'}</span></div>
      </div>
      <p style="font-size: 13px; color: #64748b;">You can adjust your arrival time accordingly. Track real-time progress on your Patient Portal dashboard.</p>
    """
    html = _wrap_email_html("Queue Delay Notice", "Schedule Adjustment", content_html)

    return NotificationContent(
        subject=f"Queue Delay Notice — Token #{token_number} with Dr. {doctor_name}",
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
        f"⚠️ *Appointment Cancellation Notice*\n\n"
        f"Dear {patient_name}, your consultation with *Dr. {doctor_name}* on *{appointment_date}* ({session.capitalize()}) — *Token #{token_number}* "
        f"has been cancelled due to approved doctor leave.\n\n"
        f"We sincerely apologise for the inconvenience. Please contact the clinic or use the Patient Portal to reschedule."
    )
    text = (
        f"Appointment Cancellation Notice — Token #{token_number}\n\n"
        f"Dear {patient_name},\n\n"
        f"Your appointment with Dr. {doctor_name} on {appointment_date} ({session}) "
        f"has been cancelled due to an approved leave of absence.\n\n"
        f"We apologise for the inconvenience. Please visit the portal or contact the clinic to reschedule.\n\n"
        f"HealthQueue Clinical Manager"
    )
    content_html = f"""
      <h2 style="margin-top: 0; font-size: 18px; color: #dc2626;">⚠️ Appointment Cancelled — Doctor Leave</h2>
      <p>Dear {patient_name}, we regret to inform you that your appointment with <strong>Dr. {doctor_name}</strong> on <strong>{appointment_date}</strong> ({session} session) has been cancelled due to an approved doctor leave of absence.</p>
      <div class="card" style="background: #fef2f2; border: 1px solid #fee2e2;">
        <div class="meta-row"><span class="meta-label">Cancelled Token</span><span class="meta-val">#{token_number}</span></div>
        <div class="meta-row"><span class="meta-label">Original Date</span><span class="meta-val">{appointment_date}</span></div>
        <div class="meta-row" style="border-bottom: none;"><span class="meta-label">Doctor</span><span class="meta-val">Dr. {doctor_name}</span></div>
      </div>
      <p>Please log in to the Patient Portal to select an alternative date or book with another specialist.</p>
    """
    html = _wrap_email_html("Appointment Cancellation Notice", "Doctor Leave Cancellation", content_html)

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
    steps_html = "".join(f"<li style='margin-bottom: 6px;'>{s}</li>" for s in follow_up_steps)

    whatsapp = (
        f"📋 *Your Post-Visit Clinical Summary is Ready*\n\n"
        f"Doctor: *Dr. {doctor_name}*\n"
        f"Patient: *{patient_name}*\n\n"
        f"Summary:\n{patient_summary[:200]}...\n\n"
        f"Please check your email for the full clinical report and structured medication schedule."
    )
    text = (
        f"Post-Visit Summary — From Dr. {doctor_name}\n\n"
        f"Dear {patient_name},\n\n"
        f"{patient_summary}\n\n"
        f"Medication Schedule:\n{medication_schedule}\n\n"
        f"Follow-up Steps:\n{steps_text}\n\n"
        f"HealthQueue Clinical Manager"
    )
    content_html = f"""
      <h2 style="margin-top: 0; font-size: 18px; color: #16a34a;">📋 Post-Visit Clinical Summary</h2>
      <p>Dear {patient_name}, here is the summary of your consultation with <strong>Dr. {doctor_name}</strong>.</p>
      
      <div class="card">
        <h3 style="margin-top: 0; font-size: 14px; color: #475569;">Summary & Assessment</h3>
        <p style="margin-bottom: 0; font-size: 14px; line-height: 1.5;">{patient_summary}</p>
      </div>

      {f'<div class="card"><h3 style="margin-top: 0; font-size: 14px; color: #475569;">Medication Instructions</h3><p style="margin-bottom: 0; font-size: 14px;">{medication_schedule}</p></div>' if medication_schedule else ''}

      {f'<div class="card"><h3 style="margin-top: 0; font-size: 14px; color: #475569;">Follow-Up & Care Steps</h3><ul style="padding-left: 18px; margin: 0; font-size: 14px;">{steps_html}</ul></div>' if follow_up_steps else ''}
    """
    html = _wrap_email_html(f"Post-Visit Summary from Dr. {doctor_name}", "Clinical Consultation Report", content_html)

    return NotificationContent(
        subject=f"Your Post-Visit Summary from Dr. {doctor_name}",
        whatsapp_body=whatsapp,
        email_html=html,
        email_text=text,
    )
