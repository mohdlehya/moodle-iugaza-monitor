import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from contextlib import contextmanager

Base = declarative_base()

_engine = None
_current_db_url = None


def get_db_url():
    url = os.getenv("DATABASE_URL", "sqlite:///./moodle.db")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return url


DATABASE_URL = get_db_url()


def get_engine():
    global _engine, _current_db_url
    url = get_db_url()

    if _engine is None or _current_db_url != url:
        connect_args = {}
        if url.startswith("sqlite"):
            connect_args["check_same_thread"] = False
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
        _current_db_url = url

    return _engine


def SessionLocal():
    return sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=get_engine())()


def get_db():
    """Yield a database session for generator / API usage."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager for non-generator database session usage with auto-commit/rollback."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    """Ensure all SQLAlchemy tables are created on database engine."""
    import models  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables verified and created.", flush=True)
