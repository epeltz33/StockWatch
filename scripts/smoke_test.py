"""Post-deploy smoke test for StockWatch.

    python scripts/smoke_test.py https://stockwatch-cqzs.onrender.com
    python scripts/smoke_test.py https://stockwatch-cqzs.onrender.com \\
        --email demo@stockwatch.dev --password 'Demo123!'

Checks demo access (public, sample data, read-only), authenticated access
(log in, open the dashboard, load a quote), and loading failures (a failed
search explains itself and leaves the chart alone). Talks to the Dash apps
the way the browser does, using only `requests`. Exits non-zero on failure.
"""

import argparse
import json
import re
import sys

import requests

# Render's free tier can take ~30s to wake up
TIMEOUT = 90


class Smoke:
    def __init__(self, base):
        self.base = base.rstrip("/")
        self.http = requests.Session()
        self.failures = 0

    def check(self, label, ok, detail=""):
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f" — {detail}" if detail else ""))
        if not ok:
            self.failures += 1
        return ok

    def get(self, path, **kwargs):
        return self.http.get(self.base + path, timeout=TIMEOUT, **kwargs)

    # --- Dash, the way its renderer calls it ------------------------------

    def callback(self, prefix, has_output, has_input):
        """Server callback spec whose output key and inputs mention these."""
        specs = self.get(f"{prefix}_dash-dependencies").json()
        for spec in specs:
            inputs = [f"{i['id']}.{i['property']}" for i in spec["inputs"]]
            if (
                not spec.get("clientside_function")
                and has_output in spec["output"]
                and has_input in inputs
            ):
                return spec
        raise LookupError(f"no callback outputs {has_output} from {has_input}")

    def call(self, prefix, spec, values, changed):
        key = spec["output"]
        parts = key[2:-2].split("...") if key.startswith("..") else [key]
        outputs = [dict(zip(("id", "property"), p.rsplit(".", 1), strict=True)) for p in parts]

        def deps(items):
            return [{**d, "value": values.get(f"{d['id']}.{d['property']}")} for d in items]

        body = {
            "output": key,
            "outputs": outputs if key.startswith("..") else outputs[0],
            "inputs": deps(spec["inputs"]),
            "state": deps(spec["state"]),
            "changedPropIds": [changed],
        }
        return self.http.post(
            f"{self.base}{prefix}_dash-update-component", json=body, timeout=TIMEOUT
        )


def props(response):
    return response.json().get("response", {}) if response.status_code == 200 else {}


def text_of(node):
    """The visible text in a serialized Dash component tree."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(text_of(child) for child in node)
    if isinstance(node, dict):
        return text_of(node.get("props", {}).get("children", node.get("children", "")))
    return ""


def run(base, email=None, password=None):
    s = Smoke(base)

    health = s.get("/health")
    s.check("health endpoint", health.status_code == 200, health.text.strip()[:80])

    landing = s.get("/").text
    ctas = landing[landing.find("cta-buttons") :]
    s.check(
        "landing leads with Explore demo",
        0 <= ctas.find('href="/demo/"') < ctas.find("/auth/login"),
    )

    # --- demo access ------------------------------------------------------
    s.check("demo page is public", s.get("/demo/").status_code == 200)
    layout = json.dumps(s.get("/demo/_dash-layout").json(), ensure_ascii=False)
    s.check("demo labels sample data", "Sample data · Not live prices" in layout)

    loader = s.callback("/demo/", "stock-symbol-store.data", "restore-request.data")
    opened = props(s.call("/demo/", loader, {"restore-request.data": {}}, "restore-request.data"))
    s.check(
        "demo opens on AAPL with a sample close",
        opened.get("stock-symbol-store", {}).get("data") == "AAPL"
        and "Sample close" in json.dumps(opened.get("stock-quote-caption")),
    )

    crafted = s.http.post(
        f"{s.base}/demo/_dash-update-component",
        json={"output": "watchlist-version.data", "outputs": {}, "inputs": [], "state": []},
        timeout=TIMEOUT,
    )
    s.check(
        "demo rejects a crafted edit request", crafted.status_code == 403, str(crafted.status_code)
    )

    outside = props(
        s.call(
            "/demo/",
            loader,
            {"search-button.n_clicks": 1, "stock-input.value": "TSLA"},
            "search-button.n_clicks",
        )
    )
    s.check(
        "demo search outside the sample explains itself, chart untouched",
        "isn't in the sample data" in json.dumps(outside) and "stock-chart" not in outside,
    )

    # --- authenticated access ---------------------------------------------
    gate = s.get("/dash/", allow_redirects=False)
    s.check(
        "dashboard requires login",
        gate.status_code == 302 and "/auth/login" in gate.headers.get("Location", ""),
    )

    if email and password:
        form = s.get("/auth/login").text
        token = re.search(r'name="csrf_token" type="hidden" value="([^"]+)"', form)
        login = s.http.post(
            f"{s.base}/auth/login",
            data={
                "email": email,
                "password": password,
                **({"csrf_token": token.group(1)} if token else {}),
            },
            allow_redirects=False,
            timeout=TIMEOUT,
        )
        s.check("log in", login.status_code == 302, login.headers.get("Location", ""))
        s.check("dashboard opens after login", s.get("/dash/").status_code == 200)

        loader = s.callback("/dash/", "stock-symbol-store.data", "restore-request.data")
        restored = props(
            s.call("/dash/", loader, {"restore-request.data": {}}, "restore-request.data")
        )
        symbol = restored.get("stock-symbol-store", {}).get("data")
        caption = text_of(restored.get("stock-quote-caption", {}).get("children"))
        if symbol:
            s.check(
                f"dashboard loads {symbol} with a dated close",
                "Close" in caption or "price history" in caption,
                caption,
            )
        else:
            s.check("dashboard opens (no watchlist ticker to show yet)", "chart-card" in restored)

        failed = props(
            s.call(
                "/dash/",
                loader,
                {
                    "search-button.n_clicks": 1,
                    "stock-input.value": "ZZZZZZ",
                    "stock-symbol-store.data": symbol,
                },
                "search-button.n_clicks",
            )
        )
        s.check(
            "failed search names the symbol and leaves the chart alone",
            "Couldn't load ZZZZZZ" in json.dumps(failed) and "stock-chart" not in failed,
        )
    else:
        print("SKIP  authenticated checks (pass --email and --password)")

    print(f"\n{'All checks passed.' if not s.failures else f'{s.failures} check(s) failed.'}")
    return 1 if s.failures else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("base_url")
    parser.add_argument("--email")
    parser.add_argument("--password")
    args = parser.parse_args()
    sys.exit(run(args.base_url, args.email, args.password))
