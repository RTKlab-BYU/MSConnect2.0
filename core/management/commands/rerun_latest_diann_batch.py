from django.core.management.base import BaseCommand, CommandError

from core.services.batch_rerun import rerun_latest_diann_batch


class Command(BaseCommand):
    help = "Backfill mzML conversion jobs and rerun the latest failed DIA-NN worklist batch."

    def add_arguments(self, parser):
        parser.add_argument("--worklist-id", type=int, help="Target a specific acquisition worklist.")
        parser.add_argument(
            "--project-code",
            help="Restrict the lookup to the most recent worklist for the given project code.",
        )

    def handle(self, *args, **options):
        try:
            result = rerun_latest_diann_batch(
                worklist_id=options.get("worklist_id"),
                project_code=options.get("project_code"),
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"worklist={result['worklist_id']} converted={result['converted']} rerun={result['rerun']} "
                f"skipped={result['skipped']} pipeline={result['pipeline_id']}"
            )
        )
