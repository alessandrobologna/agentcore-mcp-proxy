.PHONY: help test lint format quality

.DEFAULT_GOAL := help

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

PYTHON_TEST_VERSION ?= 3.13

test: ## Run tests, linting, and formatting checks
	uvx ruff check .
	uvx ruff format --check
	uvx --python $(PYTHON_TEST_VERSION) --with .[dev] --with .[server] pytest tests/

lint: ## Run ruff lint checks
	uvx ruff check .

format: ## Format code with ruff
	uvx ruff format

quality: lint ## Run quality checks (lint + formatting validation)
	uvx ruff format --check
