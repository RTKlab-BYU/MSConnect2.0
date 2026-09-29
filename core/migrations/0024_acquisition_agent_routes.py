import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0023_peptideidentification_q_value_context_and_more")]

    operations = [
        migrations.CreateModel(
            name="AcquisitionAgent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=128, unique=True)),
                ("token_label", models.CharField(max_length=128, unique=True)),
                ("source_root", models.TextField(blank=True)),
                ("proposed_source_root", models.TextField(blank=True)),
                ("source_root_status", models.CharField(choices=[("approved", "Approved"), ("pending", "Pending approval"), ("rejected", "Rejected")], default="pending", max_length=32)),
                ("config_version", models.PositiveIntegerField(default=1)),
                ("active", models.BooleanField(default=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_validation", models.JSONField(blank=True, default=dict)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="AcquisitionRoute",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("source_prefix", models.TextField(blank=True, help_text="Relative folder below the agent's approved source root.")),
                ("spool_folder", models.CharField(max_length=255)),
                ("mode", models.CharField(choices=[("worklist", "Worklist"), ("adhoc", "Ad hoc experiment")], default="worklist", max_length=16)),
                ("status", models.CharField(choices=[("active", "Active"), ("paused", "Paused")], default="active", max_length=16)),
                ("quiet_period_seconds", models.PositiveIntegerField(default=300)),
                ("delete_spool_after_upload", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("agent", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="routes", to="core.acquisitionagent")),
                ("experiment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="acquisition_routes", to="core.experiment")),
                ("processing_pipeline", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="acquisition_routes", to="core.processingpipeline")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="acquisition_routes", to="core.project")),
                ("worklist", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="routes", to="core.acquisitionworklist")),
            ],
            options={"ordering": ("agent__name", "name")},
        ),
        migrations.AddConstraint(
            model_name="acquisitionroute",
            constraint=models.UniqueConstraint(fields=("agent", "name"), name="uniq_acquisition_route_name"),
        ),
    ]
