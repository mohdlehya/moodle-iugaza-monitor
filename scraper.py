import requests, os, time
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from dotenv import load_dotenv

load_dotenv()

MOODLE_BASE = os.getenv("MOODLE_URL", "https://moodle.iugaza.edu.ps")


def safe_get(session, url: str, retries: int = 3, delay: int = 3):
    for attempt in range(retries):
        try:
            time.sleep(delay)
            return session.get(url, timeout=30)
        except Exception as e:
            print(f"    ⚠️ محاولة {attempt+1}/{retries} فشلت: {type(e).__name__}")
            if attempt < retries - 1:
                time.sleep(8)
    return None


def create_session(username: str, password: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    })

    print("🔄 جاري الاتصال بصفحة Moodle...")
    r = safe_get(session, f"{MOODLE_BASE}/auth/saml2/login.php", delay=2)
    if not r:
        raise Exception("❌ فشل الاتصال بصفحة الدخول")
    print(f"📍 URL بعد التوجيه: {r.url}")

    parsed = urlparse(r.url)
    params = parse_qs(parsed.query)
    if "AuthState" not in params:
        raise Exception("❌ لم يُعثر على AuthState")

    auth_state = params["AuthState"][0]
    print(f"✅ AuthState: {auth_state[:40]}...")

    print("🔄 جاري إرسال بيانات الدخول...")
    r2 = session.post(
        r.url,
        data={
            "username":  username,
            "password":  password,
            "AuthState": auth_state,
        },
        allow_redirects=True,
        timeout=30,
    )
    print(f"📍 URL بعد الدخول: {r2.url}")

    soup2     = BeautifulSoup(r2.text, "html.parser")
    acs_form  = soup2.find("form", {"action": lambda x: x and "saml2-acs" in x})

    if acs_form:
        print("🔄 إكمال SAML handshake (ACS)...")
        acs_url   = acs_form["action"]
        saml_data = {
            inp["name"]: inp.get("value", "")
            for inp in acs_form.find_all("input") if inp.get("name")
        }
        print(f"📍 ACS URL: {acs_url}")
        time.sleep(2)
        r3    = session.post(acs_url, data=saml_data, allow_redirects=True, timeout=30)
        print(f"📍 URL النهائي: {r3.url}")
        final = r3
    else:
        final = r2

    keywords = ["loggedinas", "Log out", "تسجيل الخروج", "Dashboard", "data-userid"]
    if any(k in final.text for k in keywords) or "moodle.iugaza.edu.ps/my" in final.url:
        print("✅ تم الدخول بنجاح!")
        return session

    raise Exception("❌ فشل تسجيل الدخول")


import html
import re


def _clean_course_name(name: str) -> str:
    if not name:
        return ""
    soup = BeautifulSoup(name, "html.parser")
    clean = soup.get_text(strip=True)
    clean = html.unescape(clean)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def get_courses(session) -> list:
    print("\n🔄 جاري جلب المساقات...")
    courses_by_id = {}

    # 1. Primary approach: Moodle internal AJAX WebService API (Moodle 3.6 - 4.x+)
    sesskey = None
    try:
        from calendar_api import get_sesskey
        sesskey = get_sesskey(session)
    except Exception as e:
        print(f"  ⚠️ تعذر استخراج sesskey: {e}")

    if sesskey:
        print(f"  🔑 استخدام sesskey: {sesskey[:10]}...")
        api_url = (
            f"{MOODLE_BASE}/lib/ajax/service.php"
            f"?sesskey={sesskey}"
            f"&info=core_course_get_enrolled_courses_by_timeline_classification"
        )
        payload = [
            {
                "index": i,
                "methodname": "core_course_get_enrolled_courses_by_timeline_classification",
                "args": {
                    "offset": 0,
                    "limit": 0,
                    "classification": cls,
                    "sort": "fullname"
                }
            }
            for i, cls in enumerate(["all", "allincludinghidden", "inprogress"])
        ]
        try:
            resp = session.post(api_url, json=payload, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for item in data:
                    if isinstance(item, dict) and not item.get("error"):
                        c_list = item.get("data", {}).get("courses", [])
                        for c in c_list:
                            c_id = c.get("id")
                            if not c_id or str(c_id) == "1":
                                continue
                            raw_name = c.get("fullname") or c.get("fullnamedisplay") or c.get("shortname") or ""
                            c_name = _clean_course_name(raw_name)
                            if not c_name:
                                continue
                            c_url = c.get("viewurl") or f"{MOODLE_BASE}/course/view.php?id={c_id}"
                            if not c_url.startswith("http"):
                                c_url = f"{MOODLE_BASE}{c_url}"
                            courses_by_id[str(c_id)] = {"name": c_name, "url": c_url}
        except Exception as e:
            print(f"  ⚠️ استدعاء AJAX للمساقات واجه خطأ: {e}")

    # 2. Secondary approach: Scrape HTML from /my/courses.php and /my/
    for path in ["/my/courses.php", "/my/"]:
        try:
            r = safe_get(session, f"{MOODLE_BASE}{path}", delay=2)
            if not r:
                continue
            soup = BeautifulSoup(r.text, "html.parser")
            for link in soup.select('a[href*="/course/view.php"]'):
                href = link.get("href", "")
                parsed = urlparse(href)
                params = parse_qs(parsed.query)
                c_id = params.get("id", [None])[0]
                if not c_id or str(c_id) == "1":
                    continue
                c_name = _clean_course_name(link.get_text(strip=True))
                if not c_name or c_name.lower() in ["course image", "view", "عرض", "المقرر"]:
                    continue
                c_url = f"{MOODLE_BASE}/course/view.php?id={c_id}"
                if str(c_id) not in courses_by_id or len(c_name) > len(courses_by_id[str(c_id)]["name"]):
                    courses_by_id[str(c_id)] = {"name": c_name, "url": c_url}
        except Exception as e:
            print(f"  ⚠️ فحص صفحة {path} واجه خطأ: {e}")

    # 3. Fallback: If still 0 courses, check upcoming calendar events
    if not courses_by_id:
        try:
            from calendar_api import get_upcoming_events
            events = get_upcoming_events(session)
            for ev in events:
                c = ev.get("course", {})
                c_id = c.get("id")
                raw_name = c.get("fullname") or c.get("shortname") or ""
                c_name = _clean_course_name(raw_name)
                if c_id and str(c_id) != "1" and c_name:
                    c_url = c.get("viewurl") or f"{MOODLE_BASE}/course/view.php?id={c_id}"
                    if not c_url.startswith("http"):
                        c_url = f"{MOODLE_BASE}{c_url}"
                    courses_by_id[str(c_id)] = {"name": c_name, "url": c_url}
        except Exception as e:
            print(f"  ⚠️ استخراج المساقات من أحداث التقويم واجه خطأ: {e}")

    courses = list(courses_by_id.values())
    print(f"✅ عدد المساقات: {len(courses)}")
    return courses