"""Job Canonical Identity (Fase 2, Prompt 9.1).

Causa raiz real, comprovada em producao (ver docs/continuous-improvement/
PILOT-FORENSICS.md e o relatorio do Prompt 9.1): `job_fingerprint`
(quality.py) hasheia tokens do `description` raspado - mas o "description"
do LinkedIn nao e so o texto da vaga, e o dump de texto da pagina inteira,
incluindo UI/sidebar volatil (contagem de candidaturas, "ha X dias", vagas
similares no rodape) que MUDA a cada nova raspagem da MESMA vaga real.
Confirmado com os 7 registros reais da vaga da Zeleno Meds: nenhum dos 7
`description` tem o mesmo tamanho (8378 a 8588 caracteres), logo nenhum dos
7 fingerprints bateu, e 1 vaga real virou 7 linhas em `jobs`.

A correcao certa (Secao 2 do Prompt 9.1): preferir um ID estavel do
provider, extraido DIRETAMENTE da URL - nunca do conteudo volatil da
pagina, nunca adivinhado. So cai para o fingerprint semantico existente
(quality.job_fingerprint, mantido 100% inalterado - e o fallback
conservador da Secao 5, nao um bug a corrigir) quando nenhum ID estavel
puder ser extraido.
"""

from __future__ import annotations

import re
from hashlib import sha256

from .quality import job_fingerprint, normalize

# Padroes reais confirmados por amostragem direta de producao (Prompt 9.1,
# Secao 1) - so os 3 providers que realmente existem hoje (Secao 4: "nao
# criar framework para ATS ainda inexistentes"). Cada padrao extrai
# somente um ID JA PRESENTE na URL - nunca deriva/adivinha nada.
_PROVIDER_ID_PATTERNS = {
    "linkedin": re.compile(r"/jobs/view/(\d+)"),
    "infojobs": re.compile(r"__(\d+)\.aspx"),
    "catho": re.compile(r"/vagas/[^/?#]+/(\d+)"),
}

PROVIDER_ID_METHOD = "PROVIDER_ID"
CONTENT_FINGERPRINT_METHOD = "CONTENT_FINGERPRINT"


def extract_provider_job_id(source: str | None, url: str | None) -> str | None:
    """So extrai um ID que ja esta embutido na URL real - nunca adivinha,
    nunca deriva de conteudo de pagina, nunca inventa para uma source
    desconhecida (Secao 4)."""
    if not source or not url:
        return None
    pattern = _PROVIDER_ID_PATTERNS.get(source.strip().lower())
    if not pattern:
        return None
    match = pattern.search(url)
    return match.group(1) if match else None


def canonical_job_fingerprint(*, company: str, title: str, location: str, description: str,
                              source: str | None = None, source_url: str | None = None,
                              canonical_url: str | None = None) -> tuple[str, str, str | None]:
    """Devolve (fingerprint, method, provider_job_id).

    Preferencia de evidencia (Secao 2): 1) provider job ID estavel extraido
    da URL (canonical_url OU source_url - qualquer raspagem real da MESMA
    vaga carrega o mesmo ID, imune a tracking params E a conteudo volatil
    de pagina) -> 2) fingerprint semantico de conteudo (quality.job_fingerprint,
    inalterado - fallback conservador quando a source nao tem ID extraivel).

    Nunca usa `company` no fingerprint baseado em provider ID: o proprio ID
    do provider ja e uma identidade suficiente e mais estavel que o nome de
    empresa resolvido (que pode mudar de forma minima entre resolucoes)."""
    provider_id = (extract_provider_job_id(source, canonical_url)
                   or extract_provider_job_id(source, source_url))
    if provider_id:
        material = f"{(source or '').strip().lower()}:{provider_id}"
        return sha256(material.encode()).hexdigest(), PROVIDER_ID_METHOD, provider_id
    return job_fingerprint(company, title, location, description), CONTENT_FINGERPRINT_METHOD, None


# ---------------------------------------------------------------------------
# Secao 16 - DUPLICATE CONFIDENCE (para reconciliacao de dados historicos)
# ---------------------------------------------------------------------------

DUPLICATE_CONFIDENCE_LEVELS = (
    "EXACT_PROVIDER_ID", "EXACT_CANONICAL_URL", "HIGH_CONFIDENCE_SEMANTIC", "AMBIGUOUS", "DISTINCT",
)

# Somente estes dois niveis podem ser reconciliados automaticamente
# (Secao 16: "Somente niveis seguros podem ser reconciliados
# automaticamente"). HIGH_CONFIDENCE_SEMANTIC e deliberadamente deixado de
# fora do merge automatico nesta entrega - exige match de company+title+
# location simultaneamente, o que ja e conservador, mas a Secao 16 pede
# "somente niveis seguros" e o unico nivel 100% livre de qualquer
# ambiguidade semantica e o baseado em identidade explicita (provider ID /
# URL canonica) - reconciliar por semantica fica para uma decisao humana
# explicita, nunca automatica.
AUTO_MERGE_CONFIDENCE_LEVELS = {"EXACT_PROVIDER_ID", "EXACT_CANONICAL_URL"}


