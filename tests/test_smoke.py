from app import app


def test_home_redirects_to_login():
    client = app.test_client()
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 303)


def test_login_page():
    client = app.test_client()
    response = client.get("/login")
    assert response.status_code == 200
