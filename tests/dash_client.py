"""Drive a mounted Dash app's server callbacks over HTTP.

Builds the same `_dash-update-component` request the browser's renderer
sends, so a test exercises Flask routing, the app's request guards, and the
callback together — the path a hand-crafted request would take too.
"""

import json

from dash._utils import split_callback_id, stringify_id


def _is_pattern(id_):
    return isinstance(id_, str) and id_.startswith("{")


def changed(id_, prop):
    """changedPropIds entry for a component id (plain or pattern-matching)."""
    return f"{stringify_id(id_)}.{prop}"


class DashClient:
    def __init__(self, flask_client, dash_app):
        self.client = flask_client
        self.dash_app = dash_app
        self.url = f"{dash_app.config.requests_pathname_prefix}_dash-update-component"

    def find(self, name):
        """(key, entry) of the server callback defined by function `name`."""
        for key, entry in self.dash_app.callback_map.items():
            fn = entry.get("callback")
            fn = getattr(fn, "__wrapped__", fn)
            if getattr(fn, "__name__", None) == name:
                return key, entry
        raise KeyError(f"no server callback named {name!r}")

    def has(self, name):
        try:
            self.find(name)
        except KeyError:
            return False
        return True

    def body(self, name, values=None, triggered=(), components=None):
        """Request body for callback `name`.

        values: {"id.prop": value} for plain ids, {"type.prop": [values]} for
            pattern-matching ids (one per concrete component)
        components: {pattern type: [concrete ids]} present on the page
        triggered: changedPropIds, e.g. ["search-button.n_clicks"]
        """
        key, entry = self.find(name)
        values = values or {}
        components = components or {}

        def expand(dep, with_value):
            id_, prop = dep["id"], dep["property"]
            if _is_pattern(id_):
                pattern = json.loads(id_)
                concrete = components.get(pattern["type"], [])
                vals = values.get(f"{pattern['type']}.{prop}", [None] * len(concrete))
                return [
                    {"id": c, "property": prop, **({"value": v} if with_value else {})}
                    for c, v in zip(concrete, vals, strict=True)
                ]
            item = {"id": id_, "property": prop}
            if with_value:
                item["value"] = values.get(f"{id_}.{prop}")
            return item

        outputs = split_callback_id(key)
        single = isinstance(outputs, dict)
        expanded = [expand(o, False) for o in ([outputs] if single else outputs)]
        return {
            "output": key,
            "outputs": expanded[0] if single else expanded,
            "inputs": [expand(d, True) for d in entry["inputs"]],
            "state": [expand(d, True) for d in entry["state"]],
            "changedPropIds": list(triggered),
        }

    def call(self, name, values=None, triggered=(), components=None):
        return self.post(self.body(name, values, triggered, components))

    def post(self, body):
        return self.client.post(self.url, json=body)


def response_props(response):
    """{component id (stringified): {prop: value}} from a callback response."""
    if response.status_code == 204:
        return {}
    return response.get_json()["response"]
