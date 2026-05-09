import os, requests, re, time
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"


# ══════════════════════════════════════
# استدعاء Groq
# ══════════════════════════════════════

def ask_groq(prompt: str, max_tokens: int = 500) -> str:
    if not GROQ_API_KEY:
        return ""
    try:
        r = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json"
            },
            json={
                "model":       GROQ_MODEL,
                "messages":    [{"role": "user", "content": prompt}],
                "max_tokens":  max_tokens,
                "temperature": 0.3
            },
            timeout=20
        )
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"⚠️ Groq error: {e}")
        return ""


# ══════════════════════════════════════
# جلب محتوى صفحة Moodle
# ══════════════════════════════════════

def scrape_moodle_page(session, url: str) -> dict:
    """يجلب كل التفاصيل من صفحة كويز أو واجب"""
    result = {
        "description": "",
        "time_open":   "",
        "time_close":  "",
        "time_limit":  "",
        "attempts":    "",
        "due_date":    "",
        "status":      "",
        "raw_text":    ""
    }
    try:
        time.sleep(2)
        r    = session.get(url, timeout=25)
        soup = BeautifulSoup(r.text, "html.parser")

        # احذف العناصر غير المفيدة
        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # ── الوصف / التعليمات
        for sel in [
            "#intro", ".generalbox.intro",
            ".activity-description",
            "[data-region='description']",
            ".box.generalbox.boxaligncenter",
            ".quizinfo"
        ]:
            el = soup.select_one(sel)
            if el:
                result["description"] = el.get_text(separator=" ", strip=True)[:800]
                break

        # ── جدول تفاصيل الكويز/الواجب
        for table in soup.select("table.generaltable"):
            for row in table.select("tr"):
                cells = row.find_all(["th", "td"])
                if len(cells) < 2:
                    continue
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)

                if any(k in label for k in ["open", "opens", "يفتح", "بداية"]):
                    result["time_open"] = value
                elif any(k in label for k in ["clos", "يغلق", "نهاية", "due", "deadline"]):
                    result["time_close"] = value or result.get("due_date", "")
                elif any(k in label for k in ["time limit", "مدة", "وقت"]):
                    result["time_limit"] = value
                elif any(k in label for k in ["attempt", "محاولة", "محاولات"]):
                    result["attempts"] = value
                elif any(k in label for k in ["due date", "تسليم", "استحقاق"]):
                    result["due_date"] = value
                elif any(k in label for k in ["submission status", "حالة"]):
                    result["status"] = value

        # ── نص كامل احتياطي
        main = soup.select_one("#region-main, .maincontent, main")
        if main:
            result["raw_text"] = re.sub(r'\s+', ' ', main.get_text(separator=" ", strip=True))[:1500]

    except Exception as e:
        print(f"⚠️ فشل scraping: {e}")

    return result


# ══════════════════════════════════════
# تلخيص كويز
# ══════════════════════════════════════

def summarize_quiz(session, name: str, url: str, course: str,
                   event_time_close: str = "", event_description: str = "") -> str:

    details = scrape_moodle_page(session, url)

    time_open  = details["time_open"]  or "غير محدد"
    time_close = details["time_close"] or event_time_close or "غير محدد"
    time_limit = details["time_limit"] or "غير محدد"
    attempts   = details["attempts"]   or "غير محدد"
    desc       = details["description"] or event_description or details["raw_text"] or "لا يوجد وصف"

    prompt = f"""أنت مساعد طالب جامعي ذكي. لخّص هذا الكويز بالعربي بشكل واضح.

📌 اسم الكويز: {name}
📚 المساق: {course}
🕐 يفتح: {time_open}
🔴 يغلق: {time_close}
⏱ مدة الكويز: {time_limit}
🔁 عدد المحاولات: {attempts}
📋 الوصف والمحتوى:
{desc}

اكتب ملخصاً منظماً يشمل:
1. 📌 موضوع الكويز في جملة
2. 📚 المواضيع والمحتوى المغطى (نقاط)
3. ⏰ وقت البداية والنهاية ومدة الكويز
4. 🔁 عدد المحاولات المتاحة
5. ⚠️ تنبيه عاجل إذا كان الموعد قريباً

اكتب بالعربي فقط، موجز ولا يتجاوز 8 أسطر."""

    return ask_groq(prompt, max_tokens=400)


# ══════════════════════════════════════
# تلخيص واجب/Assignment
# ══════════════════════════════════════

def summarize_assignment(session, name: str, url: str, course: str,
                         event_due_date: str = "", event_description: str = "") -> str:

    details = scrape_moodle_page(session, url)

    due_date = details["due_date"] or event_due_date or "غير محدد"
    status   = details["status"]   or "لم يُسلَّم"
    desc     = details["description"] or event_description or details["raw_text"] or "لا يوجد وصف"

    prompt = f"""أنت مساعد طالب جامعي ذكي. لخّص هذا الواجب بالعربي بشكل واضح.

📌 اسم الواجب: {name}
📚 المساق: {course}
⏰ موعد التسليم: {due_date}
📋 حالة التسليم: {status}
📄 تفاصيل الواجب:
{desc}

اكتب ملخصاً منظماً يشمل:
1. 📌 المطلوب من الطالب بدقة
2. 📋 التفاصيل والمتطلبات المهمة (نقاط)
3. ⏰ موعد التسليم بوضوح
4. 💡 نصيحة سريعة للتنفيذ
5. ⚠️ تنبيه إذا كان الموعد عاجلاً

اكتب بالعربي فقط، موجز ولا يتجاوز 8 أسطر."""

    return ask_groq(prompt, max_tokens=400)


