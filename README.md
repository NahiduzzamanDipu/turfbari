# TURFOS — Smart Turf Management System

Multi-tenant turf management SaaS + public turf discovery for Bangladesh.
Django / DRF / MySQL 8 / Celery / Redis backend, React / TypeScript / Tailwind frontend.

- Architecture, data model, security plan and roadmap: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Status

| Phase | State |
|---|---|
| 1. Repository inspection & architecture | ✅ done |
| 2. Project setup (Django, MySQL, React shell) | ✅ done — 17 backend + 9 frontend tests pass |
| 3+ | not started |

## Repository layout

```
backend/    Django project (config/, apps/, tests/)
frontend/   React + Vite app
docs/       architecture and guides
docker-compose.yml   optional: MySQL 8.4, Redis 7, Mailpit
.env.example         every setting, no real secrets
```

## Local development (Windows)

### 1. One-time: install MySQL 8

Install MySQL Community Server 8.4 (LTS). With winget, in an **Administrator** PowerShell:

```powershell
winget install -e --id Oracle.MySQL
```

Then pick **one** of the two ways to run it.

#### Option A — project-local server (default for this repo, no admin rights)

Data lives in `.mysql/` (git-ignored); the server listens on 127.0.0.1:3306 only. After creating `.env` (step 2):

```powershell
backend\.venv\Scripts\python scripts\local_mysql.py init
```

This creates the data folder, sets a random root password (saved to `.env` as `MYSQL_ROOT_PASSWORD`)
and creates the `turfos` database and user. Each time you work on TURFOS, start the server in its own terminal:

```powershell
backend\.venv\Scripts\python scripts\local_mysql.py start
```

Stop it with Ctrl+C, or from another terminal with `local_mysql.py stop`; `local_mysql.py status` shows whether it's running.
If MySQL is installed somewhere else, set `MYSQL_BASEDIR` to that folder.

#### Option B — Windows service

The winget/MSI install only copies files. Configure the server once with **MySQL Configurator**
(Start menu → "MySQL Configurator", or `C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql_configurator.exe`):
choose *Development Computer*, keep port 3306, set a root password, and leave "Configure MySQL Server as a Windows Service" ticked.

Then, after creating `.env` (step 2), create the TURFOS database and app user from the repository root.
It reads `MYSQL_DATABASE`, `MYSQL_USER` and `MYSQL_PASSWORD` from `.env` and prompts for the root password:

```powershell
backend\.venv\Scripts\python scripts\mysql_setup_sql.py | & "C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe" -u root -p
```

It grants the user access to `turfos` and `test_turfos` (pytest's temporary database) for both `localhost` and `127.0.0.1`, and is safe to re-run.

Alternative: with Docker installed, `docker compose up -d` starts MySQL, Redis and Mailpit with matching settings.

### 2. Configure environment

```powershell
copy .env.example .env
```

Edit `.env`: set `DJANGO_SECRET_KEY` and use the same password in both `MYSQL_PASSWORD` and `DATABASE_URL`.

### 3. Backend

```powershell
cd backend
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements\dev.txt
.venv\Scripts\python manage.py migrate
.venv\Scripts\python manage.py createsuperuser
.venv\Scripts\python manage.py runserver 127.0.0.1:8010
```

The API runs on **port 8010** (8000 is often taken by other local projects).

- Health check: http://127.0.0.1:8010/api/health/
- API docs (DEBUG only): http://127.0.0.1:8010/api/docs/

`createsuperuser` creates the TURFOS **Super Admin**.

### 4. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Vite proxies `/api` and `/media` to `127.0.0.1:8010`
(override with the `VITE_BACKEND_URL` environment variable).

### 5. Redis and background workers (needed from Phase 16 on)

Celery (subscription reminders, emails) needs Redis. On Windows use Docker
(`docker compose up -d redis mailpit`), Memurai (a Redis-compatible Windows service), or Redis inside WSL.
Until then, leave `CACHE_URL` empty and Django uses an in-memory cache.

```powershell
cd backend
.venv\Scripts\celery -A config worker -l info --pool=solo
.venv\Scripts\celery -A config beat -l info
```

`--pool=solo` is required on Windows; Linux production uses the default prefork pool.

## Tests and checks

```powershell
cd backend
.venv\Scripts\pytest
.venv\Scripts\ruff check .
.venv\Scripts\python manage.py check --deploy --settings=config.settings.prod

cd ..\frontend
npm test
npm run build
```

Backend tests need MySQL running. They check that the database is MySQL 8 with InnoDB,
utf8mb4 and strict SQL mode, because booking safety relies on InnoDB row locks.

## Settings modules

| Module | Used by |
|---|---|
| `config.settings.dev` | `manage.py` default |
| `config.settings.test` | pytest (fast hasher, eager Celery, in-memory email) |
| `config.settings.prod` | `wsgi.py` / `asgi.py` (HTTPS, secure cookies, HSTS, S3 storage, Sentry; requires Redis `CACHE_URL`) |
