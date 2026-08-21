import os
import json
import urllib.request
import dramatiq
from dramatiq.brokers.redis import RedisBroker

from .sources import build_adapter

broker = RedisBroker(url=os.getenv("REDIS_URL", "redis://localhost:6379/0"))
dramatiq.set_broker(broker)


@dramatiq.actor(queue_name="system")
def health_probe() -> str:
    """Non-destructive worker smoke task."""
    return "ok"


@dramatiq.actor(queue_name="scoring", max_retries=3, min_backoff=5000)
def score_job(job_id: str) -> dict:
    """Request deterministic scoring; the API upsert makes retries idempotent."""
    if os.getenv("AUTO_SCORE_ENABLED", "false").lower() != "true":
        return {"status": "disabled", "job_id": job_id}
    api_url = os.getenv("CAREER_API_URL", "http://api:8000").rstrip("/")
    token = os.environ["ADMIN_API_TOKEN"]
    request = urllib.request.Request(
        f"{api_url}/api/v1/jobs/{job_id}/score",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _ingest(payload: dict) -> dict:
    api_url = os.getenv("CAREER_API_URL", "http://api:8000").rstrip("/")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{api_url}/api/v1/jobs",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {os.environ['ADMIN_API_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def _report_run(connection_id: str, payload: dict) -> dict:
    api_url = os.getenv("CAREER_API_URL", "http://api:8000").rstrip("/")
    request = urllib.request.Request(
        f"{api_url}/api/v1/sources/{connection_id}/runs",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {os.environ['ADMIN_API_TOKEN']}",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


@dramatiq.actor(queue_name="discovery", max_retries=3, min_backoff=10000)
def discover_source(source: str, account: str, company: str, maximum: int = 200,
                    connection_id: str | None = None) -> dict:
    """Read a public ATS feed and idempotently ingest normalized jobs."""
    if os.getenv("AUTO_DISCOVERY_ENABLED", "false").lower() != "true":
        return {"status": "disabled", "source": source}
    run_id = None
    if connection_id:
        run_id = _report_run(connection_id, {"status": "RUNNING"})["run_id"]
    try:
        jobs = build_adapter(source, account, company).discover()[: max(1, min(maximum, 500))]
        created = 0
        deduplicated = 0
        for job in jobs:
            result = _ingest(job.as_payload())
            created += int(result["created"])
            deduplicated += int(result["deduplicated"])
        result = {"status": "ok", "source": source, "connection_id": connection_id,
                  "found": len(jobs), "created": created, "deduplicated": deduplicated}
        if connection_id:
            _report_run(connection_id, {"run_id": run_id, "status": "COMPLETED",
                        "found_count": len(jobs), "created_count": created,
                        "deduplicated_count": deduplicated})
        return result
    except Exception as error:
        if connection_id and run_id:
            _report_run(connection_id, {"run_id": run_id, "status": "FAILED",
                        "error_message": str(error)[:2000]})
        raise
