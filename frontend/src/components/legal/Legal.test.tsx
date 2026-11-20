import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { LegalRef } from "@/lib/types";
import { LegalAcceptBox, LegalBody, legalPayload } from "./Legal";

const DOCS: LegalRef[] = [
  { version_id: 11, version: 2, category: "terms", scope: "platform", title_en: "Terms & Conditions", title_bn: "শর্তাবলী", url: "/legal/terms", sector_slug: null },
  { version_id: 12, version: 1, category: "sector_rules", scope: "sector", title_en: "Football rules", title_bn: "", url: "/legal/sector/football-turf#sector_rules", sector_slug: "football-turf" },
];

function Box() {
  const [agree, setAgree] = useState(false);
  return (
    <MemoryRouter>
      <LegalAcceptBox docs={DOCS} checked={agree} onChange={setAgree} />
      <span>{agree ? "agreed" : "not agreed"}</span>
    </MemoryRouter>
  );
}

describe("legal agreement", () => {
  it("starts unchecked and links every required document version", () => {
    render(<Box />);
    const box = screen.getByRole("checkbox");
    expect(box).not.toBeChecked();
    expect(screen.getByRole("link", { name: /শর্তাবলী/ })).toHaveAttribute("href", "/legal/terms");
    expect(screen.getByRole("link", { name: /Football rules/ })).toHaveAttribute("href", "/legal/sector/football-turf#sector_rules");
    fireEvent.click(box);
    expect(screen.getByText("agreed")).toBeInTheDocument();
  });

  it("renders nothing when no document is required", () => {
    const { container } = render(
      <MemoryRouter>
        <LegalAcceptBox docs={[]} checked={false} onChange={() => {}} />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("sends the exact versions shown, and nothing when none are pending", () => {
    expect(legalPayload(DOCS, true)).toEqual({ agree_legal: true, accepted_versions: [11, 12] });
    expect(legalPayload([], false)).toEqual({});
  });

  it("falls back to the other language with a note", () => {
    render(<LegalBody doc={{ body_en: "<p>English only</p>", body_bn: "" }} lang="bn" />);
    expect(screen.getByText("English only")).toBeInTheDocument();
    expect(screen.getByText(/এখনো বাংলায় নেই/)).toBeInTheDocument();
  });
});
