"""Autonomous Action Engine (Fase 2, Prompt 5) - camada de ACAO.

BRAIN (Prompt 4) decide "o que isso significa" (ACTIONABLE/PREPARE/...).
ACTION ENGINE decide "o que fazer com isso" - e ACTIONABLE nunca significa
SUBMIT automatico. Toda decisao aqui e determinista, pura, sem rede/banco
(mesmo padrao de quality.py/opportunity_brain.py) - o caller (career.py)
busca os dados reais e persiste o resultado.

Nenhuma linha deste modulo envia e-mail, clica em nada ou muda estado
externo. `send_application_email`/automacao de browser existentes
(automation-host) sao reusadas, nunca reimplementadas, e continuam atras
do gate de produto AUTO_APPLY_ENABLED.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from hashlib import sha256

ACTION_ENGINE_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Secao 1/2/3 - PROFILE COMPLETENESS / LANGUAGE / SKILL VERIFICATION
# ---------------------------------------------------------------------------

COMPLETENESS_STATES = ("VERIFIED", "EVIDENCE_BACKED", "DECLARED", "UNKNOWN", "MISSING")


def classify_profile_completeness(profile: dict, skills: list[dict], resumes: list[dict]) -> dict:
    """Cada dimensao classificada so com dado real persistido - nunca com
    'memoria' do agente. candidate_profiles hoje NAO tem colunas de
    experience/education/certifications - essas dimensoes sao
    estruturalmente MISSING, nao UNKNOWN (sabemos que nao existem, nao e
    incerteza)."""
    approved_answers = profile.get("approved_answers") or {}
    report: dict[str, str] = {}

    if approved_answers.get("nome completo") and approved_answers.get("e-mail"):
        report["identity"] = "EVIDENCE_BACKED"
    elif profile.get("headline") or profile.get("linkedin_url"):
        report["identity"] = "DECLARED"
    else:
        report["identity"] = "MISSING"

    report["location"] = "DECLARED" if profile.get("city") and profile.get("state") else "MISSING"
    report["work_preferences"] = "DECLARED" if profile.get("work_models") else "MISSING"
    report["salary_floor"] = "DECLARED" if profile.get("salary_expectation") else "MISSING"
    report["target_roles"] = "DECLARED" if profile.get("target_roles") else "MISSING"
    report["languages"] = "DECLARED" if profile.get("language_levels") else "MISSING"

    verified_skills = [item for item in skills if item.get("verified")]
    evidence_backed_skills = [item for item in skills
                              if not item.get("verified") and (item.get("evidence_count") or 0) > 0]
    if verified_skills:
        report["skills"] = "VERIFIED"
    elif evidence_backed_skills:
        report["skills"] = "EVIDENCE_BACKED"
    elif skills:
        report["skills"] = "DECLARED"
    else:
        report["skills"] = "MISSING"

    report["experience"] = "MISSING"
    report["education"] = "MISSING"
    report["certifications"] = "MISSING"

    approved_resumes = [item for item in resumes if item.get("approved_at") and item.get("active")]
    report["resume_inventory"] = "VERIFIED" if approved_resumes else "MISSING"
    return report


_MATERIAL_COMPLETENESS_DIMENSIONS = ("identity", "location", "languages", "resume_inventory")
_INSUFFICIENT_COMPLETENESS_STATES = {"UNKNOWN", "MISSING"}


def is_profile_completeness_sufficient(report: dict) -> bool:
    """Minimo material para POLICY_ACTION (Secao 8): identidade, localizacao,
    idiomas e inventario de resume tem que ser pelo menos DECLARED/
    EVIDENCE_BACKED/VERIFIED - nunca UNKNOWN/MISSING nessas dimensoes."""
    return all(report.get(dimension) not in _INSUFFICIENT_COMPLETENESS_STATES
               for dimension in _MATERIAL_COMPLETENESS_DIMENSIONS)


def assess_language_status(profile: dict) -> dict:
    """Nao inventa nivel. Sem language_levels persistido, cria uma
    HUMAN_INTERVENTION especifica (Secao 2) em vez de preencher
    automaticamente ou de bloquear vagas que nao exigem idioma."""
    if profile.get("language_levels"):
        return {"status": "DECLARED", "needs_intervention": False}
    return {
        "status": "MISSING",
        "needs_intervention": True,
        "intervention_reason": "MISSING_PROFILE_DATA",
        "intervention_title": "Declarar nível real de idioma",
        "intervention_instructions": (
            "Nenhum nível de idioma do candidato está persistido em "
            "candidate_profiles.language_levels. Declare seu nível real de inglês "
            "(e outros idiomas relevantes) para que vagas com requisito EXPLÍCITO de "
            "idioma possam ser avaliadas com confiança. Até isso ser resolvido, essas "
            "vagas específicas permanecem HUMAN_REQUIRED - vagas sem requisito "
            "explícito de idioma não são bloqueadas por isso."
        ),
    }


def classify_skill_verification(skill: dict, evidence_count: int = 0) -> str:
    if skill.get("verified"):
        return "VERIFIED"
    if evidence_count > 0:
        return "EVIDENCE_BACKED"
    if skill.get("name"):
        return "DECLARED"
    return "UNKNOWN"


# ---------------------------------------------------------------------------
# Secao 6/7 - CHANNEL TRUST / PRIORITY
# ---------------------------------------------------------------------------

CHANNEL_TRUST_STATES = ("VERIFIED_AVAILABLE", "AUTH_REQUIRED", "CAPTCHA_REQUIRED", "BOT_GATED",
                         "STALE", "UNVERIFIABLE", "UNAVAILABLE")
_STALE_DAYS = 90

# Ordem conceitual da Secao 7 - RECRUITER_INSTRUCTION acima de EMAIL generico
# porque e uma instrucao explicita da propria vaga, nao uma heuristica.
_CHANNEL_PRIORITY = {
    "OFFICIAL_ATS": 1, "OFFICIAL_CAREERS": 2, "RECRUITER_INSTRUCTION": 3,
    "OFFICIAL_EMAIL": 4, "TALENT_POOL": 5, "ASSISTED": 6, "SPONTANEOUS_APPLICATION": 6,
}


def classify_channel_trust(channel: dict, now: datetime | None = None) -> str:
    """Nunca infere e-mail/canal - so classifica o que ja foi verificado/
    persistido (Secao 6). BOT_GATED vem de evidence.board_status quando a
    checagem estruturada do Prompt 3 (classify_board_fetch) ja rodou."""
    if channel.get("status") == "REJECTED":
        return "UNAVAILABLE"
    if (channel.get("evidence") or {}).get("board_status") == "BOT_GATED":
        return "BOT_GATED"
    if channel.get("requires_captcha"):
        return "CAPTCHA_REQUIRED"
    if channel.get("requires_auth"):
        return "AUTH_REQUIRED"
    if channel.get("status") != "VERIFIED":
        return "UNVERIFIABLE"
    verified_at = channel.get("verified_at")
    if verified_at:
        reference = now or datetime.now(UTC)
        if isinstance(verified_at, str):
            verified_at = datetime.fromisoformat(verified_at)
        if (reference - verified_at).days > _STALE_DAYS:
            return "STALE"
    if channel.get("requires_human"):
        return "UNVERIFIABLE"
    return "VERIFIED_AVAILABLE"


def select_channel(channels: list[dict]) -> dict | None:
    """So seleciona entre canais VERIFIED_AVAILABLE - nunca 'promove' um
    canal nao confiavel so por ser o unico disponivel (isso vira
    PREPARE_ONLY/HUMAN_REQUIRED na Action Policy, nao uma escolha aqui)."""
    trusted = [item for item in channels if classify_channel_trust(item) == "VERIFIED_AVAILABLE"]
    if not trusted:
        return None
    return min(trusted, key=lambda item: _CHANNEL_PRIORITY.get(item.get("type"), 50))


# ---------------------------------------------------------------------------
# Secao 18 - SENSITIVE FIELDS
# ---------------------------------------------------------------------------

SENSITIVE_FIELD_STATES = ("KNOWN_SAFE", "KNOWN_SENSITIVE", "MISSING_USER_REQUIRED")

_KNOWN_SENSITIVE_FIELDS = {"cpf", "document_number", "date_of_birth", "photo",
                           "legal_declaration", "relocation_consent"}


def classify_sensitive_field(field_name: str, value: object, allow_sensitive_autofill: bool = False) -> str:
    if value in (None, ""):
        return "MISSING_USER_REQUIRED"
    normalized = field_name.strip().lower().replace(" ", "_")
    if normalized in _KNOWN_SENSITIVE_FIELDS and not allow_sensitive_autofill:
        return "KNOWN_SENSITIVE"
    return "KNOWN_SAFE"


# ---------------------------------------------------------------------------
# Secao 4/9 - ACTION ENGINE BOUNDARY / AUTONOMY CLASSES
# ---------------------------------------------------------------------------

AUTONOMY_CLASSES = ("AUTO_SAFE", "AUTO_PREPARE", "POLICY_ACTION", "HUMAN_REQUIRED")
ACTION_DECISIONS = ("NO_ACTION", "WATCH", "PREPARE_ONLY", "POLICY_ACTION_ALLOWED",
                    "HUMAN_APPROVAL_REQUIRED", "HUMAN_EXECUTION_REQUIRED", "BLOCKED")


@dataclass
class ActionPolicyResult:
    autonomy_class: str
    action_decision: str
    reasons: list[str] = field(default_factory=list)
    blocked_gates: list[str] = field(default_factory=list)
    human_requirements: list[str] = field(default_factory=list)
    action_engine_version: str = ACTION_ENGINE_VERSION

    def as_dict(self) -> dict:
        return asdict(self)


def evaluate_action_policy(*, brain_decision: str, hard_blocks: list[str] | None = None,
                            unknowns: list[str] | None = None, salary_known: bool = False,
                            salary_below_floor: bool = False, location_work_model_blocked: bool = False,
                            language_incompatible: bool = False, channel_trust: str | None = None,
                            resume_available: bool = True, duplicate_exists: bool = False,
                            sensitive_missing: list[str] | None = None, attempt_cap_reached: bool = False,
                            profile_completeness_sufficient: bool = True,
                            product_auto_apply_enabled: bool = False) -> ActionPolicyResult:
    """Formaliza a Action Policy determinista da Secao 8 - qualquer falha
    produz um estado explicito (Secao 8: 'Qualquer falha deve produzir
    estado explicito'), nunca um catch-all silencioso. ACTIONABLE do Brain
    nunca vira POLICY_ACTION_ALLOWED sem TODOS os gates + autorizacao de
    produto explicita (Secao 4/10 - policy eligible != globally authorized)."""
    hard_blocks = hard_blocks or []
    unknowns = unknowns or []
    sensitive_missing = sensitive_missing or []

    if brain_decision in {"DROP", "WATCH", "RECHECK"}:
        decision = "NO_ACTION" if brain_decision == "DROP" else "WATCH"
        return ActionPolicyResult("AUTO_SAFE", decision, reasons=[f"brain_decision:{brain_decision}"])

    if brain_decision == "BLOCK":
        return ActionPolicyResult("AUTO_SAFE", "BLOCKED", reasons=["brain_decision:BLOCK"],
                                   blocked_gates=list(hard_blocks) or ["BLOCK"])

    if brain_decision == "HUMAN_REQUIRED":
        return ActionPolicyResult("HUMAN_REQUIRED", "HUMAN_APPROVAL_REQUIRED",
                                   reasons=["brain_decision:HUMAN_REQUIRED"],
                                   human_requirements=list(unknowns) or ["MATERIAL_UNKNOWN"])

    # A partir daqui: brain_decision in {"PREPARE", "ACTIONABLE"}.
    blocked_gates: list[str] = []
    if hard_blocks:
        blocked_gates.append("hard_blocks_present")
    if salary_known and salary_below_floor:
        blocked_gates.append("salary_below_floor")
    if location_work_model_blocked:
        blocked_gates.append("location_work_model_blocked")
    if language_incompatible:
        blocked_gates.append("language_incompatible")
    if blocked_gates:
        return ActionPolicyResult("AUTO_SAFE", "BLOCKED", reasons=["eligibility_gate_failed"],
                                   blocked_gates=blocked_gates)

    if duplicate_exists:
        return ActionPolicyResult("AUTO_SAFE", "NO_ACTION", reasons=["duplicate_application_prevented"])

    if attempt_cap_reached:
        return ActionPolicyResult("AUTO_SAFE", "BLOCKED", reasons=["attempt_cap_reached"],
                                   blocked_gates=["ATTEMPT_CAP"])

    if channel_trust == "CAPTCHA_REQUIRED":
        return ActionPolicyResult("HUMAN_REQUIRED", "HUMAN_EXECUTION_REQUIRED",
                                   reasons=["captcha_required"], human_requirements=["CAPTCHA"])
    if channel_trust == "AUTH_REQUIRED":
        return ActionPolicyResult("HUMAN_REQUIRED", "HUMAN_EXECUTION_REQUIRED",
                                   reasons=["auth_required"], human_requirements=["AUTH_REQUIRED"])
    if channel_trust in {None, "BOT_GATED", "STALE", "UNVERIFIABLE", "UNAVAILABLE"}:
        return ActionPolicyResult("AUTO_PREPARE", "PREPARE_ONLY", reasons=[f"channel_trust:{channel_trust}"])

    if sensitive_missing:
        return ActionPolicyResult("HUMAN_REQUIRED", "HUMAN_APPROVAL_REQUIRED",
                                   reasons=["sensitive_field_missing"], human_requirements=list(sensitive_missing))

    if not resume_available:
        if brain_decision == "PREPARE":
            return ActionPolicyResult("AUTO_PREPARE", "PREPARE_ONLY", reasons=["resume_unavailable"])
        return ActionPolicyResult("HUMAN_REQUIRED", "HUMAN_APPROVAL_REQUIRED", reasons=["resume_unavailable"],
                                   human_requirements=["RESUME_SELECTION"])

    if not profile_completeness_sufficient:
        return ActionPolicyResult("HUMAN_REQUIRED", "HUMAN_APPROVAL_REQUIRED",
                                   reasons=["profile_completeness_insufficient"],
                                   human_requirements=["PROFILE_COMPLETENESS"])

    if brain_decision == "PREPARE":
        return ActionPolicyResult("AUTO_PREPARE", "PREPARE_ONLY", reasons=["eligible_prepare_only"])

    # brain_decision == "ACTIONABLE" e todos os gates de elegibilidade passaram.
    if not product_auto_apply_enabled:
        return ActionPolicyResult("AUTO_PREPARE", "HUMAN_APPROVAL_REQUIRED",
                                   reasons=["product_authorization_missing"],
                                   human_requirements=["FINAL_APPROVAL"])

    return ActionPolicyResult("POLICY_ACTION", "POLICY_ACTION_ALLOWED", reasons=["all_gates_passed"])


# ---------------------------------------------------------------------------
# Secao 14 - APPLICATION PLAN
# ---------------------------------------------------------------------------

def application_plan_idempotency_key(opportunity_id: str, channel_type: str | None) -> str:
    return sha256(f"{opportunity_id}:{channel_type or 'none'}".encode()).hexdigest()


def build_application_plan(*, opportunity_id: str, job_id: str | None, channel: dict | None,
                            resume: dict | None, policy_result: ActionPolicyResult,
                            required_fields: list[str] | None = None,
                            missing_fields: list[str] | None = None,
                            evidence: dict | None = None) -> dict:
    """Estrutura auditavel (Secao 14/18 do output) - nao persiste em tabela
    nova, e devolvida para o caller gravar em opportunities.evidence
    (mesma decisao de evolucao minima do Prompt 4)."""
    return {
        "opportunity_id": opportunity_id,
        "job_id": job_id,
        "channel": {"type": channel.get("type"), "url_or_email": channel.get("url_or_email")} if channel else None,
        "resume_version_id": resume.get("id") if resume else None,
        "resume_hash": resume.get("sha256") if resume else None,
        "action_decision": policy_result.action_decision,
        "autonomy_class": policy_result.autonomy_class,
        "required_fields": required_fields or [],
        "missing_fields": missing_fields or [],
        "human_requirements": policy_result.human_requirements,
        "policy_result": policy_result.as_dict(),
        "idempotency_key": application_plan_idempotency_key(opportunity_id,
                                                             channel.get("type") if channel else None),
        "evidence": evidence or {},
        "action_engine_version": ACTION_ENGINE_VERSION,
    }
