# Makefile for MeshAdminRevertIt

.PHONY: help install install-dev test lint format clean build docs

# Default target
help:
	@echo "Available targets:"
	@echo "  install      - Install package for production use"
	@echo "  install-dev  - Install package with development dependencies"
	@echo "  test         - Run test suite"
	@echo "  test-cov     - Run test suite with coverage"
	@echo "  lint         - Run code linting (flake8, mypy)"
	@echo "  format       - Format code (black, isort)"
	@echo "  format-check - Check code formatting without changes"
	@echo "  clean        - Clean build artifacts"
	@echo "  build        - Build distribution packages"
	@echo "  docs         - Build documentation"
	@echo "  system-install - Install system-wide (requires sudo)"
	@echo "  system-uninstall - Uninstall system-wide (requires sudo)"

# Installation targets
install:
	pip3 install -e .

install-dev:
	pip3 install -e .
	pip3 install -r requirements-dev.txt

# Testing targets
test:
	python3 -m pytest tests/ -v

test-cov:
	python3 -m pytest tests/ -v --cov=meshadmin_revertit --cov-report=html --cov-report=term

# Code quality targets
lint:
	flake8 src/meshadmin_revertit tests/
	mypy src/meshadmin_revertit

format:
	black src/meshadmin_revertit tests/
	isort src/meshadmin_revertit tests/

format-check:
	black --check src/meshadmin_revertit tests/
	isort --check-only src/meshadmin_revertit tests/

# Build targets
clean:
	rm -rf build/
	rm -rf dist/
	rm -rf src/*.egg-info/
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build: clean
	python3 setup.py sdist bdist_wheel

# Documentation targets
docs:
	@echo "Documentation target not yet implemented"
	@echo "See README.md for current documentation"

# System installation targets (require sudo)
system-install:
	@echo "Installing MeshAdminRevertIt system-wide..."
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: This target must be run with sudo"; \
		exit 1; \
	fi
	./scripts/install.sh

system-uninstall:
	@echo "Uninstalling MeshAdminRevertIt system-wide..."
	@if [ "$$(id -u)" != "0" ]; then \
		echo "Error: This target must be run with sudo"; \
		exit 1; \
	fi
	./scripts/uninstall.sh

# Development workflow targets
dev-setup: install-dev
	@echo "Development environment setup complete"
	@echo "Run 'make test' to verify installation"

dev-test: format-check lint test
	@echo "All development checks passed"

# CI/CD targets
ci: format-check lint test-cov
	@echo "CI pipeline completed successfully"