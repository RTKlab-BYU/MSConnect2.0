import hashlib
from datetime import timedelta

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
    help = "Seed a complete MSConnect showcase with HYE A/B QC, worklist, raw-file matching, and DIA-NN jobs."

    def handle(self, *args, **options):
        with transaction.atomic():
            context = self._seed()
        self.stdout.write(self.style.SUCCESS("Demo showcase seeded."))
        self.stdout.write(f"Project: {context['project'].code} - {context['project'].title}")
        self.stdout.write(f"Worklist: {context['worklist'].name}")
        self.stdout.write("Open: http://127.0.0.1:8000/ui/showcase")

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

        project, _ = Project.objects.get_or_create(
            lab=lab,
            code="HYE-DIA-DEMO",
            defaults={
                "title": "HYE A/B DIA-MS Showcase",
                "pi": pi_user,
                "description": (
                    "End-to-end showcase for design, worklist generation, raw-file matching, and DIA-NN processing."
                ),
            },
        )
        experiment, _ = Experiment.objects.get_or_create(
            project=project,
            name="HYE A/B balanced DIA design",
            defaults={
                "hypothesis": (
                    "HYE A/B QC pairs should remain stable across the batch "
                    "while biological samples cluster by condition."
                ),
                "created_by": researcher,
                "metadata": {
                    "factors": {"condition": ["control", "treated"], "qc_pair": ["HYE-A", "HYE-B"]},
                    "design_summary": (
                        "Balanced acquisition with blanks, libraries, HYE A/B QC pairs, and biological samples."
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
                "notes": "Generated demo worklist: blank, library, HYE A/B QC pairs, balanced samples, and wash.",
                "metadata": {
                    "ordering_policy": "QC every 4 injections; HYE A/B paired before and after sample blocks.",
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

    def _seed_samples(self, experiment, researcher):
        sample_defs = [
            ("BLANK", RunFileRole.BLANK, "Solvent blank", {}),
            ("LIB-HYE", RunFileRole.LIBRARY, "HYE spectral library pool", {"library": True}),
            ("HYE-A", RunFileRole.QC, "Human/Yeast/Ecoli QC A", {"qc_pair": "A", "mix": "65/30/5"}),
            ("HYE-B", RunFileRole.QC, "Human/Yeast/Ecoli QC B", {"qc_pair": "B", "mix": "50/45/5"}),
            ("S01-Control", RunFileRole.SAMPLE, "Control replicate 1", {"condition": "control"}),
            ("S02-Control", RunFileRole.SAMPLE, "Control replicate 2", {"condition": "control"}),
            ("S03-Control", RunFileRole.SAMPLE, "Control replicate 3", {"condition": "control"}),
            ("S04-Treated", RunFileRole.SAMPLE, "Treated replicate 1", {"condition": "treated"}),
            ("S05-Treated", RunFileRole.SAMPLE, "Treated replicate 2", {"condition": "treated"}),
            ("S06-Treated", RunFileRole.SAMPLE, "Treated replicate 3", {"condition": "treated"}),
            ("WASH", RunFileRole.WASH, "Column wash", {}),
        ]
        samples = {}
        for name, role, description, metadata in sample_defs:
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
        return samples

    def _seed_worklist_entries(self, worklist, samples, configuration, admin_user):
        plan = [
            ("BLANK", RunFileRole.BLANK, "B1", "batch-start"),
            ("LIB-HYE", RunFileRole.LIBRARY, "L1", "library"),
            ("HYE-A", RunFileRole.QC, "HYE-PAIR-01", "qc-open"),
            ("HYE-B", RunFileRole.QC, "HYE-PAIR-01", "qc-open"),
            ("S01-Control", RunFileRole.SAMPLE, "", "block-1"),
            ("S04-Treated", RunFileRole.SAMPLE, "", "block-1"),
            ("S02-Control", RunFileRole.SAMPLE, "", "block-1"),
            ("HYE-A", RunFileRole.QC, "HYE-PAIR-02", "qc-mid"),
            ("HYE-B", RunFileRole.QC, "HYE-PAIR-02", "qc-mid"),
            ("S05-Treated", RunFileRole.SAMPLE, "", "block-2"),
            ("S03-Control", RunFileRole.SAMPLE, "", "block-2"),
            ("S06-Treated", RunFileRole.SAMPLE, "", "block-2"),
            ("HYE-A", RunFileRole.QC, "HYE-PAIR-03", "qc-close"),
            ("HYE-B", RunFileRole.QC, "HYE-PAIR-03", "qc-close"),
            ("WASH", RunFileRole.WASH, "W1", "batch-end"),
        ]
        entries = []
        for position, (sample_name, role, hye_pair, block) in enumerate(plan, start=1):
            expected_filename = f"HYE_DIA_DEMO_{position:03d}_{sample_name}.raw"
            run, _ = Run.objects.update_or_create(
                sample=samples[sample_name],
                run_name=f"HYE_DIA_DEMO_{position:03d}_{sample_name}",
                defaults={
                    "configuration": configuration,
                    "acquired_by": admin_user,
                    "status": RunStatus.PLANNED,
                    "file_role": role,
                    "expected_filename": expected_filename,
                    "worklist_position": position,
                    "hye_pair_label": hye_pair,
                    "metadata": {"block": block, "expected_filename": expected_filename},
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
                    "metadata": {"autosampler_vial": f"A{position:02d}", "method": "Demo_DIA_45min_60SPD"},
                },
            )
            entries.append(entry)
        return entries

    def _seed_diann_pipeline(self):
        pipeline, _ = ProcessingPipeline.objects.update_or_create(
            name="DIA-NN",
            version="demo-1.9-compatible",
            defaults={
                "container_image": "ghcr.io/msconnect/diann-node:demo",
                "parameters": {
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
        acquired_base = timezone.now() - timedelta(hours=8)
        missing_positions = {12}
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
                    "storage_path": f"/data/raw/HYE-DIA-DEMO/{entry.expected_filename}",
                    "filename": entry.expected_filename,
                    "size_bytes": 1_250_000_000 + entry.position * 1_000_000,
                    "acquired_at": acquired_base + timedelta(minutes=50 * entry.position),
                    "imported_at": acquired_base + timedelta(minutes=50 * entry.position + 5),
                    "status": RawFileStatus.IMPORTED,
                    "file_role": entry.file_role,
                    "match_confidence": 1.0,
                    "metadata": {
                        "matched_by": "expected_filename",
                        "worklist_position": entry.position,
                        "autosampler_vial": entry.metadata.get("autosampler_vial"),
                        "lc_ms_telemetry": {
                            "tic": 8.5e9 + entry.position * 1.2e8,
                            "base_peak_intensity": 2.2e7 + entry.position * 3.5e5,
                            "ms1_features": 52000 + entry.position * 450,
                            "ms2_spectra": 185000 + entry.position * 2100,
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
                "source_path": "/data/incoming/HYE_DIA_DEMO_999_OPERATOR_NOTE.raw",
                "storage_path": "/data/raw/HYE-DIA-DEMO/unmatched/HYE_DIA_DEMO_999_OPERATOR_NOTE.raw",
                "filename": "HYE_DIA_DEMO_999_OPERATOR_NOTE.raw",
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
                    "log_path": f"/data/results/HYE-DIA-DEMO/{raw_file.run.run_name}/diann.log",
                    "metadata": {
                        "node": node.name,
                        "settings_snapshot": pipeline.parameters,
                        "result_directory": f"/data/results/HYE-DIA-DEMO/{raw_file.run.run_name}",
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
            return 0.95 if "Control" in raw_file.run.sample.name else 1.2
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
