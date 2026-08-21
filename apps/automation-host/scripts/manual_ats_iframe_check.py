"""Validação manual (não faz parte do pytest/CI) da detecção de ATS e da
busca de CTA dentro de iframes em Greenhouse/Lever/Ashby.

Uso:
    .venv/Scripts/python.exe apps/automation-host/scripts/manual_ats_iframe_check.py \
        https://boards.greenhouse.io/<empresa>/jobs/<id> \
        https://jobs.lever.co/<empresa>/<id> \
        https://jobs.ashbyhq.com/<empresa>/<id> \
        https://www.linkedin.com/jobs/view/<id>   # controle, não deve mudar de comportamento

Abre cada URL num navegador real (headed), roda a mesma detecção/CTA usada em
execute_application_queue, tira um screenshot antes/depois e imprime o
resultado. NÃO chama execute_application_queue nem toca em APPLICATIONS —
só observação, sem qualquer risco de disparo.
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright  # noqa: E402

from src.ats_detection import detect_ats  # noqa: E402
from src.main import EXTERNAL_APPLY_CTA_PATTERN, click_first_visible, search_roots  # noqa: E402

SCREENSHOT_DIR = Path(__file__).resolve().parent / "manual-ats-check-output"


async def check(url: str) -> None:
    match = detect_ats(url)
    print(f"\n=== {url} ===")
    print(f"detect_ats -> {match}")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=False, channel="chrome")
        page = await browser.new_page(viewport={"width": 1280, "height": 900})
        await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(2000)

        SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(c if c.isalnum() else "-" for c in url)[-80:]
        before = SCREENSHOT_DIR / f"{safe_name}-before.png"
        await page.screenshot(path=str(before), full_page=True)

        roots = await search_roots(page)
        print(f"search_roots -> {len(roots)} raiz(es) (1 = só page; >1 = page + iframe(s) de ATS)")

        clicked = await click_first_visible(page, EXTERNAL_APPLY_CTA_PATTERN)
        print(f"click_first_visible(CTA) -> {clicked}")
        await page.wait_for_timeout(1500)

        after = SCREENSHOT_DIR / f"{safe_name}-after.png"
        await page.screenshot(path=str(after), full_page=True)
        print(f"screenshots: {before.name} / {after.name}")

        await browser.close()


async def main(urls: list[str]) -> None:
    for url in urls:
        await check(url)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    asyncio.run(main(sys.argv[1:]))
