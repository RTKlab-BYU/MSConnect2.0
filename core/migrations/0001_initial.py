import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="University",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255, unique=True)),
                ("abbreviation", models.CharField(blank=True, max_length=64)),
                ("website", models.URLField(blank=True)),
                ("active", models.BooleanField(default=True)),
            ],
            options={"ordering": ("name",)},
        ),
        migrations.CreateModel(
            name="Peptide",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("sequence", models.CharField(max_length=1024)),
                ("modified_sequence", models.CharField(blank=True, max_length=2048)),
                ("charge", models.PositiveSmallIntegerField(blank=True, null=True)),
            ],
            options={"ordering": ("sequence", "modified_sequence", "charge")},
        ),
        migrations.CreateModel(
            name="ProcessingPipeline",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=128)),
                ("version", models.CharField(max_length=128)),
                ("container_image", models.CharField(blank=True, max_length=255)),
                ("parameters", models.JSONField(blank=True, default=dict)),
            ],
            options={"ordering": ("name", "version")},
        ),
        migrations.CreateModel(
            name="Protein",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("accession", models.CharField(max_length=128)),
                ("gene_symbol", models.CharField(blank=True, max_length=128)),
                ("description", models.TextField(blank=True)),
                ("organism", models.CharField(blank=True, max_length=128)),
            ],
            options={"ordering": ("accession",)},
        ),
        migrations.CreateModel(
            name="Facility",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=80)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("active", models.BooleanField(default=True)),
                (
                    "university",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="facilities",
                        to="core.university",
                    ),
                ),
            ],
            options={"ordering": ("university__name", "name")},
        ),
        migrations.CreateModel(
            name="Lab",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=80)),
                ("billing_code", models.CharField(blank=True, max_length=128)),
                ("active", models.BooleanField(default=True)),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="labs",
                        to="core.facility",
                    ),
                ),
                (
                    "pi",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="pi_labs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("facility__name", "name")},
        ),
        migrations.CreateModel(
            name="UserProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "global_role",
                    models.CharField(
                        choices=[
                            ("admin", "Admin"),
                            ("pi", "PI"),
                            ("researcher", "Researcher"),
                            ("collaborator", "Collaborator"),
                        ],
                        default="researcher",
                        max_length=32,
                    ),
                ),
                ("phone", models.CharField(blank=True, max_length=64)),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="LabMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "role",
                    models.CharField(
                        choices=[
                            ("admin", "Admin"),
                            ("pi", "PI"),
                            ("researcher", "Researcher"),
                            ("collaborator", "Collaborator"),
                        ],
                        default="researcher",
                        max_length=32,
                    ),
                ),
                ("active", models.BooleanField(default=True)),
                (
                    "lab",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="core.lab",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lab_memberships",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("lab__name", "user__username")},
        ),
        migrations.CreateModel(
            name="Instrument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("nickname", models.CharField(max_length=128)),
                (
                    "instrument_type",
                    models.CharField(
                        choices=[("lc", "LC"), ("ms", "MS"), ("lcms", "LC-MS"), ("other", "Other")],
                        max_length=20,
                    ),
                ),
                ("manufacturer", models.CharField(blank=True, max_length=128)),
                ("model", models.CharField(blank=True, max_length=128)),
                ("serial_number", models.CharField(blank=True, max_length=128)),
                ("active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instruments",
                        to="core.facility",
                    ),
                ),
            ],
            options={"ordering": ("facility__name", "nickname")},
        ),
        migrations.CreateModel(
            name="InstrumentConfiguration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("method_name", models.CharField(blank=True, max_length=255)),
                ("column_description", models.CharField(blank=True, max_length=255)),
                ("gradient_description", models.TextField(blank=True)),
                ("ion_source", models.CharField(blank=True, max_length=128)),
                ("active", models.BooleanField(default=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "facility",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="instrument_configurations",
                        to="core.facility",
                    ),
                ),
                (
                    "lc_instrument",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="lc_configurations",
                        to="core.instrument",
                    ),
                ),
                (
                    "ms_instrument",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="ms_configurations",
                        to="core.instrument",
                    ),
                ),
            ],
            options={"ordering": ("facility__name", "name")},
        ),
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("title", models.CharField(max_length=255)),
                ("code", models.CharField(max_length=80)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "Active"),
                            ("paused", "Paused"),
                            ("complete", "Complete"),
                            ("archived", "Archived"),
                        ],
                        default="active",
                        max_length=32,
                    ),
                ),
                ("description", models.TextField(blank=True)),
                (
                    "lab",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="projects",
                        to="core.lab",
                    ),
                ),
                (
                    "pi",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="owned_projects",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("lab__name", "code")},
        ),
        migrations.CreateModel(
            name="Experiment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("hypothesis", models.TextField(blank=True)),
                ("started_on", models.DateField(blank=True, null=True)),
                ("ended_on", models.DateField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_experiments",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="experiments",
                        to="core.project",
                    ),
                ),
            ],
            options={"ordering": ("project__code", "name")},
        ),
        migrations.CreateModel(
            name="Sample",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=255)),
                ("external_id", models.CharField(blank=True, max_length=128)),
                ("species", models.CharField(blank=True, max_length=128)),
                ("matrix", models.CharField(blank=True, max_length=128)),
                ("digestion_protocol", models.CharField(blank=True, max_length=255)),
                ("enrichment_protocol", models.CharField(blank=True, max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "experiment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="samples",
                        to="core.experiment",
                    ),
                ),
                (
                    "submitted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="submitted_samples",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ("experiment__name", "name")},
        ),
        migrations.CreateModel(
            name="Run",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("run_name", models.CharField(max_length=255)),
                ("acquisition_started_at", models.DateTimeField(blank=True, null=True)),
                ("acquisition_ended_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("planned", "Planned"),
                            ("acquired", "Acquired"),
                            ("imported", "Imported"),
                            ("processed", "Processed"),
                            ("failed", "Failed"),
                        ],
                        default="planned",
                        max_length=32,
                    ),
                ),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "acquired_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="acquired_runs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "configuration",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="runs",
                        to="core.instrumentconfiguration",
                    ),
                ),
                (
                    "sample",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="runs",
                        to="core.sample",
                    ),
                ),
            ],
            options={"ordering": ("-acquisition_started_at", "run_name")},
        ),
        migrations.CreateModel(
            name="RawFile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("source_path", models.TextField(db_index=True)),
                ("storage_path", models.TextField(unique=True)),
                ("filename", models.CharField(max_length=255)),
                ("checksum_sha256", models.CharField(max_length=64, unique=True)),
                ("size_bytes", models.PositiveBigIntegerField()),
                ("acquired_at", models.DateTimeField(blank=True, null=True)),
                ("imported_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("discovered", "Discovered"),
                            ("validated", "Validated"),
                            ("imported", "Imported"),
                            ("processed", "Processed"),
                            ("failed", "Failed"),
                        ],
                        default="discovered",
                        max_length=32,
                    ),
                ),
                ("failure_reason", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "run",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="raw_files",
                        to="core.run",
                    ),
                ),
            ],
            options={"ordering": ("-imported_at", "filename")},
        ),
        migrations.CreateModel(
            name="ProcessingJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("queued", "Queued"),
                            ("running", "Running"),
                            ("succeeded", "Succeeded"),
                            ("failed", "Failed"),
                        ],
                        default="queued",
                        max_length=32,
                    ),
                ),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("log_path", models.TextField(blank=True)),
                ("error_message", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "pipeline",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="jobs",
                        to="core.processingpipeline",
                    ),
                ),
                (
                    "raw_file",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="processing_jobs",
                        to="core.rawfile",
                    ),
                ),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="processing_jobs",
                        to="core.run",
                    ),
                ),
            ],
            options={"ordering": ("-created_at",)},
        ),
        migrations.CreateModel(
            name="ProteinIdentification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("score", models.FloatField(blank=True, null=True)),
                ("q_value", models.FloatField(blank=True, null=True)),
                ("coverage_percent", models.FloatField(blank=True, null=True)),
                ("peptide_count", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="protein_identifications",
                        to="core.processingjob",
                    ),
                ),
                (
                    "protein",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="identifications",
                        to="core.protein",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PeptideIdentification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("score", models.FloatField(blank=True, null=True)),
                ("q_value", models.FloatField(blank=True, null=True)),
                ("retention_time_seconds", models.FloatField(blank=True, null=True)),
                ("mz", models.FloatField(blank=True, null=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="peptide_identifications",
                        to="core.processingjob",
                    ),
                ),
                (
                    "peptide",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="identifications",
                        to="core.peptide",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ProteinQuant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(default="abundance", max_length=128)),
                ("value", models.FloatField()),
                ("unit", models.CharField(blank=True, max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="protein_quants",
                        to="core.processingjob",
                    ),
                ),
                (
                    "protein",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="quants",
                        to="core.protein",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="PeptideQuant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("label", models.CharField(default="abundance", max_length=128)),
                ("value", models.FloatField()),
                ("unit", models.CharField(blank=True, max_length=64)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "job",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="peptide_quants",
                        to="core.processingjob",
                    ),
                ),
                (
                    "peptide",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="quants",
                        to="core.peptide",
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="facility",
            constraint=models.UniqueConstraint(fields=("university", "slug"), name="uniq_facility_slug_per_university"),
        ),
        migrations.AddConstraint(
            model_name="lab",
            constraint=models.UniqueConstraint(fields=("facility", "slug"), name="uniq_lab_slug_per_facility"),
        ),
        migrations.AddConstraint(
            model_name="labmembership",
            constraint=models.UniqueConstraint(fields=("user", "lab"), name="uniq_user_lab_membership"),
        ),
        migrations.AddConstraint(
            model_name="instrument",
            constraint=models.UniqueConstraint(
                fields=("facility", "nickname"),
                name="uniq_instrument_nickname_per_facility",
            ),
        ),
        migrations.AddConstraint(
            model_name="instrumentconfiguration",
            constraint=models.UniqueConstraint(
                fields=("facility", "name"),
                name="uniq_configuration_name_per_facility",
            ),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.UniqueConstraint(fields=("lab", "code"), name="uniq_project_code_per_lab"),
        ),
        migrations.AddConstraint(
            model_name="experiment",
            constraint=models.UniqueConstraint(fields=("project", "name"), name="uniq_experiment_name_per_project"),
        ),
        migrations.AddConstraint(
            model_name="sample",
            constraint=models.UniqueConstraint(fields=("experiment", "name"), name="uniq_sample_name_per_experiment"),
        ),
        migrations.AddConstraint(
            model_name="run",
            constraint=models.UniqueConstraint(fields=("sample", "run_name"), name="uniq_run_name_per_sample"),
        ),
        migrations.AddConstraint(
            model_name="processingpipeline",
            constraint=models.UniqueConstraint(fields=("name", "version"), name="uniq_pipeline_name_version"),
        ),
        migrations.AddConstraint(
            model_name="protein",
            constraint=models.UniqueConstraint(
                fields=("accession", "organism"),
                name="uniq_protein_accession_organism",
            ),
        ),
        migrations.AddConstraint(
            model_name="peptide",
            constraint=models.UniqueConstraint(
                fields=("sequence", "modified_sequence", "charge"),
                name="uniq_peptide_variant",
            ),
        ),
        migrations.AddConstraint(
            model_name="proteinidentification",
            constraint=models.UniqueConstraint(fields=("job", "protein"), name="uniq_protein_identification_per_job"),
        ),
        migrations.AddConstraint(
            model_name="peptideidentification",
            constraint=models.UniqueConstraint(fields=("job", "peptide"), name="uniq_peptide_identification_per_job"),
        ),
        migrations.AddConstraint(
            model_name="proteinquant",
            constraint=models.UniqueConstraint(
                fields=("job", "protein", "label"),
                name="uniq_protein_quant_per_job_label",
            ),
        ),
        migrations.AddConstraint(
            model_name="peptidequant",
            constraint=models.UniqueConstraint(
                fields=("job", "peptide", "label"),
                name="uniq_peptide_quant_per_job_label",
            ),
        ),
    ]
