"""Limite diário real de candidaturas - Fase 13 do Plano Mestre (anti-spam).

Antes desta correção, o `limit` de `execute_application_queue` era aplicado
por EXECUÇÃO, não por dia - como o pipeline roda 3x/dia (8h/12h/18h), o
teto de fato podia chegar a 3x o valor configurado em `daily_target`. Este
módulo calcula quantas candidaturas ainda podem ser enviadas hoje, olhando
o que já foi efetivamente enviado (status APPLIED com submitted_at de
hoje) - não quantas foram apenas processadas/preparadas.

Sem dependências de Playwright/FastAPI (mesmo padrão de ats_detection.py,
hard_blocks.py, kill_switches.py, evidence_check.py e email_discovery.py).
"""

from datetime import datetime


def applications_submitted_today(applications: list[dict], today: datetime) -> int:
    today_date = today.date().isoformat()
    count = 0
    for application in applications:
        if application.get("status") != "APPLIED":
            continue
        submitted_at = application.get("submitted_at") or ""
        if isinstance(submitted_at, str) and submitted_at[:10] == today_date:
            count += 1
    return count


def remaining_daily_quota(applications: list[dict], daily_target: int, today: datetime) -> int:
    return max(0, daily_target - applications_submitted_today(applications, today))
