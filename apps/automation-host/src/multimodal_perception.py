"""Multimodal Market Perception (Fase 2, Prompt 13).

CONTENT UNDERSTANDING separado de CONTENT ACQUISITION (Secao 28/4 do
prompt) - este modulo NUNCA busca conteudo sozinho (nenhum crawler de
feed social, nenhum bypass de LinkedIn/login/CAPTCHA, Secao 27). Recebe
texto/payloads JA disponiveis ao pipeline (DOM, texto OCR/vision-
extraido, payload de QR ja decodificado) e produz evidencia estruturada
no MESMO formato ja usado por structured_fields.py
(value/confidence/evidence_snippet/source_url/extraction_method) - nunca
duplica os extratores de mandatory/preferred/language/salary/work_model/
location ja existentes la (reusar via extract_all quando aplicavel); so
adiciona o que ainda nao existe: deteccao de vaga visual, WhatsApp,
seguranca/decodificacao de QR, e particionamento de multi-vaga.

Pure, stdlib-first - a UNICA excecao com dependencia externa e
decode_qr_from_image_bytes (Pillow/pyzbar, import tardio e opcional -
Secao 8: decodificacao local/offline). Nenhuma chamada de rede em lugar
nenhum deste arquivo.
"""

from __future__ import annotations

import re
import unicodedata
from hashlib import sha256
from urllib.parse import urlsplit

from .email_discovery import detect_email_application

# ---------------------------------------------------------------------------
# Secao 3 - SOURCE TYPES (taxonomia, sem logica de acquisition aqui)
# ---------------------------------------------------------------------------

SOURCE_TYPES = ("JOB_PAGE", "SOCIAL_POST", "COMPANY_POST", "RECRUITER_POST", "IMAGE_CARD",
                "PUBLIC_WEB_PAGE", "UNKNOWN")

# Secao 28 - status de ACQUISITION, nunca confundido com falha do parser
# de CONTENT UNDERSTANDING (que roda perfeitamente sobre o texto/imagem
# que recebe, independente de como ele chegou).
ACQUISITION_STATUSES = ("SUPPORTED", "UNSUPPORTED", "HUMAN_SOURCE", "FUTURE_CONNECTOR")


def _normalize(value: str) -> str:
    plain = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", plain.lower()).split())


# ---------------------------------------------------------------------------
# Secao 2/5 - CONTENT PERCEPTION / IMAGE VACANCY DETECTION
# ---------------------------------------------------------------------------

VACANCY_CLASSIFICATIONS = ("VACANCY_CANDIDATE", "NON_VACANCY", "UNCERTAIN")

# Cada sinal conta 1 ponto (Secao 5) - nunca um unico sinal isolado
# decide sozinho ("local"/"cargo" aparecem em qualquer texto corporativo).
_VACANCY_SIGNALS = (
    "vaga", "vagas", "oportunidade", "estamos contratando", "contratando",
    "requisitos", "requisito", "beneficios", "envie curriculo", "envie seu curriculo",
    "candidate se", "candidatar se", "inscreva se", "inscricoes",
    "processo seletivo", "recrutamento", "job opening", "we are hiring",
    "hiring", "apply now", "trabalhe conosco",
)
_ROLE_TITLE_MARKERS = (
    "analista", "assistente", "auxiliar", "coordenador", "especialista",
    "desenvolvedor", "engenheiro", "engenheira", "tecnico", "tecnica", "gerente",
    "estagiario", "estagiaria", "supervisor", "consultor", "vendedor",
    "analyst", "developer", "engineer", "technician", "manager",
)
_CONTACT_HINT_PATTERN = re.compile(
    r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}|qr\s*code|escaneie|aponte a camera|leia o (qr|codigo)",
    re.IGNORECASE,
)

_MIN_SIGNALS_FOR_VACANCY_CANDIDATE = 3
_MIN_SIGNALS_FOR_UNCERTAIN = 1


