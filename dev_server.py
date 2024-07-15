import frontend.callbacks
from app import create_app, db
from frontend.layout import create_layout
from dash import Dash


# Flask app
app = create_app()

# Make sure db is created
with app.pp_context():
    db.create_all()

# Create Dash app and intergrate with Flask backend
dash_app = Dash(__name__, server=app, url_base_pathname='/dash/')
dash_app.layout = create_layout()

# Import and register Dash callbacks

if __name__ == '__main__':
    app.run(debug=True, port=5000)
