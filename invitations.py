import json
import urllib.error
import urllib.request
import smtplib
from email.message import EmailMessage
from datetime import datetime


def build_invitation_subject(invitation_row):
    return f"Invitation to speak at: {invitation_row['event_title']}"


def _format_event_date(raw_date):
    try:
        dt = datetime.strptime(raw_date, "%Y-%m-%d")
        return dt.strftime("%A, %d/%m/%Y")
    except (ValueError, TypeError):
        return raw_date


def build_invitation_body(invitation_row, response_url, personal_message=None):
    name = invitation_row['advisor_name']

    if personal_message:
        personal_block = personal_message.replace("{name}", name)
        personal_block = personal_block.replace("{event_title}", invitation_row['event_title'])
        personal_block += "\n\n"
    else:
        personal_block = ""

    formatted_date = _format_event_date(invitation_row['event_date'])

    return (
        f"Dear {name},\n\n"
        f"{personal_block}"
        "You are invited to speak at the following event:\n\n"
        f"Event: {invitation_row['event_title']}\n"
        f"Topic: {invitation_row['event_topic']}\n"
        f"Date: {formatted_date}\n"
        f"Time: {invitation_row['start_time']} - {invitation_row['end_time']}\n"
        f"Location: {invitation_row['location']}\n\n"
        "Please respond using this link:\n"
        f"{response_url}\n\n"
        "Kind regards,\n"
        "BAU Seminar & Summit Management Team"
    )


def send_invitation_email(config, to_email, subject, body):
    smtp_host = config.get("SMTP_HOST")
    smtp_port = config.get("SMTP_PORT", 587)
    smtp_username = config.get("SMTP_USERNAME")
    smtp_password = config.get("SMTP_PASSWORD")
    smtp_use_tls = config.get("SMTP_USE_TLS", True)
    from_email = config.get("SMTP_FROM_EMAIL")

    if not smtp_host or not from_email:
        return False, "SMTP configuration is missing (SMTP_HOST and SMTP_FROM_EMAIL required)."
    if not to_email:
        return False, "Advisor email is missing."
    if smtp_username and not smtp_password:
        return False, "SMTP_USERNAME is set but SMTP_PASSWORD is missing."

    message = EmailMessage()
    message["From"] = from_email
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as smtp:
            if smtp_use_tls:
                smtp.starttls()
            if smtp_username:
                smtp.login(smtp_username, smtp_password)
            smtp.send_message(message)
        return True, "Invitation email sent successfully."
    except Exception as e:
        return False, f"SMTP sending failed: {e}"


def send_invitation_email_api(config, to_email, subject, body):
    api_key = config.get("EMAIL_API_KEY") or config.get("SENDINBLUE_API_KEY")
    provider = config.get("EMAIL_PROVIDER", "sendinblue").lower()
    from_email = config.get("EMAIL_FROM_EMAIL") or config.get("SMTP_FROM_EMAIL")
    from_name = config.get("EMAIL_FROM_NAME", "BAU Seminar & Summit Management Team")

    if not api_key:
        return False, "Email API key is missing. Set EMAIL_API_KEY or SENDINBLUE_API_KEY."
    if provider != "sendinblue":
        return False, f"Unsupported email API provider '{provider}'. Only 'sendinblue' is supported."
    if not from_email:
        return False, "Email from-address is missing. Set EMAIL_FROM_EMAIL or SMTP_FROM_EMAIL."
    if not to_email:
        return False, "Advisor email is missing."

    payload = {
        "sender": {"name": from_name, "email": from_email},
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    request_body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "api-key": api_key,
    }
    req = urllib.request.Request(
        "https://api.sendinblue.com/v3/smtp/email",
        data=request_body,
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.getcode()
            if 200 <= status_code < 300:
                return True, "Invitation email sent successfully via email API."
            message = response.read().decode("utf-8", errors="ignore")
            return False, f"Email API returned unexpected status {status_code}: {message}"
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="ignore")
        return False, f"Email API HTTP error {exc.code}: {error_body}"
    except urllib.error.URLError as exc:
        return False, f"Email API request failed: {exc.reason}"
