from database import get_db_context
from models import User


def delete_user_account(user_id: int) -> bool:
    """Completely delete user account and cascade-delete all associated settings, snapshots, and logs."""
    with get_db_context() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False
        db.delete(user)
        return True


def delete_user_by_telegram_id(telegram_chat_id: int) -> bool:
    """Delete user account using telegram_chat_id."""
    with get_db_context() as db:
        user = db.query(User).filter(User.telegram_chat_id == telegram_chat_id).first()
        if not user:
            return False
        db.delete(user)
        return True
