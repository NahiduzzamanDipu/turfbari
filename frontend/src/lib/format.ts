// Date/time helpers. All display is in Asia/Dhaka regardless of the viewer's machine timezone.

export const TZ = "Asia/Dhaka";
export const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
export const WEEKDAYS_SHORT = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

const timeFmt = new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" });
const dateFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });
const dayFmt = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
const isoDayFmt = new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" });

export const fmtTime = (iso: string) => timeFmt.format(new Date(iso));
export const fmtDate = (iso: string) => dateFmt.format(new Date(iso));
export const fmtDay = (iso: string) => dayFmt.format(new Date(iso));
export const fmtDateTime = (iso: string) => `${fmtDay(iso)}, ${fmtTime(iso)}`;
export const fmtRange = (start: string, end: string) => `${fmtTime(start)} – ${fmtTime(end)}`;

/** Today's date in Dhaka as YYYY-MM-DD. */
export function todayISO(): string {
  return isoDayFmt.format(new Date());
}

/** Dhaka calendar date (YYYY-MM-DD) of an ISO timestamp. */
export function dhakaDay(iso: string): string {
  return isoDayFmt.format(new Date(iso));
}

export function addDays(isoDate: string, days: number): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Builds an ISO timestamp for a Dhaka wall-clock time (UTC+6, no DST). */
export function dhakaISO(isoDate: string, hhmm: string): string {
  return `${isoDate}T${hhmm.length === 5 ? `${hhmm}:00` : hhmm}+06:00`;
}

/** "18:00:00" -> "6:00 PM" */
export function fmtClock(hhmmss: string): string {
  const [h = "0", m = "0"] = hhmmss.split(":");
  const hour = Number(h);
  const suffix = hour >= 12 ? "PM" : "AM";
  const h12 = hour % 12 === 0 ? 12 : hour % 12;
  return `${h12}:${m.padStart(2, "0")} ${suffix}`;
}

export function weekdayLabel(days: number[]): string {
  if (days.length === 0 || days.length === 7) return "Every day";
  return days.map((d) => WEEKDAYS_SHORT[d]).join(", ");
}

export const TURF_TYPE_LABEL: Record<string, string> = { outdoor: "Outdoor", indoor: "Indoor", rooftop: "Rooftop" };
export const SURFACE_LABEL: Record<string, string> = {
  artificial: "Artificial grass",
  natural: "Natural grass",
  hybrid: "Hybrid",
};
export const PAYMENT_METHODS: Record<string, string> = {
  cash: "Cash",
  bkash: "bKash",
  nagad: "Nagad",
  rocket: "Rocket",
  card: "Card",
  bank: "Bank transfer",
};
