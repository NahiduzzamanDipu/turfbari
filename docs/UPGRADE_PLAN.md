# TurfBari platform upgrade — audit and plan

## Phase 1 — Audit (what exists today)

| Area | What is already there | Gap against the brief |
|---|---|---|
| Stack | Django 5.2 + DRF, React 19 + TS + Vite + Tailwind 4, MariaDB locally / Postgres (Aiven) in production, Celery + beat configured | **Production has no Redis and no Celery worker** (Render free web service only). Anything "background" must also work without a worker. |
| Tenancy | `Turf` is the tenant; `TenantMembership` (owner / manager); `IsTenantMember` pins every workspace query to `request.tenant`; `owner_only` / `owner_only_writes` flags | Managers have one fixed permission set. No per-manager permissions (approve payments, manage slots). |
| Public site | `/` home with search, `/explore` marketplace, `/turfs/<slug>` turf page, QR SVG at `/api/public/turfs/<slug>/qr.svg`, no customer accounts | Marketplace must go; turf pages must stay and work by direct link / QR. |
| Slots | Per-field `slot_minutes` grid inside per-weekday `OperatingHours` (overnight supported); 15-min boundaries; maintenance blocks | No hand-made slots, no per-day slot lists, no date overrides for schedules. |
| Pricing | `PricingRule` bands (weekday/date/field/priority), 15-min segment quote engine, price snapshot on the booking | No Morning/Evening/Night/Midnight categories; no per-slot override. |
| Booking safety | `reserve_slot()` locks the field row (`SELECT … FOR UPDATE`) and rejects overlaps; 10-min public `SlotHold` + IP cooldown | Online requests are `pending` with no payment proof; no hold lifetime for a submitted request (pending blocks forever until staff act). |
| Payments | `Payment` rows (cash/bKash/…) recorded by staff | No customer bKash submission, no verification queue, no ৳500 rule. |
| Notifications | Email only (Resend, test mode = admin address only); subscription reminders 10/7/3/1 days via `ReminderLog` | No SMS at all. |
| Accounts | Email/username login, argon2, axes lockout, 2FA (TOTP + email code for admin), change password; temp passwords generated for new owners and managers and shown once | Temp password is permanent (no forced change, no expiry); no forgot-password; admin cannot unlock / reset / deactivate users from the UI. |
| Admin | Overview, applications, turfs (suspend/activate), plans & payments, promo codes, audit log | No account management, no subscription extend/expire tools, no SMS, no health page. |
| Theme | 6 presets + one accent colour on the public turf page | No secondary/background colours, button style, font, preview/publish. |
| Video | — | Nothing. |

### BulkSMSBD findings
- API (third-party mirror of their docs, to be confirmed against your panel): `POST https://bulksmsbd.net/api/smsapi` (`api_key`, `senderid`, `number`, `message`), `…/smsapimany`, `…/getBalanceApi`. Success code `202`; errors `1002`–`1032` (e.g. 1007 insufficient balance, 1032 IP not whitelisted).
- **No delivery-report endpoint is documented** → we store "submitted" / "failed", not "delivered".
- **No official embed/iframe support** → a native SMS screen built on the API (no embedded login form). A plain "Open BulkSMSBD panel" link is offered for everything else (recharge, sender IDs).
- Error 1032 means your account may require IP whitelisting; Render's outbound IPs must then be whitelisted in the BulkSMSBD panel.

## Phase 2 — Design

### Background work without a worker
`SmsMessage` rows are an outbox. A message is sent right after the DB transaction commits (in a short-lived thread, so a slow provider never blocks a booking) and also by a periodic **tick** that:
1. retries due `queued`/`failed` SMS (max 3 attempts, back-off),
2. expires lapsed payment holds,
3. sends subscription reminders/expiry notices (idempotent per period+day+channel).

The tick runs from Celery beat when a worker exists, from `manage.py run_tick`, and from `POST /api/system/tick/` protected by a secret header (the existing Supabase pg_cron keep-awake job can call it every 10 min). Hold expiry is also enforced lazily on read, so correctness never depends on the tick.

### Booking states (online)
`awaiting_payment` (hold; slot blocked) → customer submits bKash proof → `pending` shown as **Awaiting verification** → owner **Approve** → `confirmed` (+SMS) / **Reject** → `rejected` (+SMS, slot freed). Hold lapses → `expired` (slot freed). Confirmed is never touched by expiry. Approval re-checks overlaps under the field lock.

Advance rule: `required = min(total, max(500, turf.advance_amount))`; submitted amount must be ≥ required and ≤ total.

### New / changed models
- `Turf`: `bkash_number`, `advance_amount`, `payment_hold_minutes`, `youtube_video_id`, theme JSON (`theme`), `notify_*` flags.
- `PriceCategory` (turf, key morning/evening/night/midnight, start, end, hourly_rate) — replaces default bands in the UI; `PricingRule` stays for special dates.
- `SlotTemplate` (turf, field, weekday, start, end, is_active, price_override) — when a field has templates for a weekday they define the slots; otherwise the existing grid is used. `SlotOverride` for dates (closed / custom).
- `PaymentSubmission` (booking, amount, sender number, trx id unique per turf, status, reviewed_by/at, reason).
- `Booking.Status`: add `awaiting_payment`, `expired`; `hold_expires_at`.
- `TenantMembership.permissions` (JSON: approve_payments, manage_slots, view_sms).
- `SmsMessage` (turf?, to, body, kind, dedupe_key unique, status, attempts, provider_code, related ids), `SmsTemplate`.
- `User`: `must_change_password`, `temp_password_expires_at`; `PasswordResetCode` (hashed, 15 min, single use).

## Phases 3–7
Each phase lands with tests, then the frontend, then a full check (pytest, ruff, migrations, tsc, vitest, build):

1. Marketplace removal + redirects; QR download in workspace.
2. Accounts: forced first-login change, temp expiry, forgot password, admin account tools.
3. SMS layer (BulkSMSBD client, outbox, templates, logs, balance; admin + workspace screens), tick.
4. Booking + bKash verification flow, ৳500 rule, holds, Payment Verification screen, SMS on approve/reject.
5. Four-category pricing + custom slot templates + date overrides.
6. Theme editor + YouTube popup.
7. Admin: subscriptions (extend/expire with reason, reminder schedule), SMS, health; docs + env.
