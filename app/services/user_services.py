from app.models import User
from app import db
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash


def get_all_users():
    return User.query.all()


def get_user_by_id(user_id):
    return User.query.get(user_id)


def get_user_by_username(username):
    return User.query.filter_by(username=username).first()


def create_user(username, email, password):
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
        return user
    except IntegrityError:
        db.session.rollback()
        return None


def update_user(user_id, username=None, email=None):
    user = get_user_by_id(user_id)
    if user:
        if username:
            user.username = username
        if email:
            user.email = email
        try:
            db.session.commit()
            return user
        except IntegrityError:
            db.session.rollback()
            return None
    return None


def delete_user(user_id):
    user = get_user_by_id(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
        return True
    return False


def authenticate_user(username, password):
    user = get_user_by_username(username)
    if user and check_password_hash(user.password_hash, password):
        return user
    return None

# more user-related services as needed
