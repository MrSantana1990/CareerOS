import base64
import json
import re
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
]


def _credentials(token_path: Path) -> Credentials:
    return Credentials.from_authorized_user_file(str(token_path), SCOPES)


def connection_status(token_path: Path) -> dict:
    if not token_path.exists():
        return {"connected": False, "email": None, "calendar": False}
    credentials = _credentials(token_path)
    gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    calendar = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    profile = gmail.users().getProfile(userId="me").execute()
    calendar.events().list(calendarId="primary", maxResults=1, singleEvents=True).execute()
    return {"connected": True, "email": profile.get("emailAddress"), "calendar": True}


def create_application_email_draft(token_path: Path, recipient: str, subject: str, body: str,
                                   resume_path: Path) -> dict:
    credentials = _credentials(token_path)
    gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    message = EmailMessage()
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    subtype = "pdf" if resume_path.suffix.lower() == ".pdf" else "vnd.openxmlformats-officedocument.wordprocessingml.document"
    message.add_attachment(resume_path.read_bytes(), maintype="application", subtype=subtype,
                           filename=resume_path.name)
    raw = base64.urlsafe_b64encode(message.as_bytes()).decode()
    draft = gmail.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return {"draft_id": draft["id"]}


def _headers(payload: dict) -> dict[str, str]:
    return {item.get("name", "").lower(): item.get("value", "") for item in payload.get("headers", [])}


def _body(payload: dict) -> str:
    data = payload.get("body", {}).get("data")
    if data and payload.get("mimeType") in {"text/plain", "text/html"}:
        decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
        return re.sub(r"<[^>]+>", " ", decoded) if payload.get("mimeType") == "text/html" else decoded
    parts = payload.get("parts", [])
    plain = next((part for part in parts if part.get("mimeType") == "text/plain"), None)
    ordered = ([plain] if plain else []) + [part for part in parts if part is not plain]
    return "\n".join(_body(part) for part in ordered)[:30000]


def _links(payload: dict) -> list[str]:
    found: list[str] = []
    data = payload.get("body", {}).get("data")
    if data:
        decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", errors="replace")
        found.extend(re.findall(r"https?://[^\s\"'<>]+", decoded))
        found.extend(re.findall(r"href=[\"'](https?://[^\"']+)", decoded, re.IGNORECASE))
    for part in payload.get("parts", []):
        found.extend(_links(part))
    cleaned = []
    for url in found:
        url = url.replace("&amp;", "&").rstrip(".,);]")
        if url not in cleaned:
            cleaned.append(url)
    return cleaned


def _questionnaire_url(urls: list[str]) -> str | None:
    blocked = ("unsubscribe", "descadastrar", "privacy", "privacidade", "facebook.com", "instagram.com", "tiktok.com", "x.com/", "xiti.com", "googleapis.com", "gstatic.com", "blob.core.windows.net", "ncdn.infojobs.com.br", "stc.infojobs.com.br")
    candidates = [url for url in urls if not any(term in url.lower() for term in blocked) and not re.search(r"\.(?:png|jpe?g|gif|svg|webp)(?:\?|$)", url, re.IGNORECASE)]
    priorities = [
        lambda url: "pandape.infojobs.com.br/test" in url.lower(),
        lambda url: any(term in url.lower() for term in ("forms.gle", "docs.google.com/forms", "typeform.com", "forms.office.com")),
        lambda url: "dataannotation.tech/coding" in url.lower(),
        lambda url: any(term in url.lower() for term in ("questionario", "questionnaire", "assessment", "/test")),
    ]
    for predicate in priorities:
        match = next((url for url in candidates if predicate(url)), None)
        if match:
            return match
    return None


def _questionnaire_state(gmail, message: dict, body: str, previous: dict) -> str:
    if previous.get("questionnaire_status") == "COMPLETED_MANUALLY":
        return "COMPLETED_MANUALLY"
    evidence = r"respostas? (?:foram )?(?:registradas?|recebidas?)|question[aá]rio (?:foi )?(?:conclu[ií]do|respondido)|obrigad[oa] por responder"
    if re.search(evidence, body, re.IGNORECASE):
        return "COMPLETED_CONFIRMED"
    thread = gmail.users().threads().get(userId="me", id=message.get("threadId"), format="full").execute()
    for thread_message in thread.get("messages", []):
        thread_body = _body(thread_message.get("payload", {}))
        if re.search(evidence, thread_body, re.IGNORECASE):
            return "COMPLETED_CONFIRMED"
        if "SENT" in thread_message.get("labelIds", []):
            return "COMPLETED_BY_REPLY"
    return "PENDING_UNCONFIRMED"


