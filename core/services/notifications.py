from django.conf import settings
from django.core.mail import send_mail

from core.models import DeploymentSetting


def notification_recipients() -> list[str]:
    configured = getattr(settings, "MSCONNECT_NOTIFICATION_EMAILS", [])
    try:
        metadata = (DeploymentSetting.objects.filter(scope="site").values_list("metadata", flat=True).first() or {})
        configured = (metadata.get("notifications") or {}).get("recipients") or configured
    except Exception:
        pass
    return [email.strip() for email in configured if str(email).strip()]


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
