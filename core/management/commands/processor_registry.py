import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.models import ProcessingPipeline
from core.processing.registry import (
    ENGINE_NAMES,
    add_engine_profile,
    add_reference,
    add_settings,
    engine_profile,
    load_registry,
    registry_path,
    resolve_pipeline_parameters,
    save_registry,
    validate_engine_profile,
    validate_registry_selection,
)


class Command(BaseCommand):
    help = "Manage processor reference assets and shared engine settings in PROCESSOR_SHARED_STORAGE_ROOT."

    def add_arguments(self, parser):
        subparsers = parser.add_subparsers(dest="action", required=True)

        subparsers.add_parser("init", help="Create the processor registry if it does not exist.")
        subparsers.add_parser("list", help="Print the processor registry JSON.")
        engine_choices = tuple(sorted(ENGINE_NAMES))

        add_reference_parser = subparsers.add_parser("add-reference", help="Register a shared reference asset.")
        add_reference_parser.add_argument(
            "--kind",
            required=True,
            choices=("fasta", "speclib", "skyline_document", "fragpipe_workflow"),
        )
        add_reference_parser.add_argument("--key", required=True)
        add_reference_parser.add_argument("--path", required=True)
        add_reference_parser.add_argument("--copy", action="store_true")
        add_reference_parser.add_argument("--force", action="store_true")

        add_settings_parser = subparsers.add_parser("add-settings", help="Register shared processor settings JSON.")
        add_settings_parser.add_argument("--engine", required=True, choices=engine_choices)
        add_settings_parser.add_argument("--key", required=True)
        add_settings_parser.add_argument("--json-file", required=True)

        add_engine_parser = subparsers.add_parser(
            "add-engine",
            help="Register an installable processor engine profile.",
        )
        add_engine_parser.add_argument("--engine", required=True, choices=engine_choices)
        add_engine_parser.add_argument("--version", required=True)
        add_engine_parser.add_argument("--install-type", choices=("image", "external"), default="")
        add_engine_parser.add_argument("--image", default="")
        add_engine_parser.add_argument("--image-digest", default="")
        add_engine_parser.add_argument("--executable", default="")
        add_engine_parser.add_argument("--version-command", nargs="+", default=[])
        add_engine_parser.add_argument("--version-command-json", default="")
        add_engine_parser.add_argument("--source", default="")
        add_engine_parser.add_argument("--source-sha256", default="")
        add_engine_parser.add_argument("--license-note", default="")

        validate_parser = subparsers.add_parser(
            "validate",
            help="Validate registry references and optional executable.",
        )
        validate_parser.add_argument("--engine", required=True, choices=engine_choices)
        validate_parser.add_argument("--settings-key", default="")
        validate_parser.add_argument("--require-executable", action="store_true")

        validate_engine_parser = subparsers.add_parser("validate-engine", help="Validate a processor engine profile.")
        validate_engine_parser.add_argument("--engine", required=True, choices=engine_choices)
        validate_engine_parser.add_argument("--version", required=True)
        validate_engine_parser.add_argument("--require-image", action="store_true")
        validate_engine_parser.add_argument("--require-executable", action="store_true")

        pipeline_parser = subparsers.add_parser(
            "create-pipeline",
            help="Create or update a ProcessingPipeline from registry settings.",
        )
        pipeline_parser.add_argument("--engine", required=True, choices=engine_choices)
        pipeline_parser.add_argument("--version", required=True)
        pipeline_parser.add_argument("--engine-version", default="")
        pipeline_parser.add_argument("--settings-key", required=True)
        pipeline_parser.add_argument("--name", default="")
        pipeline_parser.add_argument("--container-image", default="")

    def handle(self, *args, **options):
        action = options["action"]
        if action == "init":
            path = save_registry(load_registry())
            self.stdout.write(self.style.SUCCESS(f"processor registry ready: {path}"))
            return
        if action == "list":
            self.stdout.write(json.dumps(load_registry(), indent=2, sort_keys=True))
            return
        if action == "add-reference":
            entry = add_reference(
                kind=options["kind"],
                key=options["key"],
                source_path=options["path"],
                copy=options["copy"],
                force=options["force"],
            )
            self.stdout.write(
                self.style.SUCCESS(f"registered reference {entry['kind']}/{entry['key']}: {entry['path']}")
            )
            return
        if action == "add-settings":
            values = self._load_settings_file(Path(options["json_file"]))
            entry = add_settings(engine=options["engine"], key=options["key"], values=values)
            self.stdout.write(self.style.SUCCESS(f"registered settings {entry['engine']}/{entry['key']}"))
            return
        if action == "add-engine":
            entry = add_engine_profile(
                engine=options["engine"],
                version=options["version"],
                image=options["image"],
                executable=options["executable"],
                version_command=self._version_command(options),
                install_type=options["install_type"],
                image_digest=options["image_digest"],
                source=options["source"],
                source_sha256=options["source_sha256"],
                license_note=options["license_note"],
            )
            label = f"{entry['engine']}/{entry['version']} {entry['install_type']}"
            detail = entry.get("image") or entry.get("executable") or "registered"
            self.stdout.write(self.style.SUCCESS(f"registered engine {label}: {detail}"))
            return
        if action == "validate":
            errors = validate_registry_selection(
                engine=options["engine"],
                settings_key=options["settings_key"],
                require_executable=options["require_executable"],
            )
            if errors:
                for error in errors:
                    self.stderr.write(self.style.ERROR(f"- {error}"))
                raise CommandError("Processor registry validation failed.")
            self.stdout.write(self.style.SUCCESS("processor registry validation ok"))
            return
        if action == "validate-engine":
            errors = validate_engine_profile(
                engine=options["engine"],
                version=options["version"],
                require_image=options["require_image"],
                require_executable=options["require_executable"],
            )
            if errors:
                for error in errors:
                    self.stderr.write(self.style.ERROR(f"- {error}"))
                raise CommandError("Processor engine validation failed.")
            self.stdout.write(self.style.SUCCESS("processor engine validation ok"))
            return
        if action == "create-pipeline":
            pipeline = self._create_pipeline(options)
            self.stdout.write(self.style.SUCCESS(f"processor pipeline ready: {pipeline.name} {pipeline.version}"))
            return
        raise CommandError(f"Unknown processor registry action: {action}")

    def _load_settings_file(self, path: Path) -> dict:
        if not path.exists():
            raise CommandError(f"Settings JSON file does not exist: {path}")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise CommandError(f"Settings JSON file is invalid: {path}") from exc
        if not isinstance(payload, dict):
            raise CommandError("Settings JSON file must contain an object.")
        return payload

    def _version_command(self, options) -> list[str]:
        if not options["version_command_json"]:
            return options["version_command"]
        try:
            payload = json.loads(options["version_command_json"])
        except json.JSONDecodeError as exc:
            raise CommandError("--version-command-json must be a JSON string array.") from exc
        if not isinstance(payload, list) or not all(isinstance(item, str) and item for item in payload):
            raise CommandError("--version-command-json must be a JSON string array.")
        return payload

    def _create_pipeline(self, options):
        engine = options["engine"]
        engine_version = options["engine_version"] or options["version"]
        profile = engine_profile(registry=load_registry(), engine=engine, version=engine_version)
        parameters = resolve_pipeline_parameters(
            {
                "adapter": engine,
                "required_engine": engine,
                "required_engine_version": engine_version,
                "settings_ref": options["settings_key"],
            },
            engine=engine,
        )
        name = options["name"] or {
            "diann": "Real DIA-NN",
            "fragpipe": "Real FragPipe",
            "proteome-discoverer": "Real Proteome Discoverer",
            "skyline": "Skyline Targeted",
            "spectronaut": "Real Spectronaut",
        }[engine]
        pipeline, _created = ProcessingPipeline.objects.update_or_create(
            name=name,
            version=options["version"],
            defaults={
                "container_image": options["container_image"] or profile.get("image", ""),
                "parameters": parameters,
            },
        )
        registry_file = registry_path()
        pipeline.parameters = {
            **(pipeline.parameters or {}),
            "registry_file": str(registry_file),
        }
        pipeline.save(update_fields=["parameters", "updated_at"])
        return pipeline
