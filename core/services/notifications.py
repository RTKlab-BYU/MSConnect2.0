from django.conf import settings
from django.core.mail import send_mail


def notification_recipients() -> list[str]:
    return [email for email in getattr(settings, "MSCONNECT_NOTIFICATION_EMAILS", []) if email]


def send_notification(*, subject: str, message: str) -> int:
    recipients = notification_recipients()
    if not recipients:
        return 0
    return send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        recipients,
        fail_silently=getattr(settings, "MSCONNECT_EMAIL_FAIL_SILENT", True),
    )
