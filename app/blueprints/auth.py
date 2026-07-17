from urllib.parse import urlparse

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db, limiter
from app.forms import LoginForm, RegistrationForm
from app.models import User

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        username = form.username.data.strip()

        if User.query.filter(db.func.lower(User.email) == email).first():
            form.email.errors.append("Email address already in use.")
        elif User.query.filter_by(username=username).first():
            form.username.errors.append("Username already taken.")
        else:
            new_user = User(username=username, email=email)
            new_user.set_password(form.password.data)
            db.session.add(new_user)
            db.session.commit()

            flash("Congratulations, you are now a registered user!", "success")
            return redirect(url_for("auth.login"))

    return render_template("auth/register.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        # Case-insensitive match so accounts created before emails were
        # normalized to lowercase can still log in
        email = form.email.data.strip().lower()
        user = User.query.filter(db.func.lower(User.email) == email).first()

        if user and user.check_password(form.password.data):
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get("next")
            # Only allow relative redirect targets to prevent open redirects
            if not next_page or urlparse(next_page).netloc != "":
                next_page = url_for("main.dashboard")
            flash("Logged in successfully.", "success")
            return redirect(next_page)
        flash("Invalid email or password", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("auth.login"))
