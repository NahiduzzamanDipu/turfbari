# TurfBari upgrade — what changed and how to run it

Delivered in seven commits on `main` (each one tested, then pushed):

| Commit | Area |
|---|---|
| `8de735c` | Public directory retired, booking-page QR downloads |
| `c5b7b15` | Account security: forced first-login change, forgot password, admin account tools, manager permissions, lockout fix |
| `f6c346d` | BulkSMSBD SMS layer, outbox, templates, logs, background tick |
| `d7215e3` | Online booking with manual bKash advance verification |
| `d789155` | Custom slot schedules, Morning/Evening/Night/Midnight pricing |
| `b04fa7d` | Page design editor, YouTube popup |
| (this commit) | Admin subscriptions & health, docs |

Tests: **206 backend tests** (pytest, MariaDB) + 10 frontend tests (Vitest); `ruff`, `tsc`, migrations check and the production build all pass.

---

## 1. Manual actions for you

1. **BulkSMSBD** — in your BulkSMSBD panel: copy the API key and your approved sender ID. In Render → *Environment* add
   `BULKSMSBD_API_KEY`, `BULKSMSBD_SENDER_ID`, `SMS_BACKEND=bulksmsbd`. If BulkSMSBD answers error **1032** (IP not
   whitelisted), add Render's outbound IPs (Render → service → *Connect* → *Outbound*) to the BulkSMSBD IP whitelist.
   Then Admin → **SMS** → *Send a test SMS* to your own phone.
2. **Background tick** — add `TICK_TOKEN` (a long random string) on Render, then schedule a call every 10 minutes. You
   already have Supabase pg_cron keeping the site awake; add a second job in the Supabase SQL editor (paste the token
   yourself):
   ```sql
   select cron.schedule('turfbari-tick', '*/10 * * * *', $$
     select net.http_post(
       url := 'https://turfbari.onrender.com/api/system/tick/',
       headers := jsonb_build_object('X-Tick-Token', 'PASTE_TICK_TOKEN_HERE', 'Content-Type', 'application/json')
     )
   $$);
   ```
   Admin → **Health** shows "Background tasks: N min ago" once it runs.
3. **Every turf owner must add a bKash number** (Settings → *bKash payments*). Without it the booking page still shows
   slots but takes no online bookings (by design: online bookings now require a bKash advance).
4. Optional: `TEMP_PASSWORD_HOURS` (default 72).

Render redeploys on push and `manage.py startup` runs the migrations automatically.

## 2. New environment variables

| Variable | Default | Purpose |
|---|---|---|
| `BULKSMSBD_API_KEY` | empty | BulkSMSBD API key (env only; never stored in DB or shown in UI) |
| `BULKSMSBD_SENDER_ID` | empty | Approved sender ID (admin can override in the SMS page) |
| `BULKSMSBD_BASE_URL` | `https://bulksmsbd.net/api` | API base |
| `SMS_BACKEND` | `bulksmsbd` | `bulksmsbd` / `console` (log only) / `disabled` |
| `SMS_DISPATCH` | `thread` | `thread` (send after commit in background) / `inline` |
| `TICK_TOKEN` | empty | Secret for `POST /api/system/tick/`; empty disables the endpoint |
| `TEMP_PASSWORD_HOURS` | `72` | Lifetime of temporary passwords |

## 3. Database migrations (all additive; no data rewritten)

- `accounts.0004_password_policies` — `User.must_change_password`, `temp_password_expires_at`; `PasswordResetCode`.
- `turfs.0006_manager_permissions` — `TenantMembership.permissions` (JSON).
- `turfs.0007_turf_sms_settings`, `notifications.0001_initial` — SMS outbox, templates, config.
- `turfs.0008_…` — `Turf.bkash_number`, `advance_amount` (default 500), `payment_hold_minutes` (default 60).
- `bookings.0004_…` — `Booking.hold_expires_at`, status `expired`; `PaymentSubmission` (unique TrxID per turf).
- `turfs.0009_price_categories_slot_templates` — `PriceCategory`, `SlotTemplate`.
- `turfs.0010_theme_settings_video` — `theme_settings`, `theme_draft`, `youtube_video_id`.

Existing users keep working passwords (`must_change_password` defaults to false). Existing pending requests without a
bKash submission stay visible under **Bookings** (badge) and can still be confirmed there.

## 4. How the main flows work

**Online booking (customer).** Turf page → pick slot (held 10 min) → bKash *Send Money* box shows the number, slot
price, advance (≥ ৳500, or the full price if cheaper) and amount due at the turf → enter amount, sender number, TrxID →
Bengali notice. The booking is *Awaiting verification*, not confirmed and not paid. The slot stays held for the
turf's hold time (default 60 min); after that it reopens and the request shows *Expired*.

