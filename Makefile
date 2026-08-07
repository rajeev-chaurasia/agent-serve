GATEWAY_URL  ?= http://localhost:8000
COMPOSE_FILE ?= docker-compose.yml

.PHONY: help up down logs restart status test lint check install lock study demo smoke clean

# Default target — show available targets
help:
	@printf "\nUsage: make <target>\n\n"
	@printf "  %-12s %s\n" "up"      "Start all services in the background (docker compose up -d)"
	@printf "  %-12s %s\n" "down"    "Stop and remove containers (docker compose down)"
	@printf "  %-12s %s\n" "logs"    "Tail logs from all services"
	@printf "  %-12s %s\n" "restart" "Restart the gateway service"
	@printf "  %-12s %s\n" "status"  "Check gateway /status endpoint"
	@printf "\n"
	@printf "  %-12s %s\n" "test"    "Run the full pytest suite"
	@printf "  %-12s %s\n" "lint"    "Run ruff on gateway/src"
	@printf "  %-12s %s\n" "check"   "lint + test in sequence"
	@printf "\n"
	@printf "  %-12s %s\n" "install" "Install all dependencies including dev (uv sync)"
	@printf "  %-12s %s\n" "lock"    "Regenerate the lock file (uv lock)"
	@printf "\n"
	@printf "  %-12s %s\n" "study"   "Run the full load study"
	@printf "\n"
	@printf "  %-12s %s\n" "demo"    "Run 5 demo agent sessions"
	@printf "  %-12s %s\n" "smoke"   "Hit /healthz and /v1/models to verify the stack is up"
	@printf "\n"
	@printf "  %-12s %s\n" "clean"   "Remove __pycache__ and .pytest_cache dirs"
	@printf "\nOverrides: GATEWAY_URL=$(GATEWAY_URL)  COMPOSE_FILE=$(COMPOSE_FILE)\n\n"

# Start all services detached
up:
	docker compose -f $(COMPOSE_FILE) up -d

# Stop and remove containers
down:
	docker compose -f $(COMPOSE_FILE) down

# Follow logs for all services
logs:
	docker compose -f $(COMPOSE_FILE) logs -f

# Bounce just the gateway
restart:
	docker compose -f $(COMPOSE_FILE) restart gateway

# Pretty-print the gateway status response
status:
	curl -s $(GATEWAY_URL)/status | python3 -m json.tool

# Run the full test suite
test:
	cd gateway && uv run pytest tests/ -v

# Lint gateway source with ruff
lint:
	cd gateway && uv run ruff check src/

# Lint then test
check: lint test

# Install all deps including dev extras
install:
	cd gateway && uv sync

# Regenerate the lock file
lock:
	cd gateway && uv lock

# Run the full load study
study:
	bash studies/run_load_study.sh

# Spin up 5 demo agent sessions
demo:
	python3 -m demo_agent.run_session --sessions 5

# Quick stack check: healthz then model list
smoke:
	@curl -sf $(GATEWAY_URL)/healthz \
		&& echo "healthz OK" \
		&& curl -sf $(GATEWAY_URL)/v1/models | python3 -m json.tool

# Remove bytecode and test cache dirs
clean:
	find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name '.pytest_cache' -exec rm -rf {} + 2>/dev/null || true
