"""Validação manual (não faz parte do pytest/CI) do avanço em formulário de
múltiplas etapas (fix do "botão final não localizado").

Uso:
    .venv/Scripts/python.exe apps/automation-host/scripts/manual_multi_step_check.py \
        https://exemplo.com/vaga/123

Abre a URL num navegador real (headed), clica no CTA inicial, preenche os
campos conhecidos com um perfil de teste (sem currículo real - o upload de
arquivo é pulado quando o caminho não existe), e reproduz o MESMO loop de
avanço de etapas usado em execute_application_queue: procura o botão final,
se não achar tenta "próxima etapa", preenche de novo, repete até
MAX_APPLICATION_STEPS. NÃO clica no botão final em nenhuma hipótese - só
reporta se o achou e depois de quantas etapas. Sem risco de envio real.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright  # noqa: E402

from src.main import (  # noqa: E402
    EXTERNAL_APPLY_CTA_PATTERN,
    FINAL_SUBMIT_CTA_PATTERN,
    MAX_APPLICATION_STEPS,
    NEXT_STEP_CTA_PATTERN,
    ProfessionalProfile,
    click_first_visible,
    dismiss_overlays,
    fill_known_fields,
    find_first_visible,
    required_unknown_fields,
    search_roots,
)

SCREENSHOT_DIR = Path(__file__).resolve().parent / "manual-multi-step-output"

TEST_PROFILE = ProfessionalProfile(
    full_name="Candidato Teste",
    email="candidato.teste@example.com",
    phone="11999999999",
    city="Campinas",
    state="SP",
    linkedin_url="https://www.linkedin.com/in/candidato-teste",
    salary_expectation="7000",
    resume_path="",
)


async def check(url: str) -> None:
    print(f"\n=== {url} ===")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, channel="chrome")
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2000)
        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "-" for c in url)[-80:]

        await dismiss_overlays(page)
        clicked = await click_first_visible(page, EXTERNAL_APPLY_CTA_PATTERN)
        print(f"click_first_visible(CTA inicial) -> {clicked}")
        await page.wait_for_timeout(1800)
        await dismiss_overlays(page)

        visible_submit = None
        steps_advanced = 0
        unknown: list[str] = []
        while not unknown and visible_submit is None and steps_advanced < MAX_APPLICATION_STEPS:
            for root in await search_roots(page):
                await fill_known_fields(root, TEST_PROFILE)
                unknown.extend(await required_unknown_fields(root))
                visible_submit = await find_first_visible(root, FINAL_SUBMIT_CTA_PATTERN)
                if visible_submit is not None:
                    break
            shot = SCREENSHOT_DIR / f"{safe_name}-step{steps_advanced}.png"
            await page.screenshot(path=str(shot), full_page=True)
            print(f"etapa {steps_advanced}: unknown={len(unknown)} can_submit={visible_submit is not None} screenshot={shot.name}")
            if visible_submit is not None or unknown:
                break
            if not await click_first_visible(page, NEXT_STEP_CTA_PATTERN):
                print("nenhum botão de próxima etapa encontrado - parando aqui.")
                break
            steps_advanced += 1
            await page.wait_for_timeout(1500)
            await dismiss_overlays(page)

        print(f"RESULTADO: steps_advanced={steps_advanced} can_submit={visible_submit is not None} unknown_fields={len(unknown)}")
        print("Nenhum clique no botão final foi executado por este script.")
        await browser.close()


async def main(urls: list[str]) -> None:
    for url in urls:
        await check(url)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1:]))
