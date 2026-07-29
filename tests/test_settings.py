import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db_context
from models import User, UserSettings
from telegram_bot import (
    get_or_create_user_settings,
    build_settings_keyboard,
    build_coursefilter_keyboard,
)


@pytest.fixture(scope="function")
def db_session(monkeypatch, tmp_path):
    db_file = tmp_path / "test_settings.db"
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


def test_user_settings_creation_and_defaults(db_session):
    with get_db_context() as db:
        u = User(telegram_chat_id=888111, moodle_username="setting_usr", status="active")
        db.add(u)
        db.flush()
        user_id = u.id

    st = get_or_create_user_settings(user_id)

    assert st.notify_files is True
    assert st.notify_assignments is True
    assert st.notify_quizzes is True
    assert st.notify_folders is True
    assert st.ai_summaries_enabled is True
    assert st.digest_mode == "instant"
    assert st.muted_courses == [] or st.muted_courses is None


def test_user_settings_mutation_and_course_muting(db_session):
    with get_db_context() as db:
        u = User(telegram_chat_id=888222, moodle_username="mute_usr", status="active")
        db.add(u)
        db.flush()
        user_id = u.id

    with get_db_context() as db:
        st = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not st:
            st = UserSettings(user_id=user_id)
            db.add(st)
            db.flush()

        st.notify_files = False
        st.ai_summaries_enabled = False
        st.muted_courses = ["CS101 - Algorithms", "MATH201"]

    with get_db_context() as db:
        check_st = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        assert check_st.notify_files is False
        assert check_st.ai_summaries_enabled is False
        assert "CS101 - Algorithms" in check_st.muted_courses
        assert "MATH201" in check_st.muted_courses


def test_inline_keyboard_builders(db_session):
    st = UserSettings(user_id=1, notify_files=True, notify_assignments=False, muted_courses=["MATH201"])
    kb_settings = build_settings_keyboard(st)
    assert kb_settings is not None
    assert len(kb_settings.inline_keyboard) >= 4

    courses = ["CS101", "MATH201", "PHYS301"]
    kb_courses = build_coursefilter_keyboard(courses, st.muted_courses)
    assert kb_courses is not None
    # 3 courses + 1 back to settings + 1 back to main menu = 5 rows
    assert len(kb_courses.inline_keyboard) == 5
    assert "🔇" in kb_courses.inline_keyboard[1][0].text
    assert "✅" in kb_courses.inline_keyboard[0][0].text
