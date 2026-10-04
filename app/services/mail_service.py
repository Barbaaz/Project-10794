"""
E-mail to users (password reset now; wishlist alerts later). Sent by SMTP with STARTTLS once
SMTP_HOST is set (app/config.py; any provider: Brevo, Mailgun, a mailbox's own server). Until
then each message is only written to the log, so the flows work and can be tried without one.
"""
import logging
import smtplib
from email.message import EmailMessage

from app import config

log = logging.getLogger(__name__)


def send(to, subject, text):
    """Send a plain-text e-mail; True when it went out by SMTP, False when only logged."""
    if not config.SMTP_HOST:
        log.info("E-mail not sent (no SMTP_HOST) to %s: %s\n%s", to, subject, text)
        return False
    message = EmailMessage()
    message["From"] = config.MAIL_FROM or config.SMTP_USER
    message["To"] = to
    message["Subject"] = subject
    message.set_content(text)
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as smtp:
        smtp.starttls()
        if config.SMTP_USER:
            smtp.login(config.SMTP_USER, config.SMTP_PASSWORD)
        smtp.send_message(message)
    return True
