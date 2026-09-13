"""Application Conflict Forensics (Fase 2, Prompt 9.2).

APPLICATION ROW != REAL APPLICATION (Secao 3). Uma linha PREPARING/READY/
ERROR criada pelo pipeline tradicional nunca chegou a acao externa
comprovada - mas uma candidatura CONFIRMED real nunca pode ser descartada
ou sobrescrita. Este modulo classifica cada Application e cada grupo de
conflito (Jobs duplicados com Applications proprias) usando EVIDENCIA real
(status + provider_message_id + external_reference + confirmation_evidence
+ applied_at), nunca so o nome do status - CLOSED/REJECTED sao alcancaveis
tanto antes quanto depois de um envio real (ver ALLOWED_TRANSITIONS em
quality.py), entao o nome sozinho nunca prova nada.

Pure, sem I/O - o caller (career.py) busca os dados reais.
"""

from __future__ import annotations

APPLICATION_REALITY_STATES = (
    "NON_EXTERNAL_ARTIFACT", "EXTERNAL_ATTEMPT_UNCONFIRMED", "EXTERNAL_CONFIRMED", "HISTORICAL_UNKNOWN",
)

# Estados que, por construcao do grafo ALLOWED_TRANSITIONS (quality.py), so
# sao alcancaveis DEPOIS de um SENT/CONFIRMED real - nenhuma ambiguidade
# possivel so pelo nome.
_ONLY_REACHABLE_AFTER_CONFIRMATION = {
    "SENT", "CONFIRMED", "RECRUITER_RESPONSE", "INTERVIEW", "TECHNICAL_TEST", "FINAL_STAGE", "OFFER",
}
# Pre-submissao por construcao - nunca passaram por SUBMITTING/SENT.
_PRE_SUBMISSION_STATUSES = {
    "DISCOVERED", "VALIDATING", "VALIDATED", "QUALIFIED", "WAITING_DECISION",
    "PREPARING", "READY", "ERROR", "MANUAL_REQUIRED",
}
# Ambiguos pelo nome sozinho - CLOSED/REJECTED/DISCARDED sao alcancaveis
# tanto de estados pre-submissao (READY->DISCARDED, VALIDATING->CLOSED)
# quanto pos-confirmacao (CONFIRMED->REJECTED/CLOSED). Exigem evidencia ou
# historico de eventos para desambiguar (Secao 2: "nao classificar apenas
# pelo nome do status").
_AMBIGUOUS_BY_NAME_ALONE = {"CLOSED", "REJECTED", "DISCARDED"}


def _has_external_evidence(application: dict) -> bool:
    if application.get("provider_message_id"):
        return True
    if application.get("external_reference"):
        return True
    evidence = application.get("confirmation_evidence") or {}
    if isinstance(evidence, dict) and any(value for value in evidence.values()):
        return True
    return bool(application.get("applied_at"))


def classify_application_reality(application: dict, event_history: list[dict] | None = None) -> str:
    """event_history (opcional): lista de application_events reais dessa
    Application (append-only, nunca fabricado) - usado so para desambiguar
    CLOSED/REJECTED/DISCARDED quando a evidencia direta na propria
    Application nao basta."""
    status = str(application.get("status") or "").upper()
    has_evidence = _has_external_evidence(application)

    if status in _ONLY_REACHABLE_AFTER_CONFIRMATION:
        return "EXTERNAL_CONFIRMED"
    if status == "SUBMITTING":
        return "EXTERNAL_ATTEMPT_UNCONFIRMED"
    if status in _PRE_SUBMISSION_STATUSES:
        # Achado real (Secao 3): mesmo com status pre-submissao, se
        # evidencia externa real ja existir (nunca deveria, mas a
        # evidencia sempre vence o nome do status), nunca classificar como
        # artefato tecnico.
        return "EXTERNAL_ATTEMPT_UNCONFIRMED" if has_evidence else "NON_EXTERNAL_ARTIFACT"
    if status in _AMBIGUOUS_BY_NAME_ALONE:
        if has_evidence:
            return "EXTERNAL_CONFIRMED"
        for event in event_history or []:
            if str(event.get("to_status") or "").upper() in _ONLY_REACHABLE_AFTER_CONFIRMATION:
                return "EXTERNAL_CONFIRMED"
        if event_history is not None:
            # Historico real consultado e nenhuma confirmacao encontrada -
            # nao e "desconhecido", e comprovadamente pre-submissao.
            return "NON_EXTERNAL_ARTIFACT"
        return "HISTORICAL_UNKNOWN"
    return "HISTORICAL_UNKNOWN"


