"""Email OTP delivery. Never persist raw login codes or expose through API."""
import os
import smtplib
import ssl
from email.message import EmailMessage


class MailError(RuntimeError):
    pass


def send_code(destination: str, code: str):
    host = os.getenv('SMTP_HOST', '')
    sender = os.getenv('SMTP_FROM', '')
    if not host or not sender:
        if os.getenv('APP_ENV') != 'production' and os.getenv('EMAIL_DEV_CONSOLE') == 'true':
            print(f'KISA DEVELOPMENT EMAIL OTP for {destination}: {code}')
            return
        raise MailError('Email delivery is not configured')
    msg = EmailMessage()
    msg['Subject'] = 'Your KISA sign-in code'
    msg['From'] = sender
    msg['To'] = destination
    msg.set_content(f'Your KISA sign-in code: {code}\nExpires in 10 minutes. Do not share it.')
    port = int(os.getenv('SMTP_PORT', '465'))
    user = os.getenv('SMTP_USERNAME', '')
    password = os.getenv('SMTP_PASSWORD', '')
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=12) as smtp:
                if user: smtp.login(user, password)
                smtp.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=12) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                if user: smtp.login(user, password)
                smtp.send_message(msg)
    except (OSError, smtplib.SMTPException) as exc:
        raise MailError('Email could not be delivered') from exc
