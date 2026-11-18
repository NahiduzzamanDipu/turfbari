# TurfBari — Bengali promotional video production package

Everything needed to produce a ~3:35 Bengali promo for the **public website, turf owners, managers and football teams**.
No Super Admin / admin screen, feature or wording appears anywhere in this package.

> **Brand name:** the brief says “TURFOS”; the product was renamed **TurfBari** (টার্ফবাড়ি) on 18 Nov 2026 with a new logo.
> This package uses the real, current brand. Tagline: **«প্রতিটি টার্ফের ঠিকানা»**. URL used on the end card: `turfbari.com` (not registered yet — register it or change `tools/production_data.py` and rebuild).

## Start here
1. Read `06-script/full-bengali-voiceover.md` and record the voiceover (direction in `08-audio/`).
2. Follow `09-editing-guide/editing-guide.md` with the storyboard `07-storyboard/storyboard.md`.
3. Real UI: `02-real-app-screenshots/`. Cinematic footage: generate from `04-ai-image-prompts/` and `05-ai-video-prompts/`.
4. Everything in one document: `TurfBari_Bengali_Promotional_Video_Guide.pdf`.

## Structure
```
promotional-video/
├── 01-brand-assets/        logo (SVG + PNG: on light, on dark, transparent dark-ink and light-ink), colours, typography
├── 02-real-app-screenshots/ real screens, 1920×1080 desktop and 390×844 mobile
│   ├── public-homepage/ turf-discovery/ turf-details/ qr-booking/
│   ├── owner-dashboard/ booking-management/ customer-management/
│   ├── field-and-pricing/ payment-management/ reports/
│   └── manager-dashboard/  (manager's own login only — never owner/admin screens)
├── 03-reference-images/    scene-01 … scene-09 keyframes + _illustrations/
├── 04-ai-image-prompts/    IMG-01 … IMG-10
├── 05-ai-video-prompts/    VID-01 … VID-07
├── 06-script/              full-bengali-voiceover.md/.txt, scene-by-scene-script.md, bengali-subtitles.srt
├── 07-storyboard/          storyboard.md, storyboard-sheet.png, frames.json
├── 08-audio/               audio-direction.md (voice, music, SFX, mix, cue sheet)
├── 09-editing-guide/       editing-guide.md
├── 10-pdf/                 source HTML + images for the PDF
├── tools/                  scripts that produced all of the above (re-runnable)
└── TurfBari_Bengali_Promotional_Video_Guide.pdf
```

## Feature audit (from the real code and running app, 18 Nov 2026)
### ✅ Implemented — promoted in the video
| Feature | What exists |
|---|---|
| Public website | Home with search and district filter; no account needed |
| Turf discovery | Explore with district / area / type / price / amenity filters, name search, sort; 'near me' with distance badges |
| Turf details | Cover photo, gallery + full-screen viewer, profile picture, amenities, fields, opening hours, price table, contact, Google Maps directions |
| QR code | Unique QR per turf that opens its booking page (shown on the turf page and in owner Settings, downloadable SVG) |
| Public booking | Pick field, date and free slots; send a request with name + mobile; status stays Pending until the turf confirms |
| Booking status | Look up a request with reference + mobile number |
| Owner dashboard | Today's bookings, collected today, this month, dues outstanding, 14-day collections chart, coming up, pending-requests banner |
| Book a slot board | Free / booked / request / maintenance per field and day; book a team with discount (৳ or %) and advance |
| Booking management | Day board and list, filters, confirm / reject / reschedule / cancel / no-show |
| Payments | Record payments and refunds per booking (cash, bKash, Nagad, Rocket, card, bank) with paid / due |
| Customers | Customer list with bookings count, total paid and last booking |
| Fields, hours, pricing | Fields, opening hours (incl. past midnight), peak / weekend / special-date pricing rules |
| Maintenance | Block a field for repairs |
| Expenses & reports | Expenses; reports with collected, expenses, net, bookings, daily chart, by field, by payment method, Excel export (owner only) |
| Team | Owner adds managers; each manager gets a separate login |
| Manager workspace | Dashboard, book a slot, bookings, confirm, record payments, customers, maintenance; fields / hours / pricing view-only |
| Public profile | Owner edits listing, photos, profile picture, Google Maps pin |

### ⚠️ Partial
| Feature | Status |
|---|---|
| Manager permissions | Fixed by role (not configurable per manager). The script says what the role can and can't do. |
| Activity log | Being built in a parallel session; not shown in the video until it is finished and tested. |

### ❌ Not implemented — kept out of the script
| Feature | Status |
|---|---|
| Notification centre | Not built — only the dashboard's pending-requests banner exists. Not mentioned in the video. |
| Online payment by players | Not built — players don't pay online; staff record payments. The video never says 'pay online'. |
| Booking calendar (month view) | Not built — there is a day board and a list. The video says 'board', not 'calendar'. |
| SMS / email to players | Not built — the turf calls the player to confirm. The video says the turf confirms. |
| Customer / manager-activity reports | Not built — reports cover collections, expenses, fields and payment methods. |


## About the data in the screenshots
The screenshots come from the real application running locally with its **demo data** (demo turfs, teams and amounts). They are real screens, not mock-ups, but the numbers are demo numbers.
Before publishing, either keep them clearly as a product demo or re-capture with your own turf's data:

```bash
node promotional-video/tools/capture.mjs        # all groups; or: public | owner | manager
```
The turf photos on the demo turfs are TurfBari-palette illustrations (`tools/scenes.html`), uploaded through the app's normal photo upload. Replace them with real turf photos for the final cut.

## Rebuilding
```bash
cd promotional-video/tools
python build_package.py frames && node render-frames.mjs   # reference frames
python build_package.py docs && node render-docs.mjs        # docs, storyboard sheet, PDF
node render-brand.mjs                                      # logo, palette, type sheets
```
Requires the dev servers (backend 8011, frontend 5175) for screenshots, Node 22+ and Chrome.

## Final quality checklist
- [x] Duration 3:35 (3–4 min) · 9 scenes
- [x] 100% Bengali voiceover; English only for product terms
- [x] Hook in the first 5 seconds («দল রেডি, বুট রেডি, মনটাও রেডি। কিন্তু মাঠ কোথায়?»)
- [x] Public website, location-based discovery (district, area, near-me), turf details, gallery
- [x] QR booking explained accurately (request → turf confirms; status lookup)
- [x] Owner dashboard, booking, customers, fields, pricing, payments, reports
- [x] Manager dashboard as its own scene, real manager screenshots, honest permissions
- [x] Only implemented features promoted; missing ones listed above and kept out
- [x] Real screenshots, real logo, exact brand colours
- [x] Bengali SRT with the same wording as the voiceover
- [x] AI image + video prompts with negatives (no fake UI, logos or QR)
- [x] Final CTA (find a turf / list your turf / URL)
- [x] No Super Admin or admin content anywhere
