import json
from urllib import error, request


class AgentApiError(RuntimeError):
    pass


class AgentApiClient:
    def __init__(self, *, base_url: str, token: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def heartbeat(self, *, name: str, node_type: str, status: str, container_image: str, metadata=None, settings=None):
        return self._request(
            "POST",
            "/agents/heartbeat/",
            {
                "name": name,
                "node_type": node_type,
                "status": status,
                "container_image": container_image,
                "metadata": metadata or {},
                "settings": settings or {},
            },
        )

    def import_raw_file(self, payload: dict):
        return self._request("POST", "/agents/raw-files/import/", payload)

    def record_ingestion_failure(self, payload: dict):
        return self._request("POST", "/agents/ingestion-failures/", payload)

    def claim_next_job(self, *, node_name: str):
        return self._request("POST", "/processing-jobs/claim-next/", {"node_name": node_name}, allow_empty=True)

    def start_job(self, job_id: int, *, node_name: str):
        return self._request("POST", f"/processing-jobs/{job_id}/start/", {"node_name": node_name})

    def complete_job(self, job_id: int, payload: dict):
        body = {"node_name": payload.pop("node_name")}
        body.update(payload)
        return self._request("POST", f"/processing-jobs/{job_id}/complete/", body)

    def fail_job(self, job_id: int, payload: dict):
        body = {"node_name": payload.pop("node_name")}
        body.update(payload)
        return self._request("POST", f"/processing-jobs/{job_id}/fail/", body)

    def _request(self, method: str, path: str, payload: dict | None = None, *, allow_empty: bool = False):
        data = None
        headers = {"Authorization": f"Bearer {self.token}"}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        http_request = request.Request(f"{self.base_url}{path}", data=data, headers=headers, method=method)
        try:
            with request.urlopen(http_request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                if not raw:
                    return None
                return json.loads(raw)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if allow_empty and exc.code == 204:
                return None
            raise AgentApiError(f"{method} {path} failed with HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise AgentApiError(f"{method} {path} failed: {exc.reason}") from exc
