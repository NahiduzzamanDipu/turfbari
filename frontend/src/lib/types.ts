// Shapes returned by the TurfBari API. Money is always a decimal string.

import type { PageTheme } from "./themes";

export interface Paginated<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface Place {
  name: string;
  slug: string;
}

export interface Membership {
  turf_id: string;
  turf_name: string;
  turf_slug: string;
  role: "owner" | "manager";
  permissions: ManagerPermissions;
}

export interface ManagerPermissions {
  approve_payments: boolean;
  manage_slots: boolean;
  view_sms: boolean;
}

export interface Me {
  authenticated: boolean;
  user: {
    id: string;
    email: string;
    full_name: string;
    phone: string;
    is_platform_admin: boolean;
    must_change_password: boolean;
  } | null;
  memberships: Membership[];
  active_turf_id: string | null;
  home: string;
  /** Set by /auth/login/ when the password was right but an authenticator code is still needed. */
  two_factor_required?: boolean;
  /** "email": a code was emailed (Super Admins, every sign-in); "totp": authenticator app. */
  two_factor_method?: "email" | "totp";
  /** Masked address the code went to, e.g. "md*****@gmail.com". */
  email_hint?: string | null;
  can_use_authenticator?: boolean;
}

export interface Division extends Place {
  districts: (Place & { areas: Place[] })[];
}

export interface TurfCard {
  name: string;
  slug: string;
  short_description: string;
  district: Place;
  area: Place | null;
  address: string;
  latitude: string | null;
  longitude: string | null;
  map_link: string | null;
  distance_km: number | null;
  profile_image_url: string | null;
  cover_url: string | null;
  turf_type: "outdoor" | "indoor" | "rooftop";
  surface: string;
  amenities: string[];
  min_price: string | null;
  fields_count: number;
  is_featured: boolean;
  public_booking_enabled: boolean;
}

export interface Hours {
  weekday: number;
  opens_at: string;
  closes_at: string;
  is_closed: boolean;
}

export interface PublicPhoto {
  url: string;
  thumbnail_url: string;
  width: number;
  height: number;
  caption: string;
}

export interface TurfDetail extends TurfCard {
  photos: PublicPhoto[];
  theme: PageTheme;
  /** The platform-wide "how to book" video (same on every turf page). */
  youtube_video_id: string | null;
  terms_version: { id: number; version: number } | null;
  max_slots_per_customer: number;
  description: string;
  maps_url: string;
  public_phone: string;
  public_email: string;
  booking_instructions: string;
  cancellation_policy: string;
  payment_methods_text: string;
  fields_list: {
    id: string;
    name: string;
    size: string;
    surface: string;
    is_indoor: boolean;
    has_lighting: boolean;
    slot_minutes: number;
  }[];
  hours: Hours[];
  pricing: {
    label: string;
    weekdays: number[];
    date: string | null;
    start_time: string;
    end_time: string;
    hourly_rate: string;
    field_name: string | null;
  }[];
  base_rates: { field: string; hourly_rate: string }[];
  payment: TurfPaymentInfo;
  price_categories: { key: "morning" | "evening" | "night" | "midnight"; label: string; start: string; end: string; hourly_rate: string }[];
}

/** free | yours (held by this visitor) | held (someone else is booking) | requested | booked | unavailable | past */
export type PublicSlotState = "free" | "yours" | "held" | "requested" | "booked" | "unavailable" | "past";

export interface Slot {
  start: string;
  end: string;
  available: boolean;
  price?: string;
}

export interface PublicSlot extends Slot {
  state?: PublicSlotState;
}

/** A 10-minute hold on selected public slots. */
export interface SlotHold {
  token: string;
  field: string;
  start: string;
  end: string;
  expires_at: string;
}

export interface PublicAvailability {
  date: string;
  field: string;
  slots: PublicSlot[];
  my_hold: SlotHold | null;
  cooldown_until: string | null;
}

