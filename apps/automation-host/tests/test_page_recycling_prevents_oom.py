from pathlib import Path


def _source() -> str:
    return (Path(__file__).resolve().parents[1] / "src" / "main.py").read_text(encoding="utf-8")


def test_execute_application_queue_recycles_the_page_after_every_candidate() -> None:
    # Achado real em produção: uma única página do Chrome era reaproveitada
    # para todas as ~20 candidaturas de cada execução agendada
    # (page = browser.pages[0] if browser.pages else await browser.new_page(),
    # antes do loop). Memória (DOM/JS heap/recursos em cache de cada
    # navegação pesada) se acumulava sem nunca ser liberada, até o OOM
    # killer do Linux matar o processo do Chrome no meio do page.goto -
    # confirmado no dmesg do host (task=headless_shell, Killed process) e
    # em 260 de 533 candidaturas FAILED reais com o mesmo motivo
    # ("Page.goto: Page crashed"), em praticamente todas as execuções
    # agendadas desde 24/08. Cada candidatura agora fecha as páginas da
    # execução anterior e abre uma nova, limitando o acúmulo de memória a
    # uma única candidatura por vez, não ao lote inteiro.
    source = _source()
    start = source.index("        finally:\n            save_json(APPLICATIONS, applications)")
    end = source.index('    update(status="completed", message=f"Preparação concluída')
    body = source[start:end]
    assert "stale_pages = list(browser.pages)" in body
    assert "page = await browser.new_page()" in body
    assert "await stale.close()" in body
