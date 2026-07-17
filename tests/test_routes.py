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
    assert response.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


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
