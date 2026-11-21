import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { HomePage } from "./HomePage";

const mocks = vi.hoisted(() => ({ useQuery: vi.fn(), useMe: vi.fn(), language: "en" }));
vi.mock("@tanstack/react-query", () => ({ useQuery: mocks.useQuery }));
vi.mock("@/features/auth/auth", () => ({ useMe: mocks.useMe }));
vi.mock("@/lib/i18n", () => ({ useLanguage: () => ({
  language: mocks.language,
  t: (key: string) => mocks.language === "bn"
    ? ({ "See More": "আরও দেখুন", "See Less": "কম দেখুন" }[key] ?? key)
    : key,
}) }));

beforeEach(() => {
  mocks.language = "en";
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

  it("shows four FAQs first, expands and collapses in the API's order without reloading", () => {
    const faqs = Array.from({ length: 6 }, (_, index) => ({
      id: `faq-${index + 1}`, question_en: `Question ${index + 1}?`, question_bn: "",
      answer_en: `Answer ${index + 1}`, answer_bn: "",
    }));
    mocks.useQuery.mockImplementation(({ queryKey }: { queryKey: string[] }) => ({
      data: queryKey[1] === "faqs" ? faqs : queryKey[1] === "plans" ? [] : { configured: false, examples: [] },
      isPending: false,
      isError: false,
    }));
    const { container } = render(<MemoryRouter><HomePage /></MemoryRouter>);

    expect(screen.getAllByRole("button", { name: "See More" })).toHaveLength(1);
    expect(screen.getAllByRole("region", { name: "Frequently Asked Questions" })).toHaveLength(1);
    expect(screen.getAllByText(/^Question [1-4]\?$/)).toHaveLength(4);
    expect(container.querySelector("#faq-extra")).toHaveAttribute("aria-hidden", "true");
    fireEvent.click(screen.getByText("Question 1?"));
    expect(screen.getByText("Question 1?").closest("details")).toHaveAttribute("open");
    expect(screen.getByText("Answer 1")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "See More" }));
    expect(screen.getAllByText(/^Question [1-6]\?$/)).toHaveLength(6);
    expect([...container.querySelectorAll("summary")].map((summary) => summary.textContent?.trim().replace("＋", ""))).toEqual(faqs.map((faq) => faq.question_en));
    expect(screen.getByRole("button", { name: "See Less" })).toHaveAttribute("aria-expanded", "true");
    expect(container.querySelector("#faq-extra")).toHaveAttribute("aria-hidden", "false");

    fireEvent.click(screen.getByRole("button", { name: "See Less" }));
    expect(screen.getByRole("button", { name: "See More" })).toHaveAttribute("aria-expanded", "false");
    expect(container.querySelector("#faq-extra")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("Answer 1")).toBeInTheDocument();
  });

  it("hides the control with four or fewer published FAQs and updates the label in Bengali", () => {
    const fourFaqs = Array.from({ length: 4 }, (_, index) => ({
      id: `faq-${index + 1}`, question_en: `Question ${index + 1}?`, question_bn: "",
      answer_en: `Answer ${index + 1}`, answer_bn: "",
    }));
    mocks.useQuery.mockImplementation(({ queryKey }: { queryKey: string[] }) => ({
      data: queryKey[1] === "faqs" ? fourFaqs : queryKey[1] === "plans" ? [] : { configured: false, examples: [] },
      isPending: false,
      isError: false,
    }));
    const { rerender } = render(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "See More" })).not.toBeInTheDocument();

    mocks.language = "bn";
    rerender(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.queryByRole("button", { name: "আরও দেখুন" })).not.toBeInTheDocument();

    mocks.useQuery.mockImplementation(({ queryKey }: { queryKey: string[] }) => ({
      data: queryKey[1] === "faqs" ? [...fourFaqs, { id: "faq-5", question_en: "Question 5?", question_bn: "", answer_en: "Answer 5", answer_bn: "" }] : queryKey[1] === "plans" ? [] : { configured: false, examples: [] },
      isPending: false,
      isError: false,
    }));
    rerender(<MemoryRouter><HomePage /></MemoryRouter>);
    expect(screen.getByRole("button", { name: "আরও দেখুন" })).toBeInTheDocument();
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
