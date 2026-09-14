"""Recuperacao operacional do Gmail - auditoria encontrou que nenhum
refresh de access token era persistido de volta no disco (o
access_token renovado - e um eventual refresh_token novo, se o Google
decidir rotacionar - so vivia em memoria e desaparecia a cada nova
leitura do arquivo). Isso, por si so, nao explica a causa raiz real
(refresh tokens de app OAuth em modo "Testing" expiram em 7 dias
independente de uso - ver docs/AI_AND_GOOGLE.md, que instrui
explicitamente manter o app em teste), mas e uma lacuna real de robustez
que corrigimos: quando o Google devolver um refresh_token novo (rotacao),
ele precisa sobreviver; quando nao devolver, o existente nunca pode ser
apagado; e duas chamadas concorrentes nunca podem corromper o arquivo.

Testes puros contra src/google_career.py (import direto - sem
dependencia de rede: Credentials.refresh e sempre mockado) + testes de
wiring por texto-fonte contra src/main.py e deploy.yml (mesmo padrao de
test_google_mail_health.py / test_job_correlation_wiring.py - nunca
importa main.py diretamente, que tem dependencias pesadas como
playwright)."""

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials

from src.google_career import SCOPES, _credentials, credential_storage_health


def _write_token(path: Path, *, expired: bool, refresh_token: str = "original-refresh-token") -> None:
    expiry = datetime.now(timezone.utc) + (timedelta(hours=-1) if expired else timedelta(hours=1))
    data = {
        "refresh_token": refresh_token,
        "client_id": "fake-client-id",
        "client_secret": "fake-client-secret",
        "token": "original-access-token",
        "token_uri": "https://oauth2.googleapis.com/token",
        "scopes": list(SCOPES),
        "expiry": expiry.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


@pytest.fixture
def token_path(tmp_path):
    return tmp_path / "google" / "google-token.json"


# A: refresh token sobrevive ao refresh do access token ----------------------------------------------------

def test_a_refresh_persists_new_access_token_and_preserves_refresh_token(token_path):
    _write_token(token_path, expired=True)

    def fake_refresh(self, request):
        self.token = "brand-new-access-token"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch.object(Credentials, "refresh", fake_refresh):
        credentials = _credentials(token_path)
    assert credentials.token == "brand-new-access-token"
    assert credentials.refresh_token == "original-refresh-token"
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["token"] == "brand-new-access-token"
    assert persisted["refresh_token"] == "original-refresh-token"


# B: resposta de refresh SEM novo refresh_token preserva o existente / COM novo, persiste o novo -------------

def test_b_refresh_without_new_refresh_token_keeps_existing(token_path):
    _write_token(token_path, expired=True, refresh_token="only-refresh-token-we-have")

    def fake_refresh(self, request):
        self.token = "new-access-token"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        # nao altera self.refresh_token - simula o Google NAO devolvendo
        # um refresh_token novo (o caso normal/mais comum).

    with patch.object(Credentials, "refresh", fake_refresh):
        _credentials(token_path)
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["refresh_token"] == "only-refresh-token-we-have"


def test_b_refresh_with_rotated_refresh_token_persists_the_new_one(token_path):
    _write_token(token_path, expired=True, refresh_token="old-refresh-token")

    def fake_refresh(self, request):
        self.token = "new-access-token"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)
        self._refresh_token = "rotated-refresh-token"

    with patch.object(Credentials, "refresh", fake_refresh):
        _credentials(token_path)
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["refresh_token"] == "rotated-refresh-token"


# C: restart do container preserva a credencial (simulado: releitura do disco em chamadas separadas) ---------

def test_c_credential_reloaded_from_disk_reflects_last_persisted_state(token_path):
    _write_token(token_path, expired=True)

    def fake_refresh(self, request):
        self.token = "persisted-across-restart"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch.object(Credentials, "refresh", fake_refresh):
        _credentials(token_path)
    # "restart" = uma nova chamada, do zero, recarregando so do arquivo -
    # nada em memoria e reaproveitado (mesma garantia que um container
    # reiniciado teria).
    reloaded = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    assert reloaded.token == "persisted-across-restart"
    assert not reloaded.expired


# D: deploy nao pode sobrescrever/restaurar/apagar o credential store -----------------------------------------

def test_d_deploy_script_never_touches_the_credential_store():
    deploy_source = (
        Path(__file__).resolve().parents[3] / ".github" / "workflows" / "deploy.yml"
    ).read_text(encoding="utf-8")
    for forbidden in ("integrations_data", ".runtime", "google-token", "down -v", "volume rm"):
        assert forbidden not in deploy_source


# E: credencial ausente -> AUTH_REQUIRED -----------------------------------------------------------------------

def test_d_dockerfile_never_copies_the_whole_build_context_into_the_image():
    # So copia pyproject.toml e src/ explicitamente - nunca "COPY . ." -
    # garante que .runtime/google-token.json (que so existe fora da
    # imagem, no volume integrations_data) nunca pode ser incluido no
    # build context nem assado na imagem.
    dockerfile_source = (
        Path(__file__).resolve().parents[1] / "Dockerfile"
    ).read_text(encoding="utf-8")
    assert "COPY . ." not in dockerfile_source
    assert "COPY . /app" not in dockerfile_source


def test_e_missing_credential_file_reports_absent_not_an_error(token_path):
    health = credential_storage_health(token_path)
    assert health["credential_file_present"] is False
    assert health["has_refresh_token"] is False


