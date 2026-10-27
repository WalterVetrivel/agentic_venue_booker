from sqlalchemy import select

from app.models import User, Venue
from app.seed.seed import normalise_name, seed_all


def test_counts(db):
    users = db.scalars(select(User)).all()
    venues = db.scalars(select(Venue)).all()
    assert len(venues) == 23
    # 44 faculty (Dr. V. Kumar has only the Director login) + director, HOD, OA, 4 hall in-charges
    assert len(users) == 51


def test_seed_is_idempotent(db):
    before = len(db.scalars(select(User)).all())
    seed_all(db)
    assert len(db.scalars(select(User)).all()) == before


def test_special_accounts(db):
    by_email = {u.email: u for u in db.scalars(select(User)).all()}
    assert by_email["dirim@kiot.ac.in"].role_keys == ["director"]
    assert by_email["hod.cse@kiot.ac.in"].role_keys == ["hod"]
    assert by_email["cseoa@kiot.ac.in"].role_keys == ["oa"]
    assert by_email["tkcse@kiot.ac.in"].name == "Mr. T. Karthikeyan"
    assert "vkcse@kiot.ac.in" not in by_email
    assert by_email["prcse@kiot.ac.in"].role_keys == ["faculty"]
    # Walter is in-charge of CC10 as well as a faculty member
    assert by_email["swvcse@kiot.ac.in"].role_keys == ["faculty", "incharge"]


def test_capacities(db):
    cap = {v.code: v.capacity for v in db.scalars(select(Venue)).all()}
    assert cap["CC1"] == cap["CC2"] == 60
    assert all(cap[f"CC{i}"] == 40 for i in range(3, 13))
    assert cap["PGLAB"] == cap["IOTLAB"] == 40
    assert all(cap[f"COE{i}"] == 30 for i in range(1, 5))
    assert cap["CSEPGSH"] == 80
    assert cap["ASH"] == cap["MBASH"] == 100
    assert cap["DSH"] == cap["ESH"] == 300


def test_hod_approval_only_for_cse_venues(db):
    venues = {v.code: v for v in db.scalars(select(Venue)).all()}
    assert venues["CC5"].needs_hod_approval and venues["COE2"].needs_hod_approval
    assert venues["CSEPGSH"].needs_hod_approval
    assert not any(venues[c].needs_hod_approval for c in ["ASH", "DSH", "ESH", "MBASH"])


def test_a_block_admission_rule(db):
    ash = db.scalar(select(Venue).where(Venue.code == "ASH"))
    (rule,) = ash.seasonal_rules
    assert (rule.start_month, rule.end_month, rule.kind) == (3, 7, "blocked")


def test_coe_aliases(db):
    coe3 = db.scalar(select(Venue).where(Venue.code == "COE3"))
    assert "Centre of Excellence (COE3)" in {a.alias for a in coe3.aliases}


def test_normalise_name():
    assert normalise_name("Dr.V.Kumar") == "Dr. V. Kumar"
    assert normalise_name("Mrs. R.Saranya") == "Mrs. R. Saranya"
