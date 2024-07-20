from flask import Blueprint, render_template
from flask_login import login_required

bp = Blueprint('main', __name__)


@bp.route('/dashboard')
@login_required
def dashboard():
    return render_template('main/dashboard.html')
