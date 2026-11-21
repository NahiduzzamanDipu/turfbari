import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClientLogoShowcase } from "./ClientLogoShowcase";

describe("ClientLogoShowcase", () => {
  it("shows real client names and logos and renders a hidden matching sequence for the seamless loop", () => {
    const clients = [
      { slug: "green-field", name: "Green Field", logo_url: "/media/green.webp", display_order: 1 },
      { slug: "kick-off", name: "Kick Off Arena", logo_url: "/media/kickoff.webp", display_order: 2 },
    ];
    const { container } = render(<ClientLogoShowcase clients={clients} heading="Our Trusted Clients" subtitle="Growing together." />);

    expect(screen.getByRole("heading", { name: "Our Trusted Clients" })).toBeInTheDocument();
    expect(screen.getAllByAltText("Green Field logo")[0]).toHaveAttribute("src", "/media/green.webp");
    expect(screen.getAllByText("Kick Off Arena")[0]).toBeInTheDocument();
    expect(container.querySelectorAll(".client-logo-group")).toHaveLength(2);
    expect(container.querySelector(".client-logo-group-duplicate")).toHaveAttribute("aria-hidden", "true");
    expect(container.querySelector(".client-logo-track")).toHaveStyle({ "--client-count": "2" });

    fireEvent.error(screen.getAllByAltText("Green Field logo")[0]!);
    expect(screen.queryAllByAltText("Green Field logo")).toHaveLength(0);
    expect(container.querySelector(".client-logo-track")).toHaveStyle({ "--client-count": "1" });
  });

  it("renders no empty showcase when there are no eligible clients", () => {
    const { container } = render(<ClientLogoShowcase clients={[]} heading="Our Trusted Clients" subtitle="Growing together." />);
    expect(container.firstChild).toBeNull();
  });
});
