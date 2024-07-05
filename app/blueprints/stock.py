from flask import Blueprint, render_template, jsonify
from app.services import stock_services

bp = Blueprint('stock', __name__)


@bp.route('/stocks')
def list_stocks():
    stocks = stock_services.get_all_stocks()
    return render_template('stocks/list.html', stocks=stocks)


@bp.route('/api/stocks')
def api_stocks():
    stocks = stock_services.get_all_stocks()
    return jsonify([stock.to_dict() for stock in stocks])

# Add other stock-related routes here
