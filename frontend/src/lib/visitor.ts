/**
 * Booking-page browser state, kept in localStorage (survives reloads and new tabs):
 * - a random visitor id, so the server can tell people on the same Wi-Fi/IP apart;
 * - a booking draft per turf: chosen field/day, the server hold token and the submit idempotency key.
 * No phone numbers, names or payment details are stored. Every read is wrapped: storage may be blocked.
 */

const VISITOR_KEY = "turfbari:visitor";
const DRAFT_TTL_MS = 30 * 60_000;

function read<T>(key: string): T | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : null;
  } catch {
    return null;
  }
}

function write(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode / storage full: the page still works for this visit */
  }
}

function uuid(): string {
  const c = globalThis.crypto as Crypto & { randomUUID?: () => string };
  if (typeof c.randomUUID === "function") return c.randomUUID();
  const b = c.getRandomValues(new Uint8Array(16));
  b[6] = (b[6]! & 0x0f) | 0x40;
  b[8] = (b[8]! & 0x3f) | 0x80;
  const h = [...b].map((x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

let memoryVisitor: string | null = null;
export function visitorId(): string {
  const saved = read<string>(VISITOR_KEY);
  if (saved && /^[0-9a-f-]{36}$/.test(saved)) return saved;
  const id = memoryVisitor ?? uuid();
  memoryVisitor = id;
  write(VISITOR_KEY, id);
  return id;
}

export interface BookingDraft {
  fieldId: string;
  day: string;
  token: string | null;
  idempotencyKey: string;
  savedAt: number;
}

const draftKey = (slug: string) => `turfbari:draft:${slug}`;

export function loadDraft(slug: string): BookingDraft | null {
  const d = read<BookingDraft>(draftKey(slug));
  if (!d || Date.now() - d.savedAt > DRAFT_TTL_MS) {
    if (d) write(draftKey(slug), null);
    return null;
  }
  return d;
}

export function saveDraft(slug: string, patch: Partial<BookingDraft>) {
  const current = loadDraft(slug);
  write(draftKey(slug), {
    fieldId: "",
    day: "",
    token: null,
    idempotencyKey: uuid(),
    ...current,
    ...patch,
    savedAt: Date.now(),
  });
}

export function clearDraft(slug: string) {
  write(draftKey(slug), null);
}

export function newIdempotencyKey(): string {
  return uuid();
}

export interface SubmittedBooking {
  reference: string;
  start: string;
  at: number;
}
const submittedKey = (slug: string) => `turfbari:submitted:${slug}`;

export function loadSubmitted(slug: string): SubmittedBooking | null {
  const s = read<SubmittedBooking>(submittedKey(slug));
  if (!s || new Date(s.start).getTime() < Date.now()) return null; // past bookings are forgotten
  return s;
}

export function saveSubmitted(slug: string, value: SubmittedBooking | null) {
  write(submittedKey(slug), value);
}
