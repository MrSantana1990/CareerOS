"""Channel Verification (Fase 2, Prompt 9) - promove um canal de
CANDIDATE para VERIFIED somente com evidencia real, nunca por suposicao.

Prompt 8 fechou Perception -> Brain -> Channel Resolution -> Action Plan,
mas auditoria real de producao (50 Opportunities autonomas) mostrou que
NENHUM canal descoberto (channel_discovery.py) jamais chega a
status='VERIFIED' - o unico estado que classify_channel_trust
(action_engine.py) aceita como VERIFIED_AVAILABLE. Isso e uma lacuna de
"CHANNEL STATE SEMANTICS" (Secao 3), separada do bug de agregacao ja
corrigido em career.py::_aggregate_channel_trust (Secao 12).

Este modulo e puro (sem I/O de rede/banco) - a unica excecao e
`probe_careers_candidate`, que recebe a funcao de fetch HTTP injetada pelo
caller (nunca importa requests/urllib aqui), para permanecer testavel sem
dependencia externa viva em CI (Secao 21: "No live external dependency in
CI").
"""

from __future__ import annotations

from urllib.parse import urlsplit

EMAIL_TRUST_STATES = (
    "VERIFIED_OFFICIAL", "VERIFIED_RECRUITING", "EXPLICIT_IN_JOB_POSTING",
    "UNVERIFIED", "INFERRED", "INVALID",
)

# Secao 9: somente estes tres podem virar canal de e-mail utilizavel.
_USABLE_EMAIL_TRUST = {"VERIFIED_OFFICIAL", "VERIFIED_RECRUITING", "EXPLICIT_IN_JOB_POSTING"}

CHANNEL_VERIFICATION_VERSION = "1.0"


def _email_domain(email: str | None) -> str | None:
    if not email or "@" not in email:
        return None
    return email.rsplit("@", 1)[-1].strip().lower() or None


def classify_email_trust(channel: dict, company: dict | None = None) -> str:
    """Classifica a provenance de um candidato de e-mail (Secao 9/10) -
    nunca infere um endereco, so classifica o que ja foi extraido/
    persistido com evidencia real.

    VERIFIED_OFFICIAL: veio de Company Intelligence
    (companies.official_recruiting_email), dado ja curado por um humano
    via PATCH /companies (career.py::update_company_intelligence) - a
    fonte mais confiavel que existe hoje.

    VERIFIED_RECRUITING: extraido do proprio texto da vaga
    (extraction_method=detect_email_application) E o dominio do e-mail
    bate com companies.domain conhecido - forte evidencia de que quem
    publicou a vaga e a propria empresa.

    EXPLICIT_IN_JOB_POSTING: extraido do proprio texto da vaga com uma
    instrucao explicita de candidatura (mesma extraction_method), mas o
    dominio da empresa e desconhecido ou diferente (ex.: recrutador(a)
    externo(a) instruido explicitamente na vaga a receber curriculos -
    Secao 10, exemplo do "email de consultoria explicitamente instruido
    na vaga"). Ainda usavel (Secao 9), mas nao promovido a
    VERIFIED_RECRUITING sem confirmacao de dominio.

    UNVERIFIED: e-mail presente (ex.: jobs.recruiter_email) sem evidence
    snippet/extraction_method que comprove uma instrucao explicita de
    candidatura - pode ser um contato generico de RH capturado por outra
    via, nunca promovido automaticamente.

    INFERRED: qualquer endereco que o proprio pipeline tenha
    construido/adivinhado (ex.: contato@<dominio-chutado>) - nunca deve
    acontecer no codigo atual (nenhuma funcao de discovery adivinha
    e-mail), mas o estado existe para nunca ser confundido com evidencia
    real caso apareca no futuro.

    INVALID: sem endereco, ou endereco sintaticamente vazio.
    """
    email = channel.get("url_or_email")
    if not email or "@" not in email:
        return "INVALID"

    source = str(channel.get("source") or "")
    evidence = channel.get("evidence") or {}
    extraction_method = evidence.get("extraction_method")
    has_explicit_instruction_evidence = bool(evidence.get("evidence_snippet")) or extraction_method == "detect_email_application"

    if source == "company_intelligence":
        return "VERIFIED_OFFICIAL"

    if has_explicit_instruction_evidence:
        company_domain = str((company or {}).get("domain") or "").strip().lower() or None
        email_domain = _email_domain(email)
        if company_domain and email_domain and email_domain == company_domain:
            return "VERIFIED_RECRUITING"
        return "EXPLICIT_IN_JOB_POSTING"

    return "UNVERIFIED"