export interface PublicBooking {
  reference: string;
  status: string;
  status_label: string;
  turf: string;
  turf_slug: string;
  turf_phone: string | null;
  field: string;
  start: string;
  end: string;
  total: string | null;
  amount_paid: string;
  hold_expires_at: string | null;
  payment: { amount: string; trx_id: string; status: string; rejection_reason: string | null } | null;
  /** Bengali "request received, owner will verify and confirm by SMS" notice. */
  message_bn: string | null;
}

export interface TurfPaymentInfo {
  accepts_online: boolean;
  bkash_number: string | null;
  advance_amount: string;
  min_advance: string;
  hold_minutes: number;
}

export type BookingStatus = "pending" | "confirmed" | "completed" | "cancelled" | "rejected" | "no_show" | "expired";

export interface Payment {
  id: string;
  amount: string;
  kind: "payment" | "refund";
  method: string;
  reference: string;
  paid_at: string;
  received_by_name: string | null;
}

export interface Booking {
  id: string;
  reference: string;
  field: string;
  field_name: string;
  customer: { id: string; name: string; phone: string; email: string };
  start: string;
  end: string;
  status: BookingStatus;
  status_label: string;
  source: string;
  source_label: string;
  team_name: string;
  notes: string;
  subtotal: string;
  discount: string;
  total: string;
  amount_paid: string;
  due: string;
  payment_status: "unpaid" | "partial" | "paid";
  price_snapshot: { subtotal?: string; segments?: { label: string; rate: string; minutes: number; amount: string }[] };
  created_at: string;
  confirmed_at: string | null;
  payments?: Payment[];
}

export interface Field {
  id: string;
  name: string;
  size: string;
  surface: string;
  is_indoor: boolean;
  has_lighting: boolean;
  is_active: boolean;
  sort_order: number;
  slot_minutes: number;
  default_hourly_rate: string;
}

export interface PricingRule {
  id: string;
  field: string | null;
  field_name: string | null;
  label: string;
  weekdays: number[];
  date: string | null;
  start_time: string;
  end_time: string;
  hourly_rate: string;
  priority: number;
  is_active: boolean;
}

export interface Customer {
  id: string;
  name: string;
  phone: string;
  email: string;
  notes: string;
  bookings_count: number;
  total_paid: string;
  last_booking: string | null;
  created_at: string;
}

export interface Expense {
  id: string;
  category: string;
  category_label: string;
  amount: string;
  spent_on: string;
  note: string;
  created_at: string;
}

export interface Maintenance {
  id: string;
  field: string;
  field_name: string;
  start: string;
  end: string;
  reason: string;
}

export interface Dashboard {
  turf: { name: string; slug: string; status: string; is_listed: boolean };
  role: "owner" | "manager";
  today: { bookings: number; hours_booked: number; revenue: string };
  pending_requests: number;
  month: { bookings: number; revenue: string; expenses: string | null; net: string | null };
  outstanding_due: string;
  customers: number;
  upcoming: Booking[];
  revenue_series: { date: string; revenue: string }[];
}

export interface TurfSettings {
  name: string;
  slug: string;
  status: string;
  district: string;
  area: string | null;
  address: string;
  maps_url: string;
  latitude: string | null;
  longitude: string | null;
  profile_image_url: string | null;
  theme_preset: string;
  theme_color: string;
  turf_type: string;
  surface: string;
  amenities: string[];
  short_description: string;
  description: string;
  public_phone: string;
  public_email: string;
  booking_instructions: string;
  cancellation_policy: string;
  payment_methods_text: string;
  is_listed: boolean;
  public_booking_enabled: boolean;
  show_pricing: boolean;
  weekend_days: number[];
  bkash_number: string;
  advance_amount: string;
  payment_hold_minutes: number;
}

export interface Manager {
  id: string;
  email: string;
  full_name: string;
  phone: string;
  role: "owner" | "manager";
  is_active: boolean;
  permissions: ManagerPermissions;
  must_change_password: boolean;
  temporary_password?: string | null;
}