def _validate_questionnaire_link(url: str | None) -> dict:
    checked_at = datetime.now(UTC).isoformat()
    if not url:
        return {"status": "LINK_NOT_FOUND", "checked_at": checked_at}
    try:
        request = Request(url, headers={"User-Agent": "Mozilla/5.0 CareerOS-LinkValidator/1.0"}, method="GET")
        with urlopen(request, timeout=20) as response:
            final = urlparse(response.geturl())
            status = "COMPLETED_CONFIRMED" if "/test/testresult" in final.path.lower() else "ACTIVE"
            return {"status": status, "http_status": response.status, "final_host": final.netloc, "final_path": final.path, "checked_at": checked_at}
    except HTTPError as exc:
        status = "UNAVAILABLE" if exc.code in {404, 410} else "HTTP_ERROR"
        return {"status": status, "http_status": exc.code, "final_host": urlparse(exc.url).netloc, "checked_at": checked_at}
    except (URLError, TimeoutError):
        return {"status": "VALIDATION_ERROR", "checked_at": checked_at}


def _classify(subject: str, body: str) -> tuple[str, int, str]:
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


def _suggestion(category: str) -> str:
    if category in {"INTERVIEW", "RECRUITER"}:
        return "Olá! Obrigado pelo contato e pelo interesse no meu perfil. Tenho interesse em conversar sobre a oportunidade. Poderia confirmar a data, o horário, o fuso e o formato da conversa? Atenciosamente, Rodolfo Santana."
    if category == "QUESTIONNAIRE":
        return "Olá! Obrigado pelo envio. Recebi as orientações e vou analisar o questionário dentro do prazo informado. Atenciosamente, Rodolfo Santana."
    if category == "OFFER":
        return "Olá! Obrigado pela proposta e pela confiança. Confirmo o recebimento e gostaria de revisar os detalhes antes de responder formalmente. Atenciosamente, Rodolfo Santana."
    return ""


def _event_candidate(subject: str, body: str) -> dict | None:
    text = f"{subject}\n{body}"
    match = re.search(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b.{0,120}?\b(?:às|as|at)?\s*(\d{1,2})[:h](\d{2})\b", text, re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    day, month, year, hour, minute = map(int, match.groups())
    try:
        start = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo("America/Sao_Paulo"))
    except ValueError:
        return None
    if start < datetime.now(ZoneInfo("America/Sao_Paulo")) - timedelta(hours=1):
        return None
    return {"title": f"Processo seletivo: {subject}"[:180], "start": start.isoformat(), "end": (start + timedelta(hours=1)).isoformat(), "timezone": "America/Sao_Paulo"}


def scan_recruitment_mail(token_path: Path, store_path: Path, days: int = 30, limit: int = 100) -> dict:
    credentials = _credentials(token_path)
    gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    query = f"newer_than:{days}d (vaga OR oportunidade OR entrevista OR recrutamento OR candidatura OR processo seletivo OR questionnaire OR interview)"
    result = gmail.users().messages().list(userId="me", q=query, maxResults=limit).execute()
    questionnaire_query = "newer_than:180d (subject:questionario OR subject:questionário OR subject:questionnaire OR subject:assessment OR subject:(teste técnico))"
    questionnaire_result = gmail.users().messages().list(userId="me", q=questionnaire_query, maxResults=100).execute()
    references = {item["id"]: item for item in result.get("messages", [])}
    references.update({item["id"]: item for item in questionnaire_result.get("messages", [])})
    existing = json.loads(store_path.read_text(encoding="utf-8")) if store_path.exists() else []
    previous = {item["message_id"]: item for item in existing}
    by_id = {}
    discovered = 0
    for reference in references.values():
        message = gmail.users().messages().get(userId="me", id=reference["id"], format="full").execute()
        headers = _headers(message.get("payload", {}))
        body = _body(message.get("payload", {}))
        category, confidence, reason = _classify(headers.get("subject", ""), body)
        if category == "OTHER":
            continue
        previous_item = previous.get(message["id"], {})
        questionnaire_url = _questionnaire_url(_links(message.get("payload", {}))) if category == "QUESTIONNAIRE" else None
        previous_validation = previous_item.get("questionnaire_validation")
        questionnaire_validation = None
        if category == "QUESTIONNAIRE":
            if previous_item.get("questionnaire_url") == questionnaire_url and previous_validation and previous_validation.get("checked_at"):
                try:
                    validation_age = datetime.now(UTC) - datetime.fromisoformat(previous_validation["checked_at"])
                    questionnaire_validation = previous_validation if validation_age.total_seconds() < 21600 else None
                except (TypeError, ValueError):
                    questionnaire_validation = None
            questionnaire_validation = questionnaire_validation or _validate_questionnaire_link(questionnaire_url)
        questionnaire_status = _questionnaire_state(gmail, message, body, previous_item) if category == "QUESTIONNAIRE" else None
        if questionnaire_validation and questionnaire_validation["status"] == "COMPLETED_CONFIRMED":
            questionnaire_status = "COMPLETED_CONFIRMED"
        elif questionnaire_validation and questionnaire_validation["status"] == "UNAVAILABLE" and not str(questionnaire_status).startswith("COMPLETED"):
            questionnaire_status = "UNAVAILABLE"
            questionnaire_url = None
        item = {
            "message_id": message["id"], "thread_id": message.get("threadId"),
            "subject": headers.get("subject", "(sem assunto)"), "sender": headers.get("from", ""),
            "received_at": datetime.fromtimestamp(int(message.get("internalDate", "0")) / 1000, UTC).isoformat(),
            "category": category, "confidence": confidence, "reason": reason,
            "snippet": message.get("snippet", "")[:500], "status": "NEW",
            "suggested_reply": _suggestion(category),
            "draft_id": previous.get(message["id"], {}).get("draft_id"),
            "calendar_event_id": previous.get(message["id"], {}).get("calendar_event_id"),
            "event_candidate": _event_candidate(headers.get("subject", ""), body) if category == "INTERVIEW" else None,
            "questionnaire_url": questionnaire_url,
            "questionnaire_status": questionnaire_status,
            "questionnaire_validation": questionnaire_validation,
        }
        if item["draft_id"]:
            item["status"] = "DRAFT_CREATED"
        if item["calendar_event_id"]:
            item["status"] = "CALENDAR_SCHEDULED"
        by_id[item["message_id"]] = item
        if item["message_id"] not in previous:
            discovered += 1
    items = sorted(by_id.values(), key=lambda item: item.get("received_at", ""), reverse=True)[:500]
    store_path.parent.mkdir(parents=True, exist_ok=True)
    store_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"scanned": len(references), "discovered": discovered, "items": items}


