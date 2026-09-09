"""Profile Intelligence (Fase 2, Prompt 6) - resume -> profile evidence.

Extrai FATOS explicitamente presentes no curriculo aprovado e persistido -
nunca infere, nunca usa memoria de conversa do agente (Secao 15). Cada
fato preserva resume/version, evidence_snippet, confidence e
extracted_at. So DOCX e suportado nesta entrega: zipfile+regex, stdlib
puro, sem nova dependencia - o resume realmente ROTEADO hoje por
route_resume (GENERAL) e DOCX; o CURRENT (PDF) fica como gap documentado
(extracao de PDF exigiria uma dependencia nova, fora do escopo mínimo
deste prompt).
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
import re
import zipfile

EXTRACTION_METHOD = "docx_resume_evidence"


def extract_docx_text(file_bytes: bytes) -> str:
    with zipfile.ZipFile(BytesIO(file_bytes)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    text = re.sub(r"<[^>]+>", " ", xml)
    return re.sub(r"\s+", " ", text).strip()


def _section(text: str, start_marker: str, end_markers: list[str]) -> str | None:
    start_match = re.search(start_marker, text, re.IGNORECASE)
    if not start_match:
        return None
    start = start_match.end()
    end = len(text)
    for marker in end_markers:
        end_match = re.search(marker, text[start:], re.IGNORECASE)
        if end_match:
            end = min(end, start + end_match.start())
    return text[start:end].strip()


_LANGUAGE_ENTRY = re.compile(r"([A-Za-zÀ-ÿ]+)\s*:\s*([^|]+)")


def extract_language_levels(resume_text: str) -> dict[str, dict]:
    """So retorna o que o proprio curriculo afirma, verbatim - nunca
    infere fluencia a partir do idioma do documento (Secao 18). Cada
    idioma preserva o texto exato do curriculo como nivel (nao colapsa
    uma frase nuancada como 'technical reading and writing; spoken
    communication developing' em um rotulo de nivel limpo que ela nao
    afirma ser)."""
    section = _section(resume_text, r"\bLANGUAGES?\b", [r"\bADDITIONAL INFORMATION\b", r"\bTRAINING\b",
                                                          r"\bCERTIFICATIONS?\b", r"\bEDUCATION\b"])
    if not section:
        return {}
    levels: dict[str, dict] = {}
    for match in _LANGUAGE_ENTRY.finditer(section):
        language = match.group(1).strip()
        level = match.group(2).strip().rstrip(".")
        if language and level:
            levels[language] = {"value": level, "evidence_snippet": match.group(0).strip(),
                                 "confidence": 90, "extraction_method": EXTRACTION_METHOD}
    return levels


_EXPERIENCE_ENTRY = re.compile(
    r"([A-Za-zÀ-ÿ0-9/&() ]{3,80})\s*\|\s*([A-Za-zÀ-ÿ0-9.&() ]{2,80})\s*\|\s*"
    r"([A-Za-zÀ-ÿ, ]{2,60})\s*\|\s*((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}"
    r"\s*-\s*(?:Present|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{4}))"
)


def extract_employment_history(resume_text: str) -> list[dict]:
    """So aceita entradas no formato explicito 'Cargo | Empresa | Local |
    periodo' - nunca infere um emprego a partir de texto solto (Secao 16)."""
    section = _section(resume_text, r"\bPROFESSIONAL EXPERIENCE\b", [r"\bEDUCATION\b", r"\bTRAINING\b",
                                                                       r"\bLANGUAGES?\b"])
    if not section:
        return []
    entries = []
    for match in _EXPERIENCE_ENTRY.finditer(section):
        entries.append({
            "role": match.group(1).strip(), "company": match.group(2).strip(),
            "location": match.group(3).strip(), "period": match.group(4).strip(),
            "evidence_snippet": match.group(0).strip(), "confidence": 85,
            "extraction_method": EXTRACTION_METHOD,
        })
    return entries


def extract_education(resume_text: str) -> list[dict]:
    section = _section(resume_text, r"\bEDUCATION\b", [r"\bTRAINING\b", r"\bLANGUAGES?\b",
                                                          r"\bADDITIONAL INFORMATION\b"])
    if not section:
        return []
    entries = []
    for line in re.split(r"\s*\|\s*(?=[A-ZÀ-Ý])", section):
        line = line.strip().rstrip("|").strip()
        if len(line) >= 5:
            entries.append({"value": line, "evidence_snippet": line, "confidence": 80,
                             "extraction_method": EXTRACTION_METHOD})
    return entries


def extract_certifications(resume_text: str) -> list[dict]:
    section = _section(resume_text, r"\bTRAINING\b", [r"\bLANGUAGES?\b", r"\bADDITIONAL INFORMATION\b"])
    if not section:
        return []
    entries = []
    for line in re.split(r"\s*\|\s*(?=[A-ZÀ-Ý])", section):
        line = line.strip().rstrip("|").strip()
        if len(line) >= 5:
            entries.append({"value": line, "evidence_snippet": line, "confidence": 80,
                             "extraction_method": EXTRACTION_METHOD})
    return entries


def find_skill_mentions(resume_text: str, known_skill_names: list[str]) -> list[dict]:
    """Para cada skill JA DECLARADA (skills.name), verifica se o curriculo
    aprovado a menciona explicitamente - nunca cria uma skill nova, nunca
    marca VERIFIED so por achar a palavra (Secao 17: EVIDENCE_BACKED e
    suficiente, VERIFIED continua reservado para validacao mais forte)."""
    text_lower = resume_text.lower()
    mentions = []
    for name in known_skill_names:
        name_norm = name.strip().lower()
        if not name_norm:
            continue
        pattern = re.compile(rf"\b{re.escape(name_norm)}\b", re.IGNORECASE)
        match = pattern.search(resume_text)
        if match:
            start, end = max(0, match.start() - 60), min(len(resume_text), match.end() + 60)
            mentions.append({"skill_name": name, "evidence_snippet": resume_text[start:end].strip(),
                              "confidence": 75, "extraction_method": EXTRACTION_METHOD})
    _ = text_lower  # mantido por clareza semantica (busca real e via regex acima)
    return mentions


def extract_profile_evidence(resume_text: str, known_skill_names: list[str]) -> dict:
    return {
        "language_levels": extract_language_levels(resume_text),
        "employment": extract_employment_history(resume_text),
        "education": extract_education(resume_text),
        "certifications": extract_certifications(resume_text),
        "skill_mentions": find_skill_mentions(resume_text, known_skill_names),
        "extracted_at": datetime.now(UTC).isoformat(),
    }
