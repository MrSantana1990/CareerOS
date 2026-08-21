"""Conservative discovery scheduler; inactive unless explicitly enabled."""

import json
import os
import time
import urllib.request
from datetime import datetime, timezone

from .tasks import discover_source


def enabled_sources() -> list[dict]:
    request = urllib.request.Request(
        os.getenv("CAREER_API_URL", "http://api:8000").rstrip("/") + "/api/v1/sources?enabled=true",
        headers={"Authorization": f"Bearer {os.environ['ADMIN_API_TOKEN']}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def run() -> None:
    while True:
        if os.getenv("AUTO_DISCOVERY_ENABLED", "false").lower() == "true":
            for source in enabled_sources():
                last_started = source.get("last_started_at")
                if last_started:
                    elapsed = datetime.now(timezone.utc) - datetime.fromisoformat(last_started)
                    if elapsed.total_seconds() < source["cadence_minutes"] * 60:
                        continue
                discover_source.send(
                    source["adapter"], source["account_key"], source["company_name"],
                    source["maximum_jobs"], str(source["id"]),
                )
        time.sleep(max(1800, int(os.getenv("DISCOVERY_TICK_SECONDS", "1800"))))


if __name__ == "__main__":
    run()
