"""Classificacao de resposta de e-mail e elegibilidade de follow-up.

Modulo stdlib puro (mesmo espirito de hard_blocks.py/ats_detection.py/
core_bridge.py), sem nenhuma dependencia do cliente Gmail (google-api-
python-client), justamente para poder ser importado e testado no CI do
automation-host sem instalar essas dependencias pesadas. google_career.py
faz as chamadas reais de API e usa estas funcoes so pela decisao.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import re


def classify_recruitment_mail(subject: str, body: str) -> tuple[str, int, str]:
    subject_text = subject.lower()
    text = f"{subject} {body}".lower()
    rules = [
        ("INTERVIEW", 98, r"entrevista|interview|convite.*(?:conversa|reuni[aã]o)|agendamento"),
        ("QUESTIONNAIRE", 94, r"question[aá]rio|teste t[eé]cnico|assessment|desafio t[eé]cnico"),
        ("OFFER", 99, r"carta proposta|proposta de trabalho|job offer|oferta de emprego"),
        ("REJECTION", 96, r"n[aã]o seguiremos|n[aã]o avan[cç]aremos|processo encerrado"),
        ("APPLICATION_CONFIRMED", 92, r"candidatura (?:foi )?(?:recebida|enviada)|confirma[cç][aã]o de inscri[cç][aã]o|application received"),
    ]
    for category, confidence, pattern in rules:
        if re.search(pattern, subject_text, re.IGNORECASE):
            return category, confidence, f"Assunto indica {category.lower().replace('_', ' ')}."
    if re.search(r"gostar[ií]amos?.{0,80}(?:entrevista|conversa)|convidamos?.{0,80}(?:entrevista|processo seletivo)", text):
        return "INTERVIEW", 92, "Conteúdo contém convite direto para conversa ou entrevista."
    if re.search(r"n[aã]o seguiremos|n[aã]o avan[cç]aremos|optamos por outro candidato", text):
        return "REJECTION", 92, "Conteúdo informa encerramento da candidatura."
    if re.search(r"oportunidade (?:profissional|de trabalho)|contato sobre (?:uma )?vaga|seu perfil.{0,80}(?:vaga|oportunidade)", subject_text):
        return "RECRUITER", 86, "Assunto indica contato individual sobre oportunidade."
    return "OTHER", 40, "Sem evidência suficiente de processo seletivo."


def suggested_reply(category: str) -> str:
    if category in {"INTERVIEW", "RECRUITER"}:
        return "Olá! Obrigado pelo contato e pelo interesse no meu perfil. Tenho interesse em conversar sobre a oportunidade. Poderia confirmar a data, o horário, o fuso e o formato da conversa? Atenciosamente, Rodolfo Santana."
    if category == "QUESTIONNAIRE":
        return "Olá! Obrigado pelo envio. Recebi as orientações e vou analisar o questionário dentro do prazo informado. Atenciosamente, Rodolfo Santana."
    if category == "OFFER":
        return "Olá! Obrigado pela proposta e pela confiança. Confirmo o recebimento e gostaria de revisar os detalhes antes de responder formalmente. Atenciosamente, Rodolfo Santana."
    return ""


def classify_application_thread_reply(sender: str, subject: str, body: str,
                                       auto_submitted_header: str) -> tuple[str, int, str]:
    """Cycle 010: rastrear uma candidatura especifica exige distinguir uma
    resposta humana real de bounce/auto-reply - classify_recruitment_mail
    (usado pelo scan de caixa de entrada) nunca precisou disso porque so
    processa mensagens que ja bateram no filtro de busca por palavras-chave
    de processo seletivo, o que uma notificacao de falha de entrega nunca
    conteria. Auto-Submitted e um header RFC 3834 real, mais confiavel que
    adivinhar por assunto."""
    sender_lower = sender.lower()
    subject_lower = subject.lower()
    if auto_submitted_header and auto_submitted_header.strip().lower() != "no":
        return "AUTO_REPLY", 95, "Header Auto-Submitted indica resposta automática, não humana."
    if re.search(r"mailer-daemon|postmaster|mail delivery subsystem|delivery subsystem", sender_lower):
        return "DELIVERY_FAILURE", 95, "Remetente é um sistema de entrega de e-mail, não um humano."
    if re.search(r"delivery status notification|undelivered mail|couldn.?t be delivered|returned to sender|failure notice|delivery has failed|falha na entrega", subject_lower):
        return "DELIVERY_FAILURE", 92, "Assunto indica falha de entrega do e-mail."
    if re.search(r"resposta autom[aá]tica|auto-?reply|out of office|ausente do escrit[oó]rio|estou de f[eé]rias", subject_lower):
        return "AUTO_REPLY", 85, "Assunto indica resposta automática (ausência/férias)."
    category, confidence, reason = classify_recruitment_mail(subject, body)
    if category == "INTERVIEW":
        return "INTERVIEW_REQUEST", confidence, reason
    if category in {"RECRUITER", "APPLICATION_CONFIRMED", "OFFER"}:
        return "RECRUITER_RESPONSE", confidence, reason
    if category == "REJECTION":
        return "REJECTION", confidence, reason
    return "OTHER_REPLY", confidence, reason


FOLLOW_UP_MINIMUM_DAYS = 7


def follow_up_status(sent_at: datetime, now: datetime | None = None) -> dict:
    """Cycle 010: nenhum mecanismo de follow-up existia (a migration
    'communication_followup' so persiste comunicacoes recebidas, nunca
    agenda um reenvio) - isso so decide ELEGIBILIDADE (nunca envia
    sozinho, nunca em loop de spam). Um follow-up de verdade continua
    exigindo uma chamada explicita, com o mesmo contexto real da vaga."""
    now = now or datetime.now(UTC)
    eligible_at = sent_at + timedelta(days=FOLLOW_UP_MINIMUM_DAYS)
    if now >= eligible_at:
        return {"eligible": True, "eligible_at": eligible_at.isoformat(), "days_remaining": 0}
    remaining = (eligible_at - now).days + (1 if (eligible_at - now).seconds else 0)
    return {"eligible": False, "eligible_at": eligible_at.isoformat(), "days_remaining": max(remaining, 0)}
