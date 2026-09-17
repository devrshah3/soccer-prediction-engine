.PHONY: install format lint typecheck test smoke api dashboard clean

install:
	python3.11 -m venv .venv
	.venv/bin/pip install -U pip
	.venv/bin/pip install -e '.[dev]'

format:
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

lint:
	.venv/bin/ruff format --check .
	.venv/bin/ruff check .

typecheck:
	.venv/bin/mypy src

test:
	.venv/bin/pytest

smoke:
	.venv/bin/soccer-engine demo

api:
	.venv/bin/soccer-engine serve-api

dashboard:
	.venv/bin/soccer-engine dashboard

clean:
	find src tests -type d -name __pycache__ -prune -exec rm -r {} +

