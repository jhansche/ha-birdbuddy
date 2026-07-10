SHELL = /bin/bash -xe

# Create the venv with the interpreter pinned in .python-version (3.14.4 via
# pyenv) and install the dev/test toolchain, which pulls the pinned Home
# Assistant (see requirements-dev.txt).
.PHONY: deps
deps:
	@echo "Setting up the Python environment..."
	python3 -m venv venv
	venv/bin/pip install -U pip
	venv/bin/pip install -U -r requirements-dev.txt
	@echo "Dependencies installed."

# Auto-fix formatting and lint issues.
.PHONY: format
format:
	venv/bin/ruff format
	venv/bin/ruff check --fix

.PHONY: lint
lint:
	@echo "Running format check, lint, and typecheck..."
	venv/bin/ruff check
	venv/bin/ruff format --check --diff
	npx -y markdownlint-cli2 "*.md"
	venv/bin/pyright --warnings

.PHONY: test
test:
	venv/bin/pytest

# Everything run locally before pushing: lint, type check, and the tests.
.PHONY: check
check: lint
	@echo "Running the full test suite..."
	venv/bin/pytest
	@echo "All checks passed."

.PHONY: clean
clean:
	@echo "Cleaning up..."
	rm -rf **/__pycache__
	rm -rf .pytest_cache .ruff_cache htmlcov
	rm -f .coverage .coverage.* junit.xml
	rm -rf venv
	@echo "Cleanup complete."
