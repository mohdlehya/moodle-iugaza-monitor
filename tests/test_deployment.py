import os
import sys
import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from bot_runner import shutdown_handler


PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_deployment_artifacts_exist():
    dockerfile = os.path.join(PROJECT_ROOT, "Dockerfile")
    compose = os.path.join(PROJECT_ROOT, "docker-compose.yml")
    entrypoint = os.path.join(PROJECT_ROOT, "entrypoint.sh")
    env_example = os.path.join(PROJECT_ROOT, ".env.example")

    assert os.path.exists(dockerfile)
    assert os.path.exists(compose)
    assert os.path.exists(entrypoint)
    assert os.path.exists(env_example)


def test_env_example_content_keys():
    env_example = os.path.join(PROJECT_ROOT, ".env.example")
    with open(env_example, "r", encoding="utf-8") as f:
        content = f.read()

    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "CREDENTIALS_ENCRYPTION_KEY",
        "DATABASE_URL",
        "ADMIN_CHAT_ID",
        "GROQ_API_KEY",
        "PORT",
    ]
    for var in required_vars:
        assert var in content


def test_shutdown_handler_execution(monkeypatch):
    mock_scheduler = MagicMock()
    mock_scheduler.running = True
    monkeypatch.setattr("bot_runner.scheduler_instance", mock_scheduler)

    with pytest.raises(SystemExit) as exc_info:
        shutdown_handler(15, None)

    assert exc_info.value.code == 0
    mock_scheduler.shutdown.assert_called_once_with(wait=False)
