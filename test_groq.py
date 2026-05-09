import os
from dotenv import load_dotenv
load_dotenv()

from groq_helper import ask_groq, summarize_calendar_events
from calendar_api import load_previous_events

# ── اختبار 1: هل Groq يعمل؟
print("=" * 50)
print("اختبار 1: اتصال Groq")
print("=" * 50)
result = ask_groq("قل مرحباً بالعربي في جملة واحدة")
print(f"الرد: {result}")
print()

# ── اختبار 2: تلخيص كويز وهمي
print("=" * 50)
print("اختبار 2: تلخيص كويز")
print("=" * 50)
from groq_helper import summarize_quiz, summarize_assignment

# بدون session (بيانات وهمية)
from unittest.mock import MagicMock
mock_session = MagicMock()
mock_session.get.return_value.text = """
<html>
<table class="generaltable">
<tr><td>Opens</td><td>Monday 12 May 2026, 8:00 AM</td></tr>
<tr><td>Closes</td><td>Thursday 14 May 2026, 1:00 PM</td></tr>
<tr><td>Time limit</td><td>30 minutes</td></tr>
<tr><td>Attempts allowed</td><td>1</td></tr>
</table>
<div id="intro">This quiz covers Chapter 7: Design Patterns including Factory, Observer, and Strategy patterns.</div>
</html>
"""

result = summarize_quiz(
    session          = mock_session,
    name             = "Quiz for Chapter 7",
    url              = "https://moodle.iugaza.edu.ps/mod/quiz/view.php?id=123",
    course           = "Advanced Software Engineering",
    event_time_close = "Thursday 14/05/2026 — 01:00 PM",
)
print(f"ملخص الكويز:\n{result}")
print()

# ── اختبار 3: تلخيص واجب وهمي
print("=" * 50)
print("اختبار 3: تلخيص واجب")
print("=" * 50)
mock_session.get.return_value.text = """
<html>
<table class="generaltable">
<tr><td>Due date</td><td>Sunday 17 May 2026, 12:00 AM</td></tr>
<tr><td>Submission status</td><td>No attempt</td></tr>
</table>
<div id="intro">
Implement the following design patterns using Java:
1. Factory Pattern for shape creation
2. Observer Pattern for event handling
Submit a ZIP file with source code and a PDF report.
</div>
</html>
"""

result = summarize_assignment(
    session        = mock_session,
    name           = "Design Patterns Lab — Assignment Project 2",
    url            = "https://moodle.iugaza.edu.ps/mod/assign/view.php?id=456",
    course         = "تصميم وعمارة البرمجيات",
    event_due_date = "Sunday 17/05/2026 — 12:00 AM",
)
print(f"ملخص الواجب:\n{result}")
print()

# ── اختبار 4: تلخيص أحداث التقويم الحقيقية
print("=" * 50)
print("اختبار 4: تلخيص التقويم الحقيقي")
print("=" * 50)
saved_events = load_previous_events()
if saved_events:
    import time
    now      = int(time.time())
    upcoming = [e for e in saved_events.values() if e["timestamp"] > now][:5]
    if upcoming:
        result = summarize_calendar_events(None, upcoming)
        print(f"ملخص التقويم:\n{result}")
    else:
        print("لا توجد أحداث قادمة في events.json")
else:
    print("⚠️ events.json فارغ — شغّل main.py أولاً")