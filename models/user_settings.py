from sqlalchemy import Column, Integer, Boolean, String, ForeignKey, JSON
from sqlalchemy.orm import relationship
from database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)

    notify_files = Column(Boolean, default=True, nullable=False)
    notify_assignments = Column(Boolean, default=True, nullable=False)
    notify_quizzes = Column(Boolean, default=True, nullable=False)
    notify_folders = Column(Boolean, default=True, nullable=False)

    digest_mode = Column(String(20), default="instant", nullable=False)  # instant / daily
    digest_time = Column(String(10), default="20:00", nullable=False)
    quiet_hours_start = Column(String(10), nullable=True)
    quiet_hours_end = Column(String(10), nullable=True)
    muted_courses = Column(JSON, default=list, nullable=False)
    ai_summaries_enabled = Column(Boolean, default=True, nullable=False)

    user = relationship("User", back_populates="settings")
