"""Small SVG view model for the landing page, using the demo's daily bars."""

import math
from datetime import date, timedelta


def build_price_preview(bars):
    """Map the latest year to SVG coordinates without smoothing or invented prices."""
    if len(bars) < 2:
        return None
    end = date.fromisoformat(bars[-1]["date"])
    start = end - timedelta(days=365)
    bars = [bar for bar in bars if date.fromisoformat(bar["date"]) >= start]
    if len(bars) < 2:
        return None
    prices = [bar["close"] for bar in bars]
    low = math.floor(min(prices) / 20) * 20
    high = math.ceil(max(prices) / 20) * 20
    if high == low:
        high += 20
    first = date.fromisoformat(bars[0]["date"])
    span = max((end - first).days, 1)

    def x(day):
        return 8 + (day - first).days / span * 510

    def y(price):
        return 20 + (high - price) / (high - low) * 216

    points = [(x(date.fromisoformat(bar["date"])), y(bar["close"])) for bar in bars]
    path = "M" + " L".join(f"{px:.2f},{py:.2f}" for px, py in points)
    ticks = [
        {"y": round(y(value), 2), "label": f"${value:,.0f}"} for value in range(low, high + 1, 20)
    ]
    dates = []
    for year in range(first.year, end.year + 1):
        for month in (1, 4, 7, 10):
            day = date(year, month, 1)
            if first <= day <= end:
                dates.append({"x": round(x(day), 2), "label": day.strftime("%b")})
    change = (prices[-1] / prices[0] - 1) * 100
    return {
        "path": path,
        "ticks": ticks,
        "dates": dates,
        "last_y": round(y(prices[-1]), 2),
        "price": f"${prices[-1]:,.2f}",
        "change": f"{change:+.2f}%",
        "direction": "gain" if change >= 0 else "loss",
        "date": f"{end:%b} {end.day}, {end.year}",
        "start_date": first.isoformat(),
        "end_date": end.isoformat(),
    }


def build_watchlist_preview(companies, quotes):
    """Rows for the landing watchlist table, from the demo's sample quotes."""
    rows = []
    for company in companies:
        quote = quotes.get(company.symbol)
        if quote is None:
            continue
        rows.append(
            {
                "symbol": company.symbol,
                "name": company.name,
                "price": f"${quote.price:,.2f}",
                "change": f"{quote.change_pct:+.2f}%",
                "direction": "gain" if quote.change >= 0 else "loss",
            }
        )
    return rows
