"""Market Signal source (Fase 2, Prompt 3) - Google News RSS.

P0 do Blueprint (Prompt 1): Signal Intelligence nao tinha nenhuma fonte
autonoma real - os Cycles 008-010 usaram WebSearch manual do agente, o que
nao e aceitavel como dependencia de producao (secao 30 do Prompt 3).

Fonte escolhida: RSS de busca do Google News
(news.google.com/rss/search?q=...). Justificativa (ver Source Selection
Report na entrega do Prompt 3): formato RSS 2.0 publico, documentado,
pensado para consumo programatico (syndication), sem autenticacao, sem
paywall, cobertura real do Brasil/pt-BR, permite query direcionada (reduz
ruido na fonte, antes de qualquer parsing) - ao contrario de um feed
generico de uma unica editoria, que exigiria filtrar por palavra-chave
depois de baixar tudo.

Modulo stdlib puro (urllib + xml.etree, sem Playwright/FastAPI) - mesma
razao de ats_detection.py/hard_blocks.py: testavel sem instalar as
dependencias pesadas do pacote no CI. Nenhuma chamada de rede acontece em
import time; fetch_rss() e a unica funcao com efeito de rede, isolada das
funcoes puras (parse/classify/resolve) para poderem ser testadas com
fixtures, sem depender de internet real no CI.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree
import re

RSS_BASE_URL = "https://news.google.com/rss/search"

# Consulta pequena e direcionada (secao 38: nao escalar para centenas de
# fontes) - geografia/perfil ja estabelecidos ao longo da sessao (Campinas
# primeiro, tech/remoto Brasil depois), nao um firehose generico.
DEFAULT_QUERIES = [
    "empresa expansão OR investimento OR escritório Campinas",
    "empresa expansão OR investimento tecnologia Brasil contratação",
]

_EXPANSION = re.compile(r"expans[aã]o|nov[ao] (?:escrit[oó]rio|unidade|opera[çc][aã]o|filial)", re.IGNORECASE)
_INVESTMENT = re.compile(r"investimento|investe|aporte", re.IGNORECASE)
_HIRING = re.compile(r"contrata[çc][aã]o|vagas de emprego|nova equipe|expande equipe", re.IGNORECASE)
_NEW_OFFICE = re.compile(r"in[aá]ugur|nov[ao] escrit[oó]rio|nova sede", re.IGNORECASE)


@dataclass(frozen=True)
class RawSignal:
    title: str
    link: str
    source: str | None
    published_at: str | None


def build_rss_url(query: str) -> str:
    return f"{RSS_BASE_URL}?q={quote_plus(query)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"


def fetch_rss(url: str, timeout: int = 20) -> str:
    request = Request(url, headers={"User-Agent": "CareerOS-MarketScan/1.0 (production, respectful, 1x/day)"})
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"Fonte respondeu HTTP {response.status}.")
        return response.read().decode("utf-8", errors="replace")


def parse_rss_items(xml_text: str) -> list[RawSignal]:
    root = ElementTree.fromstring(xml_text)
    items: list[RawSignal] = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        source_el = item.find("source")
        source = source_el.text.strip() if source_el is not None and source_el.text else None
        published_at = (item.findtext("pubDate") or "").strip() or None
        items.append(RawSignal(title=title, link=link, source=source, published_at=published_at))
    return items


def classify_signal_type(title: str) -> str:
    """Classificacao grosseira por palavra-chave - nao exige perfeicao
    (secao 4). Quando incerto, OTHER_VERIFIED_SIGNAL em vez de arriscar uma
    classificacao especifica errada."""
    if _NEW_OFFICE.search(title):
        return "NEW_OFFICE"
    if _EXPANSION.search(title):
        return "EXPANSION"
    if _INVESTMENT.search(title):
        return "INVESTMENT"
    if _HIRING.search(title):
        return "HIRING_ANNOUNCEMENT"
    return "OTHER_VERIFIED_SIGNAL"


def build_job_discovered_signal_payload(*, company_id: str | None, source_url: str,
                                         headline: str, job_fingerprint: str) -> dict:
    """JOB_DISCOVERED e provenance, nunca uma copia da vaga (secao 11/12):
    so source_url/headline/evidence com a fingerprint como referencia -
    Job continua o registro canonico. Nao chamada em massa para o
    historico (secao 12) - so para eventos novos, e so uma prova de
    conceito nesta entrega (wiring real no outbox fica para depois, ver
    known gaps do Prompt 3 - estender o outbox pra um novo kind="SIGNAL"
    e um risco maior do que o escopo deste prompt justifica agora)."""
    return {
        "type": "JOB_DISCOVERED",
        "company_id": company_id,
        "source_url": source_url,
        "source_type": "JOB_BOARD",
        "headline": headline[:300],
        "summary": None,
        "confidence": 90,
        "evidence": {"job_fingerprint": job_fingerprint},
    }


def resolve_company(title: str, known_company_names: list[str]) -> str | None:
    """Resolucao CONSERVADORA (secao 5): so vincula a uma Company que ja
    existe no Core (match de PALAVRA INTEIRA, case-insensitive, do nome
    real) - nunca cria nem adivinha uma empresa nova a partir de uma
    manchete. Sem match real, retorna None e o Signal e persistido com
    company_id nulo (permitido pelo schema desde o Prompt 2).

    Achado real na validacao do Prompt 4 (amostra real de Signals em
    producao): uma Company chamada "EXA" batia via substring simples em
    toda manchete que terminava com "- Exame" (o nome da propria fonte
    jornalistica, nao da empresa) - 9 dos ~15 Signals resolvidos da
    amostra eram esse falso-positivo. Substring simples (`in`) nao respeita
    fronteira de palavra; corrigido para exigir \\b nome \\b via regex."""
    matches = [name for name in known_company_names
               if len(name) >= 3 and re.search(rf"\b{re.escape(name.lower())}\b", title.lower())]
    if not matches:
        return None
    # Nome mais longo primeiro - evita casar um nome generico curto que e
    # substring acidental de outro nome real mais especifico.
    return max(matches, key=len)
