from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from app.services.user_services import create_user, get_user_by_email, verify_password

auth_bp = Blueprint('auth', __name__, url_prefix='/auth',
                    template_folder='../../templates')


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = get_user_by_email(email)
        if user and verify_password(user, password):
            login_user(user)
            flash('Login successful.')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Login failed. Check your email and password.')
    return render_template('login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        user = create_user(username, email, password)
        if user:
            flash('Congratulations, you are now a registered user!')
            return redirect(url_for('auth.login'))
        else:
            flash('Registration failed. Please try again.')
    return render_template('register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('auth.login'))
