from models import User, Stock, Watchlist
from dotenv import load_dotenv
import os
from flask import Flask, redirect
from flask_login import LoginManager
from flask_sqlalchemy import SQLAlchemy
from dash_app import create_dash_app

# Load environment variables
load_dotenv()

# Initialize Flask extensions
db = SQLAlchemy()
login_manager = LoginManager()


def create_app():
    # Flask setup
    app = Flask(__name__)

    # Configure the Flask app
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'a_default_secret_key')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
        'DATABASE_URL', 'sqlite:///your_database.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Import and register blueprints
    from auth.routes import auth_bp
    from main.routes import main_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)

    # Create Dash app
    dash_app = create_dash_app(app)

    @app.route('/')
    def index():
        return redirect('/dash/')

    # Create database tables
    with app.app_context():
        db.create_all()

    return app


# Create the Flask app
app = create_app()

# Import models after creating db to avoid circular imports


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


if __name__ == '__main__':
    app.run(debug=True)
