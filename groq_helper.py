import os, requests, re, time
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL   = "llama-3.1-8b-instant"
GROQ_URL     = "https://api.groq.com/openai/v1/chat/completions"

if not GROQ_API_KEY:
    print("⚠️ GROQ_API_KEY غير موجود في environment variables")
else:
    print(f"✅ GROQ_API_KEY موجود: {GROQ_API_KEY[:8]}...", flush=True)


# ══════════════════════════════════════
# استدعاء Groq API
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

        for tag in soup(["script", "style", "nav", "header", "footer", "aside"]):
            tag.decompose()

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

        main = soup.select_one("#region-main, .maincontent, main")
        if main:
            result["raw_text"] = re.sub(r'\s+', ' ',
                main.get_text(separator=" ", strip=True))[:1500]

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

    prompt = f"""أنت مساعد طالب جامعي ذكي. لخّص هذا الكويز بالعربي.

📌 اسم الكويز: {name}
📚 المساق: {course}
🕐 يفتح: {time_open}
🔴 يغلق: {time_close}
⏱ مدة الكويز: {time_limit}
🔁 عدد المحاولات: {attempts} (رقم 1 يعني محاولة واحدة فقط)
📋 الوصف:
{desc}

اكتب ملخصاً يشمل:
1. 📌 موضوع الكويز في جملة
2. 📚 المواضيع المغطاة (نقاط)
3. ⏰ وقت البداية والنهاية والمدة
4. 🔁 عدد المحاولات المتاحة
5. ⚠️ تنبيه عاجل إذا كان الموعد قريباً

اكتب بالعربي فقط، لا تتجاوز 8 أسطر."""

    return ask_groq(prompt, max_tokens=400)


# ══════════════════════════════════════
# تلخيص واجب
# ══════════════════════════════════════

def summarize_assignment(session, name: str, url: str, course: str,
                         event_due_date: str = "", event_description: str = "") -> str:

    details = scrape_moodle_page(session, url)

    due_date = details["due_date"] or event_due_date or "غير محدد"
    status   = details["status"]   or "لم يُسلَّم"
    desc     = details["description"] or event_description or details["raw_text"] or "لا يوجد وصف"

    prompt = f"""أنت مساعد طالب جامعي ذكي. لخّص هذا الواجب بالعربي.

📌 اسم الواجب: {name}
📚 المساق: {course}
⏰ موعد التسليم: {due_date}
📋 حالة التسليم: {status}
📄 تفاصيل الواجب:
{desc}

اكتب ملخصاً يشمل:
1. 📌 المطلوب بدقة
2. 📋 المتطلبات المهمة (نقاط)
3. ⏰ موعد التسليم بوضوح
4. 💡 نصيحة سريعة
5. ⚠️ تنبيه إذا كان الموعد عاجلاً

اكتب بالعربي فقط، لا تتجاوز 8 أسطر."""

    return ask_groq(prompt, max_tokens=400)


# ══════════════════════════════════════
# تلخيص أحداث التقويم
# ══════════════════════════════════════

def summarize_calendar_events(session, events: list) -> str:
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

        page_details = {}
        if session:
            try:
                page_details = scrape_moodle_page(session, e["url"])
            except:
                pass

        event_info = (
            f"\n• [{e['type'].upper()}] {e['name']}"
            f"\n  المساق: {e['course_full']}"
            f"\n  {label}: {dt_str} ({time_left})"
        )
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

    prompt = f"""أنت مساعد طالب جامعي ذكي. اكتب بالعربي الفصحى فقط، لا تستخدم أي لغة أخرى أبداً.
لديك هذه التحديثات الجديدة من Moodle:

{all_events_text}

اكتب تقريراً يشمل:
1. 🗓 ملخص سريع لكل حدث (اسمه، موعده، مدته)
2. ⚠️ الأحداث العاجلة التي تحتاج اهتماماً فورياً
3. 📋 ترتيب الأولويات للطالب
4. 💡 نصيحة تنظيمية للأسبوع

اكتب بالعربي فقط، منظم وواضح."""

    return ask_groq(prompt, max_tokens=600)


# ══════════════════════════════════════
# محادثة مع Groq مع context كامل
# ══════════════════════════════════════

