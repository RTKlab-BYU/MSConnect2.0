.PHONY: build up down logs migrate test lint shell createsuperuser watcher processor deploy-tag

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

watcher:
	docker compose run --rm watcher python manage.py run_watcher_agent --once --match-run-by-name

processor:
	docker compose run --rm processor python manage.py run_processor_agent --once

deploy-tag:
	docker compose pull
	docker compose up -d
