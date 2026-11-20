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

---

# Version 2 updates

## What changed
- **Global "বুকিং করার নিয়ম" video** — one YouTube video set by the Super Admin (Admin → **API** → YouTube) shows next to
  "Book a slot · বুক করুন" on every turf page and opens in a popup (youtube-nocookie, no autoplay, stops on close).
  Owners can no longer set a video (the per-turf field was removed).
- **Admin → API**: YouTube card (paste, preview, save, change, remove); BulkSMSBD card (API key saved **encrypted**
  with Fernet, shown only masked; sender ID; connection test with balance; status); customer booking limit.
  A key saved here overrides `BULKSMSBD_API_KEY`. Removing it falls back to the environment key.
- **Admin → Terms & Rules**: versioned Terms & Conditions + Booking Rules (Bengali/English, simple safe formatting,
  preview, save draft, publish, on/off). Public page `/terms`; "Terms & Conditions" link on every booking page;
  required checkbox *"আমি Terms & Conditions এবং Booking Rules & Regulations পড়েছি এবং সম্মত হয়েছি।"* checked on the
  server. Each booking stores `terms_version` + `terms_agreed_at`; publishing a new version never changes old bookings,
  and a form opened before an update is asked to accept the new version.
- **SMS usage**: every provider call is an `SmsAttempt`; usage counts logical messages (retries once). Messages are
  `tenant` (customer SMS) or `platform` (plan notices, sign-in codes, tests) — platform ones never count as a turf's
  usage or limit. Owner: usage section on SMS page + dashboard line. Admin → **SMS usage**: date/status/turf filters,
  per-turf table with attempts and a high-usage flag (≥ 3× typical, min 20), per-account log, CSV export.
- **Booking drafts & duplicates**: the browser keeps a random visitor id and a draft (field, day, hold token,
  idempotency key — no names/phones/payment data) in localStorage for 30 min. Holds are keyed by that id (IP only as a
  fallback), so a reload or new tab gets its own selection back and neighbours on one Wi-Fi are told apart. A repeated
  submit with the same `Idempotency-Key` returns the same booking. "Already submitted" is shown after a request.
- **Customer limit**: a mobile number can hold at most **2** upcoming slots across all turfs (configurable). Pending
  requests count; past, expired, rejected and cancelled don't. Enforced under a per-phone row lock.
- **Online-booking message fix** — root cause: the v1 bKash migration left `bkash_number` empty on every existing turf
  and the page treated "no bKash number" as "online booking off". Now only the owner's switch decides; until an owner
  sets a bKash number, customers are asked to Send Money to **that turf's own registered mobile**.

## Performance (measured locally, same data)
| | Before | After |
|---|---|---|
| Availability API | 12 queries, ~17 ms | 7 queries, ~12 ms |
| Turf page API | 7 queries, ~15 ms | 7 queries, ~14 ms |
| JS loaded by a turf page (gzip) | 186 kB | 140 kB |
| Slot list refresh | every 5 s | every 8 s (paused in background tabs) |

Turf configuration (hours, custom slots, price rules, categories) is cached and dropped on every change; bookings,
holds and maintenance are never cached. Production (remote Postgres) gains more, since each query is a round trip.

## Migrations
`common.0001_initial` (PlatformSettings, TermsVersion, CustomerLock), `bookings.0005` (slot_count, idempotency_key,
terms_version, terms_agreed_at), `notifications.0002`/`0003` (encrypted key, scope, provider_ref, SmsAttempt; old
platform messages re-labelled), `turfs.0011` (per-turf video removed). New dependency: `cryptography`.

## New endpoints
Public `GET /api/public/terms/`; booking request takes `agree_terms`, `terms_version`, header `Idempotency-Key`;
public calls accept `X-Visitor-Id`. Admin: `api-config/`, `api-config/youtube/`, `api-config/bulksmsbd/` (PUT save,
POST test), `api-config/booking/`, `terms/`, `terms/publish/` (POST/DELETE), `terms/switch/`, `sms/usage/`
(`?from&to&status&q`, `&export=csv`); `sms/messages/` adds `from`, `to`, `scope`. Workspace: `sms/usage/`.
Removed: `workspace/design/video/`.

