import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0019_project_metadata")]

    operations = [
        migrations.CreateModel(
            name="ProcessingNodeEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_type", models.CharField(max_length=64)),
                ("command", models.CharField(blank=True, max_length=64)),
                ("status", models.CharField(default="requested", max_length=32)),
                ("requested_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("acknowledged_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("node", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="events", to="core.processingnode")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-created_at",)},
        )
    ]
