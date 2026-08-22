"""Cliente do kill switch persistente do Core (`system_settings`).

Sem dependencias de Playwright/FastAPI (mesmo padrao de ats_detection.py e
hard_blocks.py) para poder ser testado isoladamente no CI.

Leitura falha aberta onde o risco e baixo (descoberta/analise sao apenas
leitura local); falha fechada onde o risco e alto e irreversivel (o clique
real de envio) - se o Core estiver inacessivel nesse ponto, tratamos como
pausado por seguranca em vez de assumir que esta tudo liberado.
"""

from dataclasses import dataclass
import json
from urllib.error import URLError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class KillSwitchStatus:
    paused: bool
    reason: str
    reachable: bool


def fetch_kill_switches(api_url: str, admin_token: str, timeout: int = 10) -> dict[str, dict] | None:
    if not admin_token:
        return None
    request = Request(
        api_url.rstrip("/") + "/api/v1/system/kill-switches",
        headers={"Authorization": f"Bearer {admin_token}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError, ValueError):
        return None


def is_paused(switches: dict[str, dict] | None, *keys: str, fail_closed: bool) -> KillSwitchStatus:
    if switches is None:
        return KillSwitchStatus(paused=fail_closed, reason="Core inacessível" if fail_closed else "", reachable=False)
    for key in keys:
        entry = switches.get(key) or {}
        if entry.get("paused"):
            return KillSwitchStatus(paused=True, reason=entry.get("reason") or key, reachable=True)
    return KillSwitchStatus(paused=False, reason="", reachable=True)
