import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.processing.registry import add_reference


class Command(BaseCommand):
    help = "Fetch a reviewed UniProt FASTA into shared reference storage and register it."

    def add_arguments(self, parser):
        parser.add_argument("--key", required=True, help="Stable registry key, e.g. human_reviewed.")
        parser.add_argument("--organism-id", required=True, type=int, help="NCBI taxonomy id, e.g. 9606 for human.")
        parser.add_argument("--name", required=True, help="Clear filename stem, e.g. human_reviewed_2026Q3.")
        parser.add_argument("--query", default="", help="Optional additional UniProt query expression.")
        parser.add_argument("--include-unreviewed", action="store_true")
        parser.add_argument("--force", action="store_true")

    def handle(self, *args, **options):
        key = self._token(options["key"])
        name = self._token(options["name"])
        query = f"organism_id:{options['organism_id']}"
        if not options["include_unreviewed"]:
            query += " AND reviewed:true"
        if options["query"].strip():
            query += f" AND ({options['query'].strip()})"

        root = Path(settings.PROCESSOR_SHARED_STORAGE_ROOT) / "reference" / "uniprot"
        root.mkdir(parents=True, exist_ok=True)
        fasta_path = root / f"{name}.fasta"
        metadata_path = root / f"{name}.json"
        if fasta_path.exists() and not options["force"]:
            raise CommandError(f"Reference already exists: {fasta_path}. Use --force to refresh it.")

        url = "https://rest.uniprot.org/uniprotkb/stream?format=fasta&query=" + quote(query, safe="")
        request = Request(url, headers={"User-Agent": "MSConnect/1.0 reference-fetch"})
        try:
            with urlopen(request, timeout=120) as response:
                payload = response.read()
        except OSError as exc:
            raise CommandError(f"UniProt FASTA request failed: {exc}") from exc
        if not payload.startswith(b">"):
            raise CommandError("UniProt returned no FASTA records for the requested query.")

        temp_path = fasta_path.with_suffix(".fasta.download")
        temp_path.write_bytes(payload)
        temp_path.replace(fasta_path)
        checksum = hashlib.sha256(payload).hexdigest()
        metadata = {
            "source": "UniProt",
            "url": url,
            "query": query,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "sha256": checksum,
            "sequence_count": payload.count(b"\n>") + 1,
            "filename": fasta_path.name,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        add_reference(kind="fasta", key=key, source_path=str(fasta_path), force=True)
        self.stdout.write(self.style.SUCCESS(f"fetched UniProt FASTA {key}: {fasta_path} ({metadata['sequence_count']} sequences)"))

    @staticmethod
    def _token(value: str) -> str:
        token = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
        if not token:
            raise CommandError("Reference key/name must contain letters or numbers.")
        return token
