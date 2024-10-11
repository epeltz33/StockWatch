from celery import Celery

app = Celery('stock_updater',
            broker='redis://localhost:6379/0',
            backend='redis://localhost:6379/0')

app.conf.beat_schedule = {
    'update-stocks-every-hour': {
        'task': 'tasks.update_watchlist_stocks',
        'schedule': 3600.0,  # Run every hour
    },
}