**Payment verification (owner / manager with "Approve bKash payments").** *Payment verification* page → check the
amount, sender and TrxID in the bKash app → **Approve** (confirmation dialog; re-checks the slot under a row lock,
records a bKash payment, confirms, sends the Bengali SMS) or **Reject** (optional reason; frees the slot; SMS). An
expired request can still be approved if nobody took the slot; otherwise the screen says to refund.

**Slots & prices.** *Slot schedule*: generate back-to-back slots per weekday, add/edit/disable single slots (overnight
allowed, overlaps refused), copy a day, go back to automatic. *Pricing*: four time-of-day prices with editable start
times; a slot takes the price of the period it **starts** in (slots running into the next period are flagged). Order:
special-date rule > slot's fixed price > time-of-day price > weekday rules > field rate.

**Page design.** Presets, main and second colour (main colour must keep white button text readable), background,
button shape, font; preview → save draft → publish. YouTube: paste a link; only the 11-character ID is stored and
played from youtube-nocookie.com in a popup (no autoplay; closing stops it).

**Accounts.** New owner/manager accounts get a 12-character temporary password shown once; it expires after
`TEMP_PASSWORD_HOURS` and must be replaced at first sign-in — the API refuses everything else until then. *Forgot
password* sends a 6-digit code (SMS if the account has a mobile number and SMS works, else email): 15 minutes, 5
guesses, single use, same answer whether or not the account exists; success signs out all sessions and clears
lockouts. Five wrong passwords lock the account for 15 minutes (this lockout never worked before — fixed).

**Admin.** *Accounts* (search by email/phone/username/turf; create; unlock; temporary password; require change; sign out
everywhere; turn off 2-step; deactivate; fix memberships — admins' own accounts are protected), *Subscriptions*
(standing of every turf, ending-soon filter, extend with reason, end now with reason, history), *SMS* (connection,
balance, usage by turf, switches, monthly per-turf limit, plan-reminder days, templates, log with retry, test SMS),
*Health* (DB, cache, tick freshness, SMS/sign-in/booking/billing problems, recent events). Every action is in the audit
log.

## 5. API endpoints added

Public: `POST /api/public/turfs/<slug>/book/` now also takes `payment_amount`, `bkash_sender`, `trx_id`;
`GET /api/public/turfs/<slug>/` adds `payment`, `price_categories`, `youtube_video_id`, full `theme`.
Removed: `GET /api/public/turfs/` (directory) and `/api/public/stats/`.

Auth: `POST /api/auth/password-reset/`, `POST /api/auth/password-reset/confirm/`.

Workspace: `booking-page/qr.(png|svg)`, `payment-verifications/` (+ `<id>/approve/`, `<id>/reject/`),
`sms/`, `sms/settings/`, `price-categories/`, `slot-templates/` (CRUD + `generate/`, `copy/`, `clear/`),
`design/`, `design/publish/` (POST publish, DELETE discard), `design/video/`, `managers/<id>/` (PATCH permissions).

Admin: `users/` (+ `<id>/`, `<id>/memberships/`, `<id>/<action>/`), `memberships/<id>/`, `sms/`, `sms/messages/`,
`sms/messages/<id>/retry/`, `sms/test/`, `sms/templates/` (+ `<kind>/`), `subscriptions/`,
`turfs/<id>/subscription-history/`, `turfs/<id>/extend-subscription/`, `turfs/<id>/end-subscription/`, `health/`.

System: `POST /api/system/tick/` (header `X-Tick-Token`). Also `manage.py run_tick`, Celery task `notifications.tick`.

Full OpenAPI schema: `/api/schema/` (Super Admin only in production).

## 6. Rollback

Each phase is one commit. To roll back the code, `git revert <commit>` (newest first) and push; Render redeploys.
Migrations are additive, so older code runs against the newer schema; only revert a migration
(`manage.py migrate <app> <previous>`) if you also want the data gone. Take an Aiven backup/fork before that.

## 7. Known limits

- **BulkSMSBD has no documented delivery-report API**, so "Sent" means accepted by BulkSMSBD, not delivered to the
  handset. A provider timeout is marked *Check* and never auto-resent (to avoid duplicate SMS).
- **No embedded BulkSMSBD dashboard**: BulkSMSBD offers no official embed; an iframe login would be unsafe. The SMS page
  is built on their API and links to their panel for recharge and sender IDs.
- **bKash is verified by a person.** No bKash API is used; TurfBari never moves money. Refunds happen in the bKash app.
- **Background work runs every ~10 minutes** on the free plan (no worker). Hold expiry is also enforced instantly on
  every read, so slots are never stuck; only the *Expired* label and reminder SMS wait for the tick.
- Email reset codes and owner reminder emails go only to your own address until a domain is verified in Resend.
- The 10-minute slot-selection hold is unchanged; customers who take longer to pay in bKash must re-select.
