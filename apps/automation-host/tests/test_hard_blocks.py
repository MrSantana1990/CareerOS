import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.hard_blocks import assess_hard_blocks, extract_salary_brl  # noqa: E402


def test_extract_salary_brl_picks_lowest_value_in_range() -> None:
    assert extract_salary_brl("Salário de R$ 4.500,00 a R$ 6.000,00") == 4500


def test_extract_salary_brl_ignores_out_of_range_values() -> None:
    assert extract_salary_brl("CNPJ R$ 12.345.678, salário R$ 5.000") == 5000


def test_extract_salary_brl_returns_none_when_absent() -> None:
    assert extract_salary_brl("Vaga sem faixa salarial informada.") is None


def test_relocation_required_in_english_blocks() -> None:
    result = assess_hard_blocks("relocation to our HQ is required for this role", None)
    assert "RELOCATION_REQUIRED" in result.blocks


def test_relocation_required_in_portuguese_blocks() -> None:
    result = assess_hard_blocks("mudança de cidade é obrigatória para esta vaga", None)
    assert "RELOCATION_REQUIRED" in result.blocks


def test_relocation_mentioned_without_required_does_not_block() -> None:
    result = assess_hard_blocks("ajuda de custo para relocation disponível, mas não obrigatória", None)
    assert "RELOCATION_REQUIRED" not in result.blocks


def test_spanish_fluent_blocks() -> None:
    result = assess_hard_blocks("é necessário espanhol fluente para atender a região", None)
    assert "SPANISH_FLUENT_BLOCK" in result.blocks


def test_spanish_mentioned_without_fluency_level_does_not_block() -> None:
    result = assess_hard_blocks("conhecimento básico de espanhol é um diferencial", None)
    assert "SPANISH_FLUENT_BLOCK" not in result.blocks


def test_english_c1_is_a_risk_not_a_block() -> None:
    result = assess_hard_blocks("inglês avançado obrigatório para comunicação com o time global", None)
    assert "ENGLISH_C1_REVIEW" in result.risks
    assert not result.blocks


def test_support_n1_below_minimum_blocks() -> None:
    result = assess_hard_blocks("vaga de suporte N1", 3999)
    assert "SUPPORT_N1_MINIMUM" in result.blocks


def test_support_n1_at_minimum_does_not_block() -> None:
    result = assess_hard_blocks("vaga de suporte N1", 4000)
    assert "SUPPORT_N1_MINIMUM" not in result.blocks


def test_support_n1_without_known_salary_does_not_block() -> None:
    result = assess_hard_blocks("vaga de suporte N1 sem faixa salarial", None)
    assert "SUPPORT_N1_MINIMUM" not in result.blocks


def test_support_n2_below_four_thousand_does_not_trigger_n1_rule() -> None:
    result = assess_hard_blocks("vaga de suporte N2", 3000)
    assert "SUPPORT_N1_MINIMUM" not in result.blocks


def test_clean_job_has_no_blocks_or_risks() -> None:
    result = assess_hard_blocks("vaga remota de analista de dados pleno, português fluente", 8000)
    assert result.blocks == []
    assert result.risks == []


def test_foreign_presencial_job_without_the_word_relocation_still_blocks() -> None:
    # Achado real em produção: uma vaga presencial em Seiça, Portugal
    # (Caxamar) nunca usava as palavras "relocation"/"mudança obrigatória"
    # - só descrevia o local físico de trabalho - e passava pelo gate sem
    # nenhum bloqueio, apesar de exigir relocation de fato para um
    # candidato do Brasil.
    result = assess_hard_blocks(
        "analista de sistemas erp presencial em seiça, santarém, horário 09h-18h", None,
        foreign_country=True,
    )
    assert "RELOCATION_REQUIRED" in result.blocks


def test_foreign_job_with_remote_marker_does_not_block() -> None:
    result = assess_hard_blocks(
        "dba oracle 100% remoto, projetos em portugal", None,
        foreign_country=True,
    )
    assert "RELOCATION_REQUIRED" not in result.blocks


def test_foreign_job_with_hybrid_marker_does_not_block() -> None:
    result = assess_hard_blocks(
        "vaga híbrida em lisboa, dois dias por semana no escritório", None,
        foreign_country=True,
    )
    assert "RELOCATION_REQUIRED" not in result.blocks


def test_domestic_presencial_job_is_unaffected_by_the_new_rule() -> None:
    result = assess_hard_blocks("vaga presencial em são paulo", None, foreign_country=False)
    assert "RELOCATION_REQUIRED" not in result.blocks


def test_salary_below_minimum_blocks_regardless_of_role_family() -> None:
    # SCORE != ELIGIBILITY: uma vaga de qualquer familia abaixo do piso
    # aceitavel e BLOCK, mesmo com aderencia tecnica perfeita.
    result = assess_hard_blocks("vaga remota de analista de dados pleno, aderência técnica perfeita", 1500)
    assert "MINIMUM_SALARY_BLOCK" in result.blocks


def test_salary_at_minimum_does_not_block() -> None:
    result = assess_hard_blocks("vaga remota de analista de dados pleno", 4000)
    assert "MINIMUM_SALARY_BLOCK" not in result.blocks


def test_unknown_salary_does_not_trigger_minimum_salary_block() -> None:
    result = assess_hard_blocks("vaga remota de analista de dados pleno, sem faixa salarial informada", None)
    assert "MINIMUM_SALARY_BLOCK" not in result.blocks
