import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0025_hye_profiles_and_project_assistant"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AnalysisBatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("executor", models.CharField(choices=[("local", "Local processors"), ("slurm", "BYU Slurm")], default="slurm", max_length=16)),
                ("status", models.CharField(choices=[("queued", "Queued"), ("running", "Running"), ("complete", "Complete"), ("failed", "Failed")], default="queued", max_length=16)),
                ("parameters_snapshot", models.JSONField(blank=True, default=dict)),
                ("reference_snapshot", models.JSONField(blank=True, default=dict)),
                ("raw_file_ids", models.JSONField(blank=True, default=list)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="analysis_batches", to=settings.AUTH_USER_MODEL)),
                ("experiment", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analysis_batches", to="core.experiment")),
                ("pipeline", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="analysis_batches", to="core.processingpipeline")),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="analysis_batches", to="core.project")),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.CreateModel(
            name="ReferenceAsset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("asset_type", models.CharField(choices=[("fasta", "FASTA"), ("spectral_library", "Spectral library")], max_length=32)),
                ("filename", models.CharField(max_length=255)),
                ("storage_path", models.TextField(unique=True)),
                ("checksum_sha256", models.CharField(db_index=True, max_length=64)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("scope", models.CharField(choices=[("experiment", "Experiment"), ("project", "Project")], default="experiment", max_length=16)),
                ("active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("experiment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reference_assets", to="core.experiment")),
                ("project", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="reference_assets", to="core.project")),
                ("uploaded_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="reference_assets", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("asset_type", "filename", "-created_at")},
        ),
        migrations.AddField(
            model_name="processingjob",
            name="analysis_batch",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="jobs", to="core.analysisbatch"),
        ),
    ]
