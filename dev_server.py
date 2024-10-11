from app import create_app
from pickler import get_stock_data, check_cache
from flask import jsonify
app = create_app()
@app.route('/stock/<ticker>')
def stock_data(ticker):
    data = get_stock_data(ticker)
    return jsonify(data)


if __name__ == '__main__':
    print("First call (should be a cache miss)")
    apple = get_stock_data("AAPL")

    print("\nChecking cache status")
    print(check_cache("AAPL"))

    print("\nSecond call (should be a cache hit)")
    apple = get_stock_data("AAPL")
    print(f"Apple: {apple}")
    app.run(debug=True)