def create_reply_draft(token_path: Path, store_path: Path, message_id: str) -> dict:
    items = json.loads(store_path.read_text(encoding="utf-8"))
    item = next((candidate for candidate in items if candidate["message_id"] == message_id), None)
    if not item or not item.get("suggested_reply"):
        raise ValueError("Mensagem sem resposta segura sugerida.")
    if item.get("draft_id"):
        return item
    credentials = _credentials(token_path)
    gmail = build("gmail", "v1", credentials=credentials, cache_discovery=False)
    original = gmail.users().messages().get(userId="me", id=message_id, format="metadata", metadataHeaders=["From", "Subject", "Message-ID", "References"]).execute()
    headers = _headers(original.get("payload", {}))
    reply = EmailMessage()
    reply["To"] = headers.get("from", "")
    reply["Subject"] = headers.get("subject", "") if headers.get("subject", "").lower().startswith("re:") else f"Re: {headers.get('subject', '')}"
    if headers.get("message-id"):
        reply["In-Reply-To"] = headers["message-id"]
        reply["References"] = f"{headers.get('references', '')} {headers['message-id']}".strip()
    reply.set_content(item["suggested_reply"])
    raw = base64.urlsafe_b64encode(reply.as_bytes()).decode("ascii")
    draft = gmail.users().drafts().create(userId="me", body={"message": {"raw": raw, "threadId": item.get("thread_id")}}).execute()
    item["draft_id"] = draft.get("id")
    item["status"] = "DRAFT_CREATED"
    store_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return item


def create_calendar_event(token_path: Path, store_path: Path, message_id: str) -> dict:
    items = json.loads(store_path.read_text(encoding="utf-8"))
    item = next((candidate for candidate in items if candidate["message_id"] == message_id), None)
    if not item or not item.get("event_candidate"):
        raise ValueError("O e-mail não contém data e horário exatos para agendamento seguro.")
    if item.get("calendar_event_id"):
        return item
    candidate = item["event_candidate"]
    credentials = _credentials(token_path)
    calendar = build("calendar", "v3", credentials=credentials, cache_discovery=False)
    existing = calendar.events().list(
        calendarId="primary", timeMin=candidate["start"], timeMax=candidate["end"],
        singleEvents=True, maxResults=10,
    ).execute().get("items", [])
    duplicate = next((event for event in existing if event.get("summary") == candidate["title"]), None)
    if duplicate:
        event = duplicate
    else:
        event = calendar.events().insert(calendarId="primary", body={
            "summary": candidate["title"],
            "description": f"Criado pelo CareerOS a partir do e-mail: {item['subject']}\nRemetente: {item['sender']}",
            "start": {"dateTime": candidate["start"], "timeZone": candidate["timezone"]},
            "end": {"dateTime": candidate["end"], "timeZone": candidate["timezone"]},
            "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 60}, {"method": "popup", "minutes": 1440}]},
        }).execute()
    item["calendar_event_id"] = event.get("id")
    item["status"] = "CALENDAR_SCHEDULED"
    store_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return item


def mark_questionnaire_complete(store_path: Path, message_id: str) -> dict:
    items = json.loads(store_path.read_text(encoding="utf-8"))
    item = next((candidate for candidate in items if candidate["message_id"] == message_id), None)
    if not item or item.get("category") != "QUESTIONNAIRE":
        raise ValueError("Questionário não encontrado.")
    item["questionnaire_status"] = "COMPLETED_MANUALLY"
    item["status"] = "COMPLETED"
    store_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return item
