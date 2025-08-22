.PHONY: help install dev-install build clean test lint format docker-up docker-down

help:
	@echo "Available commands:"
	@echo "  install       Install Python dependencies"
	@echo "  dev-install   Install development dependencies"
	@echo "  build         Build Rust extensions with maturin"
	@echo "  clean         Clean build artifacts"
	@echo "  test          Run tests"
	@echo "  lint          Run linters (ruff, mypy)"
	@echo "  format        Format code (black, ruff)"
	@echo "  docker-up     Start infrastructure services"
	@echo "  docker-down   Stop infrastructure services"
	@echo "  dev           Run development server"

install:
	uv pip install -e .

dev-install:
	uv pip install -e ".[dev]"
	uv pip install maturin

build:
	maturin develop --release

build-debug:
	maturin develop

clean:
	rm -rf build dist *.egg-info
	rm -rf target
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.so" -delete
	find . -type f -name "*.pyd" -delete

test:
	pytest tests/ -v --cov=platform --cov-report=term-missing

lint:
	ruff check platform/
	mypy platform/

format:
	black platform/ tests/
	ruff check --fix platform/ tests/

docker-up:
	docker-compose up -d
	@echo "Waiting for services to be healthy..."
	@sleep 5
	@echo "Services are running. Check:"
	@echo "  TimescaleDB: localhost:5432"
	@echo "  Redis: localhost:6379"
	@echo "  NATS: localhost:4222"
	@echo "  Ray Dashboard: http://localhost:8265"

docker-down:
	docker-compose down

docker-logs:
	docker-compose logs -f

# Development helpers
dev:
	uvicorn platform.api.main:app --reload --host 0.0.0.0 --port 8000

shell:
	python -m IPython

# Database management
db-init:
	python -m platform.db.init_schema

db-migrate:
	alembic upgrade head

db-rollback:
	alembic downgrade -1