# Protrixplus S0 — developer entry points.
# Windows without `make`: see dev.ps1 or run the underlying commands from README.md.

COMPOSE := docker compose -f infra/docker-compose.yml --env-file infra/.env
PY := python

.PHONY: help env up down logs ps reset health simulate \
        install lint typecheck test test-unit test-integration e2e build ci-local

help:
	@echo "make env         - copy infra/.env.example -> infra/.env"
	@echo "make up           - build + start the whole stack (detached)"
	@echo "make down          - stop the stack"
	@echo "make reset         - stop + wipe volumes"
	@echo "make health        - curl every /health"
	@echo "make simulate      - post one mock signal"
	@echo "make install       - install all python + node dev deps locally"
	@echo "make lint          - ruff + eslint across all packages"
	@echo "make typecheck     - mypy + tsc"
	@echo "make test-unit     - contracts/api/worker/web unit tests"
	@echo "make test-integration - integration suite against a running stack"
	@echo "make e2e           - Playwright e2e against a running stack"
	@echo "make build         - production build checks (next build)"
	@echo "make ci-local      - lint + typecheck + unit tests (no docker)"

env:
	cp -n infra/.env.example infra/.env || true

up: env
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

health:
	curl -fsS localhost:8000/health && echo
	curl -fsS localhost:8100/health && echo
	curl -fsS -o /dev/null -w "web /login -> %{http_code}\n" localhost:3000/login

simulate:
	$(PY) infra/scripts/simulate_signal.py

install:
	$(PY) -m pip install -e "contracts/python[dev]" -r api/requirements-dev.txt -r worker/requirements-dev.txt -r tests/requirements.txt
	cd web && npm ci

lint:
	ruff check contracts/python api worker tests infra/scripts
	ruff format --check contracts/python api worker tests infra/scripts
	cd web && npm run lint

typecheck:
	mypy contracts/python/protrix_contracts
	cd api && mypy app
	cd worker && mypy app
	cd web && npm run typecheck

test-unit:
	pytest contracts/python -q
	cd api && pytest -q
	cd worker && pytest -q
	cd web && npm test

test-integration:
	pytest tests -q

e2e:
	cd web && npx playwright test

build:
	cd web && npm run build

ci-local: lint typecheck test-unit
	@echo "local CI (no docker) passed"
