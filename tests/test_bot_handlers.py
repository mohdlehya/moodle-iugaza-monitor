import os
import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db_context
from models import User, UserSettings, CourseContent
from telegram_bot import (
    start_command,
    status_command,
    courses_command,
    admin_command,
)


@pytest.fixture(scope="function")
def db_session(monkeypatch, tmp_path):
    db_file = tmp_path / "test_bot_handlers.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def make_mock_update(chat_id: int, text: str = "/start"):
    update = MagicMock()
    update.effective_chat.id = chat_id
    update.effective_user.username = "test_user"
    update.message = MagicMock()
    update.message.text = text
    update.message.reply_text = AsyncMock()
    return update


def test_start_command_unregistered(db_session):
    update = make_mock_update(chat_id=11111)
    context = MagicMock()

    asyncio.run(start_command(update, context))

    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "/register" in call_args


def test_start_command_active_user(db_session):
    with get_db_context() as db:
        u = User(telegram_chat_id=22222, moodle_username="active_student", status="active")
        db.add(u)

    update = make_mock_update(chat_id=22222)
    context = MagicMock()

    asyncio.run(start_command(update, context))

    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "active_student" in call_args
    assert "لوحة التحكم" in call_args


def test_status_command(db_session):
    with get_db_context() as db:
        u = User(telegram_chat_id=33333, moodle_username="status_student", status="active")
        db.add(u)
        db.flush()
        st = UserSettings(user_id=u.id)
        db.add(st)

    update = make_mock_update(chat_id=33333, text="/status")
    context = MagicMock()

    asyncio.run(status_command(update, context))

    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "status_student" in call_args
    assert "ACTIVE" in call_args


def test_admin_command_access_denied(monkeypatch, db_session):
    monkeypatch.setenv("ADMIN_CHAT_ID", "999999")
    update = make_mock_update(chat_id=44444, text="/admin")
    context = MagicMock()

    asyncio.run(admin_command(update, context))

    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "مخصص لمدير النظام فقط" in call_args


def test_admin_command_access_granted(monkeypatch, db_session):
    monkeypatch.setenv("ADMIN_CHAT_ID", "999999")
    update = make_mock_update(chat_id=999999, text="/admin")
    context = MagicMock()

    asyncio.run(admin_command(update, context))

    update.message.reply_text.assert_called_once()
    call_args = update.message.reply_text.call_args[0][0]
    assert "لوحة تحكم مدير النظام" in call_args
