import pytest

ROLE_LOGINS = {
    "swvcse@kiot.ac.in": {"faculty", "incharge"},
    "tkcse@kiot.ac.in": {"faculty"},
    "hod.cse@kiot.ac.in": {"hod"},
    "dirim@kiot.ac.in": {"director"},
    "cseoa@kiot.ac.in": {"oa"},
    "sh.dblock@kiot.ac.in": {"incharge"},
}


@pytest.mark.parametrize("email,roles", ROLE_LOGINS.items())
def test_login_each_role(client, login, email, roles):
    user = login(email)
    assert set(user["roles"]) == roles
    me = client.get("/api/auth/me").json()
    assert me["user"]["email"] == email


def test_login_is_case_insensitive(login):
    assert login("SWVCSE@kiot.ac.in")["initials"] == "SWV"


def test_wrong_password(client):
    res = client.post("/api/auth/login", json={"email": "swvcse@kiot.ac.in", "password": "nope"})
    assert res.status_code == 401


def test_anonymous_me_has_public_capabilities_only(client):
    me = client.get("/api/auth/me").json()
    assert me["user"] is None
    assert set(me["capabilities"]) == {"view_venues", "check_availability", "use_assistant"}


def test_logout(client, login):
    login("swvcse@kiot.ac.in")
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me").json()["user"] is None


def test_capabilities_per_role(client, login):
    assert "manage_settings" in login("dirim@kiot.ac.in")["capabilities"]
    hod = login("hod.cse@kiot.ac.in")["capabilities"]
    assert {"approve_cse_venues", "approve_displacement"} <= set(hod)
    assert "manage_settings" not in hod
    oa = login("cseoa@kiot.ac.in")["capabilities"]
    assert "upload_timetables" in oa and "book" not in oa
    faculty = login("prcse@kiot.ac.in")["capabilities"]
    assert "book" in faculty and "approve_own_venues" not in faculty
