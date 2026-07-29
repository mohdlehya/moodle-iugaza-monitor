import os
import sys
import pytest
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from main import get_course_content, analyze_assignment, analyze_quiz, find_new_items
from calendar_api import parse_events, find_new_events


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class MockResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


class MockSession:
    def __init__(self, html_content):
        self.html_content = html_content

    def get(self, url, timeout=30):
        return MockResponse(self.html_content)


def test_parse_moodle_course_page_fixture():
    fixture_path = os.path.join(FIXTURES_DIR, "moodle_course_page.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    session = MockSession(html)
    content = get_course_content(session, "http://dummy_course_url")

    assert len(content["files"]) == 2
    assert content["files"][0]["name"] == "المحاضرة الأولى - مقدمة.pdf"
    assert "mod/resource/view.php?id=10001" in content["files"][0]["url"]

    assert len(content["assignments"]) == 1
    assert content["assignments"][0]["name"] == "الواجب الأول - حل التمارين"

    assert len(content["quizzes"]) == 1
    assert content["quizzes"][0]["name"] == "الكويز الأول - الجمل الشرطية"

    assert len(content["folders"]) == 1
    assert content["folders"][0]["name"] == "مجلد أمثلة العملي"


def test_parse_assignment_page_fixture():
    fixture_path = os.path.join(FIXTURES_DIR, "assignment_page.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    session = MockSession(html)
    info = analyze_assignment(session, "http://dummy_assign_url")

    assert "due_date" in info
    assert "15 أغسطس 2026" in info["due_date"]
    assert info.get("status") == "لم يتم التسليم بعد"


def test_parse_quiz_page_fixture():
    fixture_path = os.path.join(FIXTURES_DIR, "quiz_page.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    session = MockSession(html)
    info = analyze_quiz(session, "http://dummy_quiz_url")

    assert "closes" in info
    assert "16 أغسطس 2026" in info["closes"]


def test_find_new_items_diff_logic():
    old_data = {
        "CS101": {
            "files": [{"name": "Lecture 1", "url": "http://f1"}],
            "assignments": [],
            "quizzes": []
        }
    }
    new_data = {
        "CS101": {
            "files": [
                {"name": "Lecture 1", "url": "http://f1"},
                {"name": "Lecture 2", "url": "http://f2"}
            ],
            "assignments": [{"name": "Homework 1", "url": "http://a1"}],
            "quizzes": []
        }
    }

    diff = find_new_items(old_data, new_data)

    assert "CS101" in diff
    assert len(diff["CS101"]["files"]) == 1
    assert diff["CS101"]["files"][0]["url"] == "http://f2"
    assert len(diff["CS101"]["assignments"]) == 1
    assert diff["CS101"]["assignments"][0]["url"] == "http://a1"


def test_calendar_events_parsing_and_diff():
    raw_events = [
        {
            "id": 1,
            "name": "Midterm Exam",
            "timestart": 1700000000,
            "timesort": 1700000000,
            "modulename": "assign",
            "eventtype": "due",
            "url": "http://moodle/event/1",
            "course": {"shortname": "CS101", "fullname": "Intro to CS"}
        },
        {
            "id": 2,
            "name": "Project Submission",
            "timestart": 1700100000,
            "timesort": 1700100000,
            "modulename": "assign",
            "eventtype": "due",
            "url": "http://moodle/event/2",
            "course": {"shortname": "CS101", "fullname": "Intro to CS"}
        },
    ]
    parsed = parse_events(raw_events)
    assert len(parsed) == 2

    old_events = [parsed[0]]
    new_events = find_new_events(old_events, parsed)

    assert len(new_events) == 1
    assert new_events[0]["name"] == "Project Submission"
