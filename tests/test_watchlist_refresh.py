"""The watchlist re-renders on the shared update interval.

Rows carry live price and day change (see test_watchlist_quotes.py), so a
list rendered once at page load goes stale while the tab sits open. The
interval tick re-renders the selected watchlist and nothing else: it must not
move the user's dropdown selection or raise a toast.
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from dash import no_update
from flask import Flask

from frontend import dashboard

WATCHLIST_OUTPUT = "watchlist-section"
INTERVAL_ID = "watchlist-interval"


@pytest.fixture
def dash_app(app):
    """A Dash app mounted on its own server, so the fixture's mounted copy is
    left alone while we inspect and drive the callback registry."""
    with app.app_context():
        yield dashboard.create_dash_app(Flask(__name__))


def _watchlist_callback(dash_app):
    for key, entry in dash_app.callback_map.items():
        if WATCHLIST_OUTPUT in key:
            return entry
    raise AssertionError(f"no callback outputs {WATCHLIST_OUTPUT}")


def _interval_ctx():
    return SimpleNamespace(
        triggered_id=INTERVAL_ID,
        triggered=[{"prop_id": f"{INTERVAL_ID}.n_intervals", "value": 3}],
    )


def test_watchlist_section_is_wired_to_the_update_interval(dash_app):
    inputs = _watchlist_callback(dash_app)["inputs"]

    assert any(i.get("id") == INTERVAL_ID for i in inputs)


def test_interval_tick_rerenders_the_selected_watchlist(dash_app):
    raw = _watchlist_callback(dash_app)["callback"].__wrapped__
    rendered = Mock(return_value="fresh-rows")

    with patch.object(dashboard, "callback_context", _interval_ctx()):
        with patch.object(dashboard, "update_watchlist_section", rendered):
            section, dropdown_value, _add_labels, toast = raw(None, [], [], [], 7, 3, None, [])

    rendered.assert_called_once_with(7)
    assert section == "fresh-rows"
    # The user's selection and any visible toast are left untouched
    assert dropdown_value is no_update
    assert toast is no_update


def test_interval_tick_without_a_selected_watchlist_changes_nothing(dash_app):
    raw = _watchlist_callback(dash_app)["callback"].__wrapped__
    rendered = Mock()

    with patch.object(dashboard, "callback_context", _interval_ctx()):
        with patch.object(dashboard, "update_watchlist_section", rendered):
            section, dropdown_value, _add_labels, toast = raw(None, [], [], [], None, 3, None, [])

    rendered.assert_not_called()
    assert section is no_update
    assert dropdown_value is no_update
    assert toast is no_update
