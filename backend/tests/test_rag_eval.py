"""Retrieval quality on the mock circulars and reports (keyword search; no Ollama in CI).

Each question names the event a person would want back: a hit counts when one of the top 5
documents belongs to that event series (and year, when the question gives one).
"""

import pytest

from app.services.documents import search

QUESTIONS = [
    ("When was the in-house hackathon held in 2024?", "kiot-in-house-hackathon", 2024),
    (
        "Hands-on workshop on generative AI in CC1",
        "hands-on-workshop-on-generative-ai-for-developers",
        None,
    ),
    (
        "Model practical exams odd semester 2025 lab schedule",
        "model-practical-examinations-odd-semester",
        2025,
    ),
    ("Graduation day 2025 chief guest", "graduation-day", 2025),
    (
        "AICTE sponsored FDP on generative AI",
        "five-day-aicte-sponsored-faculty-development-programme-on-generative-ai-for-developers",
        None,
    ),
    (
        "Placement training programme in the centres of excellence",
        "placement-training-programme",
        None,
    ),
    ("Guest lecture on malware analysis", "guest-lecture-on-malware-analysis-basics", None),
    (
        "Who spoke on business analytics in the MBA seminar hall?",
        "guest-lecture-on-business-analytics",
        None,
    ),
    (
        "Power BI value-added course in CC10",
        "value-added-course-data-visualization-with-power-bi",
        None,
    ),
    ("CodeSprint coding contest in COE2", "codesprint-in-house-coding-contest", None),
    (
        "Admission counselling and spot registration 2025",
        "admission-counselling-and-spot-registration",
        2025,
    ),
    ("HOD address to CSE students odd semester", "hods-address-to-cse-students-odd-semester", None),
    (
        "First year induction programme inauguration",
        "inauguration-of-first-year-induction-programme",
        None,
    ),
    (
        "Executive chairman's address to final year students",
        "executive-chairmans-address-to-final-year-students",
        None,
    ),
    (
        "Interaction session with a space scientist",
        "special-interaction-session-with-a-space-scientist",
        None,
    ),
    ("Secure coding workshop in CC4", "hands-on-workshop-on-secure-coding", None),
    (
        "Hands-on Kubernetes and containers workshop",
        "hands-on-workshop-on-containers-and-kubernetes",
        None,
    ),
    (
        "FDP on REST API design for faculty",
        "three-day-faculty-development-programme-on-rest-api-design",
        None,
    ),
    ("Ethical hacking value added course", "value-added-course-ethical-hacking-fundamentals", None),
    ("Guest lecture on IoT with Arduino", "guest-lecture-on-iot-with-arduino", None),
    ("Talk on big data with Spark", "guest-lecture-on-big-data-with-spark", None),
    (
        "Principal's address to second year students",
        "principals-address-to-second-year-students",
        None,
    ),
    (
        "Machine learning pipelines workshop in CC5",
        "hands-on-workshop-on-machine-learning-pipelines",
        None,
    ),
    ("Lecture on edge AI", "guest-lecture-on-edge-ai", None),
    (
        "Three day FDP on SQL for analytics 2026",
        "three-day-faculty-development-programme-on-sql-for-analytics",
        2026,
    ),
    ("Resume building guest lecture for MBA students", "guest-lecture-on-resume-building", None),
    ("AWS core services value-added course", "value-added-course-aws-core-services", None),
]


def found(db, question: str, series: str, year: int | None) -> bool:
    for hit in search(db, question, limit=5):
        e = hit.event
        if e and e.series_key == series and (year is None or e.start_date.year == year):
            return True
    return False


def test_recall_at_5(docs_db):
    misses = [q for q, s, y in QUESTIONS if not found(docs_db, q, s, y)]
    recall = 1 - len(misses) / len(QUESTIONS)
    assert recall >= 0.9, f"recall@5 {recall:.2f}; missed: {misses}"


@pytest.mark.parametrize("question", ["hackathon", "the", "??", "CC1"])
def test_odd_queries_do_not_crash(docs_db, question):
    assert isinstance(search(docs_db, question), list)
