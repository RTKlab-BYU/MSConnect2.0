"""Resolve a reviewed, project-scoped UniProt FASTA for supported DIA-NN organisms."""

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

from django.conf import settings
from django.db.models import Q

from core.models import ReferenceAsset, ReferenceAssetType

ORGANISMS = {
    "human": {"label": "Human", "tax_id": 9606},
    "yeast": {"label": "Yeast", "tax_id": 559292},
    "ecoli": {"label": "E. coli", "tax_id": 83333},
    "pig": {"label": "Pig", "tax_id": 9823},
    "rat": {"label": "Rat", "tax_id": 10116},
    "mouse": {"label": "Mouse", "tax_id": 10090},
}

ALIASES = {
    "humanyeaste.coli": ("human", "yeast", "ecoli"),
    "human_yeast_ecoli": ("human", "yeast", "ecoli"),
    "human_yeast_e_coli": ("human", "yeast", "ecoli"),
    "hye": ("human", "yeast", "ecoli"),
    "e_coli": ("ecoli",),
    "e.coli": ("ecoli",),
    "e._coli": ("ecoli",),
    "escherichia_coli": ("ecoli",),
    "saccharomyces_cerevisiae": ("yeast",),
    "homo_sapiens": ("human",),
    "sus_scrofa": ("pig",),
    "rattus_norvegicus": ("rat",),
    "mus_musculus": ("mouse",),
}


def normalize_organisms(value) -> list[str]:
    if isinstance(value, str):
        raw = re.split(r"[,;+]", value.strip())
    else:
        raw = list(value or [])
    normalized = []
    for item in raw:
        token = re.sub(r"[\s-]+", "_", str(item).strip().lower())
        expanded = ALIASES.get(token, (token,))
        for organism in expanded:
            if organism not in ORGANISMS:
                raise ValueError(f"Unsupported organism {item!r}. Choose human, yeast, E. coli, pig, rat, or mouse.")
            if organism not in normalized:
                normalized.append(organism)
    if not normalized:
        raise ValueError("Select at least one organism for DIA-NN.")
    return normalized


def organism_selection(*sources) -> list[str] | None:
    """Return the first organism selection found in project/experiment settings."""
    for source in sources:
        if not isinstance(source, dict):
            continue
        diann = source.get("diann") if isinstance(source.get("diann"), dict) else {}
        sample_planning = source.get("sample_planning") if isinstance(source.get("sample_planning"), dict) else {}
        for candidate in (diann.get("organisms"), source.get("organisms"), source.get("organism"), sample_planning.get("organism")):
            if candidate:
                try:
                    return normalize_organisms(candidate)
                except ValueError:
                    continue
    return None


