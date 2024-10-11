from flask import Blueprint, render_template, url_for
from flask_login import current_user, login_required
from app import cache


bp = Blueprint('main', __name__)


@bp.route('/')
def landing():
    return render_template('main/landing.html')


@bp.route('/dashboard')
@login_required
def dashboard():
    # Fetch user's stocks from the database or user profile
    # For now,  placeholder list
    user_stocks = ['AAPL', 'GOOGL']  # Replace with actual user stocks later

    user_data = {
        'name': current_user.username,
        'stocks': user_stocks
    }
    cache.set('user_data', user_data)

    dash_url = '/dash/'
    return render_template('main/dashboard.html', dash_url=dash_url, user=current_user)
