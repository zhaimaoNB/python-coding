from python_claw_agent.provider.deepseek import DeepSeekProvider


def test_deepseek_reads_base_url_env(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://example.invalid/v1")
    provider = DeepSeekProvider()
    assert "example.invalid" in str(provider.client.base_url)


def test_deepseek_default_base_url(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    provider = DeepSeekProvider()
    assert "api.deepseek.com" in str(provider.client.base_url)
