"""Verificacao independente da evidencia citada pela IA ao gerar respostas.

A Auditoria Funcional de 21/08/2026 apontou que tanto `local_ai_advice`
quanto `ai_fill_simple_questions` (main.py) so conferem se a propria IA
autodeclarou confidence/evidence altos - nunca se a evidencia citada de
fato aparece no curriculo/perfil real. Uma IA que alucina pode citar uma
evidencia plausivel e uma confianca alta ao mesmo tempo; autodeclaracao da
mesma IA que gerou a resposta nao e prova. Este modulo faz essa segunda
checagem, independente e sem depender de outra chamada de IA, antes da
resposta ser aceita.

Sem dependencias de Playwright/FastAPI (mesmo padrao de ats_detection.py,
hard_blocks.py e kill_switches.py) para poder ser testado isoladamente.
"""

import re

_STOPWORDS = {"para", "com", "uma", "das", "dos", "and", "the"}


def normalized_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9+#.]{2,}", value.lower()) if token not in _STOPWORDS}


def is_evidence_grounded(evidence: str, *sources: str, minimum_overlap: float = 0.6) -> bool:
    """True se a evidencia citada tiver sobreposicao real com as fontes verificadas.

    Evidencia vazia ou curta demais para checar (menos de 2 tokens) nunca e
    considerada fundamentada - a IA ja e instruida a nao responder sem prova,
    entao uma evidencia vazia/vaga e ela mesma um sinal de alucinacao.
    """
    evidence_tokens = normalized_tokens(evidence)
    if len(evidence_tokens) < 2:
        return False
    source_tokens: set[str] = set()
    for source in sources:
        source_tokens |= normalized_tokens(source)
    if not source_tokens:
        return False
    overlap = len(evidence_tokens & source_tokens) / len(evidence_tokens)
    return overlap >= minimum_overlap
