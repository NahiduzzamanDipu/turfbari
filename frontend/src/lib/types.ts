// Shapes returned by the TURFOS API. Money is always a decimal string.

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
}

export interface Me {
  authenticated: boolean;
  user: { id: string; email: string; full_name: string; phone: string; is_platform_admin: boolean } | null;
  memberships: Membership[];
  active_turf_id: string | null;
  home: string;
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

export interface TurfDetail extends TurfCard {
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
}

export interface Slot {
  start: string;
  end: string;
  available: boolean;
  price?: string;
}

export interface PublicBooking {
  reference: string;
  status: string;
  status_label: string;
  turf: string;
  field: string;
  start: string;
  end: string;
  total: string | null;
}

export type BookingStatus = "pending" | "confirmed" | "completed" | "cancelled" | "rejected" | "no_show";

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
}

export interface Manager {
  id: string;
  email: string;
  full_name: string;
  phone: string;
  role: "owner" | "manager";
  is_active: boolean;
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
  created_at: string;
}