def classify_vacancy_content(text: str) -> dict:
    """VACANCY_CANDIDATE/NON_VACANCY/UNCERTAIN (Secao 2/5). Nunca decide
    por um unico sinal isolado - um cargo mencionado de passagem ou uma
    imagem institucional generica nunca vira vaga sozinha; exige multiplos
    sinais concordantes (texto real de vaga + cargo + opcionalmente
    contato/QR)."""
    text = text or ""
    normalized = _normalize(text)
    matched_signals = [signal for signal in _VACANCY_SIGNALS if _normalize(signal) in normalized]
    has_role_marker = any(marker in normalized for marker in _ROLE_TITLE_MARKERS)
    has_contact_marker = bool(_CONTACT_HINT_PATTERN.search(text))
    score = len(matched_signals) + (1 if has_role_marker else 0) + (1 if has_contact_marker else 0)
    evidence = {"matched_signals": matched_signals, "has_role_marker": has_role_marker,
                "has_contact_marker": has_contact_marker, "score": score}
    if score >= _MIN_SIGNALS_FOR_VACANCY_CANDIDATE:
        return {"classification": "VACANCY_CANDIDATE", "confidence": min(95, 50 + score * 10), "evidence": evidence}
    if score >= _MIN_SIGNALS_FOR_UNCERTAIN:
        return {"classification": "UNCERTAIN", "confidence": 40, "evidence": evidence}
    return {"classification": "NON_VACANCY", "confidence": 80, "evidence": evidence}


# ---------------------------------------------------------------------------
# Secao 6/11 - EMAIL / APPLICATION INSTRUCTION EXTRACTION (reuso, nunca duplicado)
# ---------------------------------------------------------------------------

def extract_email_from_content(text: str, source_url: str | None = None) -> dict | None:
    """Reusa detect_email_application (email_discovery.py, Prompt 3) -
    aplicavel a texto de QUALQUER origem (DOM, OCR, legenda de imagem).
    Mesmo shape de evidence de structured_fields.extract_application_instructions -
    nunca uma segunda implementacao de deteccao de e-mail."""
    instruction = detect_email_application(text or "")
    if not instruction:
        return None
    return {"value": {"recruiting_email": instruction.email, "subject": instruction.subject},
            "confidence": 85, "evidence_snippet": instruction.context,
            "extraction_method": "detect_email_application", "source_url": source_url}


_URL_INSTRUCTION_PATTERN = re.compile(
    r"(?:candidate-?se|inscreva-?se|acesse o link|acesse)\D{0,20}(https?://\S+)", re.IGNORECASE,
)


def extract_application_url_instruction(text: str, source_url: str | None = None) -> dict | None:
    """Secao 13 - "candidate-se pelo link..." - so aceita quando o link
    esta explicitamente associado a uma instrucao de candidatura (nunca
    qualquer URL solta no texto)."""
    match = _URL_INSTRUCTION_PATTERN.search(text or "")
    if not match:
        return None
    url = match.group(1).rstrip(").,;”’")
    return {"value": {"application_url": url}, "confidence": 75,
            "evidence_snippet": (text or "")[max(0, match.start() - 20):match.end() + 20].strip(),
            "extraction_method": "url_instruction_regex", "source_url": source_url}


# ---------------------------------------------------------------------------
# Secao 12 - WHATSAPP / PHONE
# ---------------------------------------------------------------------------

WHATSAPP_CLASSIFICATIONS = ("EXPLICIT_RECRUITING_WHATSAPP", "GENERIC_CONTACT", "UNKNOWN")

_WHATSAPP_MARKERS = re.compile(r"whats\s*app|\bwpp\b|zap\s*zap|chame no zap|chama no zap", re.IGNORECASE)
_RECRUITING_CONTEXT_MARKERS = re.compile(
    r"vaga|candidatura|curriculo|curr[ií]culo|\brh\b|recrutamento|processo seletivo|contrata",
    re.IGNORECASE,
)
_PHONE_PATTERN = re.compile(r"(?:\+?55\s*)?\(?(\d{2})\)?[\s.-]?(\d{4,5})[\s.-]?(\d{4})\b")
_CONTEXT_WINDOW = 60