# ---------------------------------------------------------------------------
# Secao 4 - GROUP CLASSIFICATION
# ---------------------------------------------------------------------------

GROUP_CONFLICT_CLASSES = (
    "SAFE_SINGLE_REAL_APPLICATION", "SAFE_NO_REAL_APPLICATION", "MULTIPLE_TECHNICAL_ARTIFACTS",
    "ONE_CONFIRMED_PLUS_ARTIFACTS", "MULTIPLE_REAL_APPLICATIONS", "AMBIGUOUS_HISTORY",
)

# Somente estas classes podem ser reconciliadas automaticamente (Secao 5).
AUTO_RECONCILABLE_GROUP_CLASSES = {
    "SAFE_NO_REAL_APPLICATION", "MULTIPLE_TECHNICAL_ARTIFACTS",
    "SAFE_SINGLE_REAL_APPLICATION", "ONE_CONFIRMED_PLUS_ARTIFACTS",
}


def classify_group_application_conflict(realities: list[str]) -> str:
    """`realities` e a lista de classify_application_reality(...) de TODAS
    as Applications de TODOS os Jobs do grupo (uma entrada por Application
    real, nunca por Job - um Job sem Application nao contribui nada aqui)."""
    if not realities:
        return "SAFE_NO_REAL_APPLICATION"
    if len(realities) == 1:
        return "SAFE_SINGLE_REAL_APPLICATION"

    confirmed = sum(1 for item in realities if item == "EXTERNAL_CONFIRMED")
    unknown = sum(1 for item in realities if item == "HISTORICAL_UNKNOWN")
    attempts = sum(1 for item in realities if item == "EXTERNAL_ATTEMPT_UNCONFIRMED")

    if confirmed >= 2:
        return "MULTIPLE_REAL_APPLICATIONS"
    if unknown:
        return "AMBIGUOUS_HISTORY"
    if confirmed == 1 and attempts == 0:
        return "ONE_CONFIRMED_PLUS_ARTIFACTS"
    if confirmed == 0 and attempts == 0:
        return "MULTIPLE_TECHNICAL_ARTIFACTS"
    # confirmed==1 e attempts>=1, OU confirmed==0 e attempts>=1: uma
    # tentativa externa sem confirmacao ao lado de outra evidencia real e
    # material demais para decidir sozinho - Secao 8 (nunca inventar).
    return "AMBIGUOUS_HISTORY"


_REALITY_RANK = {"EXTERNAL_CONFIRMED": 0, "EXTERNAL_ATTEMPT_UNCONFIRMED": 1,
                 "HISTORICAL_UNKNOWN": 2, "NON_EXTERNAL_ARTIFACT": 3}


def select_canonical_application(applications_with_reality: list[tuple[dict, str]]) -> dict | None:
    """Secao 6: ordem de evidencia CONFIRMED > tentativa > artefato - nunca
    oldest/newest/status sozinho. Empate: mais antiga por created_at
    (mais proxima da candidatura real original)."""
    if not applications_with_reality:
        return None
    ranked = sorted(applications_with_reality,
                     key=lambda pair: (_REALITY_RANK.get(pair[1], 9), pair[0].get("created_at") or ""))
    return ranked[0][0]
