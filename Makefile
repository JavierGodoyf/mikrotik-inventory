.PHONY: install run test docker-build docker-up docker-down docker-logs backup

install:
	./install.sh

run:
	./run.sh

test:
	.venv/bin/python -m pytest -q

docker-build:
	docker compose build

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

docker-logs:
	docker compose logs -f --tail=100

backup:
	@mkdir -p backups
	tar czf "backups/mikrotik-$$(date +%Y%m%d-%H%M%S).tgz" data/devices.db data/secret.key
	@echo "Backup en backups/"
