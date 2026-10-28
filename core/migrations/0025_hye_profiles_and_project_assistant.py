import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

DEFAULT_HYE_TARGETS = {
    "Homo sapiens": {"a": 0.65, "b": 0.65},
    "Saccharomyces cerevisiae": {"a": 0.30, "b": 0.15},
    "Escherichia coli": {"a": 0.05, "b": 0.20},
}


def create_default_hye_profile(apps, schema_editor):
    profile = apps.get_model("core", "HyeTargetProfile")
    profile.objects.get_or_create(
        name="HYE Standard",
        version="1.0",
        defaults={"targets": DEFAULT_HYE_TARGETS, "active": True},
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0024_acquisition_agent_routes"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="HyeTargetProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=128)),
                ("version", models.CharField(max_length=32)),
                ("targets", models.JSONField(default=dict)),
                ("active", models.BooleanField(db_index=True, default=True)),
            ],
            options={"ordering": ("name", "-created_at")},
        ),
        migrations.AddConstraint(
            model_name="hyetargetprofile",
            constraint=models.UniqueConstraint(fields=("name", "version"), name="uniq_hye_target_profile_version"),
        ),
        migrations.CreateModel(
            name="ProjectAssistantThread",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(blank=True, max_length=255)),
                ("provider", models.CharField(max_length=32)),
                ("model", models.CharField(max_length=128)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="assistant_threads", to="core.project")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_assistant_threads", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("-updated_at", "-id")},
        ),
        migrations.CreateModel(
            name="ProjectAssistantMessage",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("role", models.CharField(choices=[("user", "User"), ("assistant", "Assistant")], max_length=16)),
                ("content", models.TextField()),
                ("provider", models.CharField(blank=True, max_length=32)),
                ("model", models.CharField(blank=True, max_length=128)),
                ("thread", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="messages", to="core.projectassistantthread")),
            ],
            options={"ordering": ("created_at", "id")},
        ),
        migrations.RunPython(create_default_hye_profile, migrations.RunPython.noop),
    ]
