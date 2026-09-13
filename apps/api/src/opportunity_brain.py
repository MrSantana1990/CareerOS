"""Opportunity Brain (Fase 2, Prompt 4) - camada de RACIOCINIO.

PERCEPTION (Prompt 3) diz "o que encontrei e o que a fonte diz". Este
modulo diz "o que isso significa para o candidato". ACTION ENGINE
(Prompt 5) dira "como agir" - nada aqui envia candidatura, e-mail ou
ativa auto-submit. ACTIONABLE == "aprovado para possivel acao", nunca
"acao executada".

Pure, deterministico, sem efeito colateral (mesmo padrao de quality.py e
market_memory.py): recebe dicts ja carregados pelo caller (rotas em
career.py), nunca abre sessao de banco, nunca depende de rede ou de
"lembranca" do agente - todo dado vem de storage/evidence persistidos
(candidate_profiles, skills, companies, signals, jobs.structured_extraction).
Ausencia de dado necessario = UNKNOWN, nunca inferido.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re

from .quality import ScoreResult, normalize

BRAIN_VERSION = "1.0"

DECISION_STATES = ("DROP", "BLOCK", "WATCH", "RECHECK", "PREPARE", "ACTIONABLE", "HUMAN_REQUIRED")


@dataclass
class BrainDecision:
    decision: str
    eligibility: str
    fit_score: int | None
    confidence: int
    reasons: list[str] = field(default_factory=list)
    hard_blocks: list[str] = field(default_factory=list)
    transferable_matches: list[dict] = field(default_factory=list)
    preferred_gaps: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    brain_version: str = BRAIN_VERSION

    def as_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Secao 1 - SIGNAL QUALITY GATE
# ---------------------------------------------------------------------------

SIGNAL_QUALITY_STATES = ("TRUSTED_RESOLVED", "TRUSTED_UNRESOLVED", "LOW_CONFIDENCE",
                          "NOISY", "ALREADY_PROMOTED", "INSUFFICIENT_EVIDENCE")

# Prompt 3 produziu 154 Signals com 139 sem Company resolvida - estes tipos
# sozinhos ja justificam considerar o Signal "interessante" mesmo sem
# empresa resolvida ainda (TRUSTED_UNRESOLVED); um OTHER_VERIFIED_SIGNAL sem
# empresa e "artigo de mercado generico" (Secao 20) - ruido, nao promovivel.
_PROMOTABLE_SIGNAL_TYPES = {
    "EXPANSION", "INVESTMENT", "NEW_OFFICE", "NEW_OPERATION", "NEW_PROJECT",
    "HIRING_ANNOUNCEMENT", "RECRUITER_SIGNAL", "CAREERS_CHANGE", "JOB_DISCOVERED",
}
LOW_CONFIDENCE_THRESHOLD = 50


def classify_signal_quality(signal: dict) -> str:
    """Classifica um Signal ANTES de qualquer promocao a Opportunity (Secao
    1) - nao transforma cada Signal em Opportunity so para aumentar KPI."""
    if signal.get("status") == "PROMOTED":
        return "ALREADY_PROMOTED"
    if not signal.get("headline") or not signal.get("source_url") or not signal.get("evidence"):
        return "INSUFFICIENT_EVIDENCE"
    confidence = signal.get("confidence")
    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        return "LOW_CONFIDENCE"
    if signal.get("company_id"):
        return "TRUSTED_RESOLVED"
    if signal.get("type") in _PROMOTABLE_SIGNAL_TYPES:
        return "TRUSTED_UNRESOLVED"
    return "NOISY"


# ---------------------------------------------------------------------------
# Secao 2/3 - COMPANY RESOLUTION QUALITY / COMPANY RELEVANCE
# ---------------------------------------------------------------------------

COMPANY_RELEVANCE_LEVELS = ("HIGH", "MEDIUM", "LOW", "UNKNOWN")

# Prompt 4 auditou `companies`: hoje NAO existe industry/location detalhada
# (so name/domain/careers_url/ats_type/official_recruiting_email/
# talent_pool_url/br_presence/notes) - avaliar relevancia so com o que e
# real, nunca inventar setor/localizacao a partir do nome da empresa.
_HIGH_VALUE_SIGNAL_TYPES = {"EXPANSION", "INVESTMENT", "NEW_OFFICE", "HIRING_ANNOUNCEMENT"}

# Padrao real observado no Prompt 3 (ex.: "Qlik View/Sense em Recife,- PE") -
# nome herdado do pipeline tradicional (titulo/localizacao viraram nome de
# empresa por engano), nao uma empresa de verdade. So para RELATORIO
# (Secao 33) - nunca usado para deletar/mesclar automaticamente.
_MALFORMED_COMPANY_NAME = re.compile(r"\bem\s+[A-ZÀ-Ý][\wÀ-ÿ\s./]*,-\s*[A-Z]{2}$")


def assess_company_relevance(company: dict, related_signals: list[dict] | None = None,
                              has_prior_interaction: bool = False) -> dict:
    """HIGH/MEDIUM/LOW/UNKNOWN (Secao 3). Nunca bloqueia por setor nao-tech:
    a ausencia de dado (industry/location) e UNKNOWN, nunca LOW. LOW so
    ocorre com evidencia NEGATIVA real (br_presence=False)."""
    signals = related_signals or []
    high_value = [item for item in signals if item.get("type") in _HIGH_VALUE_SIGNAL_TYPES]
    if has_prior_interaction:
        return {"relevance": "HIGH", "reasons": ["historical_interaction"]}
    if high_value:
        return {"relevance": "HIGH", "reasons": [f"{len(high_value)}_high_value_signal(s)"]}
    if company.get("br_presence") is False:
        return {"relevance": "LOW", "reasons": ["no_br_presence_confirmed"]}
    reasons: list[str] = []
    if company.get("br_presence") is True:
        reasons.append("br_presence_confirmed")
    if company.get("careers_url") or company.get("ats_type"):
        reasons.append("active_hiring_channel_known")
    if signals:
        reasons.append(f"{len(signals)}_signal(s)_observed")
    if reasons:
        return {"relevance": "MEDIUM", "reasons": reasons}
    return {"relevance": "UNKNOWN", "reasons": ["no_evidence_available"]}


def opportunity_type_for_signal(signal_type: str) -> str:
    """Secao 20: hiring announcement -> FUTURE_HIRING; demais tipos
    promotiveis viram WATCH_ONLY (nunca SPONTANEOUS_APPLICATION so a
    partir de um Signal - isso exigiria uma decisao de Job real)."""
    return "FUTURE_HIRING" if signal_type == "HIRING_ANNOUNCEMENT" else "WATCH_ONLY"


def audit_company_data_quality(companies: list[dict]) -> dict:
    """Secao 33 - so relatorio, nunca mass delete/merge."""
    total = len(companies)
    suspicious = [c for c in companies if _MALFORMED_COMPANY_NAME.search(str(c.get("name") or ""))]
    return {
        "companies_total": total,
        "well_formed_count": total - len(suspicious),
        "suspicious_count": len(suspicious),
        "suspicious_names": [c.get("name") for c in suspicious][:20],
    }


# ---------------------------------------------------------------------------
# Secao 5/6/9 - REQUIREMENT CLASSIFICATION
# ---------------------------------------------------------------------------

REQUIREMENT_DOMAINS = ("CORE_REQUIREMENT", "CONTEXTUAL_REQUIREMENT", "UNCERTAIN_REQUIREMENT")

# Achado real do Prompt 3 (CI&T): "your presence in the city offices will be
# mandatory" foi capturado como mandatory requirement pelo marker-word
# "mandatory", mas e politica de trabalho, nao skill. Aqui o Brain
# reclassifica por DOMINIO - a extracao (Prompt 3) continua capturando o
# texto bruto, o Brain e quem decide o que aquilo significa.
_POLICY_MARKERS = re.compile(
    r"presence in the (city )?office|comparecimento|frequ[eê]ncia de trabalho|"
    r"frequency policy|attendance polic|dias? (presencial|no escrit[oó]rio)|"
    r"working from the office|in-?office presence|mudan[çc]a de cidade",
    re.IGNORECASE,
)
_SKILL_MARKERS = re.compile(
    r"experience with|experi[eê]ncia (com|em)|knowledge (of|in)|conhecimento em|"
    r"proficiency in|anos? de experi[eê]ncia|years? of experience|"
    r"certifica[çc][aã]o|certification|\bdegree\b|\bdiploma\b|solid experience",
    re.IGNORECASE,
)


def classify_requirement_domain(evidence_snippet: str) -> str:
    text = evidence_snippet or ""
    is_policy = bool(_POLICY_MARKERS.search(text))
    is_skill = bool(_SKILL_MARKERS.search(text))
    if is_policy and not is_skill:
        return "CONTEXTUAL_REQUIREMENT"
    if is_skill:
        return "CORE_REQUIREMENT"
    return "UNCERTAIN_REQUIREMENT"


# ---------------------------------------------------------------------------
# Secao 7 - TRANSFERABLE SKILL MODEL
# ---------------------------------------------------------------------------

# Familias deterministicas e auditaveis - transferencia aumenta o fit, nunca
# fabrica a habilidade ausente. Kubernetes tem familia vazia de proposito:
# "Docker only" NAO significa "has Kubernetes" (Secao 7, exemplo literal do
# usuario) - nao existe aresta de transferencia Docker->Kubernetes aqui.
_SKILL_FAMILIES: dict[str, set[str]] = {
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
}


def _skill_confidence(skill_row: dict) -> int:
    return 90 if skill_row.get("verified") else 55


def find_skill_evidence(requirement_text: str, candidate_skills: list[dict]) -> dict | None:
    """Retorna evidencia REAL (direta ou transferivel) para um requirement,
    ou None se nao ha nenhuma - nunca fabrica a habilidade ausente."""
    text_norm = normalize(requirement_text)
    by_name = {normalize(str(item.get("name"))): item for item in candidate_skills if item.get("name")}
    for name_norm, skill_row in by_name.items():
        if name_norm and name_norm in text_norm:
            return {"match_type": "direct", "skill": skill_row["name"],
                    "confidence": _skill_confidence(skill_row)}
    for canonical, family in _SKILL_FAMILIES.items():
        if canonical in text_norm:
            for member in family:
                if member in by_name:
                    skill_row = by_name[member]
                    return {"match_type": "transferable", "skill": skill_row["name"],
                            "requirement_technology": canonical,
                            "confidence": max(30, _skill_confidence(skill_row) - 30)}
    return None


def evaluate_requirements(structured_extraction: dict | None, candidate_skills: list[dict]) -> dict:
    """Consome mandatory_requirements/preferred_requirements do
    structured_extraction (Prompt 3) e produz a reclassificacao/avaliacao
    (Secoes 5-9). Cada CORE_REQUIREMENT_MISSING guarda requirement,
    candidate_evidence, decision, confidence e source_evidence - nunca so
    uma string de motivo (Secao 6)."""
    extraction = structured_extraction or {}
    mandatory = extraction.get("mandatory_requirements") or {}
    preferred = extraction.get("preferred_requirements") or {}
    source_url = mandatory.get("source_url") or preferred.get("source_url")

    core_missing: list[dict] = []
    transferable_matches: list[dict] = []
    contextual: list[str] = []
    uncertain: list[str] = []
    preferred_gaps: list[str] = []

    for item in mandatory.get("value") or []:
        domain = classify_requirement_domain(item)
        if domain == "CONTEXTUAL_REQUIREMENT":
            contextual.append(item)
            continue
        if domain == "UNCERTAIN_REQUIREMENT":
            uncertain.append(item)
            continue
        evidence = find_skill_evidence(item, candidate_skills)
        if evidence is None:
            core_missing.append({"requirement": item, "candidate_evidence": None,
                                  "decision": "CORE_REQUIREMENT_MISSING", "confidence": 70,
                                  "source_evidence": source_url})
        elif evidence["match_type"] == "transferable":
            transferable_matches.append({"requirement": item, **evidence})

    for item in preferred.get("value") or []:
        if find_skill_evidence(item, candidate_skills) is None:
            preferred_gaps.append(item)

    return {"core_missing": core_missing, "transferable_matches": transferable_matches,
            "contextual_requirements": contextual, "uncertain_requirements": uncertain,
            "preferred_gaps": preferred_gaps}


# ---------------------------------------------------------------------------
# Secao 10 - LANGUAGE LOGIC
# ---------------------------------------------------------------------------

_FLUENT_LEVELS = {"fluente", "fluent", "nativo", "native", "avançado", "avancado", "advanced", "c1", "c2"}


def evaluate_language_gap(structured_extraction: dict | None, candidate_language_levels: dict | None) -> dict:
    """PAGE_LANGUAGE != JOB_WORKING_LANGUAGE != EXPLICIT_REQUIRED_LANGUAGE.
    Descricao em ingles nao gera gap (structured_fields.py ja nunca infere
    isso - extract_language_requirements so retorna algo com requisito
    EXPLICITO). Nivel do candidato so vem de candidate_profiles.language_levels
    persistido; ausente = UNKNOWN, nunca inferido (Secao 4/34)."""
    lang_field = (structured_extraction or {}).get("language_requirements")
    if not lang_field:
        return {"status": "NO_EXPLICIT_REQUIREMENT"}
    required = lang_field.get("value") or {}
    language = str(required.get("language") or "").lower()
    required_level = str(required.get("level") or "").lower()
    is_demanding = required_level in _FLUENT_LEVELS
    candidate_level = None
    for key, value in (candidate_language_levels or {}).items():
        if language and (normalize(str(key)) in normalize(language) or normalize(language) in normalize(str(key))):
            candidate_level = value
            break
    if candidate_level is None:
        return {"status": "UNKNOWN", "language": language, "required_level": required_level,
                "material": is_demanding}
    candidate_level_norm = str(candidate_level).lower()
    compatible = (not is_demanding) or candidate_level_norm in _FLUENT_LEVELS
    return {"status": "COMPATIBLE" if compatible else "GAP", "language": language,
            "required_level": required_level, "candidate_level": candidate_level}


# ---------------------------------------------------------------------------
# Secao 11 - LOCATION / WORK MODEL
# ---------------------------------------------------------------------------

def evaluate_location_work_model(structured_extraction: dict | None, job: dict, profile: dict) -> dict:
    """Nunca 'Sao Paulo = BLOCK'. UNKNOWN nao presume Remote. Hibrido
    viavel segue; onsite distante sem indicio de relocation pode bloquear."""
    extraction = structured_extraction or {}
    work_model_field = extraction.get("work_model") or {}
    work_model = str((work_model_field.get("value") or {}).get("work_model")
                     or job.get("work_model") or "UNKNOWN").upper()
    desired_models = {str(item).upper() for item in (profile.get("work_models") or [])}
    location_field = extraction.get("location") or {}
    region = (location_field.get("value") or {}).get("region")
    candidate_city = profile.get("city")
    same_region = bool(region and candidate_city and normalize(str(region)) == normalize(str(candidate_city)))

    if work_model == "UNKNOWN":
        return {"status": "UNKNOWN", "work_model": work_model}
    if work_model == "REMOTE":
        compatible = not desired_models or "REMOTE" in desired_models
        return {"status": "COMPATIBLE" if compatible else "OUT_OF_PREFERENCE", "work_model": work_model}
    if work_model == "HYBRID":
        if not region:
            return {"status": "UNKNOWN", "work_model": work_model, "region": region}
        if same_region and (not desired_models or "HYBRID" in desired_models):
            return {"status": "COMPATIBLE", "work_model": work_model, "region": region}
        if not same_region:
            return {"status": "COMMUTE_BLOCK", "work_model": work_model, "region": region}
        return {"status": "OUT_OF_PREFERENCE", "work_model": work_model, "region": region}
    if work_model == "ONSITE":
        if not region:
            return {"status": "UNKNOWN", "work_model": work_model, "region": region}
        if same_region:
            return {"status": "COMPATIBLE", "work_model": work_model, "region": region}
        return {"status": "RELOCATION_BLOCK", "work_model": work_model, "region": region}
    return {"status": "UNKNOWN", "work_model": work_model}


# ---------------------------------------------------------------------------
# Secao 17/18/19 - DECISION MODEL
# ---------------------------------------------------------------------------

def evaluate_job_opportunity(*, job: dict, profile: dict, candidate_skills: list[dict],
                              score_result: ScoreResult, structured_extraction: dict | None = None,
                              channels: list[dict] | None = None,
                              already_terminal: bool = False) -> BrainDecision:
    """Ordem de decisao (Secao 17): 1 qualidade de input (assumida ja
    validada pelo caller) -> 2 hard eligibility -> 3 mandatory requirements
    -> 4 location/work model -> 5 language -> 6 salary (dentro do hard
    eligibility) -> 7 technical/transferable fit -> 8 company relevance
    (fora do escopo desta funcao - avaliada no nivel de Signal/Company) ->
    9 channel availability -> 10 estado final. Integrity before score."""
    if already_terminal:
        return BrainDecision(decision="ACTIONABLE", eligibility="ALREADY_APPLIED",
                              fit_score=score_result.total, confidence=100,
                              reasons=["already_applied_terminal_state_preserved"])

    if score_result.blocking_rules:
        return BrainDecision(decision="BLOCK", eligibility="HARD_BLOCK", fit_score=score_result.total,
                              confidence=95, reasons=list(score_result.blocking_rules),
                              hard_blocks=list(score_result.blocking_rules))

    req_eval = evaluate_requirements(structured_extraction, candidate_skills)
    if req_eval["core_missing"]:
        return BrainDecision(
            decision="BLOCK", eligibility="CORE_REQUIREMENT_MISSING", fit_score=score_result.total,
            confidence=70, reasons=[item["requirement"] for item in req_eval["core_missing"]],
            hard_blocks=["CORE_REQUIREMENT_MISSING"],
            transferable_matches=req_eval["transferable_matches"],
            preferred_gaps=req_eval["preferred_gaps"], unknowns=req_eval["uncertain_requirements"],
        )

    unknowns: list[str] = list(req_eval["uncertain_requirements"])

    location_eval = evaluate_location_work_model(structured_extraction, job, profile)
    if location_eval["status"] == "RELOCATION_BLOCK":
        return BrainDecision(decision="BLOCK", eligibility="LOCATION_BLOCK", fit_score=score_result.total,
                              confidence=80, reasons=[f"onsite_far:{location_eval.get('region')}"],
                              hard_blocks=["RELOCATION_REQUIRED_IMPLICIT"])
    if location_eval["status"] == "COMMUTE_BLOCK":
        unknowns.append("hybrid_commute_out_of_region")
    if location_eval["status"] == "UNKNOWN":
        unknowns.append("work_model_or_location_unknown")

    language_eval = evaluate_language_gap(structured_extraction, profile.get("language_levels"))
    if language_eval["status"] == "GAP":
        return BrainDecision(decision="BLOCK", eligibility="LANGUAGE_BLOCK", fit_score=score_result.total,
                              confidence=85, reasons=[f"language_gap:{language_eval.get('language')}"],
                              hard_blocks=["LANGUAGE_GAP"])
    if language_eval["status"] == "UNKNOWN" and language_eval.get("material"):
        unknowns.append("language_level_unknown")

    reasons = list(score_result.strengths)
    reasons.extend(f"transferable:{item['skill']}" for item in req_eval["transferable_matches"])
    if score_result.risks:
        unknowns.extend(score_result.risks)

    if unknowns:
        return BrainDecision(decision="HUMAN_REQUIRED", eligibility="MATERIAL_UNKNOWN",
                              fit_score=score_result.total, confidence=55, reasons=reasons, unknowns=unknowns,
                              transferable_matches=req_eval["transferable_matches"],
                              preferred_gaps=req_eval["preferred_gaps"])

    if score_result.total < 60:
        return BrainDecision(decision="DROP", eligibility="LOW_FIT", fit_score=score_result.total,
                              confidence=70, reasons=["fit_score_below_threshold"],
                              preferred_gaps=req_eval["preferred_gaps"])

    channels = channels or []
    has_verified_channel = any(item.get("status") == "VERIFIED" for item in channels)
    # Fase 2, Prompt 9, Secao 12: mesmo principio de _aggregate_channel_trust
    # (career.py) aplicado aqui - um canal VERIFIED ja disponivel nao pode
    # ser "envenenado" pela mera presenca de outra linha de canal antiga/
    # ruim (requires_human/requires_captcha) para a mesma Opportunity.
    needs_human_channel = (not has_verified_channel) and any(
        item.get("requires_human") or item.get("requires_captcha") for item in channels
    )
    if needs_human_channel:
        return BrainDecision(decision="HUMAN_REQUIRED", eligibility="PASS", fit_score=score_result.total,
                              confidence=75, reasons=reasons + ["channel_requires_human"],
                              transferable_matches=req_eval["transferable_matches"],
                              preferred_gaps=req_eval["preferred_gaps"])

    decision = "ACTIONABLE" if has_verified_channel else "PREPARE"
    return BrainDecision(decision=decision, eligibility="PASS", fit_score=score_result.total, confidence=80,
                          reasons=reasons, transferable_matches=req_eval["transferable_matches"],
                          preferred_gaps=req_eval["preferred_gaps"])


def evaluate_signal_opportunity(*, signal: dict, company: dict | None = None,
                                 related_signals: list[dict] | None = None,
                                 has_prior_interaction: bool = False) -> BrainDecision:
    """Secao 20: Signal -> Quality Gate -> Company relevance -> Opportunity
    candidate. Nunca gera Opportunity so para aumentar KPI - so promove
    Signals TRUSTED_RESOLVED, e mesmo assim so para WATCH/FUTURE_HIRING
    (nunca uma candidatura espontanea automatica so a partir de um Signal,
    Secao 30)."""
    quality = classify_signal_quality(signal)
    if quality in {"NOISY", "INSUFFICIENT_EVIDENCE", "LOW_CONFIDENCE", "ALREADY_PROMOTED"}:
        return BrainDecision(decision="DROP", eligibility="SIGNAL_QUALITY_GATE", fit_score=None,
                              confidence=60, reasons=[quality])
    if quality == "TRUSTED_UNRESOLVED":
        return BrainDecision(decision="DROP", eligibility="COMPANY_UNRESOLVED", fit_score=None,
                              confidence=50, reasons=["signal_unresolved_no_opportunity"],
                              unknowns=["company_resolution"])
    relevance = assess_company_relevance(company or {}, related_signals, has_prior_interaction)
    return BrainDecision(decision="WATCH", eligibility=f"COMPANY_RELEVANCE_{relevance['relevance']}",
                          fit_score=None, confidence=70 if relevance["relevance"] == "HIGH" else 55,
                          reasons=relevance["reasons"] + [f"signal_type:{signal.get('type')}"])


def evaluate_watch_recheck(*, new_signals: list[dict] | None = None, company: dict | None = None,
                            has_prior_interaction: bool = False) -> BrainDecision:
    """Secao 24: quando uma Watch existente recebe evidencia nova. Sem
    evidencia nova: Watch continua. Evidencia nova mas nao material:
    Watch continua. Evidencia nova e material (Signal de alto valor +
    empresa relevante): RECHECK (sinaliza para reavaliacao/busca de Job
    real - Brain nao fabrica uma Opportunity acionavel so com Signal)."""
    new_signals = new_signals or []
    if not new_signals:
        return BrainDecision(decision="WATCH", eligibility="NO_NEW_EVIDENCE", fit_score=None,
                              confidence=70, reasons=["no_change"])
    relevance = assess_company_relevance(company or {}, new_signals, has_prior_interaction)
    high_value_new = [item for item in new_signals
                       if item.get("type") in _HIGH_VALUE_SIGNAL_TYPES or item.get("type") == "JOB_DISCOVERED"]
    if high_value_new and relevance["relevance"] in {"HIGH", "MEDIUM"}:
        return BrainDecision(decision="RECHECK", eligibility="IMPROVED_EVIDENCE", fit_score=None, confidence=65,
                              reasons=[f"new_signal:{item.get('type')}" for item in high_value_new])
    return BrainDecision(decision="WATCH", eligibility="NO_MATERIAL_CHANGE", fit_score=None, confidence=60,
                          reasons=["new_evidence_insufficient"])
