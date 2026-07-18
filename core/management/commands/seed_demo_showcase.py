import hashlib
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    AcquisitionWorklist,
    Experiment,
    Facility,
    Instrument,
    InstrumentConfiguration,
    InstrumentType,
    Lab,
    LabMembership,
    Peptide,
    PeptideIdentification,
    PeptideQuant,
    ProcessingJob,
    ProcessingNode,
    ProcessingNodeStatus,
    ProcessingPipeline,
    ProcessingStatus,
    Project,
    Protein,
    ProteinIdentification,
    ProteinQuant,
    RawFile,
    RawFileStatus,
    Run,
    RunFileRole,
    RunStatus,
    Sample,
    University,
    UserProfile,
    UserRole,
    WorklistEntry,
    WorklistStatus,
)


class Command(BaseCommand):
    help = "Seed a complete MSConnect cohort showcase with embedded HYE A/B QC and DIA-NN jobs."

    project_code = "COHORT-DIA-100"
    legacy_project_codes = ("HYE-DIA-DEMO",)

    def add_arguments(self, parser):
        parser.add_argument("--write-job-results", nargs=2, metavar=("JOB_ID", "RESULTS_DIR"))

    def handle(self, *args, **options):
        if options.get("write_job_results"):
            job_id, results_dir = options["write_job_results"]
            self._write_job_results(job_id=job_id, results_dir=results_dir)
            return

        with transaction.atomic():
            context = self._seed()
        self.stdout.write(self.style.SUCCESS("Demo showcase seeded."))
        self.stdout.write(f"Project: {context['project'].code} - {context['project'].title}")
        self.stdout.write(f"Worklist: {context['worklist'].name}")
        self.stdout.write("Open: http://127.0.0.1:8000/ui/showcase")

    def _write_job_results(self, *, job_id, results_dir):
        results_path = Path(results_dir)
        results_path.mkdir(parents=True, exist_ok=True)
        protein_path = results_path / "proteins.csv"
        peptide_path = results_path / "peptides.csv"

        job_number = int(job_id)
        protein_rows = [
            ("accession,label,value,unit,score,q_value,coverage_percent,peptide_count,organism"),
            f"P00533,abundance,{1000000 + job_number * 1000},area,92,0.001,48,12,Homo sapiens",
            f"P00924,abundance,{420000 + job_number * 700},area,89,0.002,36,9,Saccharomyces cerevisiae",
            f"P0A6F5,abundance,{180000 + job_number * 400},area,87,0.003,31,7,Escherichia coli",
        ]
        peptide_rows = [
            ("sequence,modified_sequence,charge,label,value,unit,score,q_value,retention_time_seconds,mz"),
            f"LVNELTEFAK,LVNELTEFAK,2,abundance,{250000 + job_number * 500},area,94,0.001,1450,593.312",
        ]

        protein_path.write_text("\n".join(protein_rows) + "\n", encoding="utf-8")
        peptide_path.write_text("\n".join(peptide_rows) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"Wrote demo job results for job {job_id} to {results_path}"))

    def _seed(self):
        User = get_user_model()
        admin_user, _ = User.objects.get_or_create(
            username="parkerreyes",
            defaults={"is_staff": True, "is_superuser": True, "email": "parkerreyes@example.test"},
        )
        if not admin_user.is_staff or not admin_user.is_superuser:
            admin_user.is_staff = True
            admin_user.is_superuser = True
            admin_user.save(update_fields=["is_staff", "is_superuser"])
        UserProfile.objects.get_or_create(user=admin_user, defaults={"global_role": UserRole.ADMIN})

        pi_user, _ = User.objects.get_or_create(username="demo-pi", defaults={"email": "demo-pi@example.test"})
        pi_user.set_password("DemoPass-2026!")
        pi_user.save(update_fields=["password"])
        UserProfile.objects.update_or_create(user=pi_user, defaults={"global_role": UserRole.PI})

        researcher, _ = User.objects.get_or_create(
            username="demo-researcher",
            defaults={"email": "demo-researcher@example.test"},
        )
        researcher.set_password("DemoPass-2026!")
        researcher.save(update_fields=["password"])
        UserProfile.objects.update_or_create(user=researcher, defaults={"global_role": UserRole.RESEARCHER})

        university, _ = University.objects.get_or_create(
            name="Demo University",
            defaults={"abbreviation": "DU", "website": "https://example.test"},
        )
        facility, _ = Facility.objects.get_or_create(
            university=university,
            slug="proteomics-core",
            defaults={"name": "Proteomics Core", "contact_email": "proteomics@example.test"},
        )
        lab, _ = Lab.objects.get_or_create(
            facility=facility,
            slug="systems-biology",
            defaults={"name": "Systems Biology Lab", "pi": pi_user, "billing_code": "DEMO-001"},
        )
        if lab.pi_id != pi_user.id:
            lab.pi = pi_user
            lab.save(update_fields=["pi"])

        for user, role in ((admin_user, UserRole.ADMIN), (pi_user, UserRole.PI), (researcher, UserRole.RESEARCHER)):
            LabMembership.objects.update_or_create(user=user, lab=lab, defaults={"role": role, "active": True})

        lc, _ = Instrument.objects.get_or_create(
            facility=facility,
            nickname="Vanquish Neo Demo",
            defaults={
                "instrument_type": InstrumentType.LC,
                "manufacturer": "Thermo Fisher",
                "model": "Vanquish Neo",
            },
        )
        ms, _ = Instrument.objects.get_or_create(
            facility=facility,
            nickname="Orbitrap Astral Demo",
            defaults={
                "instrument_type": InstrumentType.MS,
                "manufacturer": "Thermo Fisher",
                "model": "Orbitrap Astral",
            },
        )
        configuration, _ = InstrumentConfiguration.objects.get_or_create(
            facility=facility,
            name="DIA 60 SPD - 45 min gradient",
            defaults={
                "lc_instrument": lc,
                "ms_instrument": ms,
                "method_name": "Demo_DIA_45min_60SPD",
                "column_description": "Aurora Ultimate 25 cm x 75 um",
                "gradient_description": "45 minute direct-DIA gradient with indexed retention-time standards.",
                "ion_source": "nanoESI",
                "metadata": {"dia_windows": 60, "gradient_minutes": 45},
            },
        )

        self._remove_legacy_demo_projects(lab=lab)

        project, _ = Project.objects.update_or_create(
            lab=lab,
            code=self.project_code,
            defaults={
                "title": "Healthy vs Diseased Plasma Proteome Cohort",
                "pi": pi_user,
                "description": (
                    "End-to-end DIA-MS study with 100 biological samples, balanced healthy/diseased arms, "
                    "interspersed HYE A/B QC controls, raw-file custody, and DIA-NN processing."
                ),
            },
        )
        experiment, _ = Experiment.objects.update_or_create(
            project=project,
            name="Plasma cohort DIA discovery batch 1",
            defaults={
                "hypothesis": (
                    "Healthy and diseased plasma samples should separate by inflammatory and metabolic protein "
                    "signatures while interspersed HYE controls provide longitudinal system-suitability tracking."
                ),
                "created_by": researcher,
                "metadata": {
                    "study_type": "case-control plasma proteomics",
                    "biological_sample_count": 100,
                    "factors": {
                        "condition": ["healthy", "diseased"],
                        "sex": ["female", "male"],
                        "collection_site": ["BYU-Core-A", "BYU-Core-B"],
                        "qc_material": ["HYE-A", "HYE-B"],
                    },
                    "primary_endpoint": "Differential protein abundance between healthy and diseased cohorts.",
                    "metadata_capture": [
                        "subject_id",
                        "condition",
                        "age",
                        "sex",
                        "bmi",
                        "collection_site",
                        "collection_date",
                        "fasting_state",
                        "sample_type",
                        "digestion_protocol",
                        "randomization_block",
                        "worklist_position",
                        "expected_filename",
                    ],
                    "hye_pseudo_project": {
                        "description": (
                            "HYE is not seeded as its own Project. HYE A/B runs are tagged QC injections; "
                            "the QC workspace groups them as a pseudo-project for system-suitability and "
                            "longitudinal trend analysis once HYE material is identified."
                        ),
                        "pair_interval_biological_samples": 10,
                    },
                    "design_summary": (
                        "Balanced healthy/diseased acquisition with HYE A/B pairs before the batch, every 10 "
                        "biological samples, and at batch close."
                    ),
                },
            },
        )

        samples = self._seed_samples(experiment, researcher)
        worklist, _ = AcquisitionWorklist.objects.update_or_create(
            experiment=experiment,
            name="Plate 1 DIA acquisition order",
            defaults={
                "configuration": configuration,
                "status": WorklistStatus.READY,
                "generated_by": admin_user,
                "notes": (
                    "Generated demo worklist: 100 randomized healthy/diseased plasma samples with HYE A/B "
                    "controls interspersed every 10 biological injections."
                ),
                "metadata": {
                    "ordering_policy": (
                        "Start with blank, library, and HYE A/B. Alternate healthy/diseased samples within "
                        "randomization blocks and insert an HYE A/B pair every 10 biological injections."
                    ),
                    "biological_sample_count": 100,
                    "condition_balance": {"healthy": 50, "diseased": 50},
                    "hye_interval_biological_samples": 10,
                    "hye_pseudo_project": "Derived in QC views from tagged HYE-A/HYE-B worklist entries.",
                    "export_format": "Instrument vendor worklist CSV can be generated from these entries.",
                },
            },
        )

        entries = self._seed_worklist_entries(worklist, samples, configuration, admin_user)
        pipeline = self._seed_diann_pipeline()
        node = self._seed_processing_node(pipeline)
        raw_files = self._seed_raw_files(entries)
        self._seed_jobs_and_quant(raw_files, pipeline, node)
        return {"project": project, "worklist": worklist}

    def _remove_legacy_demo_projects(self, *, lab):
        RawFile.objects.filter(run__isnull=True, filename__startswith="HYE_DIA_DEMO_").delete()
        projects = Project.objects.filter(lab=lab, code__in=self.legacy_project_codes)
        for project in projects:
            experiments = Experiment.objects.filter(project=project)
            runs = Run.objects.filter(sample__experiment__in=experiments)
            jobs = ProcessingJob.objects.filter(run__in=runs)
            ProteinQuant.objects.filter(job__in=jobs).delete()
            PeptideQuant.objects.filter(job__in=jobs).delete()
            ProteinIdentification.objects.filter(job__in=jobs).delete()
            PeptideIdentification.objects.filter(job__in=jobs).delete()
            jobs.delete()
            RawFile.objects.filter(run__in=runs).delete()
            AcquisitionWorklist.objects.filter(experiment__in=experiments).delete()
            runs.delete()
            Sample.objects.filter(experiment__in=experiments).delete()
            experiments.delete()
            project.delete()

    def _seed_samples(self, experiment, researcher):
        samples = {}
        control_defs = [
            ("BLANK", RunFileRole.BLANK, "Solvent blank", {}),
            ("LIB-HYE", RunFileRole.LIBRARY, "HYE spectral library pool", {"library": True}),
            (
                "HYE-A",
                RunFileRole.QC,
                "Human/Yeast/E. coli QC A",
                {
                    "qc_material": "HYE",
                    "qc_pair": "A",
                    "mix": "65/30/5",
                    "pseudo_project_key": "HYE",
                    "pseudo_project_role": "system_suitability",
                },
            ),
            (
                "HYE-B",
                RunFileRole.QC,
                "Human/Yeast/E. coli QC B",
                {
                    "qc_material": "HYE",
                    "qc_pair": "B",
                    "mix": "65/15/20",
                    "pseudo_project_key": "HYE",
                    "pseudo_project_role": "system_suitability",
                },
            ),
            ("WASH", RunFileRole.WASH, "Column wash", {}),
        ]

        for name, role, description, metadata in control_defs:
            sample, _ = Sample.objects.update_or_create(
                experiment=experiment,
                name=name,
                defaults={
                    "external_id": name,
                    "species": (
                        "Homo sapiens; Saccharomyces cerevisiae; Escherichia coli"
                        if role == RunFileRole.QC
                        else ""
                    ),
                    "matrix": description,
                    "digestion_protocol": "SP3 tryptic digest" if role in {RunFileRole.SAMPLE, RunFileRole.QC} else "",
                    "submitted_by": researcher,
                    "metadata": {"role": role, **metadata},
                },
            )
            samples[name] = sample

        for index in range(1, 101):
            condition = "healthy" if index <= 50 else "diseased"
            condition_index = index if condition == "healthy" else index - 50
            subject_id = f"{condition[:1].upper()}-{condition_index:03d}"
            age = 28 + ((index * 7) % 41)
            sex = "female" if index % 2 else "male"
            bmi = round(20.5 + ((index * 13) % 125) / 10, 1)
            collection_site = "BYU-Core-A" if index % 3 else "BYU-Core-B"
            clinical_score = 0 if condition == "healthy" else 2 + (index % 4)
            name = f"{condition.upper()}-{condition_index:03d}"
            sample, _ = Sample.objects.update_or_create(
                experiment=experiment,
                name=name,
                defaults={
                    "external_id": f"PLASMA-{subject_id}",
                    "species": "Homo sapiens",
                    "matrix": "EDTA plasma",
                    "digestion_protocol": "SP3 tryptic digest, 200 ng peptide load",
                    "enrichment_protocol": "None",
                    "submitted_by": researcher,
                    "metadata": {
                        "role": RunFileRole.SAMPLE,
                        "subject_id": subject_id,
                        "condition": condition,
                        "cohort_arm": "control" if condition == "healthy" else "case",
                        "age": age,
                        "sex": sex,
                        "bmi": bmi,
                        "clinical_score": clinical_score,
                        "collection_site": collection_site,
                        "collection_date": f"2026-06-{(index % 28) + 1:02d}",
                        "fasting_state": "fasted" if index % 5 else "non-fasted",
                        "sample_type": "plasma",
                        "storage_temperature_c": -80,
                        "freeze_thaw_count": index % 2,
                        "randomization_block": ((index - 1) // 10) + 1,
                        "plate": "Plate-1" if index <= 50 else "Plate-2",
                        "well": f"{chr(65 + ((index - 1) % 8))}{((index - 1) // 8) + 1:02d}",
                    },
                },
            )
            samples[name] = sample
        return samples

    def _seed_worklist_entries(self, worklist, samples, configuration, admin_user):
        plan = [("BLANK", RunFileRole.BLANK, "B1", "batch-start"), ("LIB-HYE", RunFileRole.LIBRARY, "L1", "library")]
        hye_pair_number = 1
        plan.extend(self._hye_pair_plan(hye_pair_number, "qc-open"))
        hye_pair_number += 1

        for block in range(10):
            for offset in range(5):
                healthy_index = block * 5 + offset + 1
                diseased_index = block * 5 + offset + 1
                plan.append((f"HEALTHY-{healthy_index:03d}", RunFileRole.SAMPLE, "", f"bio-block-{block + 1:02d}"))
                plan.append((f"DISEASED-{diseased_index:03d}", RunFileRole.SAMPLE, "", f"bio-block-{block + 1:02d}"))
            plan.extend(self._hye_pair_plan(hye_pair_number, f"qc-after-block-{block + 1:02d}"))
            hye_pair_number += 1

        plan.append(("WASH", RunFileRole.WASH, "W1", "batch-end"))
        entries = []
        for position, (sample_name, role, hye_pair, block) in enumerate(plan, start=1):
            expected_filename = f"COHORT_DIA_100_{position:03d}_{sample_name}.raw"
            run, _ = Run.objects.update_or_create(
                sample=samples[sample_name],
                run_name=f"COHORT_DIA_100_{position:03d}_{sample_name}",
                defaults={
                    "configuration": configuration,
                    "acquired_by": admin_user,
                    "status": RunStatus.PLANNED,
                    "file_role": role,
                    "expected_filename": expected_filename,
                    "worklist_position": position,
                    "hye_pair_label": hye_pair,
                    "metadata": {
                        "block": block,
                        "expected_filename": expected_filename,
                        "sample_condition": samples[sample_name].metadata.get("condition", ""),
                        "subject_id": samples[sample_name].metadata.get("subject_id", ""),
                        "qc_material": samples[sample_name].metadata.get("qc_material", ""),
                        "pseudo_project_key": samples[sample_name].metadata.get("pseudo_project_key", ""),
                    },
                },
            )
            entry, _ = WorklistEntry.objects.update_or_create(
                worklist=worklist,
                position=position,
                defaults={
                    "run": run,
                    "file_role": role,
                    "expected_filename": expected_filename,
                    "injection_volume_ul": 2.0 if role not in {RunFileRole.BLANK, RunFileRole.WASH} else 1.0,
                    "hye_pair_label": hye_pair,
                    "block_label": block,
                    "metadata": {
                        "autosampler_vial": f"{chr(65 + ((position - 1) % 8))}{((position - 1) // 8) + 1:02d}",
                        "method": "Demo_DIA_45min_60SPD",
                        "condition": samples[sample_name].metadata.get("condition", ""),
                        "subject_id": samples[sample_name].metadata.get("subject_id", ""),
                        "qc_material": samples[sample_name].metadata.get("qc_material", ""),
                    },
                },
            )
            entries.append(entry)
        return entries

    def _hye_pair_plan(self, pair_number, block):
        label = f"HYE-PAIR-{pair_number:02d}"
        return [("HYE-A", RunFileRole.QC, label, block), ("HYE-B", RunFileRole.QC, label, block)]

    def _seed_diann_pipeline(self):
        pipeline, _ = ProcessingPipeline.objects.update_or_create(
            name="DIA-NN",
            version="demo-1.9-compatible",
            defaults={
                "container_image": "ghcr.io/msconnect/diann-node:demo",
                "parameters": {
                    "command": [
                        "python",
                        "manage.py",
                        "seed_demo_showcase",
                        "--write-job-results",
                        "{job_id}",
                        "{results_dir}",
                    ],
                    "working_dir": "/app",
                    "result_files": {
                        "protein_table": "proteins.csv",
                        "peptide_table": "peptides.csv",
                        "delimiter": ",",
                    },
                    "library_strategy": "library-free with optional HYE library refinement",
                    "fasta": "/data/reference/hye_human_yeast_ecoli.fasta",
                    "enzyme": "Trypsin/P",
                    "missed_cleavages": 2,
                    "min_peptide_length": 7,
                    "max_peptide_length": 30,
                    "precursor_fdr": 0.01,
                    "protein_fdr": 0.01,
                    "match_between_runs": True,
                    "quantification": "integrated elution group area",
                },
            },
        )
        return pipeline

    def _seed_processing_node(self, pipeline):
        node, _ = ProcessingNode.objects.update_or_create(
            name="diann-node-demo-01",
            defaults={
                "node_type": "diann",
                "status": ProcessingNodeStatus.IDLE,
                "container_image": pipeline.container_image,
                "endpoint_url": "http://diann-node-demo-01.local:8765",
                "last_heartbeat_at": timezone.now(),
                "settings": {
                    "input_mount": "/data/raw",
                    "output_mount": "/data/results",
                    "max_parallel_jobs": 1,
                    "gpu_enabled": False,
                    "diann_binary": "/opt/diann/diann",
                },
            },
        )
        return node

    def _seed_raw_files(self, entries):
        raw_files = []
        acquired_base = timezone.now() - timedelta(hours=14)
        missing_positions = {64}
        for entry in entries:
            run = entry.run
            if entry.position in missing_positions:
                run.status = RunStatus.PLANNED
                run.save(update_fields=["status", "updated_at"])
                continue
            checksum = hashlib.sha256(entry.expected_filename.encode()).hexdigest()
            raw_file, _ = RawFile.objects.update_or_create(
                checksum_sha256=checksum,
                defaults={
                    "run": run,
                    "source_path": f"/data/incoming/{entry.expected_filename}",
                    "storage_path": f"/data/raw/{self.project_code}/{entry.expected_filename}",
                    "filename": entry.expected_filename,
                    "size_bytes": 950_000_000 + entry.position * 750_000,
                    "acquired_at": acquired_base + timedelta(minutes=48 * entry.position),
                    "imported_at": acquired_base + timedelta(minutes=48 * entry.position + 4),
                    "status": RawFileStatus.IMPORTED,
                    "file_role": entry.file_role,
                    "match_confidence": 1.0,
                    "metadata": {
                        "matched_by": "expected_filename",
                        "worklist_position": entry.position,
                        "autosampler_vial": entry.metadata.get("autosampler_vial"),
                        "condition": entry.metadata.get("condition"),
                        "subject_id": entry.metadata.get("subject_id"),
                        "qc_material": entry.metadata.get("qc_material"),
                        "lc_ms_telemetry": {
                            "tic": 7.8e9 + entry.position * 8.5e7,
                            "base_peak_intensity": 1.9e7 + entry.position * 2.8e5,
                            "ms1_features": 48000 + entry.position * 375,
                            "ms2_spectra": 168000 + entry.position * 1850,
                            "spray_stability_percent": 96.5 - (entry.position % 4) * 0.4,
                            "gradient_minutes": 45,
                            "column_pressure_bar": 710 + entry.position,
                        },
                    },
                },
            )
            run.status = RunStatus.IMPORTED
            run.acquisition_started_at = raw_file.acquired_at
            run.acquisition_ended_at = raw_file.acquired_at + timedelta(minutes=45)
            run.save(update_fields=["status", "acquisition_started_at", "acquisition_ended_at", "updated_at"])
            raw_files.append(raw_file)
        RawFile.objects.update_or_create(
            checksum_sha256=hashlib.sha256(b"unmatched-demo-file").hexdigest(),
            defaults={
                "run": None,
                "source_path": "/data/incoming/COHORT_DIA_100_999_OPERATOR_NOTE.raw",
                "storage_path": f"/data/raw/{self.project_code}/unmatched/COHORT_DIA_100_999_OPERATOR_NOTE.raw",
                "filename": "COHORT_DIA_100_999_OPERATOR_NOTE.raw",
                "size_bytes": 42_000,
                "imported_at": timezone.now(),
                "status": RawFileStatus.VALIDATED,
                "file_role": RunFileRole.CALIBRATION,
                "match_confidence": 0.0,
                "metadata": {"matched_by": "unmatched", "reason": "No expected run-file order entry."},
            },
        )
        return raw_files

    def _seed_jobs_and_quant(self, raw_files, pipeline, node):
        proteins = self._demo_proteins()
        peptide = Peptide.objects.update_or_create(
            sequence="LVNELTEFAK",
            modified_sequence="LVNELTEFAK",
            charge=2,
        )[0]

        for index, raw_file in enumerate(raw_files, start=1):
            status = ProcessingStatus.COMPLETE
            if index == len(raw_files):
                status = ProcessingStatus.RUNNING
            elif index == len(raw_files) - 1:
                status = ProcessingStatus.RETRYING
            elif raw_file.file_role in {RunFileRole.BLANK, RunFileRole.WASH}:
                status = ProcessingStatus.QUEUED
            job, _ = ProcessingJob.objects.update_or_create(
                run=raw_file.run,
                pipeline=pipeline,
                raw_file=raw_file,
                defaults={
                    "node": node if status != ProcessingStatus.QUEUED else None,
                    "status": status,
                    "started_at": (
                        raw_file.imported_at + timedelta(minutes=10)
                        if status != ProcessingStatus.QUEUED
                        else None
                    ),
                    "finished_at": (
                        raw_file.imported_at + timedelta(minutes=28)
                        if status == ProcessingStatus.COMPLETE
                        else None
                    ),
                    "log_path": f"/data/results/{self.project_code}/{raw_file.run.run_name}/diann.log",
                    "metadata": {
                        "node": node.name,
                        "settings_snapshot": pipeline.parameters,
                        "result_directory": f"/data/results/{self.project_code}/{raw_file.run.run_name}",
                        "telemetry": {
                            "protein_groups": 4300 + index * 19,
                            "precursors": 51000 + index * 220,
                            "ms1_features": raw_file.metadata.get("lc_ms_telemetry", {}).get("ms1_features"),
                            "ms2_spectra": raw_file.metadata.get("lc_ms_telemetry", {}).get("ms2_spectra"),
                            "median_ms1_mass_error_ppm": round(1.2 + (index % 3) * 0.08, 2),
                            "median_ms2_score": round(91.0 - (index % 4) * 0.7, 2),
                        },
                    },
                },
            )
            if status != ProcessingStatus.COMPLETE:
                continue

            for protein_index, protein in enumerate(proteins, start=1):
                role_multiplier = self._protein_multiplier(raw_file, protein)
                ProteinIdentification.objects.update_or_create(
                    job=job,
                    protein=protein,
                    defaults={
                        "score": 85 + protein_index,
                        "q_value": 0.002,
                        "coverage_percent": 30 + protein_index,
                        "peptide_count": 8,
                    },
                )
                ProteinQuant.objects.update_or_create(
                    job=job,
                    protein=protein,
                    label="abundance",
                    defaults={
                        "value": round((1_000_000 + protein_index * 85000 + index * 4500) * role_multiplier, 2),
                        "unit": "area",
                        "metadata": {
                            "source": "demo-seed",
                            "organism": protein.organism,
                            "log2_intensity": round(
                                self._log2((1_000_000 + protein_index * 85000 + index * 4500) * role_multiplier),
                                3,
                            ),
                        },
                    },
                )
            PeptideIdentification.objects.update_or_create(
                job=job,
                peptide=peptide,
                defaults={"score": 92.0, "q_value": 0.001, "retention_time_seconds": 1450 + index * 3, "mz": 593.312},
            )
            PeptideQuant.objects.update_or_create(
                job=job,
                peptide=peptide,
                label="abundance",
                defaults={"value": round(250000 + index * 1000, 2), "unit": "area"},
            )

    def _demo_proteins(self):
        protein_defs = [
            ("P00533", "EGFR", "Homo sapiens", "Epidermal growth factor receptor"),
            ("P38398", "BRCA1", "Homo sapiens", "Breast cancer type 1 susceptibility protein"),
            ("P04637", "TP53", "Homo sapiens", "Cellular tumor antigen p53"),
            ("P31749", "AKT1", "Homo sapiens", "RAC-alpha serine/threonine-protein kinase"),
            ("P28482", "MAPK1", "Homo sapiens", "Mitogen-activated protein kinase 1"),
            ("P00924", "ENO1", "Saccharomyces cerevisiae", "Enolase"),
            ("P00330", "ADH1", "Saccharomyces cerevisiae", "Alcohol dehydrogenase 1"),
            ("P00549", "KPYK1", "Saccharomyces cerevisiae", "Pyruvate kinase 1"),
            ("P02994", "TEF1", "Saccharomyces cerevisiae", "Elongation factor 1-alpha"),
            ("P0A6F5", "GAPDH", "Escherichia coli", "Glyceraldehyde-3-phosphate dehydrogenase A"),
            ("P0A9B2", "G3P1", "Escherichia coli", "Glyceraldehyde-3-phosphate dehydrogenase A"),
            ("P0A6P9", "ENO", "Escherichia coli", "Enolase"),
            ("P0A7V8", "RS4", "Escherichia coli", "30S ribosomal protein S4"),
        ]
        proteins = []
        for accession, gene_symbol, organism, description in protein_defs:
            proteins.append(
                Protein.objects.update_or_create(
                    accession=accession,
                    organism=organism,
                    defaults={"gene_symbol": gene_symbol, "description": description},
                )[0]
            )
        return proteins

    def _protein_multiplier(self, raw_file, protein):
        if raw_file.file_role == RunFileRole.LIBRARY:
            return 1.15
        if raw_file.file_role == RunFileRole.SAMPLE:
            condition = raw_file.run.sample.metadata.get("condition")
            if condition == "healthy":
                return 0.95 if protein.organism == "Homo sapiens" else 0.04
            if condition == "diseased":
                return 1.25 if protein.organism == "Homo sapiens" else 0.04
            return 1.0
        if raw_file.file_role != RunFileRole.QC:
            return 0.03

        hye_fractions = {
            "HYE-A": {
                "Homo sapiens": 0.65,
                "Saccharomyces cerevisiae": 0.30,
                "Escherichia coli": 0.05,
            },
            "HYE-B": {
                "Homo sapiens": 0.65,
                "Saccharomyces cerevisiae": 0.15,
                "Escherichia coli": 0.20,
            },
        }
        sample_name = raw_file.run.sample.name
        fraction = hye_fractions.get(sample_name, {}).get(protein.organism, 0.01)
        pair_offset = 1 + (raw_file.run.worklist_position or 0) * 0.002
        return fraction * pair_offset

    def _log2(self, value):
        import math

        return math.log2(value) if value > 0 else 0
