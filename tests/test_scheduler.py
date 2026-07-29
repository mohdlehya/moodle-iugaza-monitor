import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db_context, get_engine
from models import User, UserSettings, CourseContent, CalendarEvent
from main import run_check_for_user
from scheduler import scheduler, sync_user_jobs, start_scheduler
from crypto import encrypt_credential


@pytest.fixture(scope="function")
def db_session(monkeypatch, tmp_path):
    db_file = tmp_path / "test_sched.db"
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


def test_user_error_isolation(db_session, monkeypatch):
    test_key = "s-I-0DmUMvgIJ1lLCX_QQBz2pkPSKMFOvrJRMKAhEn8="
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", test_key)

    with get_db_context() as db:
        u1 = User(
            telegram_chat_id=111,
            moodle_username="user1",
            moodle_password_encrypted=encrypt_credential("badpass", key=test_key),
            status="active"
        )
        u2 = User(
            telegram_chat_id=222,
            moodle_username="user2",
            moodle_password_encrypted=encrypt_credential("goodpass", key=test_key),
            status="active"
        )
        u3 = User(
            telegram_chat_id=333,
            moodle_username="user3",
            status="paused"
        )
        db.add_all([u1, u2, u3])

    # Run check for user1 (which fails create_session in mock/unconnected environment)
    res = run_check_for_user(u1.id)
    assert res is False

    with get_db_context() as db:
        check_u1 = db.query(User).filter_by(id=u1.id).first()
        check_u2 = db.query(User).filter_by(id=u2.id).first()
        check_u3 = db.query(User).filter_by(id=u3.id).first()

        # User 1 should transition to error status
        assert check_u1.status == "error"
        assert check_u1.last_error is not None

        # User 2 and User 3 must remain isolated and unaffected
        assert check_u2.status == "active"
        assert check_u2.last_error is None
        assert check_u3.status == "paused"


def test_scheduler_job_syncing(db_session):
    with get_db_context() as db:
        u_active = User(telegram_chat_id=7001, moodle_username="active_usr", status="active")
        u_paused = User(telegram_chat_id=7002, moodle_username="paused_usr", status="paused")
        db.add_all([u_active, u_paused])

    # Sync jobs
    sync_user_jobs()

    # Active user should have a scheduled job
    active_job = scheduler.get_job(f"user_job_{u_active.id}")
    paused_job = scheduler.get_job(f"user_job_{u_paused.id}")

    assert active_job is not None
    assert paused_job is None

    # Update active user to paused
    with get_db_context() as db:
        u = db.query(User).filter_by(id=u_active.id).first()
        u.status = "paused"

    # Re-sync
    sync_user_jobs()

    # Now active_job should be removed from scheduler
    assert scheduler.get_job(f"user_job_{u_active.id}") is None
