import requests, os, json, re, threading, time
from datetime import datetime
from dotenv import load_dotenv
from calendar_api import get_deadlines_message, load_previous_events
from groq_helper import chat_with_context   # ← أضف هذا

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")
DATA_FILE = "data.json"


def send_message(text: str):
    if not BOT_TOKEN or not CHAT_ID:
        print("⚠️ BOT_TOKEN أو CHAT_ID غير موجود")
        return
    url    = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            requests.post(url, json={
                "chat_id":                  CHAT_ID,
                "text":                     chunk,
                "parse_mode":               "HTML",
                "disable_web_page_preview": True
            }, timeout=15)
        except Exception as e:
            print(f"⚠️ فشل الإرسال: {e}")


def build_report(new_items: dict) -> str:
    lines = [f"🆕 <b>محتوى جديد على Moodle</b> — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
    for course, changes in new_items.items():
        lines.append(f"\n📚 <b>{course}</b>")
        for item in changes.get("files", []):
            lines.append(f"  📄 <a href='{item['url']}'>{item['name']}</a>")
        for item in changes.get("assignments", []):
            lines.append(f"  📝 <a href='{item['url']}'>{item['name']}</a>")
        for item in changes.get("quizzes", []):
            lines.append(f"  ❓ <a href='{item['url']}'>{item['name']}</a>")
        for item in changes.get("folders", []):
            lines.append(f"  📁 <a href='{item['url']}'>{item['name']}</a>")
    return "\n".join(lines)


def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}


def _find_course(data: dict, query: str) -> str | None:
    if not query:
        return None
    q = query.upper().strip()
    for course in data:
        if q in course.upper():
            return course
    return None


