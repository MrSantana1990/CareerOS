"""Ponte automation-host -> Core (Postgres = source of truth).

O Core ja calcula deduplicacao real via fingerprint de
company+title+location+description (apps/api/src/quality.py). Este modulo
NUNCA reimplementa esse fingerprint - a chave de idempotencia local so
existe para o automation-host nao reenviar a mesma ocorrencia (source,
source_url) duas vezes; a decisao final de "e a mesma vaga" e sempre do
Core.

Sem dependencias de Playwright/FastAPI (mesmo padrao de kill_switches.py,
hard_blocks.py, anti_spam.py) para poder ser testado isoladamente no CI.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import re

SCHEMA_VERSION = 1

# Backoff exponencial por tentativa (segundos). Depois da ultima posicao,
# repete o teto em vez de crescer sem limite.
BACKOFF_SECONDS = [5, 20, 60, 180, 300]
MAX_ATTEMPTS = 5

# Erros do cliente que nao se auto-corrigem com retry (dado invalido,
# credencial errada, rota inexistente) - vao direto pra dead-letter em vez
# de gastar as 5 tentativas. 409 NAO entra aqui: e tratado a parte, como
# sucesso (ver send_core_sync).
NON_RETRYABLE_STATUS = {400, 401, 403, 404, 422}


@dataclass
class CoreSyncRecord:
    kind: str
    payload: dict
    idempotency_key: str
    correlation_id: str
    schema_version: int = SCHEMA_VERSION
    attempts: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_error: str | None = None
    last_attempt_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CoreSyncRecord":
        known = set(cls.__dataclass_fields__)
        return cls(**{key: value for key, value in data.items() if key in known})


# Achados ao vivo (primeira validação em produção, 23/08/2026):
# - InfoJobs: o título da página é o próprio texto padrão do agregador
#   ("Vaga de emprego de X em Y"), sem empresa nenhuma.
# - Catho: o título é ESTATICO E GENERICO pra qualquer vaga ("Vagas de
#   emprego em todo Brasil | Catho") - não carrega nem o cargo, quanto
#   mais a empresa. Titulo de pagina nao serve de sinal nenhum aqui.
# O LinkedIn tem um sinal muito mais forte na própria URL
# (".../-at-<empresa>-<id>").
_LINKEDIN_COMPANY_URL_PATTERN = re.compile(r"-at-([a-z0-9-]+?)-\d+(?:[/?]|$)", re.IGNORECASE)
_JOB_BOARD_BOILERPLATE = re.compile(
    r"vaga de emprego|processo seletivo|oportunidade de emprego|^vaga\b|empregos? em\b",
    re.IGNORECASE,
)
# Nomes da própria plataforma nunca são o nome da empresa que contratou -
# aparecem no título como sufixo/marca do site, não como sinal de empresa.
_KNOWN_JOB_PLATFORMS = {"catho", "infojobs", "linkedin", "indeed", "vagas", "empregos"}


def guess_company_from_linkedin_url(source_url: str) -> str:
    match = _LINKEDIN_COMPANY_URL_PATTERN.search(source_url)
    if not match:
        return ""
    slug = match.group(1)
    return " ".join(word.capitalize() for word in slug.split("-") if word)


def looks_like_job_board_boilerplate(candidate: str) -> bool:
    return bool(_JOB_BOARD_BOILERPLATE.search(candidate))


def guess_company(*, source: str, source_url: str, page_title: str) -> str:
    """Melhor esforço pra extrair nome da empresa sem inventar nada. Usa a
    URL do LinkedIn (sinal forte) quando disponível; caso contrário cai
    pro título da página, descartando qualquer resultado que pareça o
    texto padrão do agregador em vez de um nome de empresa real. Retorna
    "" quando não há sinal confiável - o chamador deve pular a vaga
    nesse caso, nunca inventar um nome."""
    if source == "LinkedIn":
        from_url = guess_company_from_linkedin_url(source_url)
        if from_url:
            return from_url
    parts = [part.strip() for part in re.split(r"\s[-|–]\s", page_title) if part.strip()]
    candidates = [part for part in parts if part.lower() not in _KNOWN_JOB_PLATFORMS]
    candidate = candidates[-1] if candidates else ""
    if not candidate or looks_like_job_board_boilerplate(candidate):
        return ""
    return candidate


def job_idempotency_key(source: str, source_url: str) -> str:
    """Mesma granularidade da constraint unica (organization_id, source,
    source_url) de job_sources no Core - uma linha por ocorrencia real."""
    return f"{source}:{source_url}"


def build_job_record(*, source: str, source_url: str, company: str, title: str,
                      description: str, location: str, correlation_id: str) -> CoreSyncRecord:
    payload = {
        "source": source,
        "source_url": source_url,
        "company": company,
        "title": title,
        "description": description,
        "location": location or None,
    }
    return CoreSyncRecord(
        kind="JOB",
        payload=payload,
        idempotency_key=job_idempotency_key(source, source_url),
        correlation_id=correlation_id,
    )


def build_score_record(*, job_id: str, correlation_id: str) -> CoreSyncRecord:
    """POST /jobs/{id}/score não tem corpo - job_id só serve pra montar o
    caminho da rota (ver _endpoint_for/_body_for)."""
    return CoreSyncRecord(kind="SCORE", payload={"job_id": job_id},
                           idempotency_key=f"score:{job_id}", correlation_id=correlation_id)


def build_prepare_record(*, job_id: str, correlation_id: str) -> CoreSyncRecord:
    """POST /jobs/{id}/prepare também não tem corpo - mesma lógica do score."""
    return CoreSyncRecord(kind="PREPARE", payload={"job_id": job_id},
                           idempotency_key=f"prepare:{job_id}", correlation_id=correlation_id)


# Recomendações do Core (quality.py) que bloqueiam a preparação da
# candidatura - espelha exatamente o gate que POST /jobs/{id}/prepare já
# aplica no lado do servidor (score >= 75 e decision fora deste conjunto).
NOT_ELIGIBLE_RECOMMENDATIONS = {"BLOCK", "DISCARD"}
PREPARE_SCORE_THRESHOLD = 75


def is_eligible_for_prepare(total: int, recommendation: str) -> bool:
    return total >= PREPARE_SCORE_THRESHOLD and recommendation not in NOT_ELIGIBLE_RECOMMENDATIONS


# Vocabulário canônico único: os status locais do automation-host (o que
# roda de verdade) mapeiam pra sequência real de transições do Core
# (apps/api/src/quality.py::ALLOWED_TRANSITIONS) - nunca duas máquinas de
# estado independentes. BLOCKED/CLOSED não têm alvo direto a partir de
# PREPARING no schema real do Core (só existem como validation_status de
# vaga ou como transição pré-candidatura, não pós-prepare) - mapeados pra
# ERROR com o motivo real preservado no campo reason, em vez de inventar
# um estado novo no Core (isso exigiria migration, fora do escopo desta
# ponte). Status sem entrada aqui (INSPECTING, ANALYZED, ...) ainda não
# chegaram no estágio de candidatura de verdade - não têm transição.
LOCAL_STATUS_TO_CORE_TRANSITION = {
    "READY_FOR_REVIEW": "READY",
    "APPLIED": "CONFIRMED",
    "MANUAL_REQUIRED": "MANUAL_REQUIRED",
    "BLOCKED": "ERROR",
    "CLOSED": "ERROR",
    "FAILED": "ERROR",
}


def map_local_status_to_core_transition(local_status: str) -> str | None:
    return LOCAL_STATUS_TO_CORE_TRANSITION.get(local_status)


def build_transition_record(*, core_application_id: str, target_status: str, reason: str,
                             correlation_id: str) -> CoreSyncRecord:
    return CoreSyncRecord(
        kind="TRANSITION",
        payload={"application_id": core_application_id, "status": target_status, "reason": reason[:2000]},
        idempotency_key=f"transition:{core_application_id}:{target_status}",
        correlation_id=correlation_id,
    )


def backoff_seconds(attempts: int) -> int:
    index = min(max(attempts, 0), len(BACKOFF_SECONDS) - 1)
    return BACKOFF_SECONDS[index]


def is_due(record: CoreSyncRecord, now: datetime) -> bool:
    if not record.last_attempt_at:
        return True
    last = datetime.fromisoformat(record.last_attempt_at)
    return (now - last).total_seconds() >= backoff_seconds(record.attempts)


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    retryable: bool
    response: dict | None = None
    error: str | None = None


def _endpoint_for(record: CoreSyncRecord) -> tuple[str, str]:
    if record.kind == "JOB":
        return "POST", "/api/v1/jobs"
    if record.kind == "SCORE":
        return "POST", f"/api/v1/jobs/{record.payload['job_id']}/score"
    if record.kind == "PREPARE":
        return "POST", f"/api/v1/jobs/{record.payload['job_id']}/prepare"
    if record.kind == "TRANSITION":
        return "POST", f"/api/v1/applications/{record.payload['application_id']}/transition"
    raise ValueError(f"Tipo de sincronização desconhecido: {record.kind}")


def _body_for(record: CoreSyncRecord) -> dict | None:
    """SCORE e PREPARE não têm corpo no Core - job_id/application_id em
    payload só existem pra montar o caminho da rota (ver _endpoint_for).
    JOB manda o corpo completo; TRANSITION manda só status/reason (o
    Core aceita actor/automation_mode como opcionais com default)."""
    if record.kind == "JOB":
        return record.payload
    if record.kind == "TRANSITION":
        return {"status": record.payload["status"], "reason": record.payload.get("reason", "")}
    return None


def send_core_sync(api_url: str, admin_token: str, record: CoreSyncRecord, timeout: int = 20) -> SyncResult:
    if not admin_token:
        return SyncResult(ok=False, retryable=False, error="missing_admin_token")
    method, path = _endpoint_for(record)
    body = _body_for(record)
    request = Request(
        api_url.rstrip("/") + path,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None,
        headers={
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json",
            "X-Correlation-Id": record.correlation_id,
        },
        method=method,
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
            return SyncResult(ok=True, retryable=False, response=body)
    except HTTPError as exc:
        if exc.code == 409:
            # Estado/transicao ja aplicada no Core - nunca reprocessar como erro,
            # senao um retry legitimo criaria a aparencia de falha permanente.
            return SyncResult(ok=True, retryable=False, response={"already_applied": True})
        retryable = exc.code not in NON_RETRYABLE_STATUS
        return SyncResult(ok=False, retryable=retryable, error=f"HTTP {exc.code}")
    except (URLError, TimeoutError, OSError) as exc:
        return SyncResult(ok=False, retryable=True, error=type(exc).__name__)