def chat_with_context(user_question: str, data: dict, events: dict) -> str:

    # ── حاول تحديد المساق المطلوب من السؤال لتقليص الـ context
    question_lower = user_question.lower()
    targeted_courses = {}

    for course in data:
        course_lower = course.lower()
        # تحقق إذا ذُكر رمز المساق أو كلمة من اسمه في السؤال
        if (course_lower in question_lower or
            any(part in question_lower for part in course_lower.split("-") if len(part) > 3)):
            targeted_courses[course] = data[course]

    # إذا ما حدد مساقاً معيناً، خذ كل المساقات لكن بملفات مختصرة
    use_data = targeted_courses if targeted_courses else data
    truncate = not bool(targeted_courses)  # اختصر إذا كل المساقات

    # ── خريطة أسماء المساقات
    course_map = "\n".join([f"  - {name}" for name in data.keys()])

    # ── بناء context المساقات مع اسم المساق في كل سطر
    courses_text = ""
    for course, content in use_data.items():
        files   = content.get("files", [])
        assigns = content.get("assignments", [])
        quizzes = content.get("quizzes", [])

        # ← اختصر الملفات إذا كانت كل المساقات (اعرض أول 5 فقط)
        max_files = 5 if truncate else 999

        courses_text += f"\n\n{'='*40}"
        courses_text += f"\n📚 [{course}]"
        courses_text += f"\n{'='*40}"

        if files:
            courses_text += f"\n  📄 الملفات ({len(files)}):"
            for f in files[:max_files]:
                courses_text += f"\n    [{course}] {f['name']} → {f['url']}"
            if truncate and len(files) > max_files:
                courses_text += f"\n    ... و{len(files) - max_files} ملفات أخرى (اذكر اسم المساق للتفاصيل)"

        if assigns:
            courses_text += f"\n  📝 الواجبات ({len(assigns)}):"
            for a in assigns:
                courses_text += f"\n    [{course}] {a['name']} → {a['url']}"

        if quizzes:
            courses_text += f"\n  ❓ الكويزات ({len(quizzes)}):"
            for q in quizzes:
                courses_text += f"\n    [{course}] {q['name']} → {q['url']}"

    # ── المواعيد القادمة (أقرب 5 فقط)
    now = int(time.time())
    upcoming = sorted(
        [e for e in events.values() if e["timestamp"] > now],
        key=lambda x: x["timestamp"]
    )[:5]

    events_text = ""
    for e in upcoming:
        dt        = datetime.fromtimestamp(e["timestamp"]).strftime("%A %d/%m/%Y %I:%M %p")
        label     = {"due": "تسليم", "close": "يغلق", "open": "يفتح"}.get(e["event_type"], "")
        remaining = e["timestamp"] - now
        days      = remaining // 86400
        hours     = (remaining % 86400) // 3600
        time_left = f"بعد {days}ي {hours}س" if days > 0 else f"بعد {hours}س ⚠️"
        events_text += (
            f"\n• [{e['type'].upper()}] {e['name']}"
            f" — {e['course']} — {label}: {dt} ({time_left})"
            f" | رابط: {e.get('action_url', e['url'])}"
        )

    system_prompt = f"""أنت مساعد ذكي لطالب جامعي في الجامعة الإسلامية غزة.
لديك بيانات Moodle الكاملة بما فيها روابط الملفات والواجبات والكويزات.

المساقات المتاحة:
{course_map}

قواعد:
1. كل سطر يبدأ بـ [اسم المساق] — استخدمه للتمييز
2. أعطِ الروابط الكاملة عند طلبها
3. إذا طُلب مساق بعينه ولم تجد ملفاته كاملة، اطلب من الطالب تحديد الرمز (مثل SDEV3305)
4. اكتب بالعربي دائماً

📚 البيانات:
{courses_text if courses_text else "لا توجد بيانات"}

📅 أقرب المواعيد:
{events_text if events_text else "لا توجد مواعيد"}"""

    return _call_groq([
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_question}
    ], max_tokens=700)


def _call_groq(messages: list, max_tokens: int = 700) -> str:
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
                "messages":    messages,
                "max_tokens":  max_tokens,
                "temperature": 0.3
            },
            timeout=25
        )
        data = r.json()

        # ── اكتشاف الخطأ من Groq
        if "error" in data:
            err = data["error"]
            code = err.get("code", "")
            msg  = err.get("message", str(err))

            if "rate_limit" in code or "rate_limit" in msg.lower():
                return "⚠️ تجاوزت حد الطلبات — انتظر دقيقة وأعد المحاولة"
            if "context_length" in code or "tokens" in msg.lower():
                return "⚠️ السؤال يحتاج بيانات كبيرة جداً — حاول تحديد المساق مباشرة (مثل: /ai SDEV3305)"
            return f"⚠️ خطأ من Groq: {msg}"

        return data["choices"][0]["message"]["content"].strip()

    except Exception as e:
        return f"⚠️ خطأ في الاتصال: {e}"        