from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0030_acquisitionagent_agent_token_hash_and_more")]

    operations = [
        migrations.CreateModel(
            name="AssistantProviderCredential",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("provider", models.CharField(max_length=32, unique=True)),
                ("encrypted_api_key", models.TextField(blank=True)),
            ],
            options={"ordering": ("provider",)},
        ),
    ]
