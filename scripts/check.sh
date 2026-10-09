#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

python_cmd="${LOTNEETI_PYTHON:-python3}"
if [[ -z "${LOTNEETI_PYTHON:-}" && -x .venv/bin/python ]]; then
  python_cmd=.venv/bin/python
fi

"$python_cmd" -m ruff check backend
"$python_cmd" -m ruff format --check backend
"$python_cmd" -m pytest backend
"$python_cmd" scripts/check_planner_matrix.py
"$python_cmd" backend/manage.py check --settings=config.settings.test
"$python_cmd" backend/manage.py makemigrations --check --dry-run --settings=config.settings.test

cd web
npm run lint
npm run typecheck
npm run test
npm run build

cd ../mobile
npm run test
npm run typecheck
VITE_LOTNEETI_WEB_URL=https://beta.example.invalid npm run android:sync