def extract_whatsapp_contact(text: str) -> dict | None:
    """Secao 12 - so classifica EXPLICIT_RECRUITING_WHATSAPP quando o
    proprio texto menciona WhatsApp E um contexto de recrutamento real
    perto do numero - nunca assume que qualquer telefone publicado e
    WhatsApp de RH (achado do caso BMW/ACT: WhatsApp e explicitamente
    citado como canal de candidatura). Nunca inventa digitos - so
    normaliza o que ja esta no texto."""
    text = text or ""
    match = _PHONE_PATTERN.search(text)
    if not match:
        return None
    area, prefix, suffix = match.groups()
    window_start = max(0, match.start() - _CONTEXT_WINDOW)
    window_end = min(len(text), match.end() + _CONTEXT_WINDOW)
    context = text[window_start:window_end]
    mentions_whatsapp = bool(_WHATSAPP_MARKERS.search(context))
    mentions_recruiting = bool(_RECRUITING_CONTEXT_MARKERS.search(context))
    if mentions_whatsapp and mentions_recruiting:
        classification = "EXPLICIT_RECRUITING_WHATSAPP"
        confidence = 85
    elif mentions_whatsapp:
        classification = "GENERIC_CONTACT"
        confidence = 45
    else:
        classification = "UNKNOWN"
        confidence = 20
    return {"value": {"country_code": "55", "area_code": area, "number": f"{prefix}{suffix}",
                       "normalized": f"+55{area}{prefix}{suffix}"},
            "confidence": confidence, "evidence_snippet": context.strip(),
            "extraction_method": "whatsapp_regex", "classification": classification}


# ---------------------------------------------------------------------------
# Secao 8/9/10 - QR DETECTION / SECURITY PIPELINE / DESTINATION RESOLUTION
# ---------------------------------------------------------------------------

QR_STATUS_STATES = ("QR_PRESENT", "QR_DECODED", "QR_UNREADABLE", "DECODER_UNAVAILABLE")
QR_SCHEME_CLASSES = ("SAFE", "UNSAFE", "UNKNOWN_SCHEME")
QR_DESTINATION_CLASSES = ("OFFICIAL_ATS", "EXTERNAL_ATS", "OFFICIAL_CAREERS", "EXTERNAL_FORM",
                          "RECRUITING_EMAIL", "RECRUITER_WHATSAPP", "TALENT_POOL", "UNKNOWN")

_QR_PRESENCE_MARKERS = re.compile(r"qr\s*code|escaneie|aponte a camera|leia o (qr|codigo)", re.IGNORECASE)
_SAFE_QR_SCHEMES = {"https", "http", "mailto", "tel"}
_UNSAFE_QR_SCHEME_PREFIXES = ("javascript:", "data:", "file:", "vbscript:", "about:")
_WHATSAPP_HOSTS = ("wa.me", "api.whatsapp.com", "chat.whatsapp.com")


def detect_qr_presence(text: str) -> bool:
    """Secao 8 - sinal textual de que uma imagem/card MENCIONA um QR Code
    (ex.: 'escaneie o QR Code') - usado para decidir SE vale a pena tentar
    decodificar, nunca para inventar um payload."""
    return bool(_QR_PRESENCE_MARKERS.search(text or ""))


def classify_qr_scheme(payload: str) -> str:
    """Secao 9 - SAFE/UNSAFE/UNKNOWN_SCHEME. Rejeita explicitamente
    javascript:/data:/file:/vbscript:/about: - nunca executa payload
    algum, so classifica a string."""
    payload = (payload or "").strip()
    lowered = payload.lower()
    if any(lowered.startswith(prefix) for prefix in _UNSAFE_QR_SCHEME_PREFIXES):
        return "UNSAFE"
    scheme = urlsplit(payload).scheme.lower()
    if scheme in _SAFE_QR_SCHEMES:
        return "SAFE"
    if not scheme and re.fullmatch(r"[+\d][\d\s()-]{7,}", payload):
        # payload de telefone puro, sem URI scheme - seguro por
        # construcao (nunca executado, so um numero de texto).
        return "SAFE"
    return "UNKNOWN_SCHEME"


def _lower_starts(value: str, prefixes: tuple[str, ...]) -> bool:
    lowered = (value or "").lower()
    return any(lowered.startswith(prefix) for prefix in prefixes)


def normalize_qr_payload(payload: str) -> dict:
    """Secao 9 - NORMALIZE PAYLOAD, primeiro passo apos DECODE."""
    payload = (payload or "").strip()
    scheme_classification = classify_qr_scheme(payload)
    parsed = urlsplit(payload) if "://" in payload or _lower_starts(payload, ("mailto:", "tel:")) else None
    return {"raw_payload": payload, "scheme_classification": scheme_classification,
            "scheme": parsed.scheme.lower() if parsed else None}


