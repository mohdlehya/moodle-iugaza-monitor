import json
import os
import time
import sys
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

from database import get_db_context
from models import User, UserSettings, CourseContent, CalendarEvent, NotificationLog
from crypto import decrypt_credential
from scraper import create_session, get_courses
from telegram_bot import send_message
from calendar_api import (
    get_upcoming_events,
    parse_events,
    find_new_events,
    build_events_message,
)
from groq_helper import (
    summarize_quiz,
    summarize_assignment,
    summarize_calendar_events,
)

load_dotenv()

MOODLE_BASE = os.getenv("MOODLE_URL", "https://moodle.iugaza.edu.ps")
SILENT_MODE = "--silent" in sys.argv


def safe_get(session, url: str, retries: int = 3, delay: int = 4):
    for attempt in range(retries):
        try:
            time.sleep(delay)
            return session.get(url, timeout=30)
        except Exception as e:
            print(f"    ⚠️ محاولة {attempt+1}/{retries} فشلت: {type(e).__name__}")
            if attempt < retries - 1:
                time.sleep(6)
    return None


def get_course_content(session, course_url: str) -> dict:
    r = safe_get(session, course_url, delay=2)
    if not r:
        return {"files": [], "assignments": [], "quizzes": [], "folders": []}

    soup = BeautifulSoup(r.text, "html.parser")
    content = {"files": [], "assignments": [], "quizzes": [], "folders": []}

    for item in soup.select('a[href*="/mod/resource/view.php"]'):
        name = item.get_text(strip=True)
        if name:
            content["files"].append({"name": name, "url": item["href"]})

    for item in soup.select('a[href*="/mod/assign/view.php"]'):
        name = item.get_text(strip=True)
        if name:
            content["assignments"].append({"name": name, "url": item["href"]})

    for item in soup.select('a[href*="/mod/quiz/view.php"]'):
        name = item.get_text(strip=True)
        if name:
            content["quizzes"].append({"name": name, "url": item["href"]})

    for item in soup.select('a[href*="/mod/folder/view.php"]'):
        name = item.get_text(strip=True)
        if name:
            content["folders"].append({"name": name, "url": item["href"]})

    return content


def analyze_assignment(session, url: str) -> dict:
    r = safe_get(session, url, delay=3)
    if not r:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    info = {}
    for row in soup.select("table.generaltable tr"):
        cells = row.find_all("td")
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(strip=True)
            if "due" in label or "deadline" in label:
                info["due_date"] = value
            elif "submission status" in label or "حالة" in label:
                info["status"] = value
    return info


def analyze_quiz(session, url: str) -> dict:
    r = safe_get(session, url, delay=3)
    if not r:
        return {}
    soup = BeautifulSoup(r.text, "html.parser")
    info = {}
    for row in soup.select("table.generaltable tr"):
        cells = row.find_all("td")
        if len(cells) >= 2:
            label = cells[0].get_text(strip=True).lower()
            value = cells[1].get_text(strip=True)
            if "clos" in label:
                info["closes"] = value
            elif "time limit" in label:
                info["time_limit"] = value
    return info


def find_new_items(old: dict, new: dict) -> dict:
    changes = {}
    for course_name, content in new.items():
        old_content = old.get(course_name, {})
        course_changes = {}
        for category in ["files", "assignments", "quizzes", "folders"]:
            old_urls = {i["url"] for i in old_content.get(category, [])}
            new_items = [i for i in content.get(category, []) if i["url"] not in old_urls]
            if new_items:
                course_changes[category] = new_items
        if course_changes:
            changes[course_name] = course_changes
    return changes


def notify_user(chat_id: int | str, msg: str, user_id: int = None, notification_type: str = "general"):
    """Notify user if silent mode is off and record NotificationLog entry in DB."""
    if not SILENT_MODE and chat_id:
        send_message(msg, chat_id=chat_id)
        if user_id:
            try:
                with get_db_context() as db:
                    log_entry = NotificationLog(
                        user_id=user_id,
                        notification_type=notification_type,
                        status="sent",
                        content_preview=msg[:100]
                    )
                    db.add(log_entry)
            except Exception as e:
                print(f"⚠️ Could not log notification: {e}")


