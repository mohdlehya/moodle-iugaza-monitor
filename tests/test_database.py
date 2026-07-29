import os
import json
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_engine
from models import User, UserSettings, CourseContent, CalendarEvent, NotificationLog
from scripts.migrate_single_user import migrate_single_user


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for fast unit testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_database_url_normalization():
    url = "postgres://user:pass@localhost:5432/dbname"
    if url.startswith("postgres://"):
        fixed_url = url.replace("postgres://", "postgresql://", 1)
    assert fixed_url == "postgresql://user:pass@localhost:5432/dbname"


def test_create_user_with_settings(db_session):
    user = User(
        telegram_chat_id=123456789,
        telegram_username="teststudent",
        moodle_username="20201234",
        moodle_password_encrypted=b"encrypted_secret",
        groq_api_key_encrypted=b"encrypted_groq_key",
        language="ar",
        status="active"
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert user.id is not None
    assert user.telegram_chat_id == 123456789

    # Add settings
    settings = UserSettings(
        user_id=user.id,
        notify_files=True,
        digest_mode="daily",
        muted_courses=["CS101"]
    )
    db_session.add(settings)
    db_session.commit()

    # Query back
    fetched_user = db_session.query(User).filter_by(telegram_chat_id=123456789).first()
    assert fetched_user is not None
    assert fetched_user.settings.digest_mode == "daily"
    assert "CS101" in fetched_user.settings.muted_courses


def test_course_content_and_calendar_json(db_session):
    user = User(telegram_chat_id=987654321, moodle_username="student2")
    db_session.add(user)
    db_session.commit()

    sample_content = {
        "Math 101": {
            "files": [{"name": "Lecture1.pdf", "url": "https://moodle/mod/resource/1"}],
            "assignments": [],
            "quizzes": [],
            "folders": []
        }
    }
    content_record = CourseContent(user_id=user.id, content_json=sample_content)
    db_session.add(content_record)

    sample_events = [{"id": 1, "name": "Midterm Exam", "eventtype": "due"}]
    event_record = CalendarEvent(user_id=user.id, events_json=sample_events)
    db_session.add(event_record)

    db_session.commit()

    fetched_content = db_session.query(CourseContent).filter_by(user_id=user.id).first()
    assert "Math 101" in fetched_content.content_json
    assert fetched_content.content_json["Math 101"]["files"][0]["name"] == "Lecture1.pdf"

    fetched_events = db_session.query(CalendarEvent).filter_by(user_id=user.id).first()
    assert len(fetched_events.events_json) == 1
    assert fetched_events.events_json[0]["name"] == "Midterm Exam"


def test_cascade_deletion(db_session):
    user = User(telegram_chat_id=555555, moodle_username="tempuser")
    db_session.add(user)
    db_session.commit()

    settings = UserSettings(user_id=user.id)
    content = CourseContent(user_id=user.id, content_json={})
    event = CalendarEvent(user_id=user.id, events_json=[])
    log = NotificationLog(user_id=user.id, notification_type="file", content_summary="Test")

    db_session.add_all([settings, content, event, log])
    db_session.commit()

    assert db_session.query(UserSettings).count() == 1
    assert db_session.query(NotificationLog).count() == 1

    db_session.delete(user)
    db_session.commit()

    assert db_session.query(UserSettings).count() == 0
    assert db_session.query(CourseContent).count() == 0
    assert db_session.query(CalendarEvent).count() == 0
    assert db_session.query(NotificationLog).count() == 0


def test_migrate_single_user_script(monkeypatch):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_file = os.path.join(tmpdir, "test_migrate.db")
        data_file = os.path.join(tmpdir, "data.json")
        events_file = os.path.join(tmpdir, "events.json")

        sample_data = {"CS101": {"files": [{"name": "Syllabus.pdf", "url": "http://test"}]}}
        sample_events = [{"id": 10, "name": "Quiz 1"}]

        with open(data_file, "w", encoding="utf-8") as f:
            json.dump(sample_data, f)
        with open(events_file, "w", encoding="utf-8") as f:
            json.dump(sample_events, f)

        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "777888999")
        monkeypatch.setenv("MOODLE_USERNAME", "migrated_user")
        monkeypatch.setenv("MOODLE_PASSWORD", "secret123")

        # Initialize tables on dynamic engine
        engine = get_engine()
        Base.metadata.create_all(bind=engine)

        result = migrate_single_user(data_path=data_file, events_path=events_file)
        assert result is True

        TestingSession = sessionmaker(bind=engine)
        session = TestingSession()
        u = session.query(User).filter_by(telegram_chat_id=777888999).first()
        assert u is not None
        assert u.moodle_username == "migrated_user"
        assert u.moodle_password_encrypted == b"secret123"

        c = session.query(CourseContent).filter_by(user_id=u.id).first()
        assert "CS101" in c.content_json

        e = session.query(CalendarEvent).filter_by(user_id=u.id).first()
        assert len(e.events_json) == 1

        session.close()
        engine.dispose()
