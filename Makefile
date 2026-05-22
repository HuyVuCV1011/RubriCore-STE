.PHONY: sync lint format typecheck test quality hooks repomix

sync:
	uv sync --dev

lint:
	uv run ruff check .

format:
	uv run ruff format .

typecheck:
	uv run pyright

test:
	uv run pytest

quality: lint typecheck test

hooks:
	uv run pre-commit run --all-files

repomix:
	npx repomix --config repomix.config.json
