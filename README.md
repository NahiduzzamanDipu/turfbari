# TurfBari — Smart Turf Management System

Multi-tenant turf management SaaS + public turf discovery for Bangladesh.
Django / DRF / MySQL-compatible database (XAMPP MariaDB or MySQL 8) backend, React / TypeScript / Tailwind frontend.

- Architecture, data model, security plan and roadmap: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## What works today

| Area | Features |
|---|---|
| Public site | Home, Explore (search, district/area/type/amenity/price filters, sort, pagination), **near me**: the browser detects the player's location (with permission) and lists the closest turfs first with distance, Google Maps pin on every card and a Directions button on the turf page, turf page with live slot availability and prices, booking request without an account, booking status lookup, QR code per turf, "List your turf" application |
| Login | One login for Super Admin, owners and managers; server decides where you land; lockout after 5 failed attempts; **My account** page (sidebar, bottom) where the Super Admin, owners and managers change their own password |
| Super Admin (`/admin`) | Platform overview, application pipeline (contact / reject / approve → creates turf + owner login), turf list with suspend/archive, list and feature toggles, add turf manually |
| Workspace (`/workspace`) | Dashboard with collections chart, bookings day board + searchable list, create / reschedule / confirm / cancel / no-show, payments and refunds with dues, customers, maintenance blocks, fields, opening hours (overnight supported), peak/weekend/special-date pricing, expenses, reports + Excel export, managers, public profile settings incl. Google Maps link and map pin (paste a full Maps link, type coordinates, or use the current location) |
| Book a slot (`/workspace/book`) | Owner/manager slot board per field and day: free slots with prices, booked slots with the team name, unconfirmed requests highlighted, maintenance blocks; tap free slots (several in a row) to book a team with advance payment; tap a booked slot to call, confirm or cancel |
| Subscriptions | Monthly / Half-yearly / Yearly plans (prices editable by the Super Admin). **No auto-renewal**: each period is a prepaid invoice. Paying while a plan runs queues the next period after it. Owners see their plan, days left and invoices under Workspace → Subscription and can renew or switch plan. 10 days before the end a banner warns; after the end there are 3 grace days, then the turf is hidden from Explore and new bookings pause (history stays readable, renewing always works) |
| Payments | Owners pay online through SSLCommerz (cards, bKash, Nagad, Rocket; set `SSLCOMMERZ_*` in `.env`, every payment is validated server-to-server) or send money to the bKash / Nagad / Rocket / bank account in `.env` and submit the TrxID; the Super Admin verifies it under **Plans & payments** |
| Super Admin plans | Turf list shows each turf's plan (Monthly / Half-yearly / Yearly), paid-until date and open orders, with a plan filter and **Change plan**; plan chosen when adding a turf or approving an application (paid now, or invoice the owner); dashboard counts turfs per plan |
| Pictures | Workspace → Settings → Pictures: one square **profile picture** (logo) shown on the turf card and page, and up to **12 public-page photos** (drag & drop, captions, reorder, first = cover on Explore and the turf page, full-screen viewer for players). Uploads are checked with Pillow, resized, re-encoded to WebP and stripped of camera/GPS data; stored under `backend/media/` (S3 in production) |
| Plan reminders | Owners get an email (English + বাংলা) 10, 7, 3 and 1 days before their paid time ends, with a renew link. Runs daily at 9 AM via Celery beat, or `python manage.py send_subscription_reminders` (cron/Task Scheduler fallback). Never sent twice (unique per period + day), skipped when the next period is already paid, failed sends retried up to 3 times |
| Activity & audit log | Every important action is recorded with who, when and from which IP: bookings (created, changed, confirmed/cancelled, online requests), payments and refunds, customers, fields, hours, pricing, settings, pictures, team changes, expenses, subscription orders/payments, sign-ins (incl. failed) and password changes. Owners: Workspace → **Activity** (own turf only; managers can't open it). Super Admin: **Audit log** (all turfs + platform actions, filters, search) |
| Two-factor sign-in | Super Admins can turn on authenticator-app codes (Google/Microsoft Authenticator, Authy) under **My account**: QR set-up, 10 one-time recovery codes (copy/download), regenerate, turn off (password + code). Sign-in then asks for the code; codes can't be replayed, 5 wrong codes or 5 minutes end the attempt, rate-limited |
| Public page colours | Workspace → Settings → **Public page colours**: six presets (TurfBari green, Ocean, Sunset, Crimson, Royal, Midnight) or a custom main colour, with live preview. Applied only to that turf's public page; colours too light for white button text are rejected |
| SaaS homepage | Public homepage shows active public plans, admin-authored benefits and limits, configured SMS segment pricing and cost examples, the global About Us video, support/onboarding steps, configured contact information and published bilingual FAQs. Plan buttons open registration with the selected billing period preselected |
| Plan configuration | Super Admin → **Plans & payments** controls billing duration, active/public status, homepage order, featured flag, benefits, limits and SMS entitlement. Subscription records preserve plan and price snapshots; plan edits affect new orders only. The configured manager cap and SMS inclusion are enforced on the backend |
| SMS plan access | Tenant SMS checks platform account controls and the active subscription's SMS entitlement snapshot. Public pricing comes from effective-dated SMS rates; the initial baseline is ৳0.35 per segment and administrators can schedule new rates |
| Homepage content | Super Admin → **Homepage FAQs** manages bilingual questions, ordering and publication. Super Admin → **Onboarding & training** tracks active accounts, plan, activation date, support assignment, schedule, notes, covered topics and change history |
| Safety | No double bookings (row lock per field, proven by a concurrent test), tenant isolation (other turfs' IDs → 404), owner-only actions enforced in the API, suspended turfs are read-only, public serializers are whitelists |

Not built yet: SMS/WhatsApp reminders (email only today), two-factor sign-in for owners and managers (Super Admins only today), and automatic database backups for the Docker stack.

Tests: 296 backend (`pytest`) + 31 frontend (`vitest`) at the last full run.

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
(XAMPP's `root` has no password by default; pick your own password for `turfbari`):

```powershell
C:\xampp\mysql\bin\mysql.exe -h localhost -u root -e "CREATE DATABASE IF NOT EXISTS turfbari CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci; CREATE USER IF NOT EXISTS 'turfbari'@'localhost' IDENTIFIED BY 'your-password'; CREATE USER IF NOT EXISTS 'turfbari'@'::1' IDENTIFIED BY 'your-password'; CREATE USER IF NOT EXISTS 'turfbari'@'127.0.0.1' IDENTIFIED BY 'your-password'; GRANT ALL ON turfbari.* TO 'turfbari'@'localhost'; GRANT ALL ON turfbari.* TO 'turfbari'@'::1'; GRANT ALL ON turfbari.* TO 'turfbari'@'127.0.0.1'; GRANT ALL ON test_turfbari.* TO 'turfbari'@'localhost'; GRANT ALL ON test_turfbari.* TO 'turfbari'@'::1'; GRANT ALL ON test_turfbari.* TO 'turfbari'@'127.0.0.1'; FLUSH PRIVILEGES;"
```

`test_turfbari` is pytest's temporary database. You can browse the data in phpMyAdmin at http://localhost/phpmyadmin.

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

`createsuperuser` creates the TurfBari **Super Admin**.

#### Demo logins (`seed_demo`, development only)

| Role | Email | Password |
|---|---|---|
| Super Admin | admin@turfbari.local | TurfBariAdmin#2026 |
| Owner (Green Arena Gulshan) | owner@turfbari.local | TurfBariOwner#2026 |
| Owner (Mirpur Kickoff Zone) | mirpur.owner@turfbari.local | TurfBariOwner#2026 |
| Manager (Green Arena Gulshan) | manager@turfbari.local | TurfBariManager#2026 |

The other demo owners (uttara.owner@, ctg.owner@) use the owner password too. `seed_demo --reset` rebuilds the demo data.
This seed command is development-only and refuses to run when `DJANGO_DEBUG` is false.

#### Interactive product demos

The homepage links to `/demo-booking` (player flow) and `/demo-account` (owner workspace). Each new browser session
receives a private 24-hour demo workspace; the booking flow and owner dashboard share that workspace in the same
browser tab. Demo workspaces, slots, customers, bookings, activity, and price snapshots use only the `apps.demo`
tables. They are not Django users or real tenants, and their APIs never call production payment, subscription, SMS,
wallet, or booking services. SMS, QR, payments, and subscription controls in the demo are previews only.

Platform admins can manage workspaces at **Admin > Demo management**. Create a workspace to get a short-lived access
link (shown once), rotate its link, disable it, change its owner/workspace labels or expiry, inspect activity, or reset
only its demo records to the seeded state. Expired access is rejected immediately. Run
`python manage.py run_tick` (or the protected `/api/system/tick/` endpoint) handles expiry and removes
their booking/customer/slot records after 30 days; the demo activity history is retained. No real tenant rows are
modified by cleanup. `python manage.py cleanup_demo_workspaces` runs this cleanup directly when needed.

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

## Production with Docker

`docker-compose.prod.yml` runs the whole stack: MySQL 8.4, Redis, the Django API on gunicorn (migrates and collects
static files on start), a Celery worker, Celery beat (plan reminders) and Nginx, which serves the React build and
proxies `/api` plus uploaded `/media`.

```bash
cp .env.production.example .env.production      # fill in every value; never commit it
docker compose -f docker-compose.prod.yml --env-file .env.production up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.production exec api python manage.py createsuperuser
```

- The `web` container listens on port 80 (`HTTP_PORT`). Put HTTPS in front of it (Caddy, Cloudflare, a load balancer
  or host Nginx) and make sure it sends `X-Forwarded-Proto: https`; Django redirects plain http and sets secure cookies.
- `TRUST_X_REAL_IP=true` lets audit logs and login lockouts see the visitor's real IP from our Nginx. Leave it off if
  anything other than this Nginx can reach the API.
- Uploaded pictures live in the `media` volume, or in S3-compatible storage when `AWS_STORAGE_BUCKET_NAME` is set.
- Back up the `mysqldata` and `media` volumes; they hold all bookings and pictures.
- Only one `beat` container may run (the schedule is stored in MySQL by django-celery-beat).

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
