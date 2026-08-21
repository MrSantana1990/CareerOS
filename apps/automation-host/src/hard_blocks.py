"""Bloqueios de seguranca por texto livre para vagas descobertas via navegador.

Modulo stdlib puro (sem Playwright/FastAPI/Pydantic), no mesmo espirito de
`ats_detection.py`, para ser testavel isoladamente — o CI do automation-host
roda os testes sem instalar as dependencias do proprio pacote.

Espelha, de forma aproximada, os hard blocks equivalentes de
`apps/api/src/quality.py::score_job` (GUPY_BLOCK ja existe em main.py,
SPANISH_FLUENT_BLOCK, ENGLISH_C1_REVIEW, RELOCATION_REQUIRED,
SUPPORT_N1_MINIMUM). O Core usa campos estruturados (ex.:
`language_requirements`) que nao existem aqui — o automation-host so tem o
texto raspado da pagina, entao esta e uma heuristica de seguranca por
palavra-chave, nao uma replica garantida das mesmas regras. Se as regras do
Core mudarem, revisar este arquivo tambem.
"""
from dataclasses import dataclass
import re

SUPPORT_N1_MINIMUM_SALARY = 4000


@dataclass(frozen=True)
class HardBlockResult:
    blocks: list[str]  # motivos que devem impedir a candidatura
    risks: list[str]   # motivos que exigem atencao humana, sem bloquear


def extract_salary_brl(text: str) -> int | None:
    values: list[int] = []
    for match in re.finditer(r"R\$\s*([\d.]+)(?:,\d{2})?", text, re.IGNORECASE):
        raw = match.group(1).replace(".", "")
        if raw.isdigit() and 1000 <= int(raw) <= 100000:
            values.append(int(raw))
    return min(values) if values else None


_RELOCATION_EN = re.compile(r"relocat", re.IGNORECASE)
_REQUIRED_EN = re.compile(r"\brequired\b", re.IGNORECASE)
_RELOCATION_PT = re.compile(r"mudan[çc]a", re.IGNORECASE)
_OBRIGATORIO_PT = re.compile(r"obrigat[oó]ri", re.IGNORECASE)

_SPANISH = re.compile(r"espanhol|spanish", re.IGNORECASE)
_ENGLISH = re.compile(r"ingl[eê]s|english", re.IGNORECASE)
_FLUENT_LEVEL = re.compile(
    r"fluente|fluent|nativo|native|avan[çc]ado|advanced|\bc1\b|\bc2\b", re.IGNORECASE
)

_SUPPORT_N1 = re.compile(r"\bn1\b|suporte n1|n[ií]vel\s*1\b", re.IGNORECASE)


def assess_hard_blocks(text: str, salary_brl: int | None) -> HardBlockResult:
    blocks: list[str] = []
    risks: list[str] = []

    if (_RELOCATION_EN.search(text) and _REQUIRED_EN.search(text)) or (
        _RELOCATION_PT.search(text) and _OBRIGATORIO_PT.search(text)
    ):
        blocks.append("RELOCATION_REQUIRED")

    if _SPANISH.search(text) and _FLUENT_LEVEL.search(text):
        blocks.append("SPANISH_FLUENT_BLOCK")

    if _SUPPORT_N1.search(text) and salary_brl is not None and salary_brl < SUPPORT_N1_MINIMUM_SALARY:
        blocks.append("SUPPORT_N1_MINIMUM")

    if _ENGLISH.search(text) and _FLUENT_LEVEL.search(text):
        risks.append("ENGLISH_C1_REVIEW")

    return HardBlockResult(blocks=blocks, risks=risks)