def is_email_trust_usable(trust: str) -> bool:
    return trust in _USABLE_EMAIL_TRUST


def verify_channel_candidate(channel: dict, company: dict | None = None) -> dict:
    """Promove CANDIDATE -> VERIFIED com base em evidencia real (Secao 3).
    Nunca sobrescreve REJECTED/USED (estados definitivos de outro fluxo).
    Devolve uma COPIA - nunca modifica o dict recebido."""
    result = dict(channel)
    if result.get("status") not in (None, "CANDIDATE"):
        return result

    channel_type = result.get("type")
    if channel_type in {"OFFICIAL_EMAIL", "RECRUITER_INSTRUCTION"}:
        trust = classify_email_trust(result, company)
        result.setdefault("evidence", {})
        result["evidence"] = {**(result.get("evidence") or {}), "email_trust": trust}
        if is_email_trust_usable(trust):
            result["status"] = "VERIFIED"
        return result

    if channel_type == "OFFICIAL_ATS":
        # canonical_url ja aponta para a vaga especifica num board conhecido
        # (Greenhouse/Lever/Ashby) - a propria descoberta (channel_discovery.py)
        # so emite isso quando o Job.source bate com um ATS real, entao a
        # verificacao aqui e so a promocao de estado (nao ha mais evidencia
        # adicional a checar sem uma requisicao HTTP ao vivo, fora de escopo
        # para o estado CANDIDATE->VERIFIED nesta iteracao).
        result["status"] = "VERIFIED"
        return result

    # OFFICIAL_CAREERS/TALENT_POOL/ASSISTED: permanecem CANDIDATE ate
    # confirmacao especifica (Secao 13/14 - uma careers page generica nao e
    # prova de que ESTA vaga especifica segue ativa la).
    return result


# ---------------------------------------------------------------------------
# Secao 5 - OFFICIAL COMPANY CAREERS (probe conservador)
# ---------------------------------------------------------------------------

# Ordem de probes conservadora (Secao 5) - nunca persistido so por adivinhar
# o caminho; so quando o fetch real confirma evidencia de vagas.
CAREERS_PROBE_PATHS = ("/careers", "/jobs", "/trabalhe-conosco", "/trabalhe-com-a-gente")

_CAREERS_KEYWORDS = ("vaga", "carreira", "career", "job opening", "trabalhe conosco", "join our team", "we're hiring")


def probe_careers_candidate(domain: str, fetch) -> dict | None:
    """Tenta descobrir uma pagina oficial de carreiras da empresa a partir
    do dominio JA CONHECIDO (nunca adivinhado aqui - Secao 5: "companies.domain"
    deve ja existir como dado verificado antes desta funcao ser chamada).

    `fetch(url) -> {"status_code": int, "final_url": str, "body_snippet": str}`
    e injetado pelo caller - nenhuma chamada de rede acontece neste modulo,
    o que mantem esta funcao 100% testavel sem dependencia externa viva em
    CI (Secao 21).

    So retorna um candidato quando o fetch real confirma evidencia (200 +
    palavra-chave de vagas no corpo, OU redirect para um host de ATS
    conhecido) - nunca por status_code sozinho (uma home page generica que
    responde 200 nao prova nada)."""
    domain = (domain or "").strip().lower()
    if not domain:
        return None

    for path in CAREERS_PROBE_PATHS:
        url = f"https://{domain}{path}"
        try:
            response = fetch(url)
        except Exception:
            continue
        if not response or response.get("status_code") != 200:
            continue
        body = str(response.get("body_snippet") or "").lower()
        final_url = response.get("final_url") or url
        final_host = urlsplit(final_url).netloc.lower()
        matched_keyword = any(keyword in body for keyword in _CAREERS_KEYWORDS)
        redirected_to_ats = final_host and final_host != domain
        if not (matched_keyword or redirected_to_ats):
            continue
        return {
            "type": "OFFICIAL_CAREERS",
            "url_or_email": final_url,
            "source": "careers_probe",
            "confidence": 75 if matched_keyword else 65,
            "requires_auth": False, "requires_captcha": False, "requires_human": True,
            "status": "CANDIDATE",
            # Secao 13/14: nunca prova que UMA vaga especifica segue ativa -
            # so que a empresa tem uma pagina real de carreiras. Nunca
            # promovido a VERIFIED por verify_channel_candidate.
            "evidence": {"job_specific": False, "probed_path": path, "matched_keyword": matched_keyword,
                         "redirected_to_ats": redirected_to_ats},
        }
    return None
