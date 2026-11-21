import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { TurfDetailPage } from "./TurfDetailPage";

const mocks = vi.hoisted(() => ({ useQuery: vi.fn() }));

vi.mock("@tanstack/react-query", () => ({ useQuery: mocks.useQuery }));
vi.mock("./BookingPanel", () => ({ BookingPanel: () => <div data-testid="booking-panel">Date and slots</div> }));
vi.mock("./PhotoGallery", () => ({ PhotoGallery: () => null }));

beforeEach(() => {
  mocks.useQuery.mockReturnValue({
    isPending: false,
    isError: false,
    data: {
      name: "Green Field", slug: "green-field", short_description: "A neighborhood pitch",
      district: { id: 1, name: "Dhaka" }, area: { id: 2, name: "Uttara" }, address: "Sector 4",
      latitude: null, longitude: null, map_link: "", distance_km: null, profile_image_url: null,
      cover_url: null, turf_type: "outdoor", surface: "artificial", amenities: ["Floodlights"],
      min_price: null, fields_count: 1, is_featured: false, public_booking_enabled: true,
      photos: [], theme: { preset: "turfbari" }, youtube_video_id: null, legal: [], max_slots_per_customer: 2,
      description: "A full-size turf", maps_url: "", public_phone: "01700000000", public_email: "",
      booking_instructions: "Select a date and slot.", cancellation_policy: "Call to cancel.",
      payment_methods_text: "bKash", fields_list: [{ id: "field-1", name: "Main", size: "5-a-side", surface: "artificial", is_indoor: false, has_lighting: true, slot_minutes: 60 }],
      hours: [{ weekday: 0, opens_at: "06:00", closes_at: "23:00", is_closed: false }],
      pricing: [], base_rates: [], payment: {},
      price_categories: [{ key: "evening", label: "Evening", start: "12", end: "18", hourly_rate: "1000" }],
    },
  });
});

describe("public turf page compact information order", () => {
  it("shows turf information and booking guidance before the date and slot selector", () => {
    render(
      <MemoryRouter initialEntries={["/turfs/green-field"]}>
        <Routes><Route path="/turfs/:slug" element={<TurfDetailPage />} /></Routes>
      </MemoryRouter>,
    );

    const orderedContent = [
      screen.getByText("Contact"),
      screen.getByRole("heading", { name: "About" }),
      screen.getByRole("heading", { name: "Amenities" }),
      screen.getByRole("heading", { name: "Fields" }),
      screen.getByRole("heading", { name: "Prices per hour" }),
      screen.getByRole("heading", { name: "Opening hours" }),
      screen.getByRole("heading", { name: "Booking information" }),
      screen.getByTestId("booking-panel"),
    ];
    const positions = orderedContent.slice(0, -1).map((element, index) =>
      element.compareDocumentPosition(orderedContent[index + 1]!) & Node.DOCUMENT_POSITION_FOLLOWING,
    );
    expect(positions.slice(1).every(Boolean)).toBe(true);
  });
});
