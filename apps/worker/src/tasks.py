import os
import json
import urllib.request
import dramatiq
from dramatiq.brokers.redis import RedisBroker

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
