.PHONY: build up down logs migrate test lint frontend-lint ci-local install-hooks shell createsuperuser watcher processor diann-build diann-up diann-logs cleanup-state tagged-fixture tagged-process tagged-verify archive capacity verify-archives operations-report deploy-tag

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

frontend-lint:
	cd frontend && npm run lint

ci-local:
	ruff check .
	cd frontend && npm run lint
	docker compose build web
	docker compose run --rm --no-deps web python manage.py check
	docker compose run --rm --no-deps web python manage.py makemigrations --check --dry-run
	docker compose run --rm --no-deps web python manage.py test

install-hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-push

shell:
	docker compose run --rm web python manage.py shell

createsuperuser:
	docker compose run --rm web python manage.py createsuperuser

watcher:
	docker compose run --rm watcher python manage.py run_watcher_agent --once --match-run-by-name

processor:
	docker compose run --rm processor python manage.py run_processor_agent --once

diann-build:
	docker compose --profile engines build processor-diann

diann-up:
	docker compose --profile engines up -d --build web nginx watcher processor-diann

cleanup-state:
	docker compose exec web python manage.py cleanup_processing_state

diann-logs:
	docker compose logs -f web nginx watcher processor-diann

tagged-fixture:
	docker compose exec web python manage.py create_tagged_operations_fixture --code-prefix OPS-TAGGED

tagged-process:
	for i in $$(seq 1 12); do docker compose run --rm processor python manage.py run_processor_agent --once; done

tagged-verify:
	docker compose exec web python manage.py verify_tagged_operations_fixture --code-prefix OPS-TAGGED

archive:
	docker compose run --rm archive-worker python manage.py archive_raw_files --limit 50

capacity:
	docker compose exec web python manage.py storage_capacity_report

verify-archives:
	docker compose exec web python manage.py verify_archives --restore-test

operations-report:
	docker compose exec web python manage.py generate_operations_report --output /app/data/operations-report.txt

deploy-tag:
	docker compose pull
	docker compose up -d