# ══════════════════════════════════════
# تلخيص أحداث التقويم الجديدة
# ══════════════════════════════════════

def summarize_calendar_events(session, events: list) -> str:
    """يلخص كل أحداث التقويم الجديدة مع تصفح روابطها"""
    if not events:
        return ""

    now          = int(time.time())
    events_lines = []

    for e in sorted(events, key=lambda x: x["timestamp"]):
        dt_str    = datetime.fromtimestamp(e["timestamp"]).strftime("%A %d/%m/%Y %I:%M %p")
        label     = {"due": "تسليم", "close": "يغلق", "open": "يفتح"}.get(e["event_type"], e["event_type"])
        remaining = e["timestamp"] - now
        days      = remaining // 86400
        hours     = (remaining % 86400) // 3600
        time_left = f"بعد {days} يوم و{hours} ساعة" if days > 0 else f"بعد {hours} ساعة فقط ⚠️"

        # جلب تفاصيل إضافية من الصفحة
        page_details = {}
        if session:
            try:
                page_details = scrape_moodle_page(session, e["url"])
            except:
                pass

        event_info = f"""
• [{e['type'].upper()}] {e['name']}
  المساق: {e['course_full']}
  {label}: {dt_str} ({time_left})"""

        if e.get("description"):
            event_info += f"\n  الوصف: {e['description'][:300]}"

        if page_details.get("time_open"):
            event_info += f"\n  يفتح: {page_details['time_open']}"
        if page_details.get("time_close"):
            event_info += f"\n  يغلق: {page_details['time_close']}"
        if page_details.get("time_limit"):
            event_info += f"\n  المدة: {page_details['time_limit']}"
        if page_details.get("attempts"):
            event_info += f"\n  المحاولات: {page_details['attempts']}"
        if page_details.get("due_date"):
            event_info += f"\n  موعد التسليم: {page_details['due_date']}"

        events_lines.append(event_info)

    all_events_text = "\n".join(events_lines)

    prompt = f"""أنت مساعد طالب جامعي ذكي. لديك هذه التحديثات الجديدة من Moodle:

{all_events_text}

اكتب تقريراً ذكياً بالعربي يشمل:
1. 🗓 ملخص سريع لكل حدث (اسمه، موعده، مدته إن وُجدت)
2. ⚠️ الأحداث العاجلة التي تحتاج اهتماماً فورياً
3. 📋 ترتيب الأولويات للطالب
4. 💡 نصيحة تنظيمية للأسبوع

اكتب بالعربي فقط، منظم وواضح."""

    return ask_groq(prompt, max_tokens=600)

def chat_with_context(user_question: str, data: dict, events: dict) -> str:
    """محادثة مع Groq مع كامل بيانات الطالب كـ context"""
    import time as _time

    # ── بناء ملخص المساقات
    courses_text = ""
    for course, content in data.items():
        files   = len(content.get("files", []))
        assigns = content.get("assignments", [])
        quizzes = content.get("quizzes", [])
        courses_text += f"\n• {course}: {files} ملف، {len(assigns)} واجب، {len(quizzes)} كويز"
        for a in assigns:
            courses_text += f"\n  - واجب: {a['name']}"
        for q in quizzes:
            courses_text += f"\n  - كويز: {q['name']}"

    # ── بناء ملخص المواعيد القادمة
    now = int(_time.time())
    upcoming = sorted(
        [e for e in events.values() if e["timestamp"] > now],
        key=lambda x: x["timestamp"]
    )[:10]

    events_text = ""
    for e in upcoming:
        from datetime import datetime
        dt        = datetime.fromtimestamp(e["timestamp"]).strftime("%A %d/%m/%Y %I:%M %p")
        label     = {"due": "تسليم", "close": "يغلق", "open": "يفتح"}.get(e["event_type"], "")
        remaining = e["timestamp"] - now
        days      = remaining // 86400
        hours     = (remaining % 86400) // 3600
        time_left = f"بعد {days}ي {hours}س" if days > 0 else f"بعد {hours} ساعة ⚠️"
        events_text += f"\n• {e['name']} — {e['course']} — {label}: {dt} ({time_left})"

    system_prompt = f"""أنت مساعد ذكي لطالب جامعي في جامعة الإسلامية غزة.
لديك كامل بيانات الطالب من نظام Moodle.

📚 المساقات والمحتوى:
{courses_text if courses_text else "لا توجد بيانات"}

📅 المواعيد القادمة:
{events_text if events_text else "لا توجد مواعيد"}

أجب على أسئلة الطالب بالعربي بشكل مفيد ودقيق بناءً على بياناته الفعلية أعلاه.
كن موجزاً وعملياً. إذا سأل عن شيء غير موجود في البيانات، أخبره بصدق."""

    if not GROQ_API_KEY:
        return "⚠️ GROQ_API_KEY غير موجود"
    try:
        r = requests.post(
            GROQ_URL,
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type":  "application/json"
            },
            json={
                "model":       GROQ_MODEL,
                "messages":    [
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_question}
                ],
                "max_tokens":  600,
                "temperature": 0.5
            },
            timeout=25
        )
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"⚠️ خطأ في Groq: {e}"