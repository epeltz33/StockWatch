"""Edits and deletions from the signed-in dashboard.

Every action goes through the data source, which scopes it to the current
user; the demo's source refuses them all. Deletions happen only after the
user confirms them in the dialog.
"""

import logging

from dash import html, no_update
from dash.exceptions import PreventUpdate

from frontend.charts import format_bar_date
from frontend.data_sources import ReadOnlyDemoError, WatchlistError
from frontend.portfolio_tab import format_quantity
from frontend.shell import toast
from frontend.watchlist_panel import watchlist_options

logger = logging.getLogger(__name__)


def add_symbol_to_watchlist(source, watchlist_id, symbol, version):
    nonce = (version or 0) + 1
    if watchlist_id is None:
        return no_update, toast("Create or pick a watchlist first.", "warning", nonce)
    try:
        added, watchlist = source.add_to_watchlist(watchlist_id, symbol)
    except (WatchlistError, ReadOnlyDemoError) as exc:
        return no_update, toast(str(exc), "danger", nonce)
    except Exception:
        logger.exception("Failed to add %s to watchlist %s", symbol, watchlist_id)
        return no_update, toast(f"Could not add {symbol}.", "danger", nonce)
    if not added:
        return no_update, toast(f"{symbol} is already in “{watchlist.name}”.", "info", nonce)
    return nonce, toast(f"Added {symbol} to “{watchlist.name}”.", "success", nonce)


def remove_symbol_from_watchlist(source, watchlist_id, stock_id, version):
    nonce = (version or 0) + 1
    try:
        removed = source.remove_from_watchlist(watchlist_id, stock_id)
    except ReadOnlyDemoError as exc:
        return no_update, toast(str(exc), "danger", nonce)
    except Exception:
        logger.exception("Failed to remove stock %s from watchlist %s", stock_id, watchlist_id)
        return no_update, toast("Could not remove that stock.", "danger", nonce)
    if removed is None:
        return nonce, no_update
    return nonce, toast(f"Removed {removed}.", "success", nonce)


def confirmation_prompt(source, kind, target_id):
    """(title, body, pending) describing a destructive action, or None."""
    if kind == "delete-watchlist":
        watchlist = source.watchlist(target_id)
        if watchlist is None:
            return None
        count = len(watchlist.stocks)
        tickers = f"its {count} ticker{'s' if count != 1 else ''}" if count else "it"
        return (
            f"Delete “{watchlist.name}”?",
            [
                html.P(f"This removes the watchlist and {tickers} from it."),
                html.P(
                    "The same tickers stay in your other watchlists and your portfolio.",
                    className="confirm-note",
                ),
            ],
            {"kind": "watchlist", "id": watchlist.id, "label": watchlist.name},
        )
    if kind == "delete-transaction":
        txn = source.transaction(target_id)
        if txn is None:
            return None
        label = (
            f"{txn.side} {format_quantity(txn.quantity)} {txn.stock.symbol} "
            f"@ ${txn.price:,.2f} on {format_bar_date(txn.executed_at.isoformat())}"
        )
        return (
            "Delete this transaction?",
            [
                html.P(label, className="confirm-subject"),
                html.P(
                    "Positions, cost basis, and P/L are recalculated without it.",
                    className="confirm-note",
                ),
            ],
            {"kind": "transaction", "id": txn.id, "label": label},
        )
    return None


def perform_confirmed_delete(source, pending, watchlist_id, version, portfolio_version):
    """Carry out the confirmed action. Ownership is re-checked by the source."""
    nonce = (version or 0) + 1
    closed = (False, None)
    kind = pending.get("kind")
    try:
        if kind == "watchlist":
            name = source.delete_watchlist(pending.get("id"))
            if name is None:
                return (
                    *closed,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    toast("Watchlist not found.", "danger", nonce),
                )
            remaining = source.watchlists()
            selected = watchlist_id
            if watchlist_id == pending.get("id") or source.watchlist(watchlist_id) is None:
                selected = remaining[0].id if remaining else None
            return (
                *closed,
                watchlist_options(remaining),
                selected,
                nonce,
                no_update,
                toast(f"Deleted watchlist “{name}”.", "success", nonce),
            )
        if kind == "transaction":
            deleted = source.delete_transaction(pending.get("id"))
            if not deleted:
                return (
                    *closed,
                    no_update,
                    no_update,
                    no_update,
                    no_update,
                    toast("Transaction not found.", "danger", nonce),
                )
            return (
                *closed,
                no_update,
                no_update,
                no_update,
                (portfolio_version or 0) + 1,
                toast("Transaction deleted.", "success", nonce),
            )
    except ReadOnlyDemoError as exc:
        return (
            *closed,
            no_update,
            no_update,
            no_update,
            no_update,
            toast(str(exc), "danger", nonce),
        )
    except ValueError as exc:
        # PortfolioError: the delete would make a later sell oversold
        return (
            *closed,
            no_update,
            no_update,
            no_update,
            no_update,
            toast(str(exc), "danger", nonce),
        )
    except Exception:
        logger.exception("Confirmed delete failed: %s", pending)
        return (
            *closed,
            no_update,
            no_update,
            no_update,
            no_update,
            toast("Could not delete that.", "danger", nonce),
        )
    raise PreventUpdate
