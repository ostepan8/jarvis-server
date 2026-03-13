.PHONY: install test docker-build docker-up docker-down docker-logs docker-shell docker-clean docker-mongo

install:
	pip install -r requirements.txt

test:
	pytest -vv

# ── Docker ──────────────────────────────────────────────────────────
docker-build:
	docker compose build

docker-up:
	docker compose up -d

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f jarvis

docker-shell:
	docker compose exec jarvis bash

docker-clean:
	docker compose down -v --rmi local

docker-mongo:
	docker compose --profile mongo up -d