def resolve_project_fasta(*, organisms, project, experiment, user) -> ReferenceAsset:
    normalized = normalize_organisms(organisms)
    existing = ReferenceAsset.objects.filter(
        asset_type=ReferenceAssetType.FASTA,
        active=True,
    ).filter(Q(project=project) | Q(project__isnull=True))
    if experiment:
        existing = existing | ReferenceAsset.objects.filter(
            asset_type=ReferenceAssetType.FASTA,
            active=True,
            experiment=experiment,
        )
    existing = existing.order_by("-created_at")
    for asset in existing:
        asset_organisms = (asset.metadata or {}).get("organisms") or []
        if not asset_organisms:
            filename_token = re.sub(r"[^a-z]+", "_", asset.filename.lower()).strip("_")
            inferred = [key for key in ORGANISMS if key in filename_token]
            asset_organisms = inferred
        try:
            matches = asset_organisms and normalize_organisms(asset_organisms) == normalized
        except ValueError:
            matches = False
        if matches and Path(asset.storage_path).is_file():
            return asset

    shared_root = Path(settings.PROCESSOR_SHARED_STORAGE_ROOT).resolve()
    shared_reference_roots = (shared_root / "reference", shared_root / "references", shared_root / "reference-assets" / "fasta")
    filename_tokens = ["+".join(normalized), "_".join(normalized), "-".join(normalized)]
    if normalized == ["human", "yeast", "ecoli"]:
        filename_tokens.extend(("hye", "human_yeast_ecoli", "human-yeast-ecoli"))
    for root in shared_reference_roots:
        for token in filename_tokens:
            for extension in (".fasta", ".fa", ".faa"):
                path = root / f"{token}{extension}"
                if path.is_file() and path.stat().st_size and path.read_bytes().startswith(b">"):
                    return _register_shared_fasta(path, organisms=normalized, project=project, user=user)

    root = Path(settings.PROCESSOR_SHARED_STORAGE_ROOT).resolve() / "reference-assets" / "fasta"
    cache_root = root / "uniprot-cache"
    cache_root.mkdir(parents=True, exist_ok=True)
    entries = []
    contents = []
    try:
        for key in normalized:
            definition = ORGANISMS[key]
            query = f"organism_id:{definition['tax_id']} AND reviewed:true"
            cache_path = cache_root / f"{key}-reviewed.fasta"
            metadata_path = cache_root / f"{key}-reviewed.json"
            if cache_path.is_file() and cache_path.stat().st_size and cache_path.read_bytes().startswith(b">"):
                payload = cache_path.read_bytes()
                metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
            else:
                url = "https://rest.uniprot.org/uniprotkb/stream?format=fasta&query=" + quote(query, safe="")
                request = Request(url, headers={"User-Agent": "MSConnect/1.0 reference-fetch"})
                with urlopen(request, timeout=120) as response:
                    payload = response.read()
                if not payload.startswith(b">"):
                    raise ValueError(f"UniProt returned no reviewed sequences for {definition['label']}.")
                cache_path.write_bytes(payload)
                metadata = {
                    "source": "UniProt",
                    "url": url,
                    "query": query,
                    "retrieved_at": datetime.now(UTC).isoformat(),
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "sequence_count": payload.count(b"\n>") + 1,
                }
                metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
            entries.append({"organism": key, "label": definition["label"], **metadata})
            contents.append(payload.rstrip() + b"\n")
    except OSError as exc:
        raise ValueError(
            "The shared FASTA is missing and the server could not retrieve it from UniProt. "
            "Check server network access or attach a reviewed FASTA reference."
        ) from exc

    payload = b"".join(contents)
    checksum = hashlib.sha256(payload).hexdigest()
    filename = f"{'+'.join(normalized)}_{checksum[:16]}.fasta"
    destination = root / checksum[:2] / filename
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        temporary = destination.with_suffix(".fasta.tmp")
        temporary.write_bytes(payload)
        temporary.replace(destination)
    asset, _created = ReferenceAsset.objects.get_or_create(
        storage_path=str(destination),
        defaults={
            "asset_type": ReferenceAssetType.FASTA,
            "filename": filename,
            "checksum_sha256": checksum,
            "size_bytes": len(payload),
            "uploaded_by": user,
            "project": project,
            "experiment": None,
            "scope": "project",
            "metadata": {
                "source": "UniProt reviewed",
                "organisms": normalized,
                "components": entries,
                "sha256": checksum,
                "retrieved_at": datetime.now(UTC).isoformat(),
            },
        },
    )
    return asset


def _register_shared_fasta(path: Path, *, organisms: list[str], project, user) -> ReferenceAsset:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    checksum = digest.hexdigest()
    asset, _created = ReferenceAsset.objects.get_or_create(
        storage_path=str(path.resolve()),
        defaults={
            "asset_type": ReferenceAssetType.FASTA,
            "filename": path.name,
            "checksum_sha256": checksum,
            "size_bytes": path.stat().st_size,
            "uploaded_by": user,
            "project": project,
            "experiment": None,
            "scope": "project",
            "metadata": {"source": "existing shared reference", "organisms": organisms, "sha256": checksum},
        },
    )
    return asset
