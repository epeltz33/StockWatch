from unittest.mock import Mock, patch


def test_landing_page(client):
    response = client.get("/")
    assert response.status_code == 200


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "healthy"}


def test_dashboard_requires_login(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_dash_routes_require_login(client):
    response = client.get("/dash/", follow_redirects=False)
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_security_headers_present(client):
    response = client.get("/")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    # The dashboard is no longer embedded in an iframe, so nothing may frame us
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


def test_landing_leads_with_the_demo(client):
    html = client.get("/").get_data(as_text=True)
    ctas = html[html.index('class="cta-buttons"') :]
    # First (primary) action is the demo; login and registration follow
    assert ctas.index('href="/demo/"') < ctas.index("/auth/login")
    assert ctas.index('href="/demo/"') < ctas.index("/auth/register")
    assert 'href="/demo/" class="btn btn-primary' in html
    assert "Live market data" not in html


def test_landing_offers_the_dashboard_to_signed_in_users(client):
    register_and_login(client)
    html = client.get("/").get_data(as_text=True)
    assert 'href="/dash/" class="btn btn-primary' in html


def test_dashboard_redirects_signed_in_users_to_the_dash_page(client):
    register_and_login(client)
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/dash/")
    assert client.get("/dash/").status_code == 200


def test_dash_callbacks_require_login_but_demo_callbacks_do_not(client):
    assert client.post("/dash/_dash-update-component", json={}).status_code in (302, 401)
    assert client.get("/demo/_dash-dependencies").status_code == 200


def test_auth_pages_link_to_the_demo(client):
    for page in ("/auth/login", "/auth/register"):
        assert 'href="/demo/"' in client.get(page).get_data(as_text=True)


def register_and_login(client):
    client.post(
        "/auth/register",
        data={
            "username": "visitor",
            "email": "visitor@example.com",
            "password": "password123",
            "confirm_password": "password123",
        },
    )
    client.post("/auth/login", data={"email": "visitor@example.com", "password": "password123"})


def test_branding_rejects_unknown_kind(client):
    assert client.get("/branding/AAPL/banner").status_code == 404


def test_branding_rejects_bad_symbol(client):
    assert client.get("/branding/AA..PL/icon").status_code == 404


def test_branding_404_when_no_details(client):
    with patch("app.blueprints.main.get_company_details", return_value=None):
        assert client.get("/branding/AAPL/icon").status_code == 404


def test_branding_proxies_and_caches_image(client):
    details = {"icon_url": "https://upstream.example.com/icon.png", "logo_url": None}
    upstream = Mock()
    upstream.content = b"\x89PNG-fake-bytes"
    upstream.headers = {"Content-Type": "image/png"}
    upstream.raise_for_status = Mock()

    with patch("app.blueprints.main.get_company_details", return_value=details):
        with patch("app.blueprints.main.requests.get", return_value=upstream) as mock_get:
            first = client.get("/branding/AAPL/icon")
            second = client.get("/branding/AAPL/icon")

    assert first.status_code == 200
    assert first.data == b"\x89PNG-fake-bytes"
    assert first.mimetype == "image/png"
    assert "max-age=86400" in first.headers["Cache-Control"]
    # Second request must be served from cache without re-hitting upstream
    assert second.status_code == 200
    assert mock_get.call_count == 1
    # The API key travels via params, never embedded in the stored URL
    _, kwargs = mock_get.call_args
    assert "apiKey" not in mock_get.call_args[0][0]


def test_branding_falls_back_to_logo_when_no_icon(client):
    details = {"icon_url": None, "logo_url": "https://upstream.example.com/logo.svg"}
    upstream = Mock()
    upstream.content = b"<svg/>"
    upstream.headers = {"Content-Type": "image/svg+xml"}
    upstream.raise_for_status = Mock()

    with patch("app.blueprints.main.get_company_details", return_value=details):
        with patch("app.blueprints.main.requests.get", return_value=upstream) as mock_get:
            response = client.get("/branding/MSFT/icon")

    assert response.status_code == 200
    assert mock_get.call_args[0][0] == "https://upstream.example.com/logo.svg"
