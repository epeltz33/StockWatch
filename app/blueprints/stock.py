from flask import Blueprint, render_template, jsonify, request
from app.services import stock_services
from datetime import datetime, timedelta

bp = Blueprint('stock', __name__)


@bp.route('/')
def list_stocks():
    stocks = stock_services.get_all_stocks()
    return render_template('stocks/list.html', stocks=stocks)


@bp.route('/api')
def api_stocks():
    stocks = stock_services.get_all_stocks()
    return jsonify([stock.to_dict() for stock in stocks])


@bp.route('/api/<symbol>')
def stock_info(symbol):
    price = stock_services.get_stock_price(symbol)
    details = stock_services.get_company_details(symbol)
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
    return jsonify(data)