def run_check_for_user(user_id: int) -> bool:
    """Run an isolated check for a single user, applying notification preferences & logging."""
    with get_db_context() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or user.status != "active":
            print(f"ℹ️ User ID {user_id} is not active. Skipping.")
            return False

        chat_id = user.telegram_chat_id
        username = user.moodle_username
        enc_password = user.moodle_password_encrypted

        if not username or not enc_password:
            user.status = "error"
            user.last_error = "Missing Moodle credentials"
            notify_user(chat_id, "⚠️ <b>فحص Moodle:</b> تعذر التشغيل بسبب نقص بيانات الدخول.", user_id=user_id, notification_type="error")
            return False

        try:
            password = decrypt_credential(enc_password)
        except Exception as e:
            user.status = "error"
            user.last_error = f"Credential decryption failed: {e}"
            notify_user(chat_id, "⚠️ <b>فحص Moodle:</b> فشل فك تشفير كلمة المرور.", user_id=user_id, notification_type="error")
            return False

        st = db.query(UserSettings).filter(UserSettings.user_id == user_id).first()
        if not st:
            st = UserSettings(user_id=user_id)
            db.add(st)
            db.flush()

        notify_files = st.notify_files
        notify_assignments = st.notify_assignments
        notify_quizzes = st.notify_quizzes
        notify_folders = st.notify_folders
        ai_enabled = st.ai_summaries_enabled
        muted_courses = list(st.muted_courses or [])

    print(f"\n🔄 [User ID {user_id} - {username}] Starting Moodle check...")
    try:
        session = create_session(username, password)
    except Exception as e:
        print(f"❌ [User ID {user_id}] Login failed: {e}")
        with get_db_context() as db:
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.status = "error"
                u.last_error = f"Login failed: {e}"
        notify_user(chat_id, f"⚠️ <b>فحص Moodle:</b> فشل تسجيل الدخول.\nالسبب: {e}\n\nيرجى إعادة التثبت عبر /register.", user_id=user_id, notification_type="error")
        return False

    try:
        courses = get_courses(session)
        current_data = {}
        for course in courses:
            print(f"  🔍 {course['name']}...")
            content = get_course_content(session, course["url"])
            current_data[course["name"]] = content

        with get_db_context() as db:
            content_rec = db.query(CourseContent).filter(CourseContent.user_id == user_id).first()
            is_first_run = content_rec is None or not content_rec.content_json
            previous_data = content_rec.content_json if content_rec and content_rec.content_json else {}

            if not content_rec:
                content_rec = CourseContent(user_id=user_id, content_json=current_data)
                db.add(content_rec)
            else:
                content_rec.content_json = current_data

        if is_first_run:
            total = sum(len(v) for c in current_data.values() for v in c.values())
            welcome = (
                f"✅ <b>تم تفعيل نظام مراقبة Moodle لحسابك!</b>\n\n"
                f"📚 المساقات المُراقَبة: <b>{len(courses)}</b>\n"
                f"📦 إجمالي المحتوى المحفوظ: <b>{total}</b> عنصر\n\n"
                f"⏰ سأُخطرك فور إضافة أي محتوى جديد 🎯"
            )
            for course in courses:
                c = current_data.get(course["name"], {})
                welcome += (
                    f"\n\n📌 <b>{course['name']}</b>\n"
                    f"   📄 {len(c.get('files', []))} ملف  |  "
                    f"📝 {len(c.get('assignments', []))} واجب  |  "
                    f"❓ {len(c.get('quizzes', []))} كويز"
                )
            notify_user(chat_id, welcome, user_id=user_id, notification_type="welcome")
        else:
            new_items = find_new_items(previous_data, current_data)
            if new_items:
                print(f"🔬 [User ID {user_id}] New items detected! Analyzing with user preferences...")
                messages = []
                for course_name, changes in new_items.items():
                    if course_name in muted_courses:
                        print(f"🔇 [User ID {user_id}] Course '{course_name}' is muted. Skipping push notification.")
                        continue

                    msg = [f"🆕 <b>محتوى جديد — {course_name}</b>\n"]
                    has_notifiable_content = False

                    if notify_assignments:
                        for item in changes.get("assignments", []):
                            has_notifiable_content = True
                            info = analyze_assignment(session, item["url"])
                            summary = summarize_assignment(
                                session, name=item["name"],
                                url=item["url"], course=course_name,
                                event_due_date=info.get("due_date", "")
                            ) if ai_enabled else ""
                            msg.append(f"📝 <b>واجب جديد:</b> {item['name']}")
                            if info.get("due_date"):
                                msg.append(f"⏰ <b>موعد التسليم:</b> {info['due_date']}")
                            if summary:
                                msg.append(f"\n🤖 <b>ملخص ذكي:</b>\n{summary}")
                            msg.append(f'🔗 <a href="{item["url"]}">افتح الواجب</a>\n')

                    if notify_quizzes:
                        for item in changes.get("quizzes", []):
                            has_notifiable_content = True
                            info = analyze_quiz(session, item["url"])
                            summary = summarize_quiz(
                                session, name=item["name"],
                                url=item["url"], course=course_name,
                                event_time_close=info.get("closes", "")
                            ) if ai_enabled else ""
                            msg.append(f"❓ <b>كويز جديد:</b> {item['name']}")
                            if info.get("closes"):
                                msg.append(f"🔴 <b>يغلق:</b> {info['closes']}")
                            if summary:
                                msg.append(f"\n🤖 <b>ملخص ذكي:</b>\n{summary}")
                            msg.append(f'🔗 <a href="{item["url"]}">افتح الكويز</a>\n')

                    if notify_files:
                        for item in changes.get("files", []):
                            has_notifiable_content = True
                            msg.append(f"📄 <b>{item['name']}</b>")
                            msg.append(f'🔗 <a href="{item["url"]}">افتح الملف</a>\n')

                    if notify_folders:
                        for item in changes.get("folders", []):
                            has_notifiable_content = True
                            msg.append(f"📁 <b>مجلد جديد: {item['name']}</b>")
                            msg.append(f'🔗 <a href="{item["url"]}">افتح المجلد</a>\n')

                    if has_notifiable_content:
                        messages.append("\n".join(msg))

                for m in messages:
                    notify_user(chat_id, m, user_id=user_id, notification_type="course_update")
                    time.sleep(1)

        # Scrape Calendar Events
        print(f"📅 [User ID {user_id}] Fetching calendar events...")
        try:
            time.sleep(3)
            raw_events = get_upcoming_events(session)
        except Exception:
            time.sleep(3)
            session = create_session(username, password)
            raw_events = get_upcoming_events(session)

        parsed_events = parse_events(raw_events)

        with get_db_context() as db:
            events_rec = db.query(CalendarEvent).filter(CalendarEvent.user_id == user_id).first()
            old_events = events_rec.events_json if events_rec and events_rec.events_json else []
            new_events = find_new_events(old_events, parsed_events)

            if not events_rec:
                events_rec = CalendarEvent(user_id=user_id, events_json=parsed_events)
                db.add(events_rec)
            else:
                events_rec.events_json = parsed_events

        if new_events:
            print(f"🆕 [User ID {user_id}] {len(new_events)} new calendar events.")
            notify_user(chat_id, build_events_message(new_events), user_id=user_id, notification_type="calendar_update")

            if ai_enabled:
                ai_summary = summarize_calendar_events(session, new_events)
                if ai_summary:
                    notify_user(chat_id, f"🤖 <b>تقرير ذكي — {len(new_events)} تحديث جديد</b>\n\n{ai_summary}", user_id=user_id, notification_type="calendar_ai_summary")

        with get_db_context() as db:
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.last_check_at = datetime.now()
                u.last_error = None

        print(f"✅ [User ID {user_id}] Check completed successfully.")
        return True

    except Exception as e:
        print(f"❌ [User ID {user_id}] Check failed with exception: {e}")
        with get_db_context() as db:
            u = db.query(User).filter(User.id == user_id).first()
            if u:
                u.last_error = str(e)
        return False


def run_check_for_all_users():
    """Trigger check for all active users sequentially."""
    with get_db_context() as db:
        active_users = db.query(User).filter(User.status == "active").all()
        user_ids = [u.id for u in active_users]

    print(f"🚀 Running check for {len(user_ids)} active user(s)...")
    for uid in user_ids:
        try:
            run_check_for_user(uid)
        except Exception as e:
            print(f"⚠️ Unhandled error checking User ID {uid}: {e}")


if __name__ == "__main__":
    run_check_for_all_users()
