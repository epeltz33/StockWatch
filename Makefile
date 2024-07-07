.PHONY: run db-init db-migrate db-upgrade

run:
	python dev_server.py

db-init:
	flask db init

db-migrate:
	flask db migrate -m "Migration"

db-upgrade:
	flask db upgrade

setup-db: db-init db-migrate db-upgrade

all: setup-db run