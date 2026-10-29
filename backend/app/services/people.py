"""Matching names to staff accounts: timetable columns, and how people refer to each other.

In the department people say "Walter sir", "EK ma'am" or "HOD sir" rather than "Mr. S. Walter
Vetrivel". `find_people` understands those: a role, initials, or any part of a name (spelt a
little differently, e.g. Sowndarya and Sowndharya), with or without sir/ma'am. It returns
every match, so the assistant can ask which one when several people share a name.
"""

import re
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserRole

_TITLES = re.compile(r"\b(dr|mr|mrs|ms|prof)\b\.?", re.I)
# What people put before or after a name when they talk about someone.
_HONORIFICS = re.compile(
    r"\b(sir|madam|ma['’]?a?m|miss|mister|mr|mrs|ms|dr|prof|professor|teacher|staff|our|my)\b\.?",
    re.I,
)
ROLE_WORDS = {
    "hod": "hod",
    "head of department": "hod",
    "head of the department": "hod",
    "cse hod": "hod",
    "hod cse": "hod",
    "director": "director",
    "oa": "oa",
    "office assistant": "oa",
}


def name_key(name: str) -> str:
    """Compare names without titles, punctuation or a trailing designation (", AP/CSE")."""
    name = name.split(",")[0]
    return re.sub(r"[^a-z]", "", _TITLES.sub("", name.lower()))


def faculty_matching(db: Session, name: str | None) -> list[User]:
    """Users whose name matches a timetable's faculty or advisor column."""
    if not name:
        return []
    key = name_key(name)
    return [u for u in db.scalars(select(User).where(User.active)) if name_key(u.name) == key]


def guides(db: Session) -> list[User]:
    """Staff a student group can name as its faculty guide: CSE faculty and the HOD."""
    rows = db.scalars(
        select(User)
        .join(UserRole)
        .where(User.active, UserRole.role_key.in_(("faculty", "hod")))
        .order_by(User.name)
    ).unique()
    return list(rows)


# Informal references ----------------------------------------------------------------------------


def sound(word: str) -> str:
    """A spelling-tolerant form of a name: Sowndharya, Sowndarya and Sowndariya sound alike."""
    w = re.sub(r"[^a-z]", "", word.lower())
    w = re.sub(r"(?<=[bcdgjkpstz])h", "", w)  # dh/th/sh/kh -> d/t/s/k
    w = w.replace("w", "v").replace("ee", "i").replace("oo", "u").replace("iy", "y")
    return re.sub(r"(.)\1+", r"\1", w)


def name_parts(name: str) -> tuple[list[str], list[str]]:
    """Initials and words of a name: "Mrs.V.SathiyaPriya" -> (["v"], ["sathiya", "priya"])."""
    name = _TITLES.sub(" ", name.split(",")[0])
    name = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)  # SathiyaPriya -> Sathiya Priya
    tokens = [t.lower() for t in re.split(r"[^A-Za-z]+", name) if t]
    return [t for t in tokens if len(t) == 1], [t for t in tokens if len(t) > 1]


def initials_of(user: User) -> str:
    if user.initials:
        return user.initials.lower()
    letters, words = name_parts(user.name)
    return "".join(letters) + "".join(w[0] for w in words)


def reference_words(text: str) -> list[str]:
    """The name in "Walter sir" or "EK ma'am": the words left once sir, ma'am and Mr. go."""
    text = _HONORIFICS.sub(" ", text.split(",")[0])
    return [w.lower() for w in re.split(r"[^A-Za-z]+", text) if w]


def _word_matches(word: str, letters: list[str], words: list[str]) -> bool:
    if len(word) == 1:  # an initial: "K Saranya"
        return word in letters or any(w[0] == word for w in words)
    s = sound(word)
    for w in map(sound, words):
        if s == w or (len(s) >= 4 and w.startswith(s)):  # "Ravi" for Ravikumar
            return True
        if len(s) >= 5 and SequenceMatcher(None, s, w).ratio() >= 0.85:  # a typo
            return True
    return False


def refers_to(text: str, name: str) -> bool:
    """Whether an informal reference ("Sowndarya ma'am", "Walter") fits a full name."""
    query = reference_words(text)
    if not query:
        return False
    letters, words = name_parts(name)
    if "".join(query) == "".join(letters + words):  # the full name, written another way
        return True
    return bool(words) and all(_word_matches(q, letters, words) for q in query)


def _distinct(users: list[User]) -> list[User]:
    """One account per person (the HOD also has a faculty login under the same name)."""
    seen: dict[str, User] = {}
    for u in users:
        seen.setdefault(name_key(u.name), u)
    return list(seen.values())


def find_people(users: list[User], text: str) -> list[User]:
    """Everyone among `users` that "Walter sir", "EK ma'am", "HOD sir" or a full name refers to.

    Tried in turn, stopping at the first that finds someone: a role (HOD), the exact name,
    initials, then parts of the name.
    """
    query = reference_words(text)
    if not query:
        return []
    role = ROLE_WORDS.get(" ".join(query))
    if role:
        return _distinct([u for u in users if role in u.role_keys])
    key = name_key(text)
    exact = [u for u in users if name_key(u.name) == key]
    if exact:
        return _distinct(exact)
    if len(query) == 1 and len(query[0]) <= 4:
        by_initials = [u for u in users if initials_of(u) == query[0]]
        if by_initials:
            return _distinct(by_initials)
    return _distinct([u for u in users if refers_to(text, u.name)])


def staff(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.active).order_by(User.id)))
