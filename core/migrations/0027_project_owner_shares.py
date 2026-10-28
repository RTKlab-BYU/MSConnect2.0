import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_project_owners(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    Project.objects.filter(owner__isnull=True).update(owner=models.F("pi"))


def preserve_existing_lab_access(apps, schema_editor):
    Project = apps.get_model("core", "Project")
    LabMembership = apps.get_model("core", "LabMembership")
    ProjectMembership = apps.get_model("core", "ProjectMembership")
    using = schema_editor.connection.alias
    project_rows = Project.objects.using(using).values_list("id", "lab_id", "owner_id")
    existing = set(ProjectMembership.objects.using(using).values_list("project_id", "user_id"))
    memberships = []
    for project_id, lab_id, owner_id in project_rows.iterator():
        users = LabMembership.objects.using(using).filter(lab_id=lab_id, active=True).values_list("user_id", flat=True)
        memberships.extend(
            ProjectMembership(project_id=project_id, user_id=user_id, active=True)
            for user_id in users
            if user_id != owner_id and (project_id, user_id) not in existing
        )
    ProjectMembership.objects.using(using).bulk_create(memberships, ignore_conflicts=True, batch_size=1000)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0026_analysis_batches_reference_assets"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="projects_created",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(backfill_project_owners, migrations.RunPython.noop),
        migrations.CreateModel(
            name="ProjectMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("active", models.BooleanField(default=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="core.project")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ("user__username",)},
        ),
        migrations.AddConstraint(
            model_name="projectmembership",
            constraint=models.UniqueConstraint(fields=("project", "user"), name="uniq_project_user_membership"),
        ),
        migrations.RunPython(preserve_existing_lab_access, migrations.RunPython.noop),
    ]
