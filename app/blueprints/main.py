import os

import requests
from flask import Blueprint, Response, abort, render_template
from flask_login import current_user, login_required

from app.extensions import cache
from app.services.stock_services import get_company_details
from app.utils.cache_manager import StockCache

bp = Blueprint("main", __name__)


@bp.route("/")
def landing():
    return render_template("main/landing.html")


@bp.route("/dashboard")
@login_required
def dashboard():
    dash_url = "/dash/"
    return render_template("main/dashboard.html", dash_url=dash_url, user=current_user)


@bp.route("/branding/<symbol>/<kind>")
def branding(symbol: str, kind: str):
    """Proxy company branding images from the market-data API.

    The upstream URLs require the API key as a query parameter; fetching them
    server-side keeps the key out of the HTML the client sees. Image bytes are
    cached for 24h so repeat views don't re-hit the upstream API.
    """
    if kind not in ("icon", "logo"):
        abort(404)

    symbol = symbol.strip().upper()
    if not symbol.isalnum() or len(symbol) > 10:
        abort(404)

    stock_cache = StockCache(cache)
    cached = stock_cache.get_cached_data(symbol, "branding", kind=kind)
    if cached is not None:
        data, content_type = cached
        return Response(
            data, mimetype=content_type, headers={"Cache-Control": "public, max-age=86400"}
        )

    details = get_company_details(symbol)
    if not details:
        abort(404)

    # Prefer the requested kind but fall back to the other one, so callers can
    # always ask for /icon and still get the logo when no icon exists.
    url = details.get(f"{kind}_url") or details.get("logo_url" if kind == "icon" else "icon_url")
    if not url:
        abort(404)

    api_key = os.getenv("POLYGON_API_KEY")
    try:
        upstream = requests.get(url, params={"apiKey": api_key}, timeout=5)
        upstream.raise_for_status()
    except requests.RequestException:
        abort(502)

    content_type = upstream.headers.get("Content-Type", "image/png")
    stock_cache.set_cached_data(symbol, "branding", (upstream.content, content_type), kind=kind)
    return Response(
        upstream.content,
        mimetype=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
