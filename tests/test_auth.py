from app.models import User


def register(client, username="alice", email="alice@example.com", password="password123"):
    return client.post(
        "/auth/register",
        data={
            "username": username,
            "email": email,
            "password": password,
            "confirm_password": password,
        },
        follow_redirects=False,
    )


def login(client, email="alice@example.com", password="password123"):
    return client.post(
        "/auth/login",
        data={"email": email, "password": password},
        follow_redirects=False,
    )


def test_register_creates_user(client, app):
    response = register(client)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]
    with app.app_context():
        user = User.query.filter_by(email="alice@example.com").first()
        assert user is not None
        assert user.username == "alice"
        assert user.check_password("password123")


def test_register_rejects_duplicate_email(client):
    register(client)
    response = register(client, username="different")
    assert response.status_code == 200
    assert b"Email address already in use." in response.data


def test_register_rejects_duplicate_username(client):
    register(client)
    response = register(client, email="other@example.com")
    assert response.status_code == 200
    assert b"Username already taken." in response.data


def test_register_rejects_short_password(client, app):
    response = register(client, password="short")
    assert response.status_code == 200
    assert b"at least 8 characters" in response.data
    with app.app_context():
        assert User.query.count() == 0


def test_register_rejects_invalid_email(client, app):
    response = register(client, email="not-an-email")
    assert response.status_code == 200
    with app.app_context():
        assert User.query.count() == 0


def test_register_rejects_password_mismatch(client, app):
    response = client.post(
        "/auth/register",
        data={
            "username": "alice",
            "email": "alice@example.com",
            "password": "password123",
            "confirm_password": "password456",
        },
    )
    assert response.status_code == 200
    assert b"Passwords must match." in response.data
    with app.app_context():
        assert User.query.count() == 0


def test_login_logout_flow(client):
    register(client)
    response = login(client)
    assert response.status_code == 302
    assert "/dashboard" in response.headers["Location"]

    response = client.get("/auth/logout", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_login_rejects_wrong_password(client):
    register(client)
    response = login(client, password="wrong-password")
    assert response.status_code == 200
    assert b"Invalid email or password" in response.data


def test_login_is_case_insensitive_on_email(client):
    register(client)
    response = login(client, email="ALICE@example.com")
    assert response.status_code == 302


def test_login_next_param_blocks_open_redirect(client):
    register(client)
    response = client.post(
        "/auth/login?next=https://evil.example.com/phish",
        data={"email": "alice@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    # Absolute external URLs must be ignored in favor of the dashboard
    assert "evil.example.com" not in response.headers["Location"]
    assert "/dashboard" in response.headers["Location"]


def test_login_next_param_allows_relative_path(client):
    register(client)
    response = client.post(
        "/auth/login?next=/dashboard",
        data={"email": "alice@example.com", "password": "password123"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dashboard")


def test_csrf_protection_rejects_post_without_token(app_with_csrf):
    client = app_with_csrf.test_client()
    response = client.post(
        "/auth/login",
        data={"email": "alice@example.com", "password": "password123"},
    )
    assert response.status_code == 400


def test_login_rate_limit_returns_429(app_with_rate_limit):
    client = app_with_rate_limit.test_client()
    for _ in range(10):
        client.post("/auth/login", data={"email": "x@example.com", "password": "bad"})
    response = client.post("/auth/login", data={"email": "x@example.com", "password": "bad"})
    assert response.status_code == 429