def classify_duplicate_confidence(job_a: dict, job_b: dict) -> str:
    """Classifica dois Jobs (mesma organization_id, ja garantido pelo
    caller) quanto a confianca de serem a MESMA vaga real. Nunca compara
    apenas titulo - Secao 5: "Analista de Dados" na mesma empresa em duas
    cidades pode ser duas vagas reais."""
    if job_a.get("id") == job_b.get("id"):
        return "DISTINCT"

    source_a = str(job_a.get("source") or "").strip().lower()
    source_b = str(job_b.get("source") or "").strip().lower()
    if source_a and source_a == source_b:
        id_a = (extract_provider_job_id(source_a, job_a.get("canonical_url"))
                or extract_provider_job_id(source_a, job_a.get("source_url")))
        id_b = (extract_provider_job_id(source_b, job_b.get("canonical_url"))
                or extract_provider_job_id(source_b, job_b.get("source_url")))
        if id_a and id_b:
            return "EXACT_PROVIDER_ID" if id_a == id_b else "DISTINCT"

    url_a = job_a.get("canonical_url") or job_a.get("source_url")
    url_b = job_b.get("canonical_url") or job_b.get("source_url")
    if url_a and url_b and url_a.split("?", 1)[0] == url_b.split("?", 1)[0]:
        return "EXACT_CANONICAL_URL"

    company_a, company_b = job_a.get("company_id"), job_b.get("company_id")
    title_a, title_b = normalize(job_a.get("title") or ""), normalize(job_b.get("title") or "")
    location_a, location_b = normalize(job_a.get("location") or ""), normalize(job_b.get("location") or "")
    if company_a and company_a == company_b and title_a and title_a == title_b:
        if location_a == location_b:
            return "HIGH_CONFIDENCE_SEMANTIC"
        return "AMBIGUOUS"

    return "DISTINCT"


def is_auto_mergeable(confidence: str) -> bool:
    return confidence in AUTO_MERGE_CONFIDENCE_LEVELS


def group_duplicate_jobs(jobs: list[dict]) -> dict:
    """Agrupamento puro (sem I/O) usado pela reconciliacao historica
    (POST /jobs/reconcile-duplicates). Cada job dict precisa de: id,
    source, source_url, canonical_url, company_id, title, location,
    discovered_at.

    Devolve {"auto_mergeable": [...], "semantic_only": [...]} - cada grupo
    e {"confidence", "canonical_job_id", "duplicate_job_ids"}. O canonico
    de cada grupo e sempre o mais antigo por discovered_at (deterministico,
    mais proximo da observacao real original). Grupos EXACT_PROVIDER_ID/
    EXACT_CANONICAL_URL sao auto-mergeaveis (Secao 16); HIGH_CONFIDENCE_
    SEMANTIC (mesma company_id + titulo normalizado + localizacao
    normalizada, Secao 5 - nunca so por titulo) so e reportado, nunca
    executado automaticamente aqui."""
    provider_groups: dict[tuple, list[dict]] = {}
    url_groups: dict[str, list[dict]] = {}
    for job in jobs:
        source = str(job.get("source") or "").strip().lower()
        provider_id = (extract_provider_job_id(source, job.get("canonical_url"))
                       or extract_provider_job_id(source, job.get("source_url")))
        if provider_id:
            provider_groups.setdefault((source, provider_id), []).append(job)
        url = job.get("canonical_url") or job.get("source_url")
        if url:
            url_groups.setdefault(url.split("?", 1)[0], []).append(job)

    auto_mergeable: list[dict] = []
    grouped_ids: set = set()

    for members in provider_groups.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda item: item["discovered_at"])
        auto_mergeable.append({"confidence": "EXACT_PROVIDER_ID", "canonical_job_id": ordered[0]["id"],
                                "duplicate_job_ids": [item["id"] for item in ordered[1:]]})
        grouped_ids.update(item["id"] for item in ordered)

    for members in url_groups.values():
        remaining = [item for item in members if item["id"] not in grouped_ids]
        if len(remaining) < 2:
            continue
        ordered = sorted(remaining, key=lambda item: item["discovered_at"])
        auto_mergeable.append({"confidence": "EXACT_CANONICAL_URL", "canonical_job_id": ordered[0]["id"],
                                "duplicate_job_ids": [item["id"] for item in ordered[1:]]})
        grouped_ids.update(item["id"] for item in ordered)

    semantic_groups: dict[tuple, list[dict]] = {}
    for job in jobs:
        if job["id"] in grouped_ids:
            continue
        company_id = job.get("company_id")
        title = normalize(job.get("title") or "")
        location = normalize(job.get("location") or "")
        if not company_id or not title:
            continue
        semantic_groups.setdefault((company_id, title, location), []).append(job)

    semantic_only: list[dict] = []
    for members in semantic_groups.values():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=lambda item: item["discovered_at"])
        semantic_only.append({"confidence": "HIGH_CONFIDENCE_SEMANTIC", "canonical_job_id": ordered[0]["id"],
                               "duplicate_job_ids": [item["id"] for item in ordered[1:]]})

    return {"auto_mergeable": auto_mergeable, "semantic_only": semantic_only}
