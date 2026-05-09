
## 📄 `main.py` — نسخة نهائية كاملة


import json, os, time, threading
from datetime import datetime
from scraper import create_session, get_courses
from bs4 import BeautifulSoup
from telegram_bot import send_message, build_report
from calendar_api import (get_upcoming_events, parse_events,
                           load_previous_events, save_events,
                           find_new_events, build_events_message)
from groq_helper import summarize_quiz, summarize_assignment, summarize_calendar_events
from dotenv import load_dotenv

load_dotenv()

MOODLE_BASE = os.getenv("MOODLE_URL", "https://moodle.iugaza.edu.ps")


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

    soup    = BeautifulSoup(r.text, "html.parser")
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


def load_previous_data(path="data.json") -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except json.JSONDecodeError:
        return {}


def save_data(data: dict, path="data.json"):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def find_new_items(old: dict, new: dict) -> dict:
    changes = {}
    for course_name, content in new.items():
        old_content    = old.get(course_name, {})
        course_changes = {}
        for category in ["files", "assignments", "quizzes", "folders"]:
            old_urls  = {i["url"] for i in old_content.get(category, [])}
            new_items = [i for i in content.get(category, []) if i["url"] not in old_urls]
            if new_items:
                course_changes[category] = new_items
        if course_changes:
            changes[course_name] = course_changes
    return changes


# ══════════════════════════════════════════════════════════════
def main():
# ══════════════════════════════════════════════════════════════
    username = os.getenv("MOODLE_USERNAME")
    password = os.getenv("MOODLE_PASSWORD")

    is_first_run = not os.path.exists("data.json")

    session = create_session(username, password)
    courses = get_courses(session)

    # ── جلب المحتوى
    print("\n📥 جاري جلب المحتوى...")
    current_data = {}
    for course in courses:
        print(f"  🔍 {course['name']}...")
        content = get_course_content(session, course["url"])
        current_data[course["name"]] = content

    save_data(current_data)
    print("💾 تم حفظ البيانات")

    # ══════════════════════════════════
    # أول تشغيل
    # ══════════════════════════════════
    if is_first_run:
        total   = sum(len(v) for c in current_data.values() for v in c.values())
        welcome = (
            f"✅ <b>تم تفعيل نظام مراقبة Moodle!</b>\n\n"
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
        send_message(welcome)
        print("📨 تم إرسال رسالة الترحيب")

    # ══════════════════════════════════
    # تشغيل عادي — ابحث عن الجديد
    # ══════════════════════════════════
    else:
        previous_data = load_previous_data()
        new_items     = find_new_items(previous_data, current_data)

        if new_items:
            print(f"\n🔬 تحليل العناصر الجديدة...")
            messages = []

            for course_name, changes in new_items.items():
                msg = [f"🆕 <b>محتوى جديد — {course_name}</b>\n"]

                # ── الواجبات الجديدة ──────────────────
                for item in changes.get("assignments", []):
                    print(f"  📝 {item['name']}")
                    info    = analyze_assignment(session, item["url"])
                    
                    # ← Groq هنا
                    summary = summarize_assignment(
                        session,
                        name           = item["name"],
                        url            = item["url"],
                        course         = course_name,
                        event_due_date = info.get("due_date", ""),
                    )
                    msg.append(f"📝 <b>واجب جديد:</b> {item['name']}")
                    if info.get("due_date"):
                        msg.append(f"⏰ <b>موعد التسليم:</b> {info['due_date']}")
                    if summary:
                        msg.append(f"\n🤖 <b>ملخص ذكي:</b>\n{summary}")
                    msg.append(f'🔗 <a href="{item["url"]}">افتح الواجب</a>\n')

                # ── الكويزات الجديدة ──────────────────
                for item in changes.get("quizzes", []):
                    print(f"  ❓ {item['name']}")
                    info    = analyze_quiz(session, item["url"])
                    
                    # ← Groq هنا
                    summary = summarize_quiz(
                        session,
                        name             = item["name"],
                        url              = item["url"],
                        course           = course_name,
                        event_time_close = info.get("closes", ""),
                    )
                    msg.append(f"❓ <b>كويز جديد:</b> {item['name']}")
                    if info.get("closes"):
                        msg.append(f"🔴 <b>يغلق:</b> {info['closes']}")
                    if summary:
                        msg.append(f"\n🤖 <b>ملخص ذكي:</b>\n{summary}")
                    msg.append(f'🔗 <a href="{item["url"]}">افتح الكويز</a>\n')

                # ── الملفات الجديدة ───────────────────
                for item in changes.get("files", []):
                    print(f"  📄 {item['name']}")
                    msg.append(f"📄 <b>{item['name']}</b>")
                    msg.append(f'🔗 <a href="{item["url"]}">افتح الملف</a>\n')

                messages.append("\n".join(msg))

            for msg in messages:
                send_message(msg)
                time.sleep(1)

            print(f"📨 تم إرسال {len(messages)} تقرير")
        else:
            print("✅ لا يوجد جديد")

    # ══════════════════════════════════
    # Calendar API
    # ══════════════════════════════════
    print("\n📅 جاري جلب أحداث التقويم...")
    try:
        time.sleep(5)
        raw_events = get_upcoming_events(session)
    except Exception:
        print("  🔄 إعادة تسجيل الدخول للـ Calendar...")
        time.sleep(5)
        session    = create_session(username, password)
        time.sleep(3)
        raw_events = get_upcoming_events(session)

    parsed_events = parse_events(raw_events)
    old_events    = load_previous_events()
    new_events    = find_new_events(old_events, parsed_events)
    save_events(parsed_events)

    if new_events:
        print(f"🆕 {len(new_events)} حدث جديد في التقويم")
        
        # الرسالة العادية
        send_message(build_events_message(new_events))
        
        # ← Groq هنا — تقرير ذكي مع تصفح الروابط
        print("🤖 جاري تلخيص الأحداث بـ Groq...")
        ai_summary = summarize_calendar_events(session, new_events)
        if ai_summary:
            send_message(
                f"🤖 <b>تقرير ذكي — {len(new_events)} تحديث جديد</b>\n\n{ai_summary}"
            )
    else:
        print("✅ لا أحداث تقويم جديدة")

    print(f"\n⏰ انتهى: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ══════════════════════════════════════
if __name__ == "__main__":
    main()