## After deploying
1. Admin → **API**: paste the booking-guide video; optionally save the BulkSMSBD key and sender ID there.
2. Admin → **Terms & Rules**: write and publish the first version (until then no checkbox is shown).
3. Tell owners to confirm their bKash number in Settings (the turf's own mobile is used until they do).

---

# Version 3 — prepaid SMS wallet, bKash recharge, campaigns, daily limit, approvals

## SMS wallet (every turf)
- Each turf has its own wallet (starts at ৳0). The balance changes only through **immutable ledger entries**
  (`WalletTransaction`: recharge, admin credit, adjustment, SMS charge, SMS refund) with unique idempotency keys; a
  database check forbids negative balances. Corrections are new entries, never edits.
- **Prices** (Admin → SMS wallets → Pricing): BDT per billable SMS part for non-masking, masking and bulk, each with an
  effective time. Every charge stores the price it used. No price set = turf SMS are blocked ("no price").
- **Parts**: Bengali/Unicode 70 characters (67 per part when longer), English 160 (153).
- **Charging policy**: the cost is taken in the same database transaction that hands the SMS to BulkSMSBD, so two
  parallel sends can never overdraw a wallet. If BulkSMSBD clearly refuses it, the amount is refunded at once with a
  separate entry. If BulkSMSBD doesn't answer (timeout), the charge stays and the message is marked *Check*; an admin
  refunds it after checking the BulkSMSBD panel. Each provider call has its own charge key, so a retry or a second
  run can never charge the same call twice; messages never handed to BulkSMSBD are never charged.
- **Not enough balance**: nothing is sent or charged; the SMS is stored as *Blocked* with the reason, the owner sees the
  Bengali warning on the dashboard and SMS page, and can *Send waiting SMS* after recharging. Bookings are never rolled
  back or blocked because of SMS.
- TurfBari's own SMS (sign-in codes, plan notices, recharge/plan confirmations) never touch a turf wallet; their cost is
  recorded as a platform expense (Finance page).

## bKash wallet recharge
Owner: SMS → Recharge Wallet → amount → the app shows the credit, the extra bKash charge (default **1.9%**,
configurable) and the total, plus TurfBari's bKash number → the owner sends the money and submits sender, total sent,
TrxID and a note. Credit is added **only** when an admin approves (Admin → SMS wallets → Recharge requests); the charge
is recorded separately and never becomes wallet money. One credit per request, TrxIDs are unique, approval/rejection
are audited and the owner gets an SMS from TurfBari's own SMS. Settings: Admin → API → Payments to TurfBari.

## Single SMS and bulk campaigns (owner SMS page)
- **Send SMS**: number, message, live character/part counter, estimated cost, balance, confirmation dialog.
- **Bulk SMS**: recipients from the turf's own bookings (date range, statuses), all saved customers, typed numbers or a
  CSV (phone/mobile + optional name, max 300 KB); placeholders `{{customer_name}} {{turf_name}} {{booking_date}}
  {{booking_time}} {{booking_id}} {{customer_phone}}`; preview with sample messages, valid/invalid/duplicate counts,
  total parts, cost and balance; confirmation; one campaign per idempotency key; the first batch goes at once and the
  rest in batches via the tick; stop/cancel (unsent messages are dropped and never charged); history with
  sent/failed/parts/cost.
- Customer lists never cross turfs (every query is filtered by the signed-in turf).

## Admin SMS controls (per account)
Admin → SMS wallets → Accounts → Manage: all SMS on/off and, separately, booking confirmation, booking made by the
turf, rejection/cancellation, reminder, single and bulk SMS; monthly limit; wallet credit/take-back with a reason;
ledger; blocked reasons. Changes apply immediately and are audited. Turned-off SMS are stored as *Blocked* (no charge)
and the owner sees *"আপনার অ্যাকাউন্টের SMS সেবা বর্তমানে প্রশাসক কর্তৃক বন্ধ রাখা হয়েছে…"*. TurfBari's own SMS are
controlled separately.

## Daily booking limit
At most **2 slots per mobile number per Bangladesh calendar day** (Asia/Dhaka; a booking belongs to the day it starts),
across all turfs; the next day starts fresh. Counts confirmed, played and pending requests that still hold their slot;
rejected, cancelled and expired don't. Enforced on the server under a per-phone row lock (tested with parallel
requests); configurable in Admin → API. The booking form states the rule; the exact remaining count is not shown
publicly so nobody can look up another number's bookings.

