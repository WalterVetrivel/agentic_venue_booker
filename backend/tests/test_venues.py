def test_venues_are_public(client):
    res = client.get("/api/venues")
    assert res.status_code == 200
    venues = res.json()
    assert len(venues) == 23
    assert [v["type"] for v in venues[:14]] == ["lab"] * 14


def test_filter_by_type(client):
    halls = client.get("/api/venues", params={"type": "seminar_hall"}).json()
    assert {v["code"] for v in halls} == {"CSEPGSH", "ASH", "DSH", "ESH", "MBASH"}


def test_venue_detail(client):
    cc5 = client.get("/api/venues/cc5").json()
    software = {e["name"] for e in cc5["equipment"] if e["category"] == "software"}
    assert "Power BI Desktop" in software
    assert cc5["in_charge"]["email"] == "mkscse@kiot.ac.in"


def test_unknown_venue(client):
    assert client.get("/api/venues/XYZ").status_code == 404


def test_health(client):
    assert client.get("/api/health").json() == {"status": "ok"}
