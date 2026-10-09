# LotNeeti

LotNeeti is an IPO planning and operations product for managing investors/demat accounts, bank balances, IPO selection, deterministic Retail/sHNI planning, application/allotment tracking, exports and realized P&L.

The approved product and Planner v2 specifications live under `docs/reference_md/` with original DOCX sources under `docs/reference/`.

Development is organized by `docs/SPRINT_PLAN.md` and the authoritative feature backlog. Autonomous Codex progress is recorded in `docs/exec-plans/STATUS.md`.

Do not add real PANs, bank details, UPI identifiers, secrets or production credentials to this repository.

## Local development

Prerequisites: Python 3.12+, Node.js 22+ and Docker with Compose.

```bash
cp .env.example .env
python3 -m venv .venv
.venv/bin/python -m pip install -e 'backend[dev]'
docker compose up -d postgres redis
.venv/bin/python backend/manage.py migrate
.venv/bin/python backend/manage.py runserver
```

The versioned API health endpoint is available at
`http://127.0.0.1:8000/api/v1/health/`.

In another terminal, start the web app:

```bash
cd web
npm install
npm run dev
```

The web app reads `API_BASE_URL` from the environment (default:
`http://127.0.0.1:8000/api/v1`) and shows the API connection state on its home page.
Local sign-in links are written to the backend terminal by Django's console email backend.
Production settings require SMTP configuration supplied through environment variables.

For the founder staff account, run `createsuperuser` and then
`enroll_founder_totp <email>` with `backend/manage.py`. Add the one-time URI to an
authenticator app and sign in at `/admin/` using the password and six-digit code.

Backend verification:

```bash
.venv/bin/ruff check backend
.venv/bin/ruff format --check backend
.venv/bin/python -m pytest backend
.venv/bin/python backend/manage.py check --settings=config.settings.test
.venv/bin/python backend/manage.py makemigrations --check --dry-run --settings=config.settings.test
```

After installing backend and web dependencies, run every Sprint 0 gate with
`bash scripts/check.sh`. CI also starts PostgreSQL and Redis and applies migrations.
