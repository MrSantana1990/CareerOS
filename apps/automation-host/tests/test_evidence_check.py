import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.evidence_check import is_evidence_grounded  # noqa: E402

RESUME = (
    "Rodolfo Santana. Analista de Suporte N3 com 5 anos de experiência em SQL Server, "
    "PostgreSQL e monitoramento de ambientes cloud na Azure. Atuou em sustentação de "
    "sistemas críticos e liderou squad de plantão 24x7."
)


def test_grounded_evidence_matching_resume_is_accepted() -> None:
    assert is_evidence_grounded("5 anos de experiência em SQL Server e PostgreSQL", RESUME) is True


def test_fabricated_evidence_not_present_in_resume_is_rejected() -> None:
    assert is_evidence_grounded("10 anos como gerente de projetos em Londres", RESUME) is False


def test_empty_evidence_is_never_grounded() -> None:
    assert is_evidence_grounded("", RESUME) is False


def test_single_word_evidence_is_too_thin_to_verify() -> None:
    assert is_evidence_grounded("SQL", RESUME) is False


def test_no_sources_available_means_nothing_can_be_grounded() -> None:
    assert is_evidence_grounded("5 anos de experiência em SQL Server") is False


def test_evidence_can_be_grounded_across_multiple_sources() -> None:
    skills = "Python SQL Server PostgreSQL Azure"
    roles = "Analista de Suporte N3"
    assert is_evidence_grounded("Analista de Suporte N3 com foco em Azure", skills, roles) is True


def test_partial_overlap_below_threshold_is_rejected() -> None:
    assert is_evidence_grounded("SQL Server e liderança de squads internacionais em Londres Paris Tóquio", RESUME) is False
