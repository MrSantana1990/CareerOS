"""Channel Population (Fase 2, Prompt 6) - descoberta CONSERVADORA de
OpportunityChannel a partir de dado ja persistido (Job/Company/structured
extraction). Nunca adivinha e-mail, nunca transforma uma homepage
corporativa generica em canal de candidatura sem evidencia (Secao 21).

Discovery Source != Application Channel: uma vaga descoberta no LinkedIn
nao vira automaticamente um canal "oficial" so por existir - o canal real
e a propria pagina de candidatura (assistida, com auth/captcha reais e ja
documentados), nunca uma inferencia.

Pure, sem I/O - recebe dicts ja carregados pelo caller (career.py).
"""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

_URL_OR_EMAIL_MAX_LENGTH = 500  # opportunity_channels.url_or_email e VARCHAR(500)


def _canonicalize_url(url: str | None) -> str | None:
    """Achado real na validacao do Prompt 6: URLs do LinkedIn carregam
    parametros de tracking (eBP/refId/trackingId/trk) que sozinhos ja
    passam de 500 caracteres - StringDataRightTruncationError real em
    producao. A query string e ruido analitico do LinkedIn, nao faz parte
    do endereco real da vaga (linkedin.com/jobs/view/{id}/ sozinho ja
    carrega para a mesma pagina) - remover a query string e uma
    canonicalizacao correta, nunca uma truncagem cega que corromperia a
    URL no meio."""
    if not url:
        return url
    if len(url) <= _URL_OR_EMAIL_MAX_LENGTH:
        return url
    parts = urlsplit(url)
    without_query = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    if len(without_query) <= _URL_OR_EMAIL_MAX_LENGTH:
        return without_query
    # Ultimo recurso, nunca esperado na pratica: path em si excede o limite.
    return without_query[:_URL_OR_EMAIL_MAX_LENGTH]


_ATS_SOURCES = {"greenhouse", "lever", "ashby"}
# Plataformas com padrao real ja documentado (Prompt 5, Secoes 31/32):
# LinkedIn exige login + reCAPTCHA; InfoJobs exige login. Nunca contornado.
_KNOWN_AUTH_SOURCES = {"linkedin", "infojobs"}
_KNOWN_CAPTCHA_SOURCES = {"linkedin"}


def _email_channel(email: str, source: str, confidence: int) -> dict:
    return {"type": "OFFICIAL_EMAIL", "url_or_email": email, "source": source,
            "confidence": confidence, "requires_auth": False, "requires_captcha": False,
            "requires_human": True, "status": "CANDIDATE"}


def discover_job_channel_candidates(job: dict, company: dict, structured_extraction: dict | None = None) -> list[dict]:
    """Ordem de descoberta da Secao 22 para uma Opportunity com Job real.
    Retorna candidatos em ordem de prioridade - o primeiro e o preferido,
    mas nenhuma escolha aqui e definitiva (Channel Trust/Action Policy
    decidem se pode ser usado)."""
    candidates: list[dict] = []
    extraction = structured_extraction or {}

    # 1. instrucao explicita de candidatura da propria vaga (Prompt 3:
    # extract_application_instructions, nunca inferido).
    application_field = extraction.get("application_instructions") or {}
    explicit_email = (application_field.get("value") or {}).get("recruiting_email")
    if explicit_email:
        # Prompt 9: evidence_snippet/extraction_method precisam viajar junto
        # com o candidato - sem isso, channel_verification.classify_email_trust
        # (Secao 9) nao tem como distinguir esta instrucao explicita de um
        # e-mail generico sem prova (achado real na validacao em producao
        # deste prompt: o candidato chegava sem evidence nenhuma).
        candidates.append({**_email_channel(explicit_email, application_field.get("source_url") or job.get("canonical_url"), 90),
                            "requires_human": False,
                            "evidence": {"evidence_snippet": application_field.get("evidence_snippet"),
                                         "extraction_method": application_field.get("extraction_method")}})
    elif job.get("recruiter_email"):
        candidates.append(_email_channel(job["recruiter_email"], job.get("canonical_url"), 85))

    # 2. ATS oficial conhecido (Greenhouse/Lever/Ashby) - canonical_url ja
    # aponta para a vaga especifica nesse board.
    source_lower = str(job.get("source") or "").strip().lower()
    channel_lower = str(job.get("application_channel") or "").strip().lower()
    if source_lower in _ATS_SOURCES or channel_lower in _ATS_SOURCES:
        candidates.append({"type": "OFFICIAL_ATS",
                            "url_or_email": _canonicalize_url(job.get("canonical_url") or job.get("source_url")),
                            "source": job.get("source"), "confidence": 95, "requires_auth": False,
                            "requires_captcha": False, "requires_human": False, "status": "CANDIDATE"})

    # 3. rota oficial de carreiras da Company (nivel de empresa, nao da vaga).
    if company.get("careers_url"):
        candidates.append({"type": "OFFICIAL_CAREERS", "url_or_email": _canonicalize_url(company["careers_url"]),
                            "source": "company_intelligence", "confidence": 80, "requires_auth": False,
                            "requires_captcha": False, "requires_human": True, "status": "CANDIDATE"})

    # 4. e-mail de recrutamento oficial verificado da Company (Company
    # Intelligence - nunca adivinhado a partir do dominio).
    if company.get("official_recruiting_email"):
        candidates.append(_email_channel(company["official_recruiting_email"], "company_intelligence", 90))

    # 5. talent pool oficial da Company.
    if company.get("talent_pool_url"):
        candidates.append({"type": "TALENT_POOL", "url_or_email": _canonicalize_url(company["talent_pool_url"]),
                            "source": "company_intelligence", "confidence": 70, "requires_auth": False,
                            "requires_captcha": False, "requires_human": True, "status": "CANDIDATE"})

    # 6. assistido/manual - a propria pagina da vaga (canonical_url), nunca
    # promovida a "oficial" sem evidencia: sinaliza auth/captcha reais e ja
    # documentados por plataforma (Secao 22 - fallback, nao invencao).
    if job.get("canonical_url") and not candidates:
        candidates.append({
            "type": "ASSISTED", "url_or_email": _canonicalize_url(job["canonical_url"]), "source": job.get("source"),
            "confidence": 60, "requires_auth": source_lower in _KNOWN_AUTH_SOURCES,
            "requires_captcha": source_lower in _KNOWN_CAPTCHA_SOURCES,
            "requires_human": True, "status": "CANDIDATE",
        })
    return candidates


def discover_company_channel_candidates(company: dict) -> list[dict]:
    """Secao 22, ramo Company/Future Opportunity (sem Job) - nunca escolhe
    SPONTANEOUS_APPLICATION so porque nao ha Job; sem evidencia real
    (careers/talent pool/e-mail), a Opportunity permanece sem canal (WATCH)."""
    candidates: list[dict] = []
    if company.get("careers_url"):
        candidates.append({"type": "OFFICIAL_CAREERS", "url_or_email": _canonicalize_url(company["careers_url"]),
                            "source": "company_intelligence", "confidence": 80, "requires_auth": False,
                            "requires_captcha": False, "requires_human": True, "status": "CANDIDATE"})
    if company.get("talent_pool_url"):
        candidates.append({"type": "TALENT_POOL", "url_or_email": _canonicalize_url(company["talent_pool_url"]),
                            "source": "company_intelligence", "confidence": 70, "requires_auth": False,
                            "requires_captcha": False, "requires_human": True, "status": "CANDIDATE"})
    if company.get("official_recruiting_email"):
        candidates.append(_email_channel(company["official_recruiting_email"], "company_intelligence", 90))
    return candidates
