SHELL := /bin/bash

.PHONY: up down logs build seed psql backend-shell test reset

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

psql:
	docker compose exec db psql -U $${POSTGRES_USER:-shift} -d $${POSTGRES_DB:-shift}

backend-shell:
	docker compose exec backend bash

reset:
	docker compose down -v
	docker compose up -d --build
