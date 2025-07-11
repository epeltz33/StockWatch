class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-this'

    # Handle DATABASE_URL properly for PostgreSQL
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        # DigitalOcean provides postgres:// but SQLAlchemy needs postgresql://
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)

        # Add connection pool settings for DigitalOcean
        SQLALCHEMY_DATABASE_URI = database_url
        SQLALCHEMY_ENGINE_OPTIONS = {
            'pool_pre_ping': True,
            'pool_recycle': 300,
            'connect_args': {
                'sslmode': 'require',
                'connect_timeout': 10
            }
        }
    else:
        SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'app.db')
        SQLALCHEMY_ENGINE_OPTIONS = {}

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Add explicit schema configuration
    # This can help with permission issues
    SQLALCHEMY_SCHEMA = os.environ.get('DB_SCHEMA', 'public')