def handle_command(text: str) -> str:
    text = text.strip()
    data = load_data()

    # ══════════════════════════════════
    # /start و /help
    # ══════════════════════════════════
    if text in ["/start", "/help"]:
        return (
            "🤖 <b>أوامر بوت Moodle Monitor</b>\n\n"
            "📚 <b>المساقات:</b>\n"
            "/courses — جميع المساقات مع الإحصائيات والروابط\n"
            "/summary — ملخص عددي\n\n"
            "📅 <b>المواعيد:</b>\n"
            "/updates — جميع المواعيد القادمة\n"
            "/deadlines — أقرب 10 مواعيد مع الوقت المتبقي\n\n"
            "📂 <b>محتوى المساقات:</b>\n"
            "/files SDEV3305 — ملفات مساق معين\n"
            "/assignments SICT — واجبات مساق\n"
            "/quizzes SDEV2107 — كويزات مساق\n\n"
            "🔍 <b>أدوات:</b>\n"
            "/search كلمة — بحث في كل المحتوى\n"
            "/last — متى كان آخر تحديث\n\n"
            "🤖 <b>الذكاء الاصطناعي:</b>\n"     # ← أُضيف هنا
            "/ai سؤالك — اسأل عن أي شيء في مساقاتك\n"
        )

    # ══════════════════════════════════
    # /courses
    # ══════════════════════════════════
    if text == "/courses":
        if not data:
            return "❌ لا توجد بيانات — شغّل main.py أولاً"
        lines     = ["📚 <b>جميع المساقات المسجّلة:</b>\n"]
        total_all = 0
        for i, (course, c) in enumerate(data.items(), 1):
            files   = c.get("files", [])
            assign  = c.get("assignments", [])
            quizzes = c.get("quizzes", [])
            total   = len(files) + len(assign) + len(quizzes)
            total_all += total
            course_url = ""
            for cat in [files, assign, quizzes]:
                if cat:
                    match = re.search(r'\?id=(\d+)', cat[0]["url"])
                    if match:
                        course_url = f"https://moodle.iugaza.edu.ps/course/view.php?id={match.group(1)}"
                    break
            lines.append(
                f"{i}. <b>{course}</b>\n"
                f"   📄 {len(files)} ملف  |  📝 {len(assign)} واجب  |  ❓ {len(quizzes)} كويز\n"
                + (f"   🔗 <a href='{course_url}'>افتح المساق</a>\n" if course_url else "")
            )
        lines.append(f"📦 <b>الإجمالي: {total_all} عنصر</b>")
        return "\n".join(lines)

    # ══════════════════════════════════
    # /summary
    # ══════════════════════════════════
    if text == "/summary":
        if not data:
            return "❌ لا توجد بيانات"
        lines     = [f"📊 <b>ملخص المحتوى</b> — {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"]
        total_all = 0
        for course, c in data.items():
            t = sum(len(v) for v in c.values())
            total_all += t
            lines.append(
                f"📌 <b>{course}</b>\n"
                f"   📄 {len(c.get('files',[]))} ملف  |  "
                f"📝 {len(c.get('assignments',[]))} واجب  |  "
                f"❓ {len(c.get('quizzes',[]))} كويز\n"
            )
        lines.append(f"📦 الإجمالي: <b>{total_all}</b> عنصر")
        return "\n".join(lines)

    # ══════════════════════════════════
    # /updates و /deadlines
    # ══════════════════════════════════
    if text in ["/updates", "/deadlines"]:
        limit = 15 if text == "/updates" else 10
        return get_deadlines_message(limit=limit)

    # ══════════════════════════════════
    # /last
    # ══════════════════════════════════
    if text == "/last":
        if os.path.exists(DATA_FILE):
            mtime = os.path.getmtime(DATA_FILE)
            dt    = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
            return f"⏰ آخر تحديث: <b>{dt}</b>"
        return "❌ لا توجد بيانات بعد"

    # ══════════════════════════════════
    # /files
    # ══════════════════════════════════
    if text.startswith("/files"):
        query  = text[6:].strip()
        if not query:
            lines = ["📄 <b>جميع الملفات:</b>\n"]
            for course, c in data.items():
                items = c.get("files", [])
                if items:
                    lines.append(f"\n📚 <b>{course}</b>")
                    for item in items:
                        lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
            return "\n".join(lines)
        course = _find_course(data, query)
        if not course:
            return f"❌ لم أجد مساقاً باسم: {query}\nاستخدم /courses للقائمة"
        items = data[course].get("files", [])
        if not items:
            return f"📂 لا توجد ملفات في {course}"
        lines = [f"📄 <b>ملفات {course}:</b>\n"]
        for item in items:
            lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
        return "\n".join(lines)

    # ══════════════════════════════════
    # /assignments
    # ══════════════════════════════════
    if text.startswith("/assignments"):
        query  = text[12:].strip()
        if not query:
            lines = ["📝 <b>جميع الواجبات:</b>\n"]
            for course, c in data.items():
                items = c.get("assignments", [])
                if items:
                    lines.append(f"\n📚 <b>{course}</b>")
                    for item in items:
                        lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
            return "\n".join(lines)
        course = _find_course(data, query)
        if not course:
            return f"❌ لم أجد مساقاً باسم: {query}"
        items = data[course].get("assignments", [])
        if not items:
            return f"📝 لا توجد واجبات في {course}"
        lines = [f"📝 <b>واجبات {course}:</b>\n"]
        for item in items:
            lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
        return "\n".join(lines)

    # ══════════════════════════════════
    # /quizzes
    # ══════════════════════════════════
    if text.startswith("/quizzes"):
        query  = text[8:].strip()
        if not query:
            lines = ["❓ <b>جميع الكويزات:</b>\n"]
            for course, c in data.items():
                items = c.get("quizzes", [])
                if items:
                    lines.append(f"\n📚 <b>{course}</b>")
                    for item in items:
                        lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
            return "\n".join(lines)
        course = _find_course(data, query)
        if not course:
            return f"❌ لم أجد مساقاً باسم: {query}"
        items = data[course].get("quizzes", [])
        if not items:
            return f"❓ لا توجد كويزات في {course}"
        lines = [f"❓ <b>كويزات {course}:</b>\n"]
        for item in items:
            lines.append(f"• <a href='{item['url']}'>{item['name']}</a>")
        return "\n".join(lines)

    # ══════════════════════════════════
    # /search
    # ══════════════════════════════════
    if text.startswith("/search"):
        keyword = text[7:].strip().lower()
        if not keyword:
            return "❌ استخدم: /search كلمة_البحث"
        results = []
        for course, c in data.items():
            for cat in ["files", "assignments", "quizzes"]:
                for item in c.get(cat, []):
                    if keyword in item["name"].lower():
                        emoji = {"files": "📄", "assignments": "📝", "quizzes": "❓"}[cat]
                        results.append(
                            f"{emoji} <a href='{item['url']}'>{item['name']}</a>\n"
                            f"   📚 {course}"
                        )
        if not results:
            return f"🔍 لا توجد نتائج لـ: <b>{keyword}</b>"
        return f"🔍 <b>نتائج \"{keyword}\":</b>\n\n" + "\n\n".join(results)

    # ══════════════════════════════════
    # /ai  ← أُضيف هنا قبل الأخير مباشرة
    # ══════════════════════════════════
    if text.startswith("/ai"):
        question = text[3:].strip()
        if not question:
            return (
                "🤖 <b>اسألني أي شيء عن مساقاتك!</b>\n\n"
                "أمثلة:\n"
                "/ai ما هي الكويزات القادمة؟\n"
                "/ai متى موعد تسليم واجبات SDEV3305؟\n"
                "/ai كيف أستعد للأسبوع القادم؟\n"
                "/ai ما هي أصعب المواد هذا الفصل؟\n"
                "/ai رتّب أولوياتي للأسبوع القادم"
            )
        if not data:
            return "❌ لا توجد بيانات — شغّل main.py أولاً"

        events = load_previous_events()
        send_message("⏳ جاري التفكير...")
        answer = chat_with_context(question, data, events)
        return f"🤖 <b>Groq AI:</b>\n\n{answer}"

    # ══════════════════════════════════
    # أمر غير معروف ← الأخير دائماً
    # ══════════════════════════════════
    return "❓ أمر غير معروف — أرسل /help للمساعدة"


# ══════════════════════════════════════
_offset = 0

def start_bot():
    global _offset
    print("🤖 البوت يستمع للأوامر...")
    while True:
        try:
            url  = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
            resp = requests.get(url, params={"offset": _offset, "timeout": 30}, timeout=35)
            for update in resp.json().get("result", []):
                _offset = update["update_id"] + 1
                msg = update.get("message", {})
                txt = msg.get("text", "")
                cid = str(msg.get("chat", {}).get("id", ""))
                if txt and cid == CHAT_ID:
                    reply = handle_command(txt)
                    send_message(reply)
        except Exception as e:
            time.sleep(5)