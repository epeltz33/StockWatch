from flask import Blueprint, render_template, request, jsonify, abort, redirect, url_for, flash
from app.services import user_services
from flask_login import login_user, logout_user, login_required, current_user

bp = Blueprint('user', __name__, url_prefix='/users')


@bp.route('/')
@login_required
def list_users():
    users = user_services.get_all_users()
    return render_template('users/list.html', users=users)


@bp.route('/<int:user_id>')
@login_required
def user_detail(user_id):
    user = user_services.get_user_by_id(user_id)
    if not user:
        abort(404)
    return render_template('users/detail.html', user=user)


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        user = user_services.create_user(username, email, password)
        if user:
            flash('Registration successful. Please log in.', 'success')
            # redirect to login not dashboard
            return redirect(url_for('auth.login'))
        else:
            flash('Registration failed. Username may already be in use.', 'error')
    return render_template('users/register.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = user_services.authenticate_user(username, password)
        if user:
            login_user(user)
            flash('Logged in successfully.', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('users/login.html')


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('main.index'))


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        user = user_services.update_user(current_user.id, username, email)
        if user:
            flash('Profile updated successfully.', 'success')
        else:
            flash('Profile update failed.', 'error')
    return render_template('users/profile.html', user=current_user)


@bp.route('/api/users')
@login_required
def api_list_users():
    users = user_services.get_all_users()
    return jsonify([user.to_dict() for user in users])


@bp.route('/api/users/<int:user_id>')
@login_required
def api_user_detail(user_id):
    user = user_services.get_user_by_id(user_id)
    if not user:
        abort(404)
    return jsonify(user.to_dict())


@bp.route('/api/users/<int:user_id>', methods=['DELETE'])
@login_required
def delete_user(user_id):
    if user_services.delete_user(user_id):
        return jsonify({'message': 'User deleted'}), 200
    else:
        return jsonify({'error': 'User not found'}), 404
