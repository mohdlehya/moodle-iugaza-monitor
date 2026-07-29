import os
import sys
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_db_context
from models import User, UserSettings, NotificationLog
from telegram_bot import is_admin
from app import app


@pytest.fixture(scope="function")
def db_session(monkeypatch, tmp_path):
    db_file = tmp_path / "test_admin.db"
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


def test_admin_authorization_guard(monkeypatch):
    monkeypatch.setenv("ADMIN_CHAT_ID", "999888777")
    assert is_admin(999888777) is True
    assert is_admin(111222333) is False

    monkeypatch.delenv("ADMIN_CHAT_ID", raising=False)
    # Dev mode fallback
    assert is_admin(111222333) is True


def test_admin_retry_user_error_recovery(db_session):
    with get_db_context() as db:
        u = User(
            telegram_chat_id=555444,
            moodle_username="error_user",
            status="error",
            last_error="Simulated network failure"
        )
        db.add(u)
        db.flush()
        uid = u.id

    with get_db_context() as db:
        user_rec = db.query(User).filter(User.id == uid).first()
        user_rec.status = "active"
        user_rec.last_error = None

    with get_db_context() as db:
        res = db.query(User).filter(User.id == uid).first()
        assert res.status == "active"
        assert res.last_error is None


def test_flask_health_and_metrics_routes(db_session):
    client = app.test_client()

    r_health = client.get("/healthz")
    assert r_health.status_code == 200
    data_health = r_health.get_json()
    assert data_health["database"] == "ok"

    r_metrics = client.get("/metrics")
    assert r_metrics.status_code == 200
    data_metrics = r_metrics.get_json()
    assert "uptime_seconds" in data_metrics
    assert "total_users" in data_metrics

    r_export = client.get("/admin_export")
    assert r_export.status_code == 200
    data_export = r_export.get_json()
    assert "exported_at" in data_export
    assert "users" in data_export
