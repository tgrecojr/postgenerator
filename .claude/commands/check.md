Run the full local quality gate for this project and fix anything that fails:

1. `.venv/bin/ruff check . && .venv/bin/ruff format --check .`
2. `.venv/bin/mypy`
3. `.venv/bin/python -m pytest -q`

Then confirm no secrets or personal data are staged: `git diff --cached --name-only` must not include the env file or anything under `data/`.
