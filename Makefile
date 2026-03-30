.PHONY: up down simulate logs test dev db-reset clean

COMPOSE := docker compose -f infra/docker-compose.yml

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

simulate:
	$(COMPOSE) --profile simulate up simulator

logs:
	$(COMPOSE) logs -f

test:
	cd backend && python -m pytest ../tests -v

dev:
	cd backend && uvicorn swarmchain.main:app --reload --port 8000

db-reset:
	$(COMPOSE) exec postgres dropdb -U swarmchain swarmchain --if-exists
	$(COMPOSE) exec postgres createdb -U swarmchain swarmchain
	@echo "Database reset complete"

clean:
	$(COMPOSE) down -v --remove-orphans
	@echo "Volumes removed"
