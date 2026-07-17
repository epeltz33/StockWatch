"""Portfolio position and P/L derivation from the transaction ledger.

All math uses Decimal end to end. Cost basis is average cost (not FIFO):
each BUY re-weights the position's average cost; each SELL realizes
(sell price - average cost) x quantity and leaves the average unchanged.
This is deterministic, simple to verify, and the common convention for
non-tax-lot portfolio trackers.
"""

import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.extensions import db
from app.models import Stock, Transaction
from app.services.stock_services import (
    get_company_details,
    get_stock_by_symbol,
    get_stock_price,
)

logger = logging.getLogger(__name__)

VALID_SIDES = ("BUY", "SELL")


class PortfolioError(ValueError):
    """Base class for domain errors surfaced to the UI/API as user mistakes."""


class InsufficientSharesError(PortfolioError):
    """Selling (or deleting a BUY) would make a position go negative."""


@dataclass
class Position:
    symbol: str
    name: str
    quantity: Decimal
    avg_cost: Decimal
    cost_basis: Decimal
    realized_pl: Decimal
    current_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pl: Decimal | None = None
    unrealized_pl_pct: Decimal | None = None


@dataclass
class _SymbolState:
    """Running state for one symbol during a ledger replay."""

    name: str
    quantity: Decimal = Decimal(0)
    avg_cost: Decimal = Decimal(0)
    realized_pl: Decimal = Decimal(0)


def _replay(transactions: list[Transaction]) -> dict[str, _SymbolState]:
    """Replay a transaction list in (executed_at, id) order.

    Raises InsufficientSharesError if any SELL exceeds the quantity held at
    that point — used both for reading positions and for validating that a
    prospective insert/delete keeps the ledger consistent.
    """
    states: dict[str, _SymbolState] = {}
    ordered = sorted(
        transactions, key=lambda t: (t.executed_at, t.id if t.id is not None else 2**63)
    )

    for txn in ordered:
        symbol = txn.stock.symbol
        state = states.setdefault(symbol, _SymbolState(name=txn.stock.name or symbol))
        quantity = Decimal(txn.quantity)
        price = Decimal(txn.price)

        if txn.side == "BUY":
            new_quantity = state.quantity + quantity
            state.avg_cost = (state.quantity * state.avg_cost + quantity * price) / new_quantity
            state.quantity = new_quantity
        else:  # SELL
            if quantity > state.quantity:
                raise InsufficientSharesError(
                    f"Cannot sell {quantity} {symbol} on {txn.executed_at}: "
                    f"only {state.quantity} held"
                )
            state.realized_pl += (price - state.avg_cost) * quantity
            state.quantity -= quantity
            if state.quantity == 0:
                state.avg_cost = Decimal(0)

    return states


def _get_or_create_stock(symbol: str) -> Stock:
    stock = get_stock_by_symbol(symbol)
    if stock is not None:
        return stock

    # Best-effort company name; fall back to the symbol itself
    name = symbol
    try:
        details = get_company_details(symbol)
        if details and isinstance(details.get("name"), str):
            name = details["name"]
    except Exception:
        logger.warning(f"Could not fetch company details for {symbol}; using symbol as name")

    stock = Stock(symbol=symbol, name=name)
    db.session.add(stock)
    db.session.flush()
    return stock


