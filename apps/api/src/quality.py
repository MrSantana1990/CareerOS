"""Deterministic core-quality rules; no network or database side effects."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from hashlib import sha256
import re
import unicodedata
from urllib.parse import urlparse


# SCORE != ELIGIBILITY: piso definido explicitamente pelo candidato - uma
# vaga abaixo disso e BLOCK independente de quao alto o score tecnico for.
MINIMUM_ACCEPTABLE_SALARY_BRL = 4000


def normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.lower()).split())


def job_fingerprint(company: str, title: str, location: str, description: str) -> str:
    meaningful = sorted({token for token in normalize(description).split() if len(token) >= 4})[:80]
    material = "|".join((normalize(company), normalize(title), normalize(location), " ".join(meaningful)))
    return sha256(material.encode()).hexdigest()


ALLOWED_TRANSITIONS = {
    "DISCOVERED": {"VALIDATING", "DISCARDED", "ERROR"},
    "VALIDATING": {"VALIDATED", "CLOSED", "MANUAL_REQUIRED", "ERROR"},
    "VALIDATED": {"QUALIFIED", "DISCARDED", "WAITING_DECISION"},
    "QUALIFIED": {"WAITING_DECISION", "PREPARING", "DISCARDED"},
    "WAITING_DECISION": {"PREPARING", "DISCARDED"},
    "PREPARING": {"READY", "MANUAL_REQUIRED", "ERROR"},
    "READY": {"SUBMITTING", "DISCARDED"},
    "SUBMITTING": {"SENT", "CONFIRMED", "MANUAL_REQUIRED", "ERROR"},
    "SENT": {"CONFIRMED", "ERROR"},
    "CONFIRMED": {"RECRUITER_RESPONSE", "REJECTED", "CLOSED"},
    "RECRUITER_RESPONSE": {"INTERVIEW", "REJECTED", "CLOSED"},
    "INTERVIEW": {"TECHNICAL_TEST", "FINAL_STAGE", "OFFER", "REJECTED"},
    "TECHNICAL_TEST": {"FINAL_STAGE", "OFFER", "REJECTED"},
    "FINAL_STAGE": {"OFFER", "REJECTED"},
}


def transition_allowed(current: str, target: str) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


@dataclass(frozen=True)
class ScoreResult:
    total: int
    recommendation: str
    dimensions: dict[str, int]
    strengths: list[str]
    gaps: list[str]
    risks: list[str]
    blocking_rules: list[str]

    def as_dict(self) -> dict:
        return asdict(self)


def _overlap(required: list[str], verified: list[str], weight: int) -> tuple[int, list[str], list[str]]:
    wanted = {normalize(item) for item in required if normalize(item)}
    known = {normalize(item) for item in verified if normalize(item)}
    if not wanted:
        return weight, [], []
    matched = wanted & known
    score = round(weight * len(matched) / len(wanted))
    return score, sorted(matched), sorted(wanted - known)


# ---------------------------------------------------------------------------
# Fase 2, Prompt 10 - STRUCTURED EXTRACTION INTELLIGENCE
#
# score_job() nunca lia job.get("structured_extraction") - so as colunas
# planas legadas (required_skills/seniority/work_model/language_requirements/
# salary_min), quase sempre vazias para vagas descobertas pelo Prompt 3/4
# (achado real do Pilot: 96 Jobs reais -> so 3 valores de score distintos,
# porque toda vaga sem coluna plana cai nos MESMOS valores fixos default
# abaixo). Os resolvers abaixo usam structured_extraction como FALLBACK
# (nunca substituindo um dado plano ja confiavel) - e so quando a propria
# evidencia nao parece contaminada (Secao 3: TRUSTED/USABLE_WITH_CAUTION/
# LOW_CONFIDENCE/UNKNOWN).
# ---------------------------------------------------------------------------

# Familias transferiveis (Fase 2, Prompt 4) - movidas para ca (from
# opportunity_brain.py, que agora importa daqui) para servirem tambem como
# vocabulario de tecnologias RECONHECIDAS por score_job, sem duplicar a
# lista em dois modulos (Secao 7: "reusar familias ja definidas"). Kubernetes
# e Docker tem familia vazia de proposito - nao existe aresta de
# transferencia Docker->Kubernetes (Secao 6/7, exemplo literal do usuario).
SKILL_FAMILIES: dict[str, set[str]] = {
    "sql server": {"oracle", "postgresql", "mysql", "sql"},
    "oracle": {"sql server", "postgresql", "mysql", "sql"},
    "postgresql": {"sql server", "oracle", "mysql", "sql"},
    "mysql": {"sql server", "oracle", "postgresql", "sql"},
    "aws": {"azure", "gcp", "google cloud"},
    "azure": {"aws", "gcp", "google cloud"},
    "gcp": {"aws", "azure", "google cloud"},
    "google cloud": {"aws", "azure", "gcp"},
    "kubernetes": set(),
    "docker": set(),
    # Prompt 10, Secao 7 - familias adicionais pedidas explicitamente,
    # conservadoras (so tecnologias realmente correlatas/intercambiaveis):
    "prometheus": {"grafana", "datadog", "new relic"},
    "grafana": {"prometheus", "datadog", "new relic"},
    "datadog": {"prometheus", "grafana", "new relic"},
    "new relic": {"prometheus", "grafana", "datadog"},
    "rest api": {"graphql", "soap"},
    "graphql": {"rest api"},
    "soap": {"rest api"},
    "power bi": {"tableau", "looker", "qlik"},
    "tableau": {"power bi", "looker", "qlik"},
    "looker": {"power bi", "tableau", "qlik"},
    "qlik": {"power bi", "tableau", "looker"},
}

# Marcadores reais de contaminacao de UI/sidebar do LinkedIn (Secao 1/3 -
# achado real de producao: o caso Zeleno Meds tinha work_model="HYBRID" e
# location="Campinas" extraidos de uma vaga de OUTRA empresa - "Fitcard" -
# listada na barra lateral "vagas similares", nao do conteudo real da
# vaga). Nunca inferido - so marca como NAO CONFIAVEL quando o proprio
# evidence_snippet contem chrome de UI conhecido do LinkedIn.
_LINKEDIN_UI_NOISE_MARKERS = (
    "exibir tudo", "ex-alunos da instituicao", "candidatura simplificada",
    "veja como voce se compara", "ative um alerta", "reative premium",
    "status da candidatura", "candidatura enviada", "ver curriculo",
)


def is_structured_field_trustworthy(field: dict | None) -> bool:
    """Secao 3 - TRUSTED/USABLE_WITH_CAUTION/LOW_CONFIDENCE/UNKNOWN,
    simplificado para um booleano de uso pratico aqui: um campo com
    evidence_snippet reconhecivel como chrome de UI (nao o conteudo real
    da vaga) nunca e tratado como fato, mesmo com confidence alta."""
    if not field:
        return False
    snippet = normalize(str(field.get("evidence_snippet") or ""))
    return not any(marker in snippet for marker in _LINKEDIN_UI_NOISE_MARKERS)


_SENIORITY_TITLE_MARKERS = (
    ("especialista", "SPECIALIST"), ("specialist", "SPECIALIST"),
    ("senior", "SENIOR"), ("sênior", "SENIOR"), ("sr.", "SENIOR"),
    ("pleno", "PLENO"), ("pl.", "PLENO"),
    ("junior", "JUNIOR"), ("júnior", "JUNIOR"), ("jr.", "JUNIOR"),
    ("lead", "LEAD"), ("líder técnico", "LEAD"),
    ("manager", "MANAGER"), ("gerente", "MANAGER"),
)


def extract_seniority_from_title(title: str | None) -> str | None:
    """Secao 9 - extrai seniority so quando o proprio titulo da vaga
    literalmente contem a palavra (nunca infere pela remuneracao/trajetoria
    do candidato aqui - isso e Career Fit, uma comparacao separada)."""
    text = normalize(str(title or ""))
    if not text:
        return None
    for marker, label in _SENIORITY_TITLE_MARKERS:
        if normalize(marker) in text:
            return label
    return None


def _requirement_sentences(structured_extraction: dict | None) -> list[str]:
    extraction = structured_extraction or {}
    sentences = list((extraction.get("mandatory_requirements") or {}).get("value") or [])
    sentences += list((extraction.get("preferred_requirements") or {}).get("value") or [])
    return [str(item) for item in sentences]


def resolve_required_technology_tokens(structured_extraction: dict | None) -> list[str]:
    """Fallback do dimension 'technology' quando job.required_skills (coluna
    plana) esta vazio (Secao 2/4). Reconhece SOMENTE tokens do vocabulario
    de SKILL_FAMILIES literalmente mencionados nas sentencas reais de
    mandatory/preferred_requirements - nunca promove um requisito que a
    vaga nao menciona, nunca infere tecnologia a partir do titulo/familia
    do job."""
    text = normalize(" ".join(_requirement_sentences(structured_extraction)))
    if not text:
        return []
    return [token for token in SKILL_FAMILIES if token in text]


def resolve_structured_work_model(structured_extraction: dict | None) -> str | None:
    """Fallback quando job.work_model (coluna plana) esta vazio (Secao 11).
    Nunca usa um campo contaminado por UI/sidebar (Secao 3).

    Fase 2, Prompt 12, Secao 10 (field-level merge por precedencia):
    'work_model_official' (escrito so por POST /jobs/{id}/enrich-official,
    apos correlacao EXACT/HIGH_CONFIDENCE com a vaga especifica numa fonte
    oficial - OFFICIAL_JOB_PAGE) tem prioridade sobre o 'work_model' comum
    (TRUSTED_STRUCTURED_EXTRACTION, extraido no scrape original) - nunca o
    contrario, e nunca overwrite bruto: as duas chaves continuam
    persistidas lado a lado, so a leitura prioriza a oficial."""
    extraction = structured_extraction or {}
    official_field = extraction.get("work_model_official")
    if is_structured_field_trustworthy(official_field):
        official_value = (official_field or {}).get("value") or {}
        official_work_model = official_value.get("work_model")
        if official_work_model and str(official_work_model).upper() != "UNKNOWN":
            return str(official_work_model)
    field = extraction.get("work_model")
    if not is_structured_field_trustworthy(field):
        return None
    value = (field or {}).get("value") or {}
    work_model = value.get("work_model")
    return str(work_model) if work_model and str(work_model).upper() != "UNKNOWN" else None


def resolve_structured_salary(structured_extraction: dict | None) -> float | None:
    """Fallback quando job.salary_min (coluna plana) esta ausente (Secao
    10). Nunca inventa conversao anual/mensal sem unidade clara - so aceita
    o valor minimo ja resolvido pela extracao (hard_blocks.extract_salary_brl,
    reusado por structured_fields.py, nunca reimplementado aqui)."""
    field = (structured_extraction or {}).get("salary")
    if not field or not is_structured_field_trustworthy(field):
        return None
    value = (field or {}).get("value") or {}
    salary_min = value.get("salary_min") or value.get("min")
    try:
        return float(salary_min) if salary_min else None
    except (TypeError, ValueError):
        return None


def resolve_structured_language_requirements(structured_extraction: dict | None) -> list[dict]:
    """Fallback quando job.language_requirements (coluna plana, lista de
    {language,required,level}) esta vazia (Secao 8). structured_extraction
    so guarda UM idioma explicito por vaga (nunca infere pela lingua da
    propria pagina) - mapeado para o mesmo formato piano para reusar a
    logica de risco/bloqueio ja existente em score_job, sem duplicar."""
    field = (structured_extraction or {}).get("language_requirements")
    if not field or not is_structured_field_trustworthy(field):
        return []
    value = (field or {}).get("value") or {}
    language = value.get("language")
    level = value.get("level")
    if not language or not level:
        return []
    return [{"language": language, "level": level, "required": True}]


def match_radars(job: dict, radars: list[dict]) -> list[str]:
    """Retorna os códigos dos radares HABILITADOS cujos roles/keywords têm
    sobreposição com o título/descrição da vaga - primeira ligação real entre
    os radares (Bloco B item 10, antes só CRUD sem nenhum efeito) e o motor
    de score. Radar desligado nunca aparece aqui, mesmo que o texto combine -
    combinar continua sendo só informativo até o radar ser ativado."""
    haystack = normalize(f"{job.get('title', '')} {job.get('description', '')}")
    matches: list[str] = []
    for radar in radars:
        if not radar.get("enabled"):
            continue
        terms = list(radar.get("roles") or []) + list(radar.get("keywords") or [])
        if any(normalize(str(term)) and normalize(str(term)) in haystack for term in terms):
            matches.append(str(radar["code"]))
    return matches


def score_job(job: dict, profile: dict, enabled_rules: set[str] | None = None) -> ScoreResult:
    enabled = enabled_rules or {"GUPY_BLOCK", "SPANISH_FLUENT_BLOCK", "ENGLISH_C1_REVIEW", "SUPPORT_N1_MINIMUM", "MINIMUM_SALARY_BLOCK"}
    text = normalize(" ".join(str(job.get(key) or "") for key in ("title", "description", "location")))
    source = normalize(str(job.get("source") or ""))
    domain = normalize(urlparse(str(job.get("canonical_url") or job.get("source_url") or "")).netloc)
    structured_extraction = job.get("structured_extraction")
    languages = job.get("language_requirements") or resolve_structured_language_requirements(structured_extraction)
    blocks: list[str] = []
    risks: list[str] = []
    if "GUPY_BLOCK" in enabled and (source == "gupy" or "gupy io" in domain):
        blocks.append("GUPY_BLOCK")
    if "SPANISH_FLUENT_BLOCK" in enabled and any(normalize(str(item.get("language"))) in {"es", "spanish", "espanhol"} and item.get("required") and normalize(str(item.get("level"))) in {"fluent", "fluente", "c1", "c2"} for item in languages if isinstance(item, dict)):
        blocks.append("SPANISH_FLUENT_BLOCK")
    if "ENGLISH_C1_REVIEW" in enabled and any(normalize(str(item.get("language"))) in {"en", "english", "ingles"} and item.get("required") and normalize(str(item.get("level"))) in {"fluent", "fluente", "c1", "c2"} for item in languages if isinstance(item, dict)):
        risks.append("ENGLISH_C1_REVIEW")
    if "RELOCATION_REQUIRED" in enabled and "relocation" in text and "required" in text:
        blocks.append("RELOCATION_REQUIRED")

    # Fase 2, Prompt 10, Secao 2/4: required_skills (coluna plana) so cai
    # para structured_extraction quando esta genuinamente vazia - nunca
    # substitui um dado plano ja confiavel. known_skills soma verified +
    # evidence-backed (Secao 5) - Score V2 e um sinal numerico grosseiro; a
    # distincao fina de confianca por skill continua no Brain
    # (find_skill_evidence/_skill_confidence), nao duplicada aqui.
    required_skills = job.get("required_skills") or resolve_required_technology_tokens(structured_extraction)
    known_skills = list(profile.get("verified_skills") or []) + list(profile.get("evidence_backed_skills") or [])
    technical, strengths, gaps = _overlap(required_skills, known_skills, 30)
    target_roles = [normalize(item) for item in profile.get("target_roles") or []]
    title = normalize(str(job.get("title") or ""))
    experience = 20 if any(role and (role in title or title in role) for role in target_roles) else 8
    seniority = normalize(str(job.get("seniority") or "") or extract_seniority_from_title(job.get("title")) or "")
    seniority_score = 10 if seniority in {"senior", "specialist", "especialista"} else 7 if seniority else 5
    work_model = normalize(str(job.get("work_model") or "") or resolve_structured_work_model(structured_extraction) or "")
    desired_models = {normalize(item) for item in profile.get("work_models") or []}
    work_score = 10 if work_model in desired_models else 6 if not work_model else 0
    salary_min = float(job.get("salary_min") or resolve_structured_salary(structured_extraction) or 0)
    if "SUPPORT_N1_MINIMUM" in enabled and normalize(str(job.get("family") or "")) == "support" and seniority in {"n1", "junior"} and salary_min and salary_min < 4000:
        blocks.append("SUPPORT_N1_MINIMUM")
    if "MINIMUM_SALARY_BLOCK" in enabled and salary_min and salary_min < MINIMUM_ACCEPTABLE_SALARY_BRL:
        blocks.append("MINIMUM_SALARY_BLOCK")
    expected = float(profile.get("salary_expectation_numeric") or 0)
    compensation = 10 if not salary_min or not expected or salary_min >= expected else max(0, round(10 * salary_min / expected))
    location = normalize(str(job.get("location") or ""))
    city = normalize(str(profile.get("city") or ""))
    location_score = 5 if work_model == "remote" or (city and city in location) else 2 if not location else 0
    language_score = 3 if risks else 5
    channel = normalize(str(job.get("application_channel") or ""))
    channel_score = 5 if channel in {"email", "ats api", "greenhouse", "lever", "ashby"} else 3
    freshness = max(0, min(5, int(job.get("freshness_score", 5))))
    dimensions = {"technology": technical, "experience": experience, "seniority": seniority_score,
                  "work_model": work_score, "compensation": compensation, "location": location_score,
                  "language": language_score, "channel": channel_score, "freshness": freshness}
    total = min(100, sum(dimensions.values()))
    if blocks:
        recommendation = "BLOCK"
    elif risks or 60 <= total < 75:
        recommendation = "REVIEW"
    elif total >= 75:
        recommendation = "APPLY_HIGH" if total >= 80 else "APPLY"
    else:
        recommendation = "DISCARD"
    return ScoreResult(total, recommendation, dimensions, strengths, gaps, risks, blocks)
