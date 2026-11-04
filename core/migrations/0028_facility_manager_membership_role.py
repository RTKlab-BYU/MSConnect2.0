from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0027_project_owner_shares")]

    operations = [
        migrations.AlterField(
            model_name="labmembership",
            name="role",
            field=models.CharField(
                choices=[
                    ("admin", "Admin"),
                    ("pi", "PI"),
                    ("facility_manager", "Facility manager"),
                    ("researcher", "Researcher"),
                    ("collaborator", "Collaborator"),
                ],
                default="researcher",
                max_length=32,
            ),
        ),
    ]
