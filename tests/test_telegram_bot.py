import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db_context
from models import User, UserSettings, CourseContent, CalendarEvent
from telegram_bot import get_user_by_chat_id, get_user_content, get_user_events, build_telegram_app
from groq_helper import validate_groq_key
from services.user_service import delete_user_by_telegram_id


@pytest.fixture(scope="function")
def db_session(monkeypatch, tmp_path):
    db_file = tmp_path / "test_bot.db"
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


def test_multi_tenant_user_content_isolation(db_session):
    with get_db_context() as db:
        u1 = User(telegram_chat_id=1001, moodle_username="student_a", status="active")
        u2 = User(telegram_chat_id=2002, moodle_username="student_b", status="active")
        db.add_all([u1, u2])
        db.flush()

        c1 = CourseContent(user_id=u1.id, content_json={"CS101": {"files": [{"name": "A_File.pdf", "url": "http://a"}]}})
        c2 = CourseContent(user_id=u2.id, content_json={"MATH202": {"files": [{"name": "B_File.pdf", "url": "http://b"}]}})
        db.add_all([c1, c2])

    found_u1 = get_user_by_chat_id(1001)
    found_u2 = get_user_by_chat_id(2002)

    assert found_u1 is not None and found_u1.moodle_username == "student_a"
    assert found_u2 is not None and found_u2.moodle_username == "student_b"

    content_u1 = get_user_content(found_u1.id)
    content_u2 = get_user_content(found_u2.id)

    assert "CS101" in content_u1
    assert "MATH202" not in content_u1

    assert "MATH202" in content_u2
    assert "CS101" not in content_u2


def test_groq_key_validation_helper():
    assert validate_groq_key("") is False
    assert validate_groq_key(None) is False
    assert validate_groq_key("invalid_key_string") is False


def test_user_deletion_by_telegram_id(db_session):
    with get_db_context() as db:
        u = User(telegram_chat_id=999000111, moodle_username="del_user", status="active")
        db.add(u)

    assert get_user_by_chat_id(999000111) is not None

    deleted = delete_user_by_telegram_id(999000111)
    assert deleted is True

    assert get_user_by_chat_id(999000111) is None


def test_build_telegram_app_structure(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
    app = build_telegram_app()
    assert app is not None
