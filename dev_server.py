
from flask import redirect
import frontend.callbacks
from app import server  # Import the Flask app
from frontend.layout import create_layout
from dash import Dash

# Create Dash app and integrate it with the Flask app
app = Dash(__name__, server=server, url_base_pathname='/dash/')
app.layout = create_layout()

# Register callbacks


@server.route('/')
def index():
    return redirect('/dash/')


if __name__ == '__main__':
    server.run(debug=True, port=5000)
