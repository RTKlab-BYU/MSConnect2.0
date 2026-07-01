.PHONY: build up down logs migrate test lint shell createsuperuser ingest

build:
	docker compose build

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

migrate:
	docker compose run --rm web python manage.py migrate

test:
	docker compose run --rm web python manage.py test

lint:
	docker compose run --rm web ruff check .

shell:
	docker compose run --rm web python manage.py shell

createsuperuser:
	docker compose run --rm web python manage.py createsuperuser

ingest:
	docker compose run --rm ingest python manage.py ingest_raw_files --recursive

