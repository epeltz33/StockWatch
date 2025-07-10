from flask import Blueprint, render_template
from flask_login import current_user, login_required

bp = Blueprint('main', __name__)


@bp.route('/')
def landing():
    return render_template('main/landing.html')


@bp.route('/dashboard')
@login_required
def dashboard():
    dash_url = '/dash/'
    return render_template('main/dashboard.html', dash_url=dash_url, user=current_user)