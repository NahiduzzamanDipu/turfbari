// Capture REAL TurfBari screenshots for the promo video (public site, owner and manager workspaces).
// No Super Admin page is ever opened. Run with the dev servers up:
//   node promotional-video/tools/capture.mjs [onlyGroup]
// Env: TB_ORIGIN (default http://localhost:5175)
import { writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { launch, page, sleep, writeText } from "./cdp.mjs";

const ORIGIN = process.env.TB_ORIGIN ?? "http://localhost:5175";
const OUT = resolve(import.meta.dirname, "../02-real-app-screenshots");
const only = process.argv[2];
const DESKTOP = [1920, 1080];
const MOBILE = [390, 844];
const GULSHAN = [23.7925, 90.4078]; // player standing near Gulshan, Dhaka
const OWNER = ["owner@turfbari.local", "TurfBariOwner#2026"];
const MANAGER = ["manager@turfbari.local", "TurfBariManager#2026"];
const TURF = "green-arena-gulshan";

const { session, close } = await launch();
const p = page(session, { origin: ORIGIN });
const failures = [];
const log = [];

async function step(name, fn) {
  try {
    await fn();
  } catch (e) {
    failures.push(`${name}: ${e.message}`);
    console.error("FAILED", name, e.message);
  }
}
const shot = (dir, file, opts) => p.shot(join(OUT, dir, file), opts).then(() => log.push(`${dir}/${file}`));
const desktop = () => p.viewport(...DESKTOP);
const mobile = () => p.viewport(...MOBILE, { mobile: true });
const escape = () => p.eval(`document.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape', bubbles:true})); window.dispatchEvent(new KeyboardEvent('keydown', {key:'Escape'}))`);

/** Pick n consecutive free slots after `afterHour` on the visible slot grid and click them. */
async function pickFreeSlots(n, afterHour = 17) {
  const ok = await p.eval(`(async () => {
    const btns = [...document.querySelectorAll('button')].filter(b => /\\d:\\d\\d [AP]M – \\d/.test(b.innerText));
    const hour = (b) => { const m = b.innerText.match(/(\\d+):(\\d\\d) ([AP]M)/); let h = +m[1] % 12; if (m[3] === 'PM') h += 12; return h; };
    const free = (b) => !b.disabled && !/booked|Needs|Confirmed|Maintenance/i.test(b.innerText) && /৳/.test(b.innerText);
    for (let i = 0; i + ${n} <= btns.length; i++) {
      const run = btns.slice(i, i + ${n});
      if (hour(run[0]) >= ${afterHour} && run.every(free)) {
        for (const b of run) { b.scrollIntoView({block:'center'}); b.click(); await new Promise(r => setTimeout(r, 250)); }
        return true;
      }
    }
    return false;
  })()`);
  if (!ok) throw new Error("no free run of slots");
  await sleep(500);
}

await p.goto("/");
await p.logout();
await p.geolocation(...GULSHAN);
await p.colorScheme("light");

// ------------------------------------------------------------------ public website
if (!only || only === "public") {
  await desktop();
  await step("home", async () => {
    await p.goto("/", { settle: 2500 });
    await shot("public-homepage", "01-home-hero.png");
    await p.scrollTo("Turfs near you");
    await shot("public-homepage", "02-home-turfs-near-you.png");
    await p.scrollTo(800);
    await p.scrollTo("Why");
    await shot("public-homepage", "03-home-benefits.png");
    await shot("public-homepage", "04-home-full-page.png", { fullPage: true });
  });
  await step("explore", async () => {
    await p.goto("/explore", { settle: 2500 });
    await shot("turf-discovery", "01-explore-nearest-first.png");
    await p.goto("/explore?district=dhaka", { settle: 2000 });
    await shot("turf-discovery", "02-explore-district-filter.png");
    await p.goto("/explore?district=dhaka&area=mirpur-dhaka", { settle: 2000 });
    await shot("turf-discovery", "03-explore-district-area-filter.png");
    await p.goto("/explore?q=Uttara", { settle: 2000 });
    await shot("turf-discovery", "04-explore-search-by-name.png");
  });
  await step("turf details", async () => {
    await p.goto(`/turfs/${TURF}`, { settle: 2500 });
    await shot("turf-details", "01-turf-cover-gallery.png");
    await p.scrollTo("Book a slot");
    await shot("turf-details", "02-turf-booking-and-contact.png");
    await p.scrollTo("About");
    await shot("turf-details", "03-turf-about-amenities-fields.png");
    await p.scrollTo("Prices per hour");
    await shot("turf-details", "04-turf-prices-hours.png");
    await shot("turf-details", "05-turf-full-page.png", { fullPage: true });
    await p.goto(`/turfs/${TURF}`, { settle: 2000 });
    await p.click("Open photo 1");
    await sleep(800);
    await shot("turf-details", "06-gallery-viewer.png");
    await escape();
    await p.goto(`/turfs/${TURF}`, { settle: 1500 });
    await p.click("QR code");
    await sleep(800);
    await shot("turf-details", "07-turf-qr-code.png");
  });
  await step("qr file", async () => {
    const svg = await p.eval(`fetch('/api/public/turfs/${TURF}/qr.svg').then(r => r.text())`);
    writeText(join(OUT, "qr-booking", "00-real-turf-qr-code.svg"), svg);
  });
  await step("mobile discovery", async () => {
    await mobile();
    await p.goto("/", { settle: 2500 });
    await shot("turf-discovery", "05-mobile-home.png");
    await p.goto("/explore", { settle: 2500 });
    await p.scrollTo("Showing turfs");
    await shot("turf-discovery", "06-mobile-explore.png");
  });
  let reference = null;
  await step("mobile qr booking", async () => {
    await mobile();
    await p.goto(`/turfs/${TURF}`, { settle: 2500 });
    await shot("qr-booking", "01-mobile-turf-page-after-scan.png");
    await p.scrollTo("Book a slot");
    // choose the second field, then the first date (from the third on) with two free evening slots
    await p.eval(`(() => { const f = document.querySelectorAll('[aria-label="Field"] button'); f[1]?.click(); })()`);
    await sleep(900);
    let picked = false;
    for (let d = 2; d < 7 && !picked; d++) {
      await p.eval(`(() => { const d = document.querySelectorAll('[aria-label="Date"] button'); d[${d}]?.click(); })()`);
      await sleep(1500);
      if (d === 2 || !picked) {
        await p.scrollTo("Book a slot");
        await shot("qr-booking", "02-mobile-pick-field-and-date.png");
      }
      picked = await pickFreeSlots(2, 18).then(() => true, () => false);
    }
    if (!picked) throw new Error("no free evening slots in the next week");
    await p.scrollTo("Tap a free slot");
    await shot("qr-booking", "03-mobile-pick-time-slots.png");
    await p.fill("Your name", "Arnab Saha");
    await p.fill("Mobile number", "01722334477");
    await p.fill("Team name (optional)", "Friday Friends FC");
    await p.scrollTo("Your name");
    await shot("qr-booking", "04-mobile-booking-form.png");
    await p.click("Send booking request");
    await sleep(2000);
    reference = await p.eval(`(document.body.innerText.match(/TRF-\\d{4}-[A-Z0-9]{5}/) || [])[0] || null`);
    await p.scrollTo("Request sent");
    await shot("qr-booking", "05-mobile-request-sent.png");
  });
  await step("booking status", async () => {
    if (!reference) throw new Error("no reference from booking step");
    for (const [size, file] of [
      ["mobile", "06-mobile-booking-status.png"],
      ["desktop", "07-booking-status-desktop.png"],
    ]) {
      await (size === "mobile" ? mobile() : desktop());
      await p.goto(`/booking-status?reference=${reference}`, { settle: 2000 });
      await p.fill("01XXXXXXXXX", "01722334477");
      await p.click("Check status");
      await sleep(1800);
      await shot("qr-booking", file);
    }
  });
  await step("register turf", async () => {
    await desktop();
    await p.goto("/register-turf", { settle: 2000 });
    await shot("public-homepage", "05-register-your-turf.png");
  });
}

// ------------------------------------------------------------------ owner workspace
async function workspaceTour(role) {
  const [email, password] = role === "owner" ? OWNER : MANAGER;
  const dir = (name) => (role === "owner" ? name : `manager-dashboard`);
  const pre = "";
  let managerIndex = 0;
  // Manager screens all go to manager-dashboard/, numbered in capture order.
  const name = (file) =>
    role === "owner" ? file : `${String(managerIndex++).padStart(2, "0")}-manager-${file.replace(/^\d+-/, "")}`;
  await desktop();
  await p.goto("/login", { settle: 1500 });
  await p.logout();
  await p.goto("/login", { settle: 1500 });
  await p.fill("Email or username", email);
  await p.fill("Password", password);
  await shot(dir("owner-dashboard"), name(`00-login.png`));
  await p.login(email, password);

  await step(`${role} dashboard`, async () => {
    await p.goto("/workspace", { settle: 2500 });
    await shot(dir("owner-dashboard"), name(`01-dashboard.png`));
    await shot(dir("owner-dashboard"), name(`02-dashboard-full.png`), { fullPage: true });
  });
  await step(`${role} slot board`, async () => {
    await p.goto("/workspace/book", { settle: 2500 });
    await shot(dir("booking-management"), name(`01-book-a-slot-board.png`));
    await pickFreeSlots(2, 18);
    await p.fill("e.g. Banani FC", role === "owner" ? "Gulshan Old Boys" : "Office League XI");
    await p.fill("Contact name", role === "owner" ? "Tanim Rahman" : "Sajid Hasan");
    await p.fill("01XXXXXXXXX", role === "owner" ? "01733445566" : "01744556677");
    await p.click("10%");
    await p.fill("Advance received (৳)", "1000");
    await p.scrollTo("Team name");
    await shot(dir("booking-management"), name(`02-book-team-with-discount.png`));
    await p.goto("/workspace/book", { settle: 2000 });
    await p.click("Needs confirming").catch(() => p.click("Confirmed"));
    await sleep(700);
    await shot(dir("booking-management"), name(`03-booked-slot-details.png`));
    await escape();
  });
  await step(`${role} bookings`, async () => {
    await p.goto("/workspace/bookings", { settle: 2500 });
    await shot(dir("booking-management"), name(`04-bookings-day-board.png`));
    await p.goto("/workspace/bookings?view=list", { settle: 2500 });
    await shot(dir("booking-management"), name(`05-bookings-list.png`));
    await p.goto("/workspace/bookings?view=list&status=pending", { settle: 2500 });
    await shot(dir("booking-management"), name(`06-pending-requests.png`));
    await p.goto("/workspace/bookings?view=list", { settle: 2500 });
    await p.eval(`document.querySelector('tbody tr')?.click()`);
    await sleep(1500);
    await shot(dir("payment-management"), name(`01-booking-details-and-payments.png`));
    await escape();
  });
  await step(`${role} customers`, async () => {
    await p.goto("/workspace/customers", { settle: 2500 });
    await shot(dir("customer-management"), name(`01-customers.png`));
  });
  await step(`${role} setup`, async () => {
    for (const [path, file] of [
      ["/workspace/fields", "01-fields.png"],
      ["/workspace/hours", "02-opening-hours.png"],
      ["/workspace/pricing", "03-pricing-rules.png"],
      ["/workspace/maintenance", "04-maintenance-blocks.png"],
    ]) {
      await p.goto(path, { settle: 2000 });
      await shot(dir("field-and-pricing"), name(`${file}`));
    }
  });
  if (role === "owner") {
    await step("owner reports", async () => {
      await p.goto("/workspace/reports", { settle: 3000 });
      await shot("reports", "01-reports-overview.png");
      await shot("reports", "02-reports-full.png", { fullPage: true });
      await p.goto("/workspace/expenses", { settle: 2000 });
      await shot("reports", "03-expenses.png");
    });
    await step("owner team & settings", async () => {
      await p.goto("/workspace/team", { settle: 2000 });
      await shot("owner-dashboard", "03-team-managers.png");
      await p.goto("/workspace/settings", { settle: 2500 });
      await shot("owner-dashboard", "04-settings-public-listing.png");
      await p.scrollTo("Location");
      await shot("owner-dashboard", "05-settings-location-google-maps.png");
      await p.scrollTo("Pictures");
      await shot("owner-dashboard", "06-settings-pictures.png");
    });
  } else {
    await step("manager limits", async () => {
      await p.goto("/workspace/pricing", { settle: 2000 });
      await shot("manager-dashboard", name("20-pricing-view-only.png"));
    });
  }
}

if (!only || only === "owner") await step("owner tour", () => workspaceTour("owner"));
if (!only || only === "manager") await step("manager tour", () => workspaceTour("manager"));

await p.goto("/");
await p.logout();
close();
writeFileSync(join(OUT, "_capture-log.txt"), [...log, "", "FAILURES:", ...failures].join("\n"));
console.log(`\n${log.length} screenshots, ${failures.length} failures`);
for (const f of failures) console.log(" -", f);
