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


def get_courses(session) -> list:
    print("\n🔄 جاري جلب المساقات...")
    r = safe_get(session, f"{MOODLE_BASE}/my/", delay=3)
    if not r:
        raise Exception("❌ فشل جلب صفحة المساقات")

    soup    = BeautifulSoup(r.text, "html.parser")
    courses = []
    seen    = set()

    for link in soup.select('a[href*="/course/view.php"]'):
        name = link.get_text(strip=True)
        if name:
            url = link["href"]
            if not url.startswith("http"):
                url = f"{MOODLE_BASE}{url}"
            if url not in seen:
                seen.add(url)
                courses.append({"name": name, "url": url})

    print(f"✅ عدد المساقات: {len(courses)}")
    return courses