## Bookings made by the turf send SMS
A booking the turf creates as *confirmed* (or a staff-made pending booking that is later confirmed) sends the customer
the Bengali confirmation, charged to the wallet and logged. It shares the dedupe key family with the online
confirmation, so a booking never gets two. The owner sees whether the SMS went or why not (e.g. low balance); the
booking always stands.

## Subscriptions need admin approval
Owners order a renewal / upgrade / downgrade (labelled automatically), see the payable amount (plan price + optional
payment charge %), TurfBari's bKash number and instructions, and submit sender, amount sent and TrxID. Nothing changes
until an admin verifies it in **Plans & payments** (owner, current plan and expiry, requested plan and period, payable
vs sent, TrxID). Approval extends from the current expiry, records who/when and SMS the owner; rejection leaves the plan
unchanged and SMS the owner. **SSLCommerz payments and 100% promo codes now also wait for approval.** Duplicate TrxIDs
are refused. History and audit records are kept.

## Finance (Admin → Finance)
Wallet balances held, SMS charged (net of refunds), approved / pending / rejected recharges, bKash charges collected
(kept separate), subscription payments received / pending / rejected, TurfBari's own SMS cost, top spenders.
Unverified money is never shown as received.

## Performance (measured locally, same data)
| | Before | After |
|---|---|---|
| Tap a slot → shown as selected | 200–247 ms (waited for the reservation and a full list reload behind a loading skeleton) | 16–36 ms (immediate; reverts if the server refuses) |
| Reservation confirmed by the server | — | 139–200 ms, in the background |
| Slot list API | 7 queries, ~10 ms | unchanged |
| Reservation (hold) API | 12 queries, ~13 ms | unchanged |
| Turf page DOM ready (dev server) | — | 256 ms |

Root cause of the delay: the slot list's cache key included the hold token, so every selection discarded the list and
downloaded it again before the tap showed. Added index: `Customer.phone` (for the cross-turf daily limit).

## Migrations
`notifications.0004_sms_wallet`, `common.0002_sms_wallet`, `subscriptions.0006_approval_flow`,
`bookings.0006_customer_phone_index` — all additive.

## New endpoints
Workspace: `sms/wallet/`, `sms/wallet/ledger/`, `sms/wallet/recharge/` (GET quote, POST submit),
`sms/retry-blocked/`, `sms/messages/<id>/retry/`, `sms/send/`, `sms/campaigns/` (+ `preview/`, `<id>/` GET/DELETE).
Admin: `sms/pricing/`, `sms/recharges/` (+ `<id>/approve|reject/`), `sms/wallets/`, `sms/messages/<id>/refund/`,
`turfs/<id>/sms/` (GET/PUT controls), `turfs/<id>/sms/adjust/`, `finance/`, `api-config/payments/`.

## After deploying
1. Admin → SMS wallets → **Pricing**: set the per-part prices (until then turf SMS are blocked).
2. Admin → API → **Payments to TurfBari**: the recharge bKash number (and optionally the subscription bKash number and
   charge).
3. Owners recharge their wallets; approve the requests in Admin → SMS wallets.
