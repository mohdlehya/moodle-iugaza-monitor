import os, requests, re, time
from bs4 import BeautifulSoup
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

from crypto import mask_secret

# ══════════════════════════════════════════════════════════════
# AI Providers Configuration
# ══════════════════════════════════════════════════════════════

PROVIDERS = {
    "gemini": {
        "name": "Google Gemini",
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "default_model": "gemini-1.5-flash",
        "prefix": "AIza",
        "doc_url": "https://aistudio.google.com/apikey",
    },
    "groq": {
        "name": "Groq (Llama-3)",
        "url": "https://api.groq.com/openai/v1/chat/completions",
        "default_model": "llama-3.1-8b-instant",
        "prefix": "gsk_",
        "doc_url": "https://console.groq.com/keys",
    },
    "openrouter": {
        "name": "OpenRouter",
        "url": "https://openrouter.ai/api/v1/chat/completions",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "prefix": "sk-or-",
        "doc_url": "https://openrouter.ai/keys",
    },
    "openai": {
        "name": "OpenAI (ChatGPT)",
        "url": "https://api.openai.com/v1/chat/completions",
        "default_model": "gpt-4o-mini",
        "prefix": "sk-",
        "doc_url": "https://platform.openai.com/api-keys",
    },
}

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def detect_provider(api_key: str) -> str:
    """Auto-detect AI provider by API key prefix."""
    if not api_key or not isinstance(api_key, str):
        return "groq"
    key = api_key.strip()
    if key.startswith("AIza"):
        return "gemini"
    elif key.startswith("sk-or-"):
        return "openrouter"
    elif key.startswith("sk-"):
        return "openai"
    elif key.startswith("gsk_"):
        return "groq"
    return "groq"


def get_provider_display_name(api_key: str) -> str:
    """Return formatted display name for given API key."""
    p_id = detect_provider(api_key)
    cfg = PROVIDERS.get(p_id, PROVIDERS["groq"])
    return cfg["name"]


def validate_ai_key(api_key: str) -> tuple[bool, str]:
    """Test if a user-supplied AI key is valid against its provider."""
    if not api_key or not isinstance(api_key, str) or not api_key.strip():
        return False, ""
    key = api_key.strip()
    provider_id = detect_provider(key)
    cfg = PROVIDERS[provider_id]

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    if provider_id == "openrouter":
        headers["HTTP-Referer"] = "https://moodle.iugaza.edu.ps"
        headers["X-Title"] = "Moodle IUG Monitor"

    try:
        r = requests.post(
            cfg["url"],
            headers=headers,
            json={
                "model": cfg["default_model"],
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 1
            },
            timeout=10
        )
        if r.status_code == 200:
            return True, cfg["name"]
        return False, ""
    except Exception:
        return False, ""


def validate_groq_key(api_key: str) -> bool:
    """Backward compatibility validation helper for Groq/AI keys."""
    is_valid, _ = validate_ai_key(api_key)
    return is_valid


# ══════════════════════════════════════════════════════════════
# Unified Multi-Provider Execution Engine
# ══════════════════════════════════════════════════════════════

