from sqlalchemy import Column, Integer, BigInteger, String, LargeBinary, DateTime, Text, func
from sqlalchemy.orm import relationship
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    telegram_chat_id = Column(BigInteger, unique=True, nullable=False, index=True)
    telegram_username = Column(String(255), nullable=True)
    moodle_username = Column(String(255), nullable=True)
    moodle_password_encrypted = Column(LargeBinary, nullable=True)
    groq_api_key_encrypted = Column(LargeBinary, nullable=True)
    moodle_url = Column(String(255), default="https://moodle.iugaza.edu.ps", nullable=False)
    language = Column(String(10), default="ar", nullable=False)
    status = Column(String(20), default="active", nullable=False)  # active, paused, error, unregistered
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_check_at = Column(DateTime(timezone=True), nullable=True)
    last_error = Column(Text, nullable=True)

    # Relationships
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    course_contents = relationship("CourseContent", back_populates="user", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="user", cascade="all, delete-orphan")
    notification_logs = relationship("NotificationLog", back_populates="user", cascade="all, delete-orphan")