# F: invalid_grant -> AUTH_REQUIRED (classificacao ja existente, aqui validada com o fluxo real de refresh) -----

def test_f_invalid_grant_raises_refresh_error_and_records_it_without_deleting_token(token_path):
    _write_token(token_path, expired=True)

    def fake_refresh(self, request):
        raise RefreshError("invalid_grant: Token has been expired or revoked.",
                           {"error": "invalid_grant", "error_description": "Token has been expired or revoked."})

    with patch.object(Credentials, "refresh", fake_refresh), pytest.raises(RefreshError):
        _credentials(token_path)
    # o arquivo de credencial original NUNCA e apagado so porque o refresh falhou -
    # a reautorizacao humana precisa do refresh_token antigo continuar visivel/auditavel.
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["refresh_token"] == "original-refresh-token"
    health = credential_storage_health(token_path)
    assert health["last_refresh_error"] == "RefreshError"


# G: falha transitoria (nao expirado - nunca dispara refresh nenhum) --------------------------------------------

def test_g_non_expired_credential_never_triggers_a_refresh_call(token_path):
    _write_token(token_path, expired=False)
    with patch.object(Credentials, "refresh") as mock_refresh:
        _credentials(token_path)
    mock_refresh.assert_not_called()


# H: refresh concorrente nao corrompe o storage -------------------------------------------------------------------

def test_h_concurrent_refresh_calls_never_corrupt_storage_and_refresh_once(token_path):
    _write_token(token_path, expired=True)
    call_count = {"n": 0}
    lock_for_counter = threading.Lock()

    def fake_refresh(self, request):
        with lock_for_counter:
            call_count["n"] += 1
        import time
        time.sleep(0.05)
        self.token = f"refreshed-{call_count['n']}"
        self.expiry = datetime.now(timezone.utc) + timedelta(hours=1)

    results = []
    errors = []

    def worker():
        try:
            with patch.object(Credentials, "refresh", fake_refresh):
                results.append(_credentials(token_path))
        except Exception as exc:  # pragma: no cover - so falha se o teste pegar corrupcao
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    # o double-checked locking garante no maximo 1 refresh de verdade -
    # as demais threads reaproveitam o resultado ja persistido.
    assert call_count["n"] == 1
    persisted = json.loads(token_path.read_text(encoding="utf-8"))
    assert persisted["token"] == "refreshed-1"


# I: segredos nunca aparecem no payload de saude ------------------------------------------------------------------

def test_i_credential_storage_health_never_exposes_secret_values(token_path):
    _write_token(token_path, expired=False, refresh_token="super-secret-refresh-token-value")
    health = credential_storage_health(token_path)
    serialized = json.dumps(health)
    assert "super-secret-refresh-token-value" not in serialized
    assert "fake-client-secret" not in serialized
    for forbidden_key in ("refresh_token", "access_token", "client_secret", "token"):
        assert forbidden_key not in health


def test_i_credential_storage_health_reports_presence_booleans_only(token_path):
    _write_token(token_path, expired=False)
    health = credential_storage_health(token_path)
    assert health["credential_file_present"] is True
    assert health["has_refresh_token"] is True
    assert health["scopes_match"] is True


# J/K: scheduler resolve intervencao na recuperacao e continua chamando core sync (wiring por texto-fonte) --------

def _main_source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_j_scheduler_resolves_reauth_intervention_on_recovery():
    source = _main_source()
    start = source.index("async def google_mail_scheduler(")
    end = source.index("\n@app.on_event", start)
    body = source[start:end]
    assert "_resolve_gmail_reauth_intervention" in body
    assert 'event("GOOGLE_MAIL_RECOVERED"' in body


def test_j_resolve_intervention_helper_is_idempotent_when_nothing_pending():
    source = _main_source()
    start = source.index("def _resolve_gmail_reauth_intervention(")
    end = source.index("\nasync def google_mail_scheduler(", start)
    body = source[start:end]
    assert "if not match:" in body
    assert "return" in body
    assert "except Exception as exc:" in body


def test_k_core_sync_still_called_on_every_successful_scan():
    source = _main_source()
    start = source.index("async def google_mail_scheduler(")
    end = source.index("\n@app.on_event", start)
    body = source[start:end]
    assert "await sync_communications_to_core(result[" in body


def test_root_cause_is_always_persisted_on_failure_not_only_at_threshold():
    source = _main_source()
    start = source.index("async def google_mail_scheduler(")
    end = source.index("\n@app.on_event", start)
    body = source[start:end]
    failure_branch = body[body.index("except Exception as exc:"):]
    assert 'root_cause = classify_gmail_auth_failure_root_cause' in failure_branch.split(
        "if consecutive_failures >= GOOGLE_HEALTH_ALERT_THRESHOLD:")[0]
    assert '"root_cause": root_cause' in failure_branch


def test_metrics_and_status_expose_credential_storage_health_without_secrets():
    source = _main_source()
    assert "credential_storage_health(GOOGLE_TOKEN)" in source
    metrics_start = source.index('@app.get("/metrics")')
    metrics_end = source.index("\n@app.get", metrics_start + 1)
    assert '"credential_storage_health"' in source[metrics_start:metrics_end]
    status_start = source.index('@app.get("/google/status")')
    status_end = source.index("\n@app.get", status_start + 1)
    assert source[status_start:status_end].count('"credential_storage_health"') >= 3
