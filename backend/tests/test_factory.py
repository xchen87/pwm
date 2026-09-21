import pytest

from pwm.extraction import factory


def test_the_default_needs_no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PWM_EXTRACTOR", raising=False)
    triager, extractor = factory.build_stages()
    assert extractor.method == "heuristic" and factory.provider_errors() == ()


def test_the_model_path_without_credentials_fails_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWM_EXTRACTOR", "anthropic")
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(factory.ProviderNotConfigured, match="needs credentials"):
        factory.build_stages()
    assert factory.ProviderNotConfigured in factory.provider_errors()


def test_an_unknown_extractor_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PWM_EXTRACTOR", "crystal-ball")
    with pytest.raises(ValueError, match="unknown PWM_EXTRACTOR"):
        factory.build_stages()
