import os
import sys
import pytest
from cryptography.fernet import InvalidToken, Fernet
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from database import Base, get_engine
from models import User, UserSettings, CourseContent, CalendarEvent, NotificationLog
from crypto import (
    generate_encryption_key,
    get_fernet,
    encrypt_credential,
    decrypt_credential,
    mask_secret,
)
from services.user_service import delete_user_account, delete_user_by_telegram_id


@pytest.fixture
def test_key():
    return generate_encryption_key()


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite database for user service testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_generate_encryption_key():
    key = generate_encryption_key()
    assert isinstance(key, str)
    assert len(key) == 44  # Base64 encoded 32 bytes with padding


def test_encrypt_decrypt_roundtrip(test_key):
    plain_password = "SuperSecretPassword123!"
    plain_groq_key = "gsk_test_1234567890abcdefghijklmnopqrstuvwxyz"

    cipher_pass = encrypt_credential(plain_password, key=test_key)
    cipher_groq = encrypt_credential(plain_groq_key, key=test_key)

    assert isinstance(cipher_pass, bytes)
    assert cipher_pass != plain_password.encode()

    decrypted_pass = decrypt_credential(cipher_pass, key=test_key)
    decrypted_groq = decrypt_credential(cipher_groq, key=test_key)

    assert decrypted_pass == plain_password
    assert decrypted_groq == plain_groq_key


def test_invalid_token(test_key):
    other_key = generate_encryption_key()
    cipher = encrypt_credential("MySecret", key=test_key)

    with pytest.raises(InvalidToken):
        decrypt_credential(cipher, key=other_key)


def test_missing_environment_key(monkeypatch):
    monkeypatch.delenv("CREDENTIALS_ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValueError, match="CREDENTIALS_ENCRYPTION_KEY environment variable is not set"):
        encrypt_credential("Secret")


def test_none_and_empty_inputs(test_key):
    assert encrypt_credential(None, key=test_key) is None
    assert encrypt_credential("", key=test_key) == b""
    assert decrypt_credential(None, key=test_key) is None
    assert decrypt_credential(b"", key=test_key) == ""


def test_mask_secret():
    assert mask_secret("gsk_1234567890abcdef") == "gsk_...cdef"
    assert mask_secret("moodle_pass_12345") == "...2345"
    assert mask_secret("123") == "***"
    assert mask_secret("") == ""


def test_delete_user_account_service(db_session, monkeypatch, test_key):
    db_file = os.path.join(tempfile.gettempdir(), "test_user_service.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")

    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()

    user = User(
        telegram_chat_id=11223344,
        moodle_username="student_del",
        moodle_password_encrypted=encrypt_credential("pass123", key=test_key),
        groq_api_key_encrypted=encrypt_credential("gsk_key", key=test_key)
    )
    session.add(user)
    session.commit()

    settings = UserSettings(user_id=user.id)
    content = CourseContent(user_id=user.id, content_json={"CS": []})
    event = CalendarEvent(user_id=user.id, events_json=[])
    log = NotificationLog(user_id=user.id, notification_type="test", content_summary="log")

    session.add_all([settings, content, event, log])
    session.commit()

    user_id = user.id
    session.close()

    # Call deletion service
    deleted = delete_user_account(user_id)
    assert deleted is True

    session2 = TestingSession()
    assert session2.query(User).filter_by(id=user_id).first() is None
    assert session2.query(UserSettings).filter_by(user_id=user_id).first() is None
    assert session2.query(CourseContent).filter_by(user_id=user_id).first() is None
    assert session2.query(CalendarEvent).filter_by(user_id=user_id).first() is None
    assert session2.query(NotificationLog).filter_by(user_id=user_id).first() is None

    session2.close()
    engine.dispose()
    if os.path.exists(db_file):
        try:
            os.remove(db_file)
        except Exception:
            pass


import tempfile
