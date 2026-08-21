"""Detecção de ATS estruturado por domínio.

Módulo stdlib puro (sem Playwright/FastAPI), no mesmo espírito de
`url_policy.py`, para ser testável isoladamente — o CI do automation-host
roda os testes sem instalar as dependências do próprio pacote.
"""
from dataclasses import dataclass
from urllib.parse import urlparse
import re

# Mesmo padrão de account_key usado pelos adapters estruturados
# (apps/worker/src/sources.py) e pelo schema de entrada da API
# (SourceConnectionInput em apps/api/src/career.py).
ACCOUNT_SLUG_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{2,100}$")


@dataclass(frozen=True)
class ATSMatch:
    adapter: str  # "GREENHOUSE" | "LEVER" | "ASHBY" — mesmos valores usados
    # pelos adapters de apps/worker/src/sources.py.
    account_key: str
    board_url: str


def _first_path_segment(path: str) -> str | None:
    return path.strip("/").split("/", 1)[0] or None


# Registro extensível: (adapter, predicado_de_host, extrator_de_slug).
# Adicionar um novo ATS (Workday, SmartRecruiters, iCIMS, ...) no futuro é
# só acrescentar uma tupla aqui, sem mexer no resto do módulo.
_MATCHERS: tuple[tuple[str, "callable", "callable"], ...] = (
    (
        "GREENHOUSE",
        lambda host: host in {"boards.greenhouse.io", "job-boards.greenhouse.io"},
        lambda host, path: _first_path_segment(path),
    ),
    (
        "LEVER",
        lambda host: host == "jobs.lever.co",
        lambda host, path: _first_path_segment(path),
    ),
    (
        "ASHBY",
        lambda host: host == "jobs.ashbyhq.com",
        lambda host, path: _first_path_segment(path),
    ),
)


def detect_ats(url: str | None) -> ATSMatch | None:
    """Identifica se uma URL pertence a um board de ATS estruturado conhecido.

    Retorna None para qualquer site que não seja um dos ATS cadastrados
    (LinkedIn, Indeed, Catho, InfoJobs, portais próprios, etc.) — o
    comportamento do executor de navegador para esses sites não muda.
    """
    if not url:
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower().split(":")[0]
    for adapter, is_host, slug_of in _MATCHERS:
        if not is_host(host):
            continue
        slug = slug_of(host, parsed.path)
        if not slug or not ACCOUNT_SLUG_PATTERN.fullmatch(slug):
            return None
        return ATSMatch(
            adapter=adapter,
            account_key=slug,
            board_url=f"{parsed.scheme}://{host}/{slug}",
        )
    return None
