from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings

from core.agents.client import AgentApiClient, AgentApiError


@dataclass(frozen=True)
class ApiDiscoveryCandidate:
    base_url: str
    source: str


def discover_api_base_urls(*, role: str, configured_base_url: str | None = None) -> list[ApiDiscoveryCandidate]:
    candidates: list[ApiDiscoveryCandidate] = []

    def add(url: str, source: str):
        normalized = _normalize_api_base_url(url)
        if not normalized:
            return
        if any(candidate.base_url == normalized for candidate in candidates):
            return
        candidates.append(ApiDiscoveryCandidate(base_url=normalized, source=source))

    if configured_base_url:
        add(configured_base_url, "configured")

    for url in getattr(settings, "MSCONNECT_API_DISCOVERY_BASE_URLS", []):
        add(url, "discovery-base-url")

    for host in getattr(settings, "MSCONNECT_API_DISCOVERY_HOSTS", []):
        host = str(host).strip()
        if not host:
            continue
        add(f"http://{host}:8000/api", "discovery-host")
        add(f"http://{host}/api", "discovery-host")

    default_host = configured_base_url or getattr(settings, "MSCONNECT_API_BASE_URL", "")
    if default_host:
        parsed = urlparse(default_host)
        if parsed.scheme and parsed.hostname:
            add(f"{parsed.scheme}://{parsed.hostname}:{parsed.port or _default_port(parsed.scheme)}/api", "configured-host")

    return candidates


def resolve_api_base_url(*, role: str, token: str, configured_base_url: str | None = None) -> str | None:
    for candidate in discover_api_base_urls(role=role, configured_base_url=configured_base_url):
        try:
            client = AgentApiClient(base_url=candidate.base_url, token=token, timeout=5, retries=1)
            payload = client.ping()
            if payload.get("agent_role") == role:
                return candidate.base_url
        except AgentApiError:
            continue
        except Exception:
            continue
    return None


def _normalize_api_base_url(value: str) -> str:
    base_url = str(value or "").strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/api"):
        return base_url
    return f"{base_url}/api"


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80
