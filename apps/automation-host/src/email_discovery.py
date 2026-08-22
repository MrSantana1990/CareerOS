"""Deteccao de instrucao de candidatura por e-mail em texto de vaga.

Fase 10 do Plano Mestre - Email Discovery Engine. Este modulo so DETECTA e
EXTRAI; nao envia nada, nao gera mensagem, nao decide nada sozinho - isso
sao os proximos passos da Fase 10 (grounding, geracao de mensagem, anexo,
envio com aprovacao humana), fora do escopo desta entrega.

Regra de seguranca: nunca inventar e-mail nem assunto. Se o texto so
menciona um e-mail sem instrucao explicita de candidatura (ex: contato de
RH generico no rodape), ou se o unico e-mail encontrado e no-reply, o
resultado e None - silencio e melhor que um palpite errado aqui.

Sem dependencias de Playwright/FastAPI (mesmo padrao de ats_detection.py,
hard_blocks.py, kill_switches.py e evidence_check.py).
"""

from dataclasses import dataclass
import re

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}")

_APPLY_INSTRUCTION_PATTERN = re.compile(
    r"(envie|enviar|mande|mandar|encaminhe|encaminhar|submeta|submeter|cadastr\w+|"
    r"send|submit|email)\s+(seu\s+|your\s+|o\s+)?(curr[ií]culo|cv|curriculum|resume)",
    re.IGNORECASE,
)

_NO_REPLY_PATTERN = re.compile(r"no-?reply|nao-?responda|do-?not-?reply", re.IGNORECASE)

_SUBJECT_INSTRUCTION_PATTERN = re.compile(
    r"assunto[:\s]+[\"“]?([^\"”\n]{3,120})|subject[:\s]+[\"“]?([^\"”\n]{3,120})",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class EmailApplicationInstruction:
    email: str
    subject: str | None
    context: str


def detect_email_application(text: str) -> EmailApplicationInstruction | None:
    """Retorna a instrução de candidatura por e-mail encontrada no texto, ou
    None quando não há e-mail, o único e-mail é no-reply, ou não há nenhuma
    instrução explícita de candidatura (um e-mail de contato genérico sem
    instrução de envio de currículo não conta)."""
    if not text:
        return None
    instruction_match = _APPLY_INSTRUCTION_PATTERN.search(text)
    if not instruction_match:
        return None
    candidates = [match.group(0) for match in _EMAIL_PATTERN.finditer(text) if not _NO_REPLY_PATTERN.search(match.group(0))]
    if not candidates:
        return None
    best_email, best_distance = candidates[0], None
    for email in candidates:
        position = text.find(email)
        distance = abs(position - instruction_match.start())
        if best_distance is None or distance < best_distance:
            best_email, best_distance = email, distance
    subject_match = _SUBJECT_INSTRUCTION_PATTERN.search(text)
    subject = None
    if subject_match:
        subject = (subject_match.group(1) or subject_match.group(2) or "").strip() or None
    context = text[max(0, instruction_match.start() - 40) : instruction_match.end() + 80].strip()
    return EmailApplicationInstruction(email=best_email, subject=subject, context=context)
