from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import ProcessingNode
from core.services.notifications import send_notification


class Command(BaseCommand):
    help = "Email administrators when processing nodes have stale heartbeats."

    def add_arguments(self, parser):
        parser.add_argument("--stale-seconds", type=int, default=180)
        parser.add_argument("--cooldown-seconds", type=int, default=3600)

    def handle(self, *args, **options):
        now = timezone.now()
        stale_after = timedelta(seconds=max(30, options["stale_seconds"]))
        cooldown = timedelta(seconds=max(60, options["cooldown_seconds"]))
        stale = []
        for node in ProcessingNode.objects.all():
            if node.last_heartbeat_at and now - node.last_heartbeat_at <= stale_after:
                continue
            metadata = node.metadata or {}
            notified_at = metadata.get("last_outage_notification_at")
            try:
                notified = timezone.datetime.fromisoformat(notified_at) if notified_at else None
            except (TypeError, ValueError):
                notified = None
            if notified and notified.tzinfo is None:
                notified = timezone.make_aware(notified)
            if notified and now - notified < cooldown:
                continue
            stale.append(node)

        if not stale:
            self.stdout.write("No stale nodes requiring notification.")
            return
        lines = ["The following MSConnect nodes have stale heartbeats:"]
        for node in stale:
            age = "never" if not node.last_heartbeat_at else str(int((now - node.last_heartbeat_at).total_seconds())) + "s"
            lines.append(f"- {node.name} ({node.node_type}): status={node.status}, last heartbeat={age} ago")
        sent = send_notification(subject="MSConnect node outage alert", message="\n".join(lines))
        if sent:
            for node in stale:
                node.metadata = {**(node.metadata or {}), "last_outage_notification_at": now.isoformat()}
                node.save(update_fields=["metadata", "updated_at"])
        self.stdout.write(f"stale nodes={len(stale)} notifications_sent={sent}")
