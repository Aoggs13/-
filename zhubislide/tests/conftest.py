import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "tests")]


@pytest.fixture(autouse=True)
def _fresh_provider_state(monkeypatch):
    """No test sees the provider picked or the keys set by another one."""
    from app import content
    for k in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "AI_PROVIDER"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(content, "_active", "")
    monkeypatch.setattr(content, "_models", {})
    monkeypatch.setattr(content, "OPENAI_MODEL", "")
    monkeypatch.setattr(content, "GEMINI_MODEL", "")
