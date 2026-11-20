import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage";

const mocks = vi.hoisted(() => ({ useQuery: vi.fn(), useMe: vi.fn() }));
vi.mock("@tanstack/react-query", () => ({ useQuery: mocks.useQuery }));
vi.mock("@/features/auth/auth", () => ({ useMe: mocks.useMe }));

beforeEach(() => {
  mocks.useMe.mockReturnValue({ data: { authenticated: false } });
  mocks.useQuery.mockImplementation(({ queryKey }: { queryKey: string[] }) => {
    const key = queryKey[1];
    const data = key === "plans"
      ? [{ id: "plan-1", period: "monthly", name: "Monthly", months: 1, price: "1499.00", description: "Monthly turf tools", featured: true, features: ["Custom slots"], limits: { managers: 2 }, sms_enabled: true }]
      : key === "sms-pricing"
        ? { configured: true, price_per_segment: "0.42", examples: [{ segments: 2, cost: "0.84" }] }
        : key === "youtube"
        ? { video_id: "dQw4w9WgXcQ", url: "https://youtu.be/dQw4w9WgXcQ", title: "About TURFBARI", enabled: true }
          : key === "faqs"
            ? [{ id: "faq-1", question_en: "Dynamic question?", question_bn: "", answer_en: "Dynamic answer", answer_bn: "" }]
            : { enabled: false };
    return { data, isPending: false, isError: false };
  });
});

describe("homepage configuration sections", () => {
  it("renders configured plans and rates and links plan selection to registration", () => {
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.getByText("৳1,499.00")).toBeInTheDocument();
    expect(screen.getByText("Custom slots")).toBeInTheDocument();
    expect(screen.getByText("2 parts")).toBeInTheDocument();
    expect(screen.getByText("৳0.84")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Choose Plan" })).toHaveAttribute("href", "/register-turf?plan=monthly");
    expect(screen.getByText("Dynamic question?")).toBeInTheDocument();
  });

  it("mounts the configured YouTube player only while About Us is open", () => {
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.queryByTitle("About TURFBARI")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "About TURFBARI" }));
    expect(screen.getByTitle("About TURFBARI")).toHaveAttribute("src", "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0&modestbranding=1");
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(screen.queryByTitle("About TURFBARI")).not.toBeInTheDocument();
  });

  it("does not fall back to another video when the homepage video is disabled", () => {
    mocks.useQuery.mockImplementation(({ queryKey }: { queryKey: string[] }) => {
      const key = queryKey[1];
      const data = key === "youtube"
        ? { video_id: "dQw4w9WgXcQ", url: "https://youtu.be/dQw4w9WgXcQ", title: "About TURFBARI", enabled: false }
        : key === "plans"
          ? []
          : key === "faqs"
            ? []
            : { configured: false, examples: [] };
      return { data, isPending: false, isError: false };
    });
    render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "About Us" })).not.toBeInTheDocument();
  });
});
