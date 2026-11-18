# TURFOS — Smart Turf Management System

Multi-tenant turf management SaaS + public turf discovery for Bangladesh.
Django / DRF / MySQL-compatible database (XAMPP MariaDB or MySQL 8) backend, React / TypeScript / Tailwind frontend.

- Architecture, data model, security plan and roadmap: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## What works today

| Area | Features |
|---|---|
| Public site | Home, Explore (search, district/area/type/amenity/price filters, sort, pagination), turf page with live slot availability and prices, booking request without an account, booking status lookup, QR code per turf, "List your turf" application |
| Login | One login for Super Admin, owners and managers; server decides where you land; lockout after 5 failed attempts |
| Super Admin (`/admin`) | Platform overview, application pipeline (contact / reject / approve → creates turf + owner login), turf list with suspend/archive, list and feature toggles, add turf manually |
| Workspace (`/workspace`) | Dashboard with collections chart, bookings day board + searchable list, create / reschedule / confirm / cancel / no-show, payments and refunds with dues, customers, maintenance blocks, fields, opening hours (overnight supported), peak/weekend/special-date pricing, expenses, reports + Excel export, managers, public profile settings, change password |
| Safety | No double bookings (row lock per field, proven by a concurrent test), tenant isolation (other turfs' IDs → 404), owner-only actions enforced in the API, suspended turfs are read-only, public serializers are whitelists |

Not built yet (roadmap phases 14–16, 25–26): subscriptions/plans/invoices, email + Celery reminders, theme customization studio, gallery image uploads, MFA, audit log, Docker production images.

Tests: 34 backend (`pytest`) + 9 frontend (`vitest`).

## Repository layout

```
backend/    Django project (config/, apps/, tests/)
  apps/locations     divisions, 64 districts, city areas (seeded by migration)
  apps/turfs         turf (tenant), memberships, fields, hours, pricing engine, public + setup APIs
  apps/bookings      customers, bookings, payments, maintenance, dashboard, reports
  apps/applications  "list your turf" applications + Super Admin API
  apps/expenses      expenses
frontend/   React + Vite app (features/public, auth, admin, workspace)
docs/       architecture and guides
```

## Local development with XAMPP (Windows)

### 1. Database (XAMPP MariaDB)

Start **MySQL** in the XAMPP Control Panel. Then create the database and app user once
(XAMPP's `root` has no password by default; pick your own password for `turfos`):

```powershell
C:\xampp\mysql\bin\mysql.exe -h localhost -u root -e "CREATE DATABASE IF NOT EXISTS turfos CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER IF NOT EXISTS 'turfos'@'localhost' IDENTIFIED BY 'your-password'; CREATE USER IF NOT EXISTS 'turfos'@'::1' IDENTIFIED BY 'your-password'; CREATE USER IF NOT EXISTS 'turfos'@'127.0.0.1' IDENTIFIED BY 'your-password'; GRANT ALL ON turfos.* TO 'turfos'@'localhost'; GRANT ALL ON turfos.* TO 'turfos'@'::1'; GRANT ALL ON turfos.* TO 'turfos'@'127.0.0.1'; GRANT ALL ON test_turfos.* TO 'turfos'@'localhost'; GRANT ALL ON test_turfos.* TO 'turfos'@'::1'; GRANT ALL ON test_turfos.* TO 'turfos'@'127.0.0.1'; FLUSH PRIVILEGES;"
```

`test_turfos` is pytest's temporary database. You can browse the data in phpMyAdmin at http://localhost/phpmyadmin.

> If another MySQL server is also listening on `127.0.0.1:3306`, connect to XAMPP through `[::1]` as in `.env.example`.

MySQL 8 also works (`scripts/local_mysql.py` and `scripts/mysql_setup_sql.py` set up a project-local MySQL 8 server).

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
.venv\Scripts\python manage.py seed_demo        # optional demo data
.venv\Scripts\python manage.py createsuperuser  # your own Super Admin
.venv\Scripts\python manage.py runserver 127.0.0.1:8010
```

The API runs on **port 8010** (8000 is often taken by other local projects).

- Health check: http://127.0.0.1:8010/api/health/
- API docs (DEBUG only): http://127.0.0.1:8010/api/docs/

`createsuperuser` creates the TURFOS **Super Admin**.

#### Demo logins (`seed_demo`, development only)

| Role | Email | Password |
|---|---|---|
| Super Admin | admin@turfos.local | TurfosAdmin#2026 |
| Owner (Green Arena Gulshan) | owner@turfos.local | TurfosOwner#2026 |
| Owner (Mirpur Kickoff Zone) | mirpur.owner@turfos.local | TurfosOwner#2026 |
| Manager (Green Arena Gulshan) | manager@turfos.local | TurfosManager#2026 |

The other demo owners (uttara.owner@, ctg.owner@) use the owner password too. `seed_demo --reset` rebuilds the demo data.
The command refuses to run when `DJANGO_DEBUG` is false.

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

Backend tests need the database running (XAMPP MySQL). They check that it is MySQL 8+ or MariaDB 10.6+ with InnoDB,
utf8mb4 and strict SQL mode, because booking safety relies on InnoDB row locks.

## Settings modules

| Module | Used by |
|---|---|
| `config.settings.dev` | `manage.py` default |
| `config.settings.test` | pytest (fast hasher, eager Celery, in-memory email) |
| `config.settings.prod` | `wsgi.py` / `asgi.py` (HTTPS, secure cookies, HSTS, S3 storage, Sentry; requires Redis `CACHE_URL`) |
