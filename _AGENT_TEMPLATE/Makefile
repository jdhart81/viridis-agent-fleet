.PHONY: help install test lint fmt clean docker-build docker-run dev health

help:
	@echo "Viridis Agent Development Commands"
	@echo "===================================="
	@echo "make install       - Install dependencies"
	@echo "make test          - Run test suite"
	@echo "make test-cov      - Run tests with coverage report"
	@echo "make lint          - Lint code (flake8)"
	@echo "make fmt           - Format code (black)"
	@echo "make fmt-check     - Check code formatting without changes"
	@echo "make clean         - Remove build artifacts and cache"
	@echo "make dev           - Run FastAPI in development mode"
	@echo "make docker-build  - Build Docker image"
	@echo "make docker-run    - Run Docker container"
	@echo "make docker-push   - Push Docker image to registry"
	@echo "make health        - Check agent health"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

test-cov:
	pytest tests/ -v --cov=src --cov-report=html --cov-report=term
	@echo "Coverage report: htmlcov/index.html"

lint:
	flake8 src adapters --max-line-length=120
	pylint src adapters || true

fmt:
	black src adapters tests

fmt-check:
	black --check src adapters tests

clean:
	rm -rf __pycache__ .pytest_cache .coverage htmlcov dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

dev:
	python -m uvicorn adapters.fastapi_server:app --reload --port 8080

mcp:
	python adapters/mcp_server.py

docker-build:
	docker build -t viridis-agent:latest .

docker-run:
	docker run -e AGENT_NAME=viridis-agent -e LOG_LEVEL=INFO \
		-p 8080:8080 viridis-agent:latest

docker-push:
	docker tag viridis-agent:latest YOUR_REGISTRY/viridis-agent:latest
	docker push YOUR_REGISTRY/viridis-agent:latest

health:
	curl -s http://localhost:8080/health | jq .

describe:
	curl -s http://localhost:8080/describe | jq .

process:
	curl -s -X POST http://localhost:8080/process \
		-H "Content-Type: application/json" \
		-d '{"test": "data"}' | jq .

# Example: test the agent with a sample payload
test-process:
	curl -s -X POST http://localhost:8080/process \
		-H "Content-Type: application/json" \
		-d '{"input": "test data"}' | jq .