export interface Application {
  id: string;
  turf_name: string;
  owner_name: string;
  phone: string;
  email: string;
  district_name: string;
  area_name: string | null;
  address: string;
  turf_type: string;
  number_of_fields: number;
  message: string;
  status: "pending" | "contacted" | "approved" | "rejected";
  admin_note: string;
  reviewed_by_email: string | null;
  reviewed_at: string | null;
  turf_slug: string | null;
  created_at: string;
}

export interface AdminTurf {
  id: string;
  name: string;
  slug: string;
  status: "active" | "suspended" | "archived";
  district: string;
  area: string | null;
  district_name: string;
  area_name: string | null;
  address: string;
  turf_type: string;
  surface: string;
  owner_name: string;
  owner_phone: string;
  owner_email: string | null;
  contract_notes: string;
  is_listed: boolean;
  is_featured: boolean;
  public_booking_enabled: boolean;
  min_public_price: string | null;
  fields_count: number;
  bookings_count: number;
  subscription: SubscriptionStanding & {
    open_order: { plan: string; status: string; amount: string } | null;
  };
  created_at: string;
}

// ------------------------------------------------------------------ slot board
export type SlotState = "free" | "booked" | "pending" | "maintenance" | "past";

export interface BoardSlot extends Slot {
  state: SlotState;
  reason?: string;
  booking?: {
    id: string;
    reference: string;
    status: string;
    customer_name: string;
    customer_phone: string;
    team_name: string;
    start: string;
    end: string;
    total: string;
    amount_paid: string;
  };
}

export interface SlotBoard {
  date: string;
  fields: { id: string; name: string; size: string; slots: BoardSlot[] }[];
}

// ------------------------------------------------------------------ subscriptions
export type PlanPeriod = "monthly" | "half_yearly" | "yearly";

export interface Plan {
  id: string;
  period: PlanPeriod;
  name: string;
  months: number;
  price: string;
  description: string;
  is_active: boolean;
}

export interface SubscriptionPeriod {
  id: string;
  plan: Plan;
  status: "pending_payment" | "active" | "cancelled";
  state: "pending_payment" | "cancelled" | "scheduled" | "current" | "ended";
  starts_on: string | null;
  ends_on: string | null;
  price: string;
  note: string;
  created_at: string;
}

export interface PaymentTx {
  id: string;
  tran_id: string;
  method: string;
  method_label: string;
  channel: "manual" | "gateway" | "admin";
  amount: string;
  status: "initiated" | "pending_verification" | "verified" | "rejected" | "failed" | "cancelled";
  status_label: string;
  reference: string;
  sender_number: string;
  note: string;
  created_at: string;
  reviewed_at: string | null;
}

export interface Invoice {
  id: string;
  number: string;
  amount: string;
  list_amount: string;
  discount: string;
  promo_code: { code: string; percent_off: number } | null;
  status: "unpaid" | "pending_verification" | "paid" | "cancelled";
  status_label: string;
  paid_at: string | null;
  created_at: string;
  subscription: SubscriptionPeriod;
  transactions: PaymentTx[];
}

export interface PromoCode {
  id: string;
  code: string;
  percent_off: number;
  description: string;
  is_active: boolean;
  valid_from: string | null;
  valid_until: string | null;
  max_uses: number | null;
  times_used: number;
  is_running: boolean;
  created_at: string;
}

export interface SubscriptionStanding {
  state: "active" | "expiring" | "grace" | "expired" | "none";
  can_operate: boolean;
  plan: Plan | null;
  current: SubscriptionPeriod | null;
  paid_until: string | null;
  days_left: number | null;
  grace_until: string | null;
  auto_renew: false;
}

export interface SubscriptionOverview {
  standing: SubscriptionStanding;
  periods: SubscriptionPeriod[];
  open_invoice: Invoice | null;
  invoices: Invoice[];
  plans: Plan[];
  payment_options: {
    online: boolean;
    online_sandbox: boolean;
    manual: { method: string; label: string; account: string }[];
  };
}

export interface AdminPayment extends PaymentTx {
  invoice_number: string;
  turf_name: string;
  plan_name: string;
  submitted_by_email: string | null;
}

export interface WorkspacePhoto extends PublicPhoto {
  id: string;
  sort_order: number;
  created_at: string;
}