def classify_qr_destination(normalized_payload: dict, final_url: str | None = None,
                            is_known_ats: bool = False, company_domain: str | None = None) -> str:
    """Secao 10 - DESTINATION RESOLUTION. O QR em si NUNCA vira application
    channel (Secao 8) - so o destino validado (final_url apos resolver
    redirect com seguranca, ja feito pelo caller) pode virar candidate.
    is_known_ats vem de ats_detection.detect_ats(final_url), reusado pelo
    caller - nunca reimplementado aqui."""
    if normalized_payload.get("scheme_classification") != "SAFE":
        return "UNKNOWN"
    scheme = normalized_payload.get("scheme")
    if scheme == "mailto":
        return "RECRUITING_EMAIL"
    if scheme == "tel" or (scheme is None and not final_url):
        # tel:/numero puro sozinho nunca prova WhatsApp de recrutamento -
        # so um numero (Secao 12: nunca assumir).
        return "UNKNOWN"
    if not final_url:
        return "UNKNOWN"
    host = urlsplit(final_url).netloc.lower()
    if any(wa_host in host for wa_host in _WHATSAPP_HOSTS):
        return "RECRUITER_WHATSAPP"
    same_company_domain = bool(company_domain and (host == company_domain.lower()
                                                     or host.endswith(f".{company_domain.lower()}")))
    if is_known_ats:
        return "OFFICIAL_ATS" if same_company_domain else "EXTERNAL_ATS"
    if same_company_domain:
        return "OFFICIAL_CAREERS"
    return "EXTERNAL_FORM"


def image_content_hash(image_bytes: bytes) -> str:
    """Secao 7 - cache por hash de imagem, nunca reprocessa OCR/QR na
    mesma imagem duas vezes."""
    return sha256(image_bytes).hexdigest()


def decode_qr_from_image_bytes(image_bytes: bytes) -> dict:
    """QR_DECODED/QR_UNREADABLE/DECODER_UNAVAILABLE (Secao 8). Decodifica
    localmente via Pillow/pyzbar (import tardio e opcional) - nunca envia
    a imagem para um servico externo. Se a biblioteca nao estiver
    disponivel no ambiente, retorna DECODER_UNAVAILABLE honestamente -
    NUNCA finge QR_UNREADABLE (Secao 28: falta de dependencia != falha do
    parser)."""
    try:
        from io import BytesIO

        from PIL import Image
        from pyzbar.pyzbar import decode as zbar_decode
    except ImportError:
        return {"status": "DECODER_UNAVAILABLE", "payload": None}
    try:
        image = Image.open(BytesIO(image_bytes))
        results = zbar_decode(image)
    except Exception:
        return {"status": "QR_UNREADABLE", "payload": None}
    if not results:
        return {"status": "QR_UNREADABLE", "payload": None}
    payload = results[0].data.decode("utf-8", errors="replace")
    return {"status": "QR_DECODED", "payload": payload}


# ---------------------------------------------------------------------------
# Secao 15/16 - MULTI-VACANCY CARD
# ---------------------------------------------------------------------------

_LIST_ITEM_PATTERN = re.compile(r"^[ \t]*(?:[-•*]|\d+[.)])[ \t]*(.+)$", re.MULTILINE)


def split_multi_vacancy_content(text: str) -> list[str]:
    """Secao 15/16 - so separa quando o conteudo tem uma lista CLARA de
    titulos de cargo (marcadores de lista/numeracao com pelo menos 2
    linhas reconheciveis como cargo) - nunca fragmenta um texto corrido em
    multiplas vagas por adivinhacao (Secao 15: 'nao criar Job cegamente
    por post')."""
    text = text or ""
    candidate_lines = [line.strip() for line in _LIST_ITEM_PATTERN.findall(text)]
    role_lines = [line for line in candidate_lines if any(marker in _normalize(line) for marker in _ROLE_TITLE_MARKERS)]
    if len(role_lines) >= 2:
        return role_lines
    stripped = text.strip()
    return [stripped] if stripped else []
