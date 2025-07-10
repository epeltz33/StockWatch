import os
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv()


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-this'

    # Handle DATABASE_URL properly for PostgreSQL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # DigitalOcean provides postgres:// but SQLAlchemy needs postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False