from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0016_analysispreset_alter_pipelineevent_event_type_and_more")]

    operations = [
        migrations.AddField(
            model_name="processingjob",
            name="lease_token",
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name="processingjob",
            name="lease_expires_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="processingjob",
            name="attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="processingjob",
            name="max_attempts",
            field=models.PositiveIntegerField(default=3),
        ),
    ]
