import ast
from pathlib import Path


def test_core_sync_uses_keyword_timeout():
    source = Path(__file__).parents[1] / "src" / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    sync_calls = [node for node in calls if isinstance(node.func, ast.Attribute)
                  and node.func.attr == "to_thread"
                  and any(keyword.arg == "timeout" for keyword in node.keywords)]
    assert sync_calls, "A sincronização HTTP deve usar timeout nomeado."


def test_sensitive_blockers_are_reported_for_human_intervention():
    source = (Path(__file__).parents[1] / "src" / "main.py").read_text(encoding="utf-8")
    assert 'application, "CAPTCHA"' in source
    assert 'application, "MFA"' in source
    assert 'application, "UNKNOWN_FIELD"' in source
    assert 'application, "SUBMISSION_UNCONFIRMED"' in source
    assert "O sistema nunca tenta contorná-lo" in source