def record_transaction(
    user_id: int,
    symbol: str,
    side: str,
    quantity: Decimal | str | int,
    price: Decimal | str | int,
    executed_at: date,
) -> Transaction:
    """Validate and persist a BUY/SELL, keeping the whole ledger consistent.

    The candidate is validated by replaying the full ledger with it included,
    so a backdated SELL that would make a later position negative is rejected,
    not just an oversell as of its own date.
    """
    symbol = symbol.strip().upper()
    if not symbol or not symbol.isalnum() or len(symbol) > 10:
        raise PortfolioError(f"Invalid symbol: {symbol!r}")

    side = side.strip().upper()
    if side not in VALID_SIDES:
        raise PortfolioError(f"Side must be BUY or SELL, got {side!r}")

    try:
        quantity = Decimal(str(quantity))
        price = Decimal(str(price))
    except ArithmeticError as exc:
        raise PortfolioError("Quantity and price must be numeric") from exc

    if quantity <= 0:
        raise PortfolioError("Quantity must be positive")
    if price < 0:
        raise PortfolioError("Price cannot be negative")
    if not isinstance(executed_at, date):
        raise PortfolioError("executed_at must be a date")

    stock = _get_or_create_stock(symbol)
    candidate = Transaction(
        user_id=user_id,
        stock_id=stock.id,
        side=side,
        quantity=quantity,
        price=price,
        executed_at=executed_at,
    )
    candidate.stock = stock

    existing = list(Transaction.query.filter_by(user_id=user_id).all())
    try:
        # id=None sorts the candidate after persisted rows on the same date,
        # matching the id it will get on insert
        _replay(existing + [candidate])
    except InsufficientSharesError:
        # Discard the possibly-flushed new Stock row along with the candidate
        db.session.rollback()
        raise

    db.session.add(candidate)
    db.session.commit()
    return candidate


def delete_transaction(user_id: int, transaction_id: int) -> bool:
    """Delete a transaction if owned by user and removal keeps the ledger valid.

    Removing an old BUY that backs a later SELL would make that position go
    negative mid-replay; such deletes raise InsufficientSharesError.
    """
    txn = Transaction.query.filter_by(id=transaction_id, user_id=user_id).first()
    if txn is None:
        return False

    remaining = [t for t in Transaction.query.filter_by(user_id=user_id).all() if t.id != txn.id]
    _replay(remaining)

    db.session.delete(txn)
    db.session.commit()
    return True


def get_positions(user_id: int) -> list[Position]:
    """Open positions (quantity > 0) with live pricing where available."""
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    states = _replay(transactions)

    positions = []
    for symbol in sorted(states):
        state = states[symbol]
        if state.quantity <= 0:
            continue

        position = Position(
            symbol=symbol,
            name=state.name,
            quantity=state.quantity,
            avg_cost=state.avg_cost,
            cost_basis=state.quantity * state.avg_cost,
            realized_pl=state.realized_pl,
        )

        raw_price = get_stock_price(symbol)
        if raw_price is not None:
            price = Decimal(str(raw_price))
            position.current_price = price
            position.market_value = state.quantity * price
            position.unrealized_pl = position.market_value - position.cost_basis
            if position.cost_basis != 0:
                position.unrealized_pl_pct = position.unrealized_pl / position.cost_basis * 100

        positions.append(position)

    return positions


def get_portfolio_summary(user_id: int) -> dict:
    """Totals across the portfolio plus allocation weights for charting.

    Positions with no available price are excluded from market-value totals
    and allocations but still counted in cost basis. Realized P/L includes
    fully closed positions.
    """
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    states = _replay(transactions)
    positions = get_positions(user_id)

    total_realized = sum((s.realized_pl for s in states.values()), Decimal(0))
    total_cost_basis = sum((p.cost_basis for p in positions), Decimal(0))
    priced = [p for p in positions if p.market_value is not None]
    total_market_value = sum((p.market_value for p in priced), Decimal(0))
    priced_cost_basis = sum((p.cost_basis for p in priced), Decimal(0))
    total_unrealized = total_market_value - priced_cost_basis

    allocations = []
    if total_market_value > 0:
        allocations = [
            {
                "symbol": p.symbol,
                "value": p.market_value,
                "weight": p.market_value / total_market_value,
            }
            for p in priced
        ]

    return {
        "positions": positions,
        "market_value": total_market_value,
        "cost_basis": total_cost_basis,
        "unrealized_pl": total_unrealized,
        "unrealized_pl_pct": (
            total_unrealized / priced_cost_basis * 100 if priced_cost_basis > 0 else None
        ),
        "realized_pl": total_realized,
        "allocations": allocations,
    }


def list_transactions(user_id: int, limit: int = 50, offset: int = 0) -> list[Transaction]:
    """Most recent transactions first (by execution date, then insert order)."""
    return (
        Transaction.query.filter_by(user_id=user_id)
        .order_by(Transaction.executed_at.desc(), Transaction.id.desc())
        .limit(limit)
        .offset(offset)
        .all()
    )