def call_ai_engine(messages: list, user_key: str = None, max_tokens: int = 600) -> tuple[str, str]:
    """Execute AI completion with user custom key or automatic fallback among system keys.
    Returns (response_text, provider_name).
    """
    # 1. Custom User Key execution
    if user_key and isinstance(user_key, str) and user_key.strip():
        key = user_key.strip()
        provider_id = detect_provider(key)
        cfg = PROVIDERS[provider_id]

        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        if provider_id == "openrouter":
            headers["HTTP-Referer"] = "https://moodle.iugaza.edu.ps"
            headers["X-Title"] = "Moodle IUG Monitor"

        try:
            r = requests.post(
                cfg["url"],
                headers=headers,
                json={
                    "model": cfg["default_model"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3
                },
                timeout=25
            )
            data = r.json()
            if "choices" in data and data["choices"]:
                content = data["choices"][0]["message"]["content"].strip()
                return content, cfg["name"]
            if "error" in data:
                err = data["error"]
                msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                return f"⚠️ خطأ من {cfg['name']}: {msg}", cfg["name"]
        except Exception as e:
            return f"⚠️ خطأ في الاتصال بـ {cfg['name']}: {e}", cfg["name"]

    # 2. System fallbacks in priority order: Groq -> Gemini -> OpenRouter -> OpenAI
    system_candidates = [
        ("groq", os.getenv("GROQ_API_KEY")),
        ("gemini", os.getenv("GEMINI_API_KEY")),
        ("openrouter", os.getenv("OPENROUTER_API_KEY")),
        ("openai", os.getenv("OPENAI_API_KEY")),
    ]

    for p_id, sys_key in system_candidates:
        if not sys_key or not sys_key.strip():
            continue
        cfg = PROVIDERS[p_id]
        headers = {
            "Authorization": f"Bearer {sys_key.strip()}",
            "Content-Type": "application/json"
        }
        if p_id == "openrouter":
            headers["HTTP-Referer"] = "https://moodle.iugaza.edu.ps"
            headers["X-Title"] = "Moodle IUG Monitor"

        try:
            r = requests.post(
                cfg["url"],
                headers=headers,
                json={
                    "model": cfg["default_model"],
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": 0.3
                },
                timeout=25
            )
            data = r.json()
            if "choices" in data and data["choices"]:
                content = data["choices"][0]["message"]["content"].strip()
                return content, cfg["name"]
            if "error" in data:
                print(f"⚠️ {cfg['name']} fallback returned error: {data['error']}", flush=True)
                continue
        except Exception as e:
            print(f"⚠️ {cfg['name']} fallback connection failed: {e}", flush=True)
            continue

    return "⚠️ لم يتم العثور على مزود ذكاء اصطناعي متاح. يرجى إضافة مفتاحك عبر /setkey.", "AI Assistant"


def ask_groq(prompt: str, max_tokens: int = 500, user_key: str = None) -> str:
    """Backward-compatible prompt execution."""
    text, _ = call_ai_engine([{"role": "user", "content": prompt}], user_key=user_key, max_tokens=max_tokens)
    return text


def ask_ai(prompt: str, max_tokens: int = 500, user_key: str = None) -> str:
    """Unified ask_ai helper."""
    return ask_groq(prompt, max_tokens=max_tokens, user_key=user_key)


def _call_groq(messages: list, max_tokens: int = 700, user_key: str = None) -> str:
    """Internal message helper."""
    text, _ = call_ai_engine(messages, user_key=user_key, max_tokens=max_tokens)
    return text


# ══════════════════════════════════════════════════════════════
# Moodle Content Scraper
# ══════════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════════
# Summarization Helpers
# ══════════════════════════════════════════════════════════════

def summarize_quiz(session, name: str, url: str, course: str,
                   event_time_close: str = "", event_description: str = "", user_key: str = None) -> str:

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

    return ask_groq(prompt, max_tokens=400, user_key=user_key)


def summarize_assignment(session, name: str, url: str, course: str,
                         event_due_date: str = "", event_description: str = "", user_key: str = None) -> str:

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

    return ask_groq(prompt, max_tokens=400, user_key=user_key)


def summarize_calendar_events(session, events: list, user_key: str = None) -> str:
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

    return ask_groq(prompt, max_tokens=600, user_key=user_key)


def chat_with_context(user_question: str, data: dict, events: dict, user_key: str = None) -> tuple[str, str]:
    """Provide comprehensive AI QA over enrolled courses, files, quizzes, and deadlines.
    Returns (answer, provider_name).
    """
    question_lower = user_question.lower()
    targeted_courses = {}

    for course in data:
        course_lower = course.lower()
        if (course_lower in question_lower or
            any(part in question_lower for part in course_lower.split("-") if len(part) > 3)):
            targeted_courses[course] = data[course]

    use_data = targeted_courses if targeted_courses else data
    truncate = not bool(targeted_courses)

    course_map = "\n".join([f"  - {name}" for name in data.keys()])

    courses_text = ""
    for course, content in use_data.items():
        files   = content.get("files", [])
        assigns = content.get("assignments", [])
        quizzes = content.get("quizzes", [])

        if not files and not assigns and not quizzes:
            continue

        courses_text += f"\n\n📚 المساق: [{course}]\n"

        if files:
            courses_text += "  الملفات والمحاضرات:\n"
            limit = 8 if truncate else len(files)
            for f in files[:limit]:
                courses_text += f"    • [{course}] {f['name']} — رابط: {f['url']}\n"
            if truncate and len(files) > 8:
                courses_text += f"    ... وهناك {len(files)-8} ملفات أخرى\n"

        if assigns:
            courses_text += "  الواجبات والتكليفات:\n"
            for a in assigns:
                courses_text += f"    • [{course}] {a['name']} — رابط: {a['url']}\n"

        if quizzes:
            courses_text += "  الكويزات والامتحانات:\n"
            for q in quizzes:
                courses_text += f"    • [{course}] {q['name']} — رابط: {q['url']}\n"

    events_text = ""
    now = int(time.time())
    for e in list(events.values())[:10]:
        t = e.get("timestamp", 0)
        dt = datetime.fromtimestamp(t).strftime("%d/%m/%Y %I:%M %p") if t else "غير محدد"
        remaining = t - now if t else 0
        days = remaining // 86400
        time_hint = f"(بعد {days} يوم)" if days > 0 else "(عاجل قريباً!)"
        events_text += f"  • [{e.get('course_full', '')}] {e.get('name', '')} — {dt} {time_hint}\n"

    system_prompt = f"""أنت مساعد طالب جامعي ذكي وباحث في مواد بوابة Moodle بالجامعة الإسلامية بغزة.
أجب عن سؤال الطالب بدقة واحترافية باللغة العربية الفصحى.

المساقات المتاحة:
{course_map}

قواعد:
1. كل سطر يبدأ بـ [اسم المساق] — استخدمه للتمييز بين المواد.
2. أعطِ الروابط المباشرة عندما يطلب الطالب الملف أو الواجب.
3. إذا سأل عن مساق محدد ولم تكن ملفاته مفصلة، وجهه لتحديد رمز المساق (مثل SDEV3305).
4. اكتب بالعربي دائماً وبشكل منظم وواضح.

📚 البيانات:
{courses_text if courses_text else "لا توجد بيانات"}

📅 أقرب المواعيد:
{events_text if events_text else "لا توجد مواعيد"}"""

    return call_ai_engine([
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_question}
    ], user_key=user_key, max_tokens=700)