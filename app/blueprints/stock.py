from flask import Blueprint, jsonify, request
from app.services import stock_services
from datetime import datetime, timedelta

bp = Blueprint('stock', __name__)


@bp.route('/api/<symbol>')
def stock_info(symbol):
    price = stock_services.get_stock_price(symbol)
    if price is None:
        return jsonify({"error": "Could not fetch stock price. Please try again later."}), 500
    details = stock_services.get_company_details(symbol)
    if not details:
        return jsonify({"error": "Could not fetch company details. Please try again later."}), 500
    return jsonify({
        "symbol": symbol,
        "price": price,
        "details": details
    })


@bp.route('/api/<symbol>/historical')
def stock_historical(symbol):
    days = request.args.get('days', default=30, type=int)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    data = stock_services.get_stock_data(
        symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
    if not data:
        return jsonify({"error": "Could not fetch historical data. Please try again later."}), 500
    return jsonify(data)

