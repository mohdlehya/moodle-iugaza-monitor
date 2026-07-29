import os
import json
import sys
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
load_dotenv()

from database import get_db_context
from models import User, UserSettings, CourseContent, CalendarEvent
from crypto import encrypt_credential


def safe_encrypt(secret_str: str) -> bytes:
    """Encrypt secret string using crypto module if key is present, else store raw UTF-8 bytes."""
    if not secret_str:
        return None
    try:
        return encrypt_credential(secret_str)
    except Exception as e:
        print(f"⚠️ Notice: Storing credential unencrypted (CREDENTIALS_ENCRYPTION_KEY not set or invalid: {e}).")
        return secret_str.encode("utf-8")


def migrate_single_user(data_path="data.json", events_path="events.json"):
    chat_id_raw = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id_raw:
        print("❌ TELEGRAM_CHAT_ID environment variable not set. Aborting migration.")
        return False

    chat_id = int(chat_id_raw)
    moodle_username = os.getenv("MOODLE_USERNAME")
    moodle_password = os.getenv("MOODLE_PASSWORD")
    groq_api_key = os.getenv("GROQ_API_KEY")
    moodle_url = os.getenv("MOODLE_URL", "https://moodle.iugaza.edu.ps")

    with get_db_context() as db:
        existing_user = db.query(User).filter(User.telegram_chat_id == chat_id).first()
        if existing_user:
            print(f"ℹ️ User with telegram_chat_id={chat_id} already exists in DB (User ID {existing_user.id}).")
            user = existing_user
        else:
            user = User(
                telegram_chat_id=chat_id,
                moodle_username=moodle_username,
                moodle_password_encrypted=safe_encrypt(moodle_password),
                groq_api_key_encrypted=safe_encrypt(groq_api_key),
                moodle_url=moodle_url,
                language="ar",
                status="active"
            )
            db.add(user)
            db.flush()

            settings = UserSettings(user_id=user.id)
            db.add(settings)
            print(f"✅ Created User (id={user.id}, telegram_chat_id={chat_id}) and default settings.")

        if os.path.exists(data_path):
            try:
                with open(data_path, "r", encoding="utf-8") as f:
                    content_json = json.load(f)

                existing_content = db.query(CourseContent).filter(CourseContent.user_id == user.id).first()
                if existing_content:
                    existing_content.content_json = content_json
                    print("✅ Updated existing CourseContent record from data.json.")
                else:
                    course_content = CourseContent(user_id=user.id, content_json=content_json)
                    db.add(course_content)
                    print("✅ Imported CourseContent snapshot from data.json.")
            except Exception as e:
                print(f"⚠️ Error reading/importing {data_path}: {e}")

        if os.path.exists(events_path):
            try:
                with open(events_path, "r", encoding="utf-8") as f:
                    events_json = json.load(f)

                existing_events = db.query(CalendarEvent).filter(CalendarEvent.user_id == user.id).first()
                if existing_events:
                    existing_events.events_json = events_json
                    print("✅ Updated existing CalendarEvent record from events.json.")
                else:
                    calendar_event = CalendarEvent(user_id=user.id, events_json=events_json)
                    db.add(calendar_event)
                    print("✅ Imported CalendarEvent snapshot from events.json.")
            except Exception as e:
                print(f"⚠️ Error reading/importing {events_path}: {e}")

    print("🎉 Migration completed successfully.")
    return True


if __name__ == "__main__":
    migrate_single_user()
