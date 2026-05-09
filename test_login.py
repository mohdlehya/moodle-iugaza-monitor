import os
from dotenv import load_dotenv
from scraper import create_session, get_courses

load_dotenv()

username = os.getenv("MOODLE_USERNAME")
password = os.getenv("MOODLE_PASSWORD")

print(f"👤 المستخدم: {username}")
print("=" * 40)

session = create_session(username, password)
courses = get_courses(session)

print("\n📚 المساقات:")
for i, c in enumerate(courses, 1):
    print(f"  {i}. {c['name']}")
    print(f"     {c['url']}")