import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def test_readme_file_exists():
    readme_path = os.path.join(PROJECT_ROOT, "README.md")
    assert os.path.exists(readme_path)


def test_readme_required_sections_and_guides():
    readme_path = os.path.join(PROJECT_ROOT, "README.md")
    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    required_keywords = [
        "TELEGRAM_BOT_TOKEN",
        "CREDENTIALS_ENCRYPTION_KEY",
        "DATABASE_URL",
        "ADMIN_CHAT_ID",
        "/register",
        "/setgroqkey",
        "/settings",
        "/coursefilter",
        "/admin",
        "/admin_broadcast",
        "/admin_retry",
        "/delete_account",
        "/healthz",
        "/metrics",
        "console.groq.com",
    ]

    for kw in required_keywords:
        assert kw in content, f"Missing required keyword/section '{kw}' in README.md"
