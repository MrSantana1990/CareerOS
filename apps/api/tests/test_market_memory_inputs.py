from datetime import datetime

import pytest
from pydantic import ValidationError

from src.career import (CompanyInput, OpportunityChannelInput, OpportunityInput,
                         OpportunityStatusInput, SignalInput, WatchInput, WatchUpdateInput)


def test_model_dump_keeps_datetime_fields_as_real_datetime_not_iso_string():
    # Bug real encontrado em producao (Prompt 2): payload.model_dump(mode="json")
    # serializa datetime para string ISO, mas asyncpg exige um objeto
    # datetime.datetime de verdade para uma coluna timestamptz - "expected a
    # datetime.date or datetime.datetime instance, got 'str'". Corrigido
    # trocando para model_dump() puro nas 5 rotas novas; este teste garante
    # que o campo nunca regride para string quando serializado dessa forma.
    channel = OpportunityChannelInput(type="OFFICIAL_EMAIL", url_or_email="rh@empresa.com",
                                       source="https://empresa.com/carreiras",
                                       verified_at=datetime(2026, 9, 6))
    dumped = channel.model_dump()
    assert isinstance(dumped["verified_at"], datetime)


def test_signal_input_accepts_no_company_yet():
    # Signal pode preceder a resolucao da Company (Blueprint secao 4/6).
    signal = SignalInput(type="EXPANSION", headline="Empresa anuncia expansão em Campinas")
    assert signal.company_id is None
    assert signal.confidence is None


def test_signal_input_rejects_unknown_type():
    with pytest.raises(ValidationError):
        SignalInput(type="RUMOR", headline="Não permitido")


def test_signal_input_confidence_bounded_0_100():
    with pytest.raises(ValidationError):
        SignalInput(type="EXPANSION", headline="X", confidence=150)


def test_opportunity_input_allows_no_job_no_signal():
    # Opportunity 0..1 -> Job: o caso central (Deutsche Bank).
    opportunity = OpportunityInput(company_id="00000000-0000-0000-0000-000000000001",
                                    type="SPONTANEOUS_APPLICATION")
    assert opportunity.job_id is None
    assert opportunity.signal_id is None
    assert opportunity.status == "DISCOVERED"


def test_opportunity_input_rejects_unknown_status():
    with pytest.raises(ValidationError):
        OpportunityInput(company_id="00000000-0000-0000-0000-000000000001",
                          type="JOB_APPLICATION", status="SOMEDAY")


def test_opportunity_status_update_rejects_unknown_status():
    with pytest.raises(ValidationError):
        OpportunityStatusInput(status="NOT_A_REAL_STATE")


def test_opportunity_channel_official_email_type_is_accepted_as_input():
    # A regra "nunca inferir e-mail" e aplicada na rota (exige source),
    # nao no modelo - o modelo so valida a forma dos dados.
    channel = OpportunityChannelInput(type="OFFICIAL_EMAIL", url_or_email="rh@empresa.com",
                                       source="https://empresa.com/carreiras")
    assert channel.requires_auth is False
    assert channel.status == "CANDIDATE"


def test_opportunity_channel_rejects_unknown_type():
    with pytest.raises(ValidationError):
        OpportunityChannelInput(type="CARRIER_PIGEON", url_or_email="x@x.com")


def test_watch_input_reason_required():
    with pytest.raises(ValidationError):
        WatchInput(company_id="00000000-0000-0000-0000-000000000001", reason="")


def test_watch_update_input_all_fields_optional():
    update = WatchUpdateInput()
    assert update.status is None
    assert update.check_count is None


def test_watch_update_input_check_count_cannot_be_negative():
    with pytest.raises(ValidationError):
        WatchUpdateInput(check_count=-1)


def test_company_input_requires_a_real_name():
    with pytest.raises(ValidationError):
        CompanyInput(name="A")
