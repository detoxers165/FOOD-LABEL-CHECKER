import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from config import Settings
import logging

logger = logging.getLogger(__name__)

def send_otp_email(email: str, otp_code: str, settings: Settings) -> None:
    if not settings.smtp_enabled:
        print(f"DEV MODE OTP for {email}: {otp_code}")
        return

    if not (settings.smtp_host and settings.smtp_port and settings.smtp_username and settings.smtp_password and settings.smtp_from_email):
        logger.error(f"SMTP configuration invalid: Missing required SMTP parameters for sending email to {email}.")
        raise ValueError("SMTP configuration invalid")

    try:
        msg = MIMEMultipart()
        msg['From'] = settings.smtp_from_email
        msg['To'] = email
        msg['Subject'] = "Your Login OTP"

        body = f"Your OTP for login is: {otp_code}\nThis OTP is valid for {settings.otp_expiry_seconds // 60} minutes."
        msg.attach(MIMEText(body, 'plain'))

        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(msg)
            
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: Invalid sender credentials or App Password required.")
        raise
    except smtplib.SMTPConnectError as e:
        logger.error(f"SMTP connection failed: Unable to connect to host {settings.smtp_host}:{settings.smtp_port}: {e}")
        raise
    except smtplib.SMTPServerDisconnected as e:
        logger.error(f"SMTP server disconnected unexpectedly while sending to {email}: {e}")
        raise
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error occurred while sending OTP email to {email}: {e}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error while sending OTP email to {email}: {e}")
        raise
