import requests, json, os, time, re
from datetime import datetime
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

MOODLE_BASE = os.getenv("MOODLE_URL", "https://moodle.iugaza.edu.ps")


def get_sesskey(session) -> str | None:
    for attempt in range(3):
        try:
            time.sleep(3)
            r = session.get(f"{MOODLE_BASE}/my/", timeout=30)

            match = re.search(r'"sesskey"\s*:\s*"([^"]+)"', r.text)
            if match:
                return match.group(1)

            soup = BeautifulSoup(r.text, "html.parser")
            inp  = soup.find("input", {"name": "sesskey"})
            if inp:
                return inp.get("value")

            el = soup.find(attrs={"data-sesskey": True})
            if el:
                return el["data-sesskey"]

        except Exception as e:
            print(f"  ⚠️ محاولة {attempt+1}/3 للـ sesskey فشلت: {type(e).__name__}")
            time.sleep(8)

    return None


def get_upcoming_events(session) -> list:
    sesskey = get_sesskey(session)
    if not sesskey:
        print("⚠️ لم يُعثر على sesskey")
        return []

    print(f"✅ sesskey: {sesskey[:10]}...")

    now = int(time.time())
    end = now + (60 * 60 * 24 * 30)

    api_url = (
        f"{MOODLE_BASE}/lib/ajax/service.php"
        f"?sesskey={sesskey}"
        f"&info=core_calendar_get_action_events_by_timesort"
    )

    payload = [{
        "index": 0,
        "methodname": "core_calendar_get_action_events_by_timesort",
        "args": {
            "timesortfrom": now,
            "timesortto":   end,
            "limitnum":     50,
            "limittononsuspendedevents": True
        }
    }]

    time.sleep(2)
    try:
        resp = session.post(api_url, json=payload, timeout=30)
        data = resp.json()
    except Exception as e:
        print(f"❌ فشل استدعاء Calendar API: {e}")
        return []

    if not data or data[0].get("error"):
        print(f"❌ خطأ في الـ API: {data}")
        return []

    events = data[0]["data"]["events"]
    print(f"✅ عدد الأحداث القادمة: {len(events)}")
    return events


def parse_events(events: list) -> list:
    parsed = []
    for e in events:
        desc_raw   = e.get("description", "") or ""
        desc       = _clean_html(desc_raw)
        actionable = e.get("action", {}).get("actionable", False)
        action_url = e.get("action", {}).get("url", e["url"])

        parsed.append({
            "id":          e["id"],
            "name":        e["name"],
            "course":      e["course"]["shortname"],
            "course_full": e["course"]["fullname"],
            "type":        e["modulename"],
            "event_type":  e["eventtype"],
            "timestamp":   e["timesort"],
            "url":         e["url"],
            "action_url":  action_url,
            "actionable":  actionable,
            "description": desc,
        })
    return parsed


def _clean_html(html: str) -> str:
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:400]


def load_previous_events(path="events.json") -> dict:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            return json.loads(content) if content else {}
    except:
        return {}


def save_events(events: list, path="events.json"):
    data = {str(e["id"]): e for e in events}
    tmp  = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def find_new_events(old: dict, new: list) -> list:
    return [e for e in new if str(e["id"]) not in old]


def build_events_message(events: list) -> str:
    if not events:
        return ""

    type_emoji  = {"assign": "📝", "quiz": "❓"}
    event_label = {
        "due":        "موعد التسليم",
        "close":      "يغلق",
        "open":       "يفتح",
        "gradingdue": "موعد التصحيح"
    }

    lines = [f"📅 <b>{len(events)} حدث جديد في التقويم</b>\n"]

    for e in sorted(events, key=lambda x: x["timestamp"]):
        emoji  = type_emoji.get(e["type"], "📌")
        label  = event_label.get(e["event_type"], e["event_type"])
        dt     = datetime.fromtimestamp(e["timestamp"])
        dt_str = dt.strftime("%A %d/%m/%Y — %I:%M %p")

        lines.append(f"{emoji} <b>{e['name']}</b>")
        lines.append(f"   📚 {e['course_full']}")
        lines.append(f"   ⏰ <b>{label}:</b> {dt_str}")

        if e.get("description"):
            lines.append(f"   📋 {e['description'][:200]}")

        if e["actionable"]:
            lines.append(f'   ✅ <a href="{e["action_url"]}">افتح الآن</a>')
        else:
            lines.append(f'   🔒 مغلق — <a href="{e["url"]}">عرض</a>')

        lines.append("")

    return "\n".join(lines)


def get_deadlines_message(limit: int = 10) -> str:
    events = load_previous_events()
    if not events:
        return "❌ لا توجد بيانات تقويم — شغّل main.py أولاً"

    now      = int(time.time())
    upcoming = [e for e in events.values() if e["timestamp"] > now]
    upcoming.sort(key=lambda x: x["timestamp"])

    if not upcoming:
        return "✅ لا توجد مواعيد قادمة خلال 30 يوم"

    type_emoji  = {"assign": "📝", "quiz": "❓"}
    event_label = {"due": "تسليم", "close": "يغلق", "open": "يفتح"}

    lines = [f"📅 <b>المواعيد القادمة ({len(upcoming)} حدث)</b>\n"]

    for e in upcoming[:limit]:
        emoji     = type_emoji.get(e["type"], "📌")
        label     = event_label.get(e["event_type"], e["event_type"])
        dt        = datetime.fromtimestamp(e["timestamp"])
        dt_str    = dt.strftime("%d/%m %I:%M %p")
        remaining = e["timestamp"] - now
        days      = remaining // 86400
        hours     = (remaining % 86400) // 3600
        time_left = f"{days}ي {hours}س" if days > 0 else f"{hours} ساعة"

        lines.append(f"{emoji} <b>{e['name']}</b>")
        lines.append(f"   📚 {e['course']}  |  ⏰ {dt_str}  |  ⏳ بعد {time_left}")
        if e.get("description"):
            lines.append(f"   📋 {e['description'][:100]}")
        lines.append(f'   🔗 <a href="{e["action_url"]}">افتح</a>\n')

    return "\n".join(lines)