import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MobileRecordCard, ResponsiveDataTable } from "./responsive";

describe("responsive data presentation", () => {
  it("provides separate mobile and desktop content without dropping fields", () => {
    render(
      <ResponsiveDataTable mobile={<p>Mobile record</p>} desktop={<p>Desktop table</p>} />,
    );
    expect(screen.getByText("Mobile record")).toBeInTheDocument();
    expect(screen.getByText("Desktop table")).toBeInTheDocument();
  });

  it("keeps mobile records in a consistent card surface", () => {
    const { container } = render(<MobileRecordCard>Booking details</MobileRecordCard>);
    expect(container.firstElementChild).toHaveClass("rounded-xl", "border", "bg-card");
  });
});
