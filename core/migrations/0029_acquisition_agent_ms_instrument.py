import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0028_facility_manager_membership_role")]

    operations = [
        migrations.AddField(
            model_name="acquisitionagent",
            name="ms_instrument",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="acquisition_agents",
                to="core.instrument",
            ),
        ),
    